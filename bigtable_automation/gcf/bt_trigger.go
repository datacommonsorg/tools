// Package btcachegeneration runs a GCF function that triggers in 2 scenarios:
// 1) completion of prophet-flume job in borg.
// 2) completion of BT cache ingestion dataflow job.
//
// In the first case, on triggering it sets up new cloud BT table, scales up BT
// cluster (only for base cache) and starts a dataflow job.
//
// In the second case it scales BT cluster down (only for base cache).
package btcachegeneration

import (
	"context"
	"fmt"
	"io/ioutil"
	"log"
	"strings"
	"time"

	"cloud.google.com/go/bigtable"
	"cloud.google.com/go/storage"
	"google.golang.org/api/dataflow/v1b3"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const (
	// TEST represents the test environment, and exported for use in cmd/main.go.
	TEST = "test"
	// Prod environment.
	prod = "prod"

	btProjectID        = "google.com:datcom-store-dev"
	dataBucket         = "prophet_cache"
	dataFilePattern    = "cache.csv*"
	dataflowTemplate   = "gs://datcom-dataflow-templates/templates/csv_to_bt_improved"
	createTableRetries = 3
	columnFamily       = "csv"
	baseCacheType      = "base"
	branchCacheType    = "branch"

	// NOTE: The following three files represents the state of a BT import. They
	// get written under:
	//
	//		gs://<env.controlBucket>/(base|branch)/<TableID>/
	//
	// Init: written by borg to start BT import.
	initFile = "init.txt"
	// Launched: written by this cloud function to mark launching of BT import job.
	launchedFile = "launched.txt"
	// Completed: written by dataflow to mark completion of BT import.
	completedFile = "completed.txt"
)

type environment struct {
	// BT instance holding base caches.
	baseBTInstance string
	// Clusters in base BT instance. There can be >1 for replicated instances.
	baseBTClusters []string
	// High and Low node count for base BT instance. Normally the node count is
	// at Low. Only during the base import, the count is raised to High.
	baseBTNodesHigh int32
	baseBTNodesLow  int32
	// BT instance holding branch caches.
	branchBTInstance string
	// GCS Bucket used for control files.
	controlBucket string
}

var (
	// CurrentEnv defaults to prod, and exported for overriding in `cmd/main.go`.
	CurrentEnv = prod

	envs = map[string]*environment{
		prod: &environment{
			baseBTInstance:   "prophet-cache",
			baseBTClusters:   []string{"prophet-cache-c1"},
			baseBTNodesHigh:  300,
			baseBTNodesLow:   20,
			branchBTInstance: "prophet-branch-cache",
			controlBucket:    "automation_control",
		},
		TEST: &environment{
			baseBTInstance:   "prophet-test",
			baseBTClusters:   []string{"prophet-test-c1"},
			baseBTNodesHigh:  3,
			baseBTNodesLow:   1,
			branchBTInstance: "prophet-test",
			controlBucket:    "automation_control_test",
		},
	}
)

// GCSEvent is the payload of a GCS event.
type GCSEvent struct {
	Name   string `json:"name"`
	Bucket string `json:"bucket"`
}

func readFromGCS(ctx context.Context, bucketName, fileName string) ([]byte, error) {
	gcsClient, err := storage.NewClient(ctx)
	if err != nil {
		log.Printf("Failed to create gcsClient: %v\n", err)
		return nil, status.Errorf(codes.Internal, "Failed to create gcsClient: %v", err)
	}

	bucket := gcsClient.Bucket(bucketName)
	rc, err := bucket.Object(fileName).NewReader(ctx)
	if err != nil {
		log.Printf("Unable to open file from bucket %q, file %q: %v\n", bucketName, fileName, err)
		return nil, status.Errorf(
			codes.Internal, "Unable to open file from bucket %q, file %q: %v", bucketName, fileName, err)
	}
	defer rc.Close()
	return ioutil.ReadAll(rc)
}

func writeToGCS(ctx context.Context, bucketName, fileName, data string) error {
	gcsClient, err := storage.NewClient(ctx)
	if err != nil {
		log.Printf("Failed to create gcsClient: %v\n", err)
		return status.Errorf(codes.Internal, "Failed to create gcsClient: %v", err)
	}

	bucket := gcsClient.Bucket(bucketName)
	w := bucket.Object(fileName).NewWriter(ctx)
	if _, err := fmt.Fprint(w, data); err != nil {
		w.Close()
		log.Printf("Unable to open file for writing from bucket %q, file %q: %v\n", bucketName, fileName, err)
		return status.Errorf(codes.Internal, "Unable to write to bucket %q, file %q: %v", bucketName, fileName, err)
	}
	return w.Close()
}

func launchDataflowJob(ctx context.Context, btInstance, controlBucket, cacheType, tableID string) error {
	dataflowService, err := dataflow.NewService(ctx)
	if err != nil {
		log.Printf("Unable to create dataflow service: %v\n", err)
		return status.Errorf(codes.Internal, "Unable to create dataflow service: %v", err)
	}
	inFile := fmt.Sprintf("gs://%s/%s/%s", dataBucket, tableID, dataFilePattern)
	outFile := fmt.Sprintf("gs://%s/%s/%s/%s", controlBucket, cacheType, tableID, completedFile)
	params := &dataflow.LaunchTemplateParameters{
		JobName: fmt.Sprintf("%s-csv2bt-%s", CurrentEnv, tableID),
		Parameters: map[string]string{
			"inputFile":          inFile,
			"completionFile":     outFile,
			"bigtableInstanceId": btInstance,
			"bigtableTableId":    tableID,
			"bigtableProjectId":  btProjectID,
		},
	}

	log.Printf("[%s/%s] Launching dataflow job: %s -> %s\n", btInstance, tableID, inFile, outFile)
	launchCall := dataflow.NewProjectsTemplatesService(dataflowService).Launch(btProjectID, params)
	_, err = launchCall.GcsPath(dataflowTemplate).Do()
	if err != nil {
		log.Printf("Unable to launch dataflow job (%s, %s): %v\n", inFile, outFile, err)
		return status.Errorf(codes.Internal, "Unable to launch dataflow job (%s, %s): %v\n", inFile, outFile, err)
	}
	return nil
}

func setupBTTable(ctx context.Context, btInstance, tableID string) error {
	adminClient, err := bigtable.NewAdminClient(ctx, btProjectID, btInstance)
	if err != nil {
		log.Printf("Unable to create a table admin client. %v", err)
		return err
	}

	// Create table. We retry 3 times in 1 minute intervals.
	dctx, cancel := context.WithDeadline(ctx, time.Now().Add(10*time.Minute))
	defer cancel()
	var ok bool
	for ii := 0; ii < createTableRetries; ii++ {
		log.Printf("Creating new bigtable table (%d): %s/%s", ii, btInstance, tableID)
		if err = adminClient.CreateTable(dctx, tableID); err == nil {
			ok = true
			break
		}
		time.Sleep(1 * time.Minute)
	}
	if !ok {
		log.Printf("Unable to create table: %s, got error: %v", tableID, err)
		return err
	}

	// Create table columnFamily.
	log.Printf("Creating column family %s in table %s/%s", columnFamily, btInstance, tableID)
	if err := adminClient.CreateColumnFamily(dctx, tableID, columnFamily); err != nil {
		log.Printf("Unable to create column family: csv for table: %s, got error: %v", tableID, err)
		return err
	}
	return nil
}

func scaleBT(ctx context.Context, btInstance string, btClusters []string, numNodes int32) error {
	// Scale up bigtable cluster. This helps speed up the dataflow job.
	// We scale down again once dataflow job completes.
	instanceAdminClient, err := bigtable.NewInstanceAdminClient(ctx, btProjectID)
	dctx, cancel := context.WithDeadline(ctx, time.Now().Add(10*time.Minute))
	defer cancel()
	if err != nil {
		log.Printf("Unable to create a table instance admin client. %v", err)
		return err
	}
	for _, c := range btClusters {
		log.Printf("Scaling BT %s cluster %s to %d nodes", btInstance, c, numNodes)
		if err := instanceAdminClient.UpdateCluster(dctx, btInstance, c, numNodes); err != nil {
			log.Printf("Unable to resize bigtable cluster %s to %d: %v", c, numNodes, err)
			return err
		}
	}
	return nil
}

func parsePath(path string) (string, string, error) {
	parts := strings.Split(path, "/")
	if len(parts) != 3 {
		return "", "", status.Errorf(codes.Internal, "Unexpected number of parts %s", path)
	}
	if parts[0] != baseCacheType && parts[0] != branchCacheType {
		return "", "", status.Errorf(codes.Internal, "Unexpected cache type %s", parts[0])
	}
	return parts[0], parts[1], nil
}

func BTImportControllerInternal(ctx context.Context, e GCSEvent) error {

	env := envs[CurrentEnv]

	if e.Bucket != env.controlBucket {
		return status.Errorf(codes.Internal, "Unexpected bucket %s", e.Bucket)
	}

	if strings.HasSuffix(e.Name, initFile) {
		log.Printf("[%s] State Init", e.Name)
		// Called when the state-machine is at Init. Logic below moves it to Launched state.

		// (base|branch)/<tableID>/<initFile>
		cacheType, tableID, err := parsePath(e.Name)
		if err != nil {
			return err
		}
		btInstance := ""
		if cacheType == baseCacheType {
			btInstance = env.baseBTInstance
		} else {
			btInstance = env.branchBTInstance
		}
		launchedPath := fmt.Sprintf("%s/%s/%s", cacheType, tableID, launchedFile)
		if _, err := readFromGCS(ctx, e.Bucket, launchedPath); err == nil {
			return status.Errorf(codes.Internal, "Cache was already built for %s/%s: %v", cacheType, tableID, err)
		}
		if err := setupBTTable(ctx, btInstance, tableID); err != nil {
			return err
		}
		if cacheType == baseCacheType {
			// Scale up only for base cache.
			if err := scaleBT(ctx, env.baseBTInstance, env.baseBTClusters, env.baseBTNodesHigh); err != nil {
				return err
			}
		}
		err = launchDataflowJob(ctx, btInstance, env.controlBucket, cacheType, tableID)
		if err != nil {
			return err
		}
		// Save the fact that we've launched the dataflow job.
		err = writeToGCS(ctx, e.Bucket, launchedPath, "")
		if err != nil {
			return err
		}
		log.Printf("[%s] State Launched", e.Name)
	} else if strings.HasSuffix(e.Name, completedFile) {
		log.Printf("[%s] State Completed", e.Name)
		// Called when the state-machine moves to Completed state from Launched.

		// (base|branch)/<tableID>/<completedFile>
		cacheType, _, err := parsePath(e.Name)
		if err != nil {
			return err
		}
		if cacheType == baseCacheType {
			if err := scaleBT(ctx, env.baseBTInstance, env.baseBTClusters, env.baseBTNodesLow); err != nil {
				return err
			}
		}
		// TODO: else, notify Mixer to load the BT table.
		log.Printf("[%s] Completed work", e.Name)
	}
	return nil
}

// BTImportController consumes a GCS event and runs an import state machine.
func BTImportController(ctx context.Context, e GCSEvent) error {
	err := BTImportControllerInternal(ctx, e)
	if err != nil {
		// Panic gets reported to Cloud Logging Error Reporting that we can then
		// alert on
		// (https://cloud.google.com/functions/docs/monitoring/error-reporting#functions-errors-log-go)
		panic(err)
	}
	return nil
}

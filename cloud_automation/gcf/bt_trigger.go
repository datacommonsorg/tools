// Package btcachegeneration runs a GCF function that triggers in 2 scenarios:
// 1) completion of prophet-flume job in borg.
//		The trigger is based on GCS file prophet-cache/latest_base_cache_run.txt.
// 2) On completion of BT cache ingestion via an airflow job. This trigger is based
//		on GCS file prophet-cache/[success|failure].txt
//
// In the first case, on triggering it sets up new cloud BT table, scales up BT cluster to 300 nodes
// and starts an airflow job by writing to prophet-cache/airflow.txt
//
// In the second case it scales BT cluster to 20 nodes.
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
	btProjectID				= "google.com:datcom-store-dev"
	baseBTInstance		= "prophet-cache"
	baseBTCluster			= "prophet-cache-c1"
	branchBTInstance	 = "prophet-branch-cache"

	dataBucket				= "prophet_cache"
	controlBucket			= "automation_control"
	dataFilePattern		= "cache.csv*"
	dataflowTemplate	= "gs://datcom-dataflow-templates/templates/csv_to_bt_improved"
	createTableRetries = 3
	columnFamily			= "csv"
	bigtableNodesHigh	= 300
	bigtableNodesLow	= 20
	baseCacheType			= "base"
	branchCacheType		= "branch"

	// NOTE: The following three files represents the state of a BT import.
	//
	//		gs://<controlBucket>/(base|branch)/<tableID>/
	//
	// Init: written by google3 to start BT import.
	initFile					 = "init.txt"
	// Launched: written by this cloud function to mark launching of BT import job.
	launchedFile			 = "launched.txt"
	// Completed: written by dataflow to mark completion of BT import.
	completedFile			= "completed.txt"

	// TODO: Deprecate these files.
	triggerFile				= "latest_base_cache_version.txt"
	successFile				= "success.txt"
	failureFile				= "failure.txt"
	airflowTriggerFile = "airflow_trigger.txt"
)

// GCSEvent is the payload of a GCS event.
type GCSEvent struct {
	Name	 string `json:"name"`
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

func launchDataflowJob(ctx context.Context, btInstance, cacheType, tableID string) error {
	dataflowService, err := dataflow.NewService(ctx)
	if err != nil {
		log.Printf("Unable to create dataflow service: %v\n", err)
		return status.Errorf(codes.Internal, "Unable to create dataflow service: %v", err)
	}
	inFile := fmt.Sprintf("gs://%s/%s/%s", dataBucket, tableID, dataFilePattern)
	outFile := fmt.Sprintf("gs://%s/%s/%s/%s", controlBucket, cacheType, tableID, completedFile)
	params := &dataflow.LaunchTemplateParameters{
		JobName: "csv2bt-" + tableID,
		Parameters: map[string]string{
			"inputFile": inFile,
			"completionFile": outFile,
			"bigtableInstanceId": btInstance,
			"bigtableTableId": tableID,
			"bigtableProjectId": btProjectID,
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

func setupBigtable(ctx context.Context, btInstance, tableID string) error {
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

func scaleBaseBT(ctx context.Context, numNodes int32) error {
	// Scale up bigtable cluster. This helps speed up the dataflow job.
	// We scale down again once dataflow job completes.
	instanceAdminClient, err := bigtable.NewInstanceAdminClient(ctx, btProjectID)
	dctx, cancel := context.WithDeadline(ctx, time.Now().Add(10*time.Minute))
	defer cancel()
	if err != nil {
		log.Printf("Unable to create a table instance admin client. %v", err)
		return err
	}
	log.Printf("Scaling BT %s instance to %d nodes", baseBTInstance, numNodes)
	if err := instanceAdminClient.UpdateCluster(dctx, baseBTInstance, baseBTCluster, numNodes); err != nil {
		log.Printf("Unable to increase bigtable cluster size: %v", err)
		return err
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

// GCSTrigger consumes a GCS event.
// TODO: Delete this after BTImportController() is launched.
func GCSTrigger(ctx context.Context, e GCSEvent) error {

	if strings.HasSuffix(e.Name, triggerFile) {
		// Read contents of GCS file. it contains path to csv files
		// for base cache.
		tableID, err := readFromGCS(ctx, e.Bucket, e.Name)
		if err != nil {
			log.Printf("Unable to read from gcs gs://%s/%s, got err: %v", e.Bucket, e.Name, err)
			return err
		}
		// Create and scale up cloud BT.
		tableIDStr := strings.TrimSpace(fmt.Sprintf("%s", tableID))
		if err := setupBigtable(ctx, baseBTInstance, tableIDStr); err != nil {
			return err
		}
		if err := scaleBaseBT(ctx, bigtableNodesHigh); err != nil {
			return err
		}
		// Write to GCS file that triggers airflow job.
		inputFile := fmt.Sprintf("gs://prophet_cache/%s/cache.csv*", tableIDStr)
		err = writeToGCS(ctx, e.Bucket, airflowTriggerFile, inputFile)
		if err != nil {
			return err
		}
	} else if strings.HasSuffix(e.Name, successFile) || strings.HasSuffix(e.Name, failureFile) {
		return scaleBaseBT(ctx, bigtableNodesLow)
	}
	return nil
}

// BTImportController consumes a GCS event and runs an import state machine.
func BTImportController(ctx context.Context, e GCSEvent) error {

	if e.Bucket != controlBucket {
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
			btInstance = baseBTInstance
		} else {
			btInstance = branchBTInstance
		}
		launchedPath := fmt.Sprintf("%s/%s/%s", cacheType, tableID, launchedFile)
		if _, err := readFromGCS(ctx, e.Bucket, launchedPath); err == nil {
			return status.Errorf(codes.Internal, "Cache was already built for %s/%s: %v", cacheType, tableID, err)
		}
		if err := setupBigtable(ctx, btInstance, tableID); err != nil {
			return err
		}
		if cacheType == baseCacheType {
			// Scale up only for base cache.
			if err := scaleBaseBT(ctx, bigtableNodesHigh); err != nil {
				return err
			}
		}
		err = launchDataflowJob(ctx, btInstance, cacheType, tableID)
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
			if err := scaleBaseBT(ctx, bigtableNodesLow); err != nil {
				return err
			}
		}
		// TODO: else, notify Mixer to load the BT table.
	}
	return nil
}

// Copyright 2022 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Package btcachegeneration runs a GCF function that triggers in 2 scenarios:
// 1) completion of prophet-flume job in borg.
// 2) completion of BT cache ingestion dataflow job.
//
// In the first case, on triggering it sets up new cloud BT table, scales up BT
// cluster (only for base cache) and starts a dataflow job.
//
// In the second case it scales BT cluster down (only for base cache).
package gcf

import (
	"context"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"time"

	"cloud.google.com/go/bigtable"
	"cloud.google.com/go/storage"
	"github.com/pkg/errors"
	dataflow "google.golang.org/api/dataflow/v1b3"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const (
	dataFilePattern    = "cache.csv*"
	createTableRetries = 3
	columnFamily       = "csv"

	// NOTE: The following three files represents the state of a BT import. They
	// get written under:
	//
	//		<controlPath>/<TableID>/
	//
	// Init: written by borg to start BT import.
	initFile = "init.txt"
	// Launched: written by this cloud function to mark launching of BT import job.
	launchedFile = "launched.txt"
	// Completed: written by dataflow to mark completion of BT import.
	completedFile = "completed.txt"
	// Default region
	region = "us-central1"
)

// GCSEvent is the payload of a GCS event.
type GCSEvent struct {
	Name   string `json:"name"`
	Bucket string `json:"bucket"`
}

// Return the GCS bucket and object from path in the form of gs://<bucket>/<object>
func parsePath(path string) (string, string, error) {
	parts := strings.Split(path, "/")
	if parts[0] != "gs:" || parts[1] != "" || len(parts) < 3 {
		return "", "", errors.Errorf("Unexpected path: %s", path)
	}
	return parts[2], strings.Join(parts[3:], "/"), nil
}

func isObjectExist(ctx context.Context, path string) (bool, error) {
	bucket, object, err := parsePath(path)
	if err != nil {
		return false, err
	}
	gcsClient, err := storage.NewClient(ctx)
	if err != nil {
		return false, errors.Wrap(err, "Failed to create gcsClient")
	}
	_, err = gcsClient.Bucket(bucket).Object(object).Attrs(ctx)
	if err == storage.ErrObjectNotExist {
		return false, nil
	}
	return true, nil
}

func writeToGCS(ctx context.Context, path, data string) error {
	bucket, object, err := parsePath(path)
	if err != nil {
		return err
	}
	gcsClient, err := storage.NewClient(ctx)
	if err != nil {
		return errors.Wrap(err, "Failed to create gcsClient")
	}
	w := gcsClient.Bucket(bucket).Object(object).NewWriter(ctx)
	defer w.Close()
	_, err = fmt.Fprint(w, data)
	return err
}

func launchDataflowJob(
	ctx context.Context,
	projectID string,
	instance string,
	tableID string,
	dataPath string,
	controlPath string,
	dataflowTemplate string,
) error {
	dataflowService, err := dataflow.NewService(ctx)
	if err != nil {
		return errors.Wrap(err, "Unable to create dataflow service")
	}
	dataFile := fmt.Sprintf("%s/%s/%s", dataPath, tableID, dataFilePattern)
	launchedPath := fmt.Sprintf("%s/%s/%s", controlPath, tableID, launchedFile)
	completedPath := fmt.Sprintf("%s/%s/%s", controlPath, tableID, completedFile)
	params := &dataflow.LaunchTemplateParameters{
		JobName: tableID,
		Parameters: map[string]string{
			"inputFile":          dataFile,
			"completionFile":     completedPath,
			"bigtableInstanceId": instance,
			"bigtableTableId":    tableID,
			"bigtableProjectId":  projectID,
			"region":             region,
		},
	}
	log.Printf("[%s/%s] Launching dataflow job: %s -> %s\n", instance, tableID, dataFile, launchedPath)
	launchCall := dataflow.NewProjectsTemplatesService(dataflowService).Launch(projectID, params)
	_, err = launchCall.GcsPath(dataflowTemplate).Do()
	if err != nil {
		return errors.WithMessagef(err, "Unable to launch dataflow job (%s, %s): %v\n", dataFile, launchedPath)
	}
	return nil
}

func setupBT(ctx context.Context, btProjectID, btInstance, tableID string) error {
	adminClient, err := bigtable.NewAdminClient(ctx, btProjectID, btInstance)
	if err != nil {
		return errors.Wrap(err, "Unable to create a table admin client")
	}
	// Create table. We retry 3 times in 10 seconds intervals.
	dctx, cancel := context.WithDeadline(ctx, time.Now().Add(10*time.Minute))
	defer cancel()
	var ok bool
	for ii := 0; ii < createTableRetries; ii++ {
		log.Printf("Creating new bigtable table (%d): %s/%s", ii, btInstance, tableID)
		err = adminClient.CreateTable(dctx, tableID)
		if err != nil {
			log.Printf("Error creating table %s, retry...", err)
		} else {
			ok = true
			break
		}
		time.Sleep(10 * time.Second)
	}
	if !ok {
		return errors.Errorf("Unable to create table: %s, got error: %v", tableID, err)
	}
	// Create table columnFamily.
	log.Printf("Creating column family %s in table %s/%s", columnFamily, btInstance, tableID)
	if err := adminClient.CreateColumnFamily(dctx, tableID, columnFamily); err != nil {
		return errors.WithMessagef(err, "Unable to create column family: csv for table: %s, got error: %v", tableID)
	}
	return nil
}

func scaleBT(ctx context.Context, projectID, instance, cluster string, numNodes int32) error {
	// Scale up bigtable cluster. This helps speed up the dataflow job.
	// We scale down again once dataflow job completes.
	instanceAdminClient, err := bigtable.NewInstanceAdminClient(ctx, projectID)
	dctx, cancel := context.WithDeadline(ctx, time.Now().Add(10*time.Minute))
	defer cancel()
	if err != nil {
		return errors.Wrap(err, "Unable to create a table instance admin client")
	}
	log.Printf("Scaling BT %s cluster %s to %d nodes", instance, cluster, numNodes)
	if err := instanceAdminClient.UpdateCluster(dctx, instance, cluster, numNodes); err != nil {
		return errors.WithMessagef(err, "Unable to resize bigtable cluster %s to %d: %v", cluster, numNodes)
	}
	return nil
}

func btImportControllerInternal(ctx context.Context, e GCSEvent) error {
	projectID := os.Getenv("projectID")
	instance := os.Getenv("instance")
	cluster := os.Getenv("cluster")
	nodesHigh := os.Getenv("nodesHigh")
	nodesLow := os.Getenv("nodesLow")
	dataflowTemplate := os.Getenv("dataflowTemplate")
	dataPath := os.Getenv("dataPath")
	controlPath := os.Getenv("controlPath")
	// Get low and high nodes number
	nodesH, err := strconv.Atoi(nodesHigh)
	if err != nil {
		return err
	}
	nodesL, err := strconv.Atoi(nodesLow)
	if err != nil {
		return err
	}
	// Get control bucket and object
	controlBucket, _, err := parsePath(controlPath)
	if err != nil {
		return err
	}
	if e.Bucket != controlBucket {
		return status.Errorf(codes.Internal, "Unexpected bucket %s", e.Bucket)
	}
	// Get table ID.
	parts := strings.Split(e.Name, "/")
	tableID := parts[len(parts)-2]

	if strings.HasSuffix(e.Name, initFile) {
		log.Printf("[%s] State Init", e.Name)
		// Called when the state-machine is at Init. Logic below moves it to Launched state.
		launchedPath := fmt.Sprintf("%s/%s/%s", controlPath, tableID, launchedFile)
		exist, err := isObjectExist(ctx, launchedPath)
		if err != nil {
			return errors.WithMessagef(err, "Failed to check %s", launchedFile)
		}
		if exist {
			return errors.WithMessagef(err, "Cache was already built for %s", tableID)
		}
		if err := setupBT(ctx, projectID, instance, tableID); err != nil {
			return err
		}
		if err := scaleBT(ctx, projectID, instance, cluster, int32(nodesH)); err != nil {
			return err
		}
		err = launchDataflowJob(ctx, projectID, instance, tableID, dataPath, controlPath, dataflowTemplate)
		if err != nil {
			return err
		}
		// Save the fact that we've launched the dataflow job.
		err = writeToGCS(ctx, launchedPath, "")
		if err != nil {
			return err
		}
		log.Printf("[%s] State Launched", e.Name)
	} else if strings.HasSuffix(e.Name, completedFile) {
		log.Printf("[%s] State Completed", e.Name)
		// Called when the state-machine moves to Completed state from Launched.
		if err := scaleBT(ctx, projectID, instance, cluster, int32(nodesL)); err != nil {
			return err
		}
		// TODO: else, notify Mixer to load the BT table.
		log.Printf("[%s] Completed work", e.Name)
	}
	return nil
}

// BTImportController consumes a GCS event and runs an import state machine.
func BTImportController(ctx context.Context, e GCSEvent) error {
	err := btImportControllerInternal(ctx, e)
	if err != nil {
		// Panic gets reported to Cloud Logging Error Reporting that we can then
		// alert on
		// (https://cloud.google.com/functions/docs/monitoring/error-reporting#functions-errors-log-go)
		panic(errors.Wrap(err, "panic"))
	}
	return nil
}

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

// Package gcf runs a GCF function that triggers in 2 scenarios:
//
// 1) completion of prophet-flume job in borg. On triggering it sets up new
//    cloud BT table, scales up BT cluster (if needed) and starts a dataflow job.
// 2) completion of BT cache ingestion dataflow job. It scales BT cluster down
//    (if needed).
//
// There are two set of trigger functions defined:
// - ProdBTImportController
// - PrivateBTImportController
// which targets on production imports and private imports. The folder structure
// are different for the two scenarios.
// The environment variables for deployments are stored in (prod|private)/*.yaml
package gcf

import (
	"context"
	"fmt"
	"log"
	"path"
	"strings"
	"time"

	"cloud.google.com/go/bigtable"
	"cloud.google.com/go/storage"
	"github.com/pkg/errors"
	dataflow "google.golang.org/api/dataflow/v1b3"
)

const (
	dataFilePattern    = "cache.csv*"
	createTableRetries = 3
	columnFamily       = "csv"
	// Default region
	region = "us-central1"

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
)

// GCSEvent is the payload of a GCS event.
type GCSEvent struct {
	Name   string `json:"name"` // File name in the control folder
	Bucket string `json:"bucket"`
}

// joinURL joins url components.
// path.Join does work well for url, for example gs:// is changaed to gs:/
func joinURL(base string, paths ...string) string {
	p := path.Join(paths...)
	return fmt.Sprintf("%s/%s", strings.TrimRight(base, "/"), strings.TrimLeft(p, "/"))
}

// parsePath returns the GCS bucket and object from path in the form of gs://<bucket>/<object>
func parsePath(path string) (string, string, error) {
	parts := strings.Split(path, "/")
	if parts[0] != "gs:" || parts[1] != "" || len(parts) < 3 {
		return "", "", errors.Errorf("Unexpected path: %s", path)
	}
	return parts[2], strings.Join(parts[3:], "/"), nil
}

func doesObjectExist(ctx context.Context, path string) (bool, error) {
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
	return errors.WithMessagef(err, "Failed to write data to %s/%s", bucket, object)
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
	dataFile := joinURL(dataPath, tableID, dataFilePattern)
	launchedPath := joinURL(controlPath, tableID, launchedFile)
	completedPath := joinURL(controlPath, tableID, completedFile)
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
	// Create table. We retry 3 times in 1 minute intervals.
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
		time.Sleep(1 * time.Minute)
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

func getBTNodes(ctx context.Context, projectID, instance, cluster string) (int, error) {
	instanceAdminClient, err := bigtable.NewInstanceAdminClient(ctx, projectID)
	if err != nil {
		return 0, errors.Wrap(err, "Unable to create a table instance admin client")
	}
	clusterInfo, err := instanceAdminClient.GetCluster(ctx, instance, cluster)
	if err != nil {
		return 0, errors.Wrap(err, "Unable to get cluster information")
	}
	return clusterInfo.ServeNodes, nil
}

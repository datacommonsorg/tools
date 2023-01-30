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

package gcf

import (
	"context"
	"log"
	"os"
	"path/filepath"
	"strings"

	"github.com/pkg/errors"
)

// TODO(alex): refactor path -> event handler logic.
func customInternal(ctx context.Context, e GCSEvent) error {
	projectID := os.Getenv("projectID")
	bucket := os.Getenv("bucket")
	instance := os.Getenv("instance")
	cluster := os.Getenv("cluster")
	dataflowTemplate := os.Getenv("dataflowTemplate")
	controllerTriggerTopic := os.Getenv("controllerTriggerTopic")
	if projectID == "" {
		return errors.New("projectID is not set in environment")
	}
	if instance == "" {
		return errors.New("instance is not set in environment")
	}
	if cluster == "" {
		return errors.New("cluster is not set in environment")
	}
	if dataflowTemplate == "" {
		return errors.New("dataflowTemplate is not set in environment")
	}
	if bucket == "" {
		return errors.New("bucket is not set in environment")
	}

	// First check if this is a csv file, if it s
	if strings.HasSuffix(e.Name, csvFileExtension) && controllerTriggerTopic != "" {
		bigstoreCSVPath := filepath.Join("/bigstore", bucket, e.Name)
		log.Printf("Detected csv file based on %s extension. Triggering the controller", csvFileExtension)
		log.Printf("Using PubSub topic: %s", controllerTriggerTopic)
		pcfg := PublishConfig{FullTopicName:controllerTriggerTopic}
		return TriggerController(ctx, pcfg, bigstoreCSVPath)
	}

	// Get table ID.
	// e.Name should is like "**/<user>/<import>/control/<table_id>/launched.txt"
	parts := strings.Split(e.Name, "/")
	idxControl := len(parts) - 3
	idxTable := len(parts) - 2
	if parts[idxControl] != "control" {
		log.Printf("Ignore irrelevant trigger from file %s", e.Name)
		return nil
	}
	tableID := parts[idxTable]
	rootFolder := "gs://" + bucket + "/" + strings.Join(parts[0:idxControl], "/")

	if strings.HasSuffix(e.Name, initFile) {
		log.Printf("[%s] State Init", e.Name)
		// Called when the state-machine is at Init. Logic below moves it to Launched state.
		launchedPath := joinURL(rootFolder, "control", tableID, launchedFile)
		exist, err := doesObjectExist(ctx, launchedPath)
		if err != nil {
			return errors.WithMessagef(err, "Failed to check %s", launchedFile)
		}
		if exist {
			return errors.WithMessagef(err, "Cache was already built for %s", tableID)
		}
		if err := setupBT(ctx, projectID, instance, tableID); err != nil {
			return err
		}
		dataPath := joinURL(rootFolder, "cache")
		controlPath := joinURL(rootFolder, "control")
		err = launchDataflowJob(ctx, projectID, instance, tableID, dataPath, controlPath, dataflowTemplate)
		if err != nil {
			if errDeleteBT := deleteBTTable(ctx, projectID, instance, tableID); errDeleteBT != nil {
				log.Printf("Failed to delete BT table on failed Dataflow launch: %v", errDeleteBT)
			}
			return err
		}
		// Save the fact that we've launched the dataflow job.
		err = writeToGCS(ctx, launchedPath, "")
		if err != nil {
			if errDeleteBT := deleteBTTable(ctx, projectID, instance, tableID); errDeleteBT != nil {
				log.Printf("Failed to delete BT table on failed GCS write: %v", errDeleteBT)
			}
			return err
		}
		log.Printf("[%s] State Launched", e.Name)
	} else if strings.HasSuffix(e.Name, completedFile) {
		// TODO: else, notify Mixer to load the BT table.
		log.Printf("[%s] Completed work", e.Name)
	}
	return nil
}

// CustomBTImportController consumes a GCS event and runs an import state machine.
func CustomBTImportController(ctx context.Context, e GCSEvent) error {
	err := customInternal(ctx, e)
	if err != nil {
		// Panic gets reported to Cloud Logging Error Reporting that we can then
		// alert on
		// (https://cloud.google.com/functions/docs/monitoring/error-reporting#functions-errors-log-go)
		panic(errors.Wrap(err, "panic"))
	}
	return nil
}

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
	"strings"

	custom "github.com/datacommonsorg/tools/gcf/custom"
	"github.com/datacommonsorg/tools/gcf/lib"
	"github.com/pkg/errors"
)

const (
	triggerPathSuffix = "/internal/control/trigger.txt"
)

// TODO(alex): refactor path -> event handler logic.
func customInternal(ctx context.Context, e lib.GCSEvent) error {
	projectID := os.Getenv("projectID")
	bucket := os.Getenv("bucket")
	instance := os.Getenv("instance")
	cluster := os.Getenv("cluster")
	dataflowTemplate := os.Getenv("dataflowTemplate")
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

	parts := strings.Split(e.Name, "/")

	// Get table ID.
	// e.Name should is like "**/<user>/<import>/control/<table_id>/launched.txt"
	idxTable := len(parts) - 2
	tableID := parts[idxTable]

	idxControl := len(parts) - 3
	rootFolder := "gs://" + bucket + "/" + strings.Join(parts[0:idxControl], "/")

	if strings.HasSuffix(e.Name, lib.InitFile) {
		log.Printf("[%s] State Init", e.Name)
		// Called when the state-machine is at Init. Logic below moves it to Launched state.
		launchedPath := lib.JoinURL(rootFolder, "control", tableID, lib.LaunchedFile)
		exist, err := lib.DoesObjectExist(ctx, launchedPath)
		if err != nil {
			return errors.WithMessagef(err, "Failed to check %s", lib.LaunchedFile)
		}
		if exist {
			return errors.WithMessagef(err, "Cache was already built for %s", tableID)
		}
		if err := lib.SetupBT(ctx, projectID, instance, tableID); err != nil {
			return err
		}
		dataPath := lib.JoinURL(rootFolder, "cache")
		controlPath := lib.JoinURL(rootFolder, "control")
		err = lib.LaunchDataflowJob(ctx, projectID, instance, tableID, dataPath, controlPath, dataflowTemplate)
		if err != nil {
			if errDeleteBT := lib.DeleteBTTable(ctx, projectID, instance, tableID); errDeleteBT != nil {
				log.Printf("Failed to delete BT table on failed Dataflow launch: %v", errDeleteBT)
			}
			return err
		}
		// Save the fact that we've launched the dataflow job.
		err = lib.WriteToGCS(ctx, launchedPath, "")
		if err != nil {
			if errDeleteBT := lib.DeleteBTTable(ctx, projectID, instance, tableID); errDeleteBT != nil {
				log.Printf("Failed to delete BT table on failed GCS write: %v", errDeleteBT)
			}
			return err
		}
		log.Printf("[%s] State Launched", e.Name)
	} else if strings.HasSuffix(e.Name, lib.CompletedFile) {
		// TODO: else, notify Mixer to load the BT table.
		log.Printf("[%s] Completed work", e.Name)
	} else if strings.HasSuffix(e.Name, triggerPathSuffix) {
		log.Printf("detected trigger file in %s", e.Name)
		root := strings.TrimSuffix(e.Name, triggerPathSuffix)
		err := custom.HandleTriggerFlow(ctx, bucket, root)
		if err != nil {
			log.Fatalf("Handle trigger flow err: %v", err)
		}

	}
	return nil
}

// Controller consumes a GCS event and runs an import state machine.
func CustomController(ctx context.Context, e lib.GCSEvent) error {
	err := customInternal(ctx, e)
	if err != nil {
		// Panic gets reported to Cloud Logging Error Reporting that we can then
		// alert on
		// (https://cloud.google.com/functions/docs/monitoring/error-reporting#functions-errors-log-go)
		panic(errors.Wrap(err, "panic"))
	}
	return nil
}

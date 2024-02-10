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

	"github.com/datacommonsorg/tools/gcf/lib"
	"github.com/pkg/errors"
)

func prodInternal(ctx context.Context, e lib.GCSEvent) error {
	projectID := os.Getenv("projectID")
	instance := os.Getenv("instance")
	cluster := os.Getenv("cluster")
	dataflowTemplate := os.Getenv("dataflowTemplate")
	dataPath := os.Getenv("dataPath")
	controlPath := os.Getenv("controlPath")
	appProfileID := os.Getenv("appProfileID")
	maxNumWorkers := os.Getenv("maxNumWorkers")
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
	if dataPath == "" {
		return errors.New("dataPath is not set in environment")
	}
	if controlPath == "" {
		return errors.New("controlPath is not set in environment")
	}
	// Get control bucket and object
	controlBucket, controlFolder, err := lib.ParsePath(controlPath)
	if err != nil {
		return err
	}
	if e.Bucket != controlBucket {
		log.Printf("Trigger bucket '%s' != '%s', skip processing", e.Bucket, controlBucket)
		return nil
	}
	// Get table ID.
	// e.Name should is like "**/*/branch_2021_01_01_01_01/launched.txt"
	parts := strings.Split(e.Name, "/")
	if len(parts) < 3 {
		log.Printf("Ignore irrelevant trigger from file %s", e.Name)
		return nil
	}
	tableID := parts[len(parts)-2]
	triggerFolder := strings.Join(parts[0:len(parts)-2], "/")
	if triggerFolder != controlFolder {
		log.Printf("Control folder '%s' != '%s', skip processing", triggerFolder, controlFolder)
		return nil
	}

	if strings.HasSuffix(e.Name, lib.InitFile) {
		log.Printf("[%s] State Init", e.Name)
		// Called when the state-machine is at Init. Logic below moves it to Launched state.
		launchedPath := lib.JoinURL(controlPath, tableID, lib.LaunchedFile)
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
		err = lib.LaunchDataflowJob(ctx, projectID, instance, tableID, dataPath, controlPath, dataflowTemplate, appProfileID, maxNumWorkers)
		if err != nil {
			if errDeleteBT := lib.DeleteBTTable(ctx, projectID, instance, tableID); errDeleteBT != nil {
				log.Printf("Failed to delete BT table on failed GCS write: %v", errDeleteBT)
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
	}
	return nil
}

// BaseController consumes a GCS event and runs an import state machine.
func BaseController(ctx context.Context, e lib.GCSEvent) error {
	err := prodInternal(ctx, e)
	if err != nil {
		// Panic gets reported to Cloud Logging Error Reporting that we can then
		// alert on
		// (https://cloud.google.com/functions/docs/monitoring/error-reporting#functions-errors-log-go)
		panic(errors.Wrap(err, "panic"))
	}
	return nil
}

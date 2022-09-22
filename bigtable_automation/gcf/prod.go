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
	"strconv"
	"strings"

	"github.com/pkg/errors"
)

func prodInternal(ctx context.Context, e GCSEvent) error {
	projectID := os.Getenv("projectID")
	instance := os.Getenv("instance")
	cluster := os.Getenv("cluster")
	nodesHigh := os.Getenv("nodesHigh")
	nodesLow := os.Getenv("nodesLow")
	dataflowTemplate := os.Getenv("dataflowTemplate")
	dataPath := os.Getenv("dataPath")
	controlPath := os.Getenv("controlPath")
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
	// Get low and high nodes number
	nodesH, err := strconv.Atoi(nodesHigh)
	if err != nil {
		return errors.Wrap(err, "Unable to parse 'nodesHigh' as an integer")
	}
	nodesL, err := strconv.Atoi(nodesLow)
	if err != nil {
		return errors.Wrap(err, "Unable to parse 'nodesLow' as an integer")
	}
	// Get control bucket and object
	controlBucket, controlFolder, err := parsePath(controlPath)
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

	numNodes, err := getBTNodes(ctx, projectID, instance, cluster)
	if err != nil {
		return err
	}

	if strings.HasSuffix(e.Name, initFile) {
		log.Printf("[%s] State Init", e.Name)
		// Called when the state-machine is at Init. Logic below moves it to Launched state.
		launchedPath := joinURL(controlPath, tableID, launchedFile)
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
		if numNodes < nodesH {
			if err := scaleBT(ctx, projectID, instance, cluster, int32(nodesH)); err != nil {
				return err
			}
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
		if numNodes == nodesH {
			// Only scale down BT nodes when the current high node is set up this config.
			// This requires different high nodes in different config.
			if err := scaleBT(ctx, projectID, instance, cluster, int32(nodesL)); err != nil {
				return err
			}
		}
		// TODO: else, notify Mixer to load the BT table.
		log.Printf("[%s] Completed work", e.Name)
	}
	return nil
}

// ProdBTImportController consumes a GCS event and runs an import state machine.
func ProdBTImportController(ctx context.Context, e GCSEvent) error {
	err := prodInternal(ctx, e)
	if err != nil {
		// Panic gets reported to Cloud Logging Error Reporting that we can then
		// alert on
		// (https://cloud.google.com/functions/docs/monitoring/error-reporting#functions-errors-log-go)
		panic(errors.Wrap(err, "panic"))
	}
	return nil
}

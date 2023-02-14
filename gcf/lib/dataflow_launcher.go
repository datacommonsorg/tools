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

// Dataflow launcher helper functions.
// launchDataflowJob will either start a Dataflow job
// using a Flex Template or a Classic Template depending on the template path.
// Flex templates are json based Dataflow templates and MUST end with ".json".
package lib

import (
	"context"
	"fmt"
	"log"
	"os"
	"path"
	"strings"
	"time"

	"github.com/pkg/errors"
	dataflow "google.golang.org/api/dataflow/v1b3"
)

const (
	dataFilePattern = "cache.csv*"
	// Default region
	region = "us-central1"

	// NOTE: The following three files represents the state of a BT import. They
	// get written under:
	//
	//		<controlPath>/<TableID>/
	//
	// Init: written by borg to start BT import.
	InitFile = "init.txt"
	// Launched: written by this cloud function to mark launching of BT import job.
	LaunchedFile = "launched.txt"
	// Completed: written by dataflow to mark completion of BT import.
	CompletedFile = "completed.txt"
)

func LaunchDataflowJob(
	ctx context.Context,
	projectID string,
	instance string,
	tableID string,
	dataPath string,
	controlPath string,
	dataflowTemplate string,
) error {
	// Flex templates are json based templates.
	// Please see the README under java/dataflow in this repo.
	if strings.HasSuffix(dataflowTemplate, ".json") {
		log.Printf("Launching Flex Template: %s", dataflowTemplate)
		return launchFromFlexTemplate(
			ctx, projectID, instance, tableID,
			dataPath, controlPath, dataflowTemplate,
		)
	}

	log.Printf("Launching Classic Template: %s", dataflowTemplate)
	return launchFromClassicTemplate(
		ctx, projectID, instance, tableID,
		dataPath, controlPath, dataflowTemplate,
	)
}

// joinURL joins url components.
// path.Join does work well for url, for example gs:// is changaed to gs:/
func JoinURL(base string, paths ...string) string {
	p := path.Join(paths...)
	return fmt.Sprintf("%s/%s", strings.TrimRight(base, "/"), strings.TrimLeft(p, "/"))
}

func launchFromFlexTemplate(
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
	dataFile := JoinURL(dataPath, tableID, dataFilePattern)
	launchedPath := JoinURL(controlPath, tableID, LaunchedFile)
	completedPath := JoinURL(controlPath, tableID, CompletedFile)
	// Job names from Flex templates can only contain alphanumerics and "-".
	jobName := fmt.Sprintf("%s-%s",
		strings.ReplaceAll(tableID, "_", "-"),
		fmt.Sprintf("%d", time.Now().Unix()),
	)

	tempLocation := os.Getenv("tempLocation")
	if tempLocation == "" {
		return fmt.Errorf("tempLocation is not set in environment")
	}

	params := &dataflow.LaunchFlexTemplateParameter{
		JobName: jobName,
		Parameters: map[string]string{
			"inputFile":          dataFile,
			"completionFile":     completedPath,
			"bigtableInstanceId": instance,
			"bigtableTableId":    tableID,
			"bigtableProjectId":  projectID,
			"tempLocation":       tempLocation,
		},
		ContainerSpecGcsPath: dataflowTemplate,
	}

	log.Printf("[%s/%s] Launching dataflow job: %s -> %s\n", instance, tableID, dataFile, launchedPath)
	launchCall := dataflow.NewProjectsLocationsFlexTemplatesService(
		dataflowService,
	).Launch(
		projectID,
		region,
		&dataflow.LaunchFlexTemplateRequest{
			LaunchParameter: params,
		},
	)

	_, err = launchCall.Do()
	if err != nil {
		return errors.WithMessagef(err, "Unable to launch dataflow job %s: %v\n", dataFile)
	}
	return nil
}

func launchFromClassicTemplate(
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
	dataFile := JoinURL(dataPath, tableID, dataFilePattern)
	launchedPath := JoinURL(controlPath, tableID, LaunchedFile)
	completedPath := JoinURL(controlPath, tableID, CompletedFile)
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

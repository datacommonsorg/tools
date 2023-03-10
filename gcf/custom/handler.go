// Copyright 2023 Google LLC
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

package custom

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/datacommonsorg/tools/gcf/lib"
	"github.com/pkg/errors"
	"google.golang.org/protobuf/encoding/prototext"
)

func HandleTriggerFlow(ctx context.Context, bucket, root string) error {
	projectID := os.Getenv("projectID")
	isLocal := os.Getenv("isLocal") == "true"
	controllerTriggerTopic := os.Getenv("controllerTriggerTopic")
	if controllerTriggerTopic == "" {
		return errors.New("controllerTriggerTopic is not set in environment")
	}
	reader := &GCSReader{}
	// List objects from GCS
	objects, err := reader.ListObjects(ctx, bucket, root)
	if err != nil {
		return err
	}
	// Folder layout can be found from:
	// https://docs.datacommons.org/custom_dc/upload_data.html
	layout, err := BuildLayout(root, objects)
	if err != nil {
		return errors.Wrap(err, "build layout got errors")
	}
	// Compute manifest
	manifest, err := ComputeManifest(ctx, reader, bucket, layout)
	if err != nil {
		return err
	}
	// Copy congfig to GCS
	marshalOpts := prototext.MarshalOptions{Multiline: true}
	bytes, err := marshalOpts.Marshal(manifest)
	if err != nil {
		log.Fatalf("Failed to serialize proto: %v", err)
		return err
	}

	if isLocal {
		// For local testing, write the context text proto to a local file.
		// PubSub is message is not sent.
		return os.WriteFile("config.textproto", bytes, 0644)
	}

	// Write to manifest to gcs.
	configPath := fmt.Sprintf(
		"gs://%s/%s/internal/config/config.textproto", bucket, root)
	if err = lib.WriteToGCS(ctx, configPath, string(bytes)); err != nil {
		return err
	}

	bigstoreRoot := fmt.Sprintf("/bigstore/%s/%s", bucket, root)
	bigstoreDataDirectory := bigstoreRoot + "/data"
	bigstoreConfigPath := bigstoreRoot + "/internal/config/config.textproto"
	bigstoreCacheDirectory := bigstoreRoot + "/internal/cache"
	bigstoreControlDirectory := bigstoreRoot + "/internal/control"

	// ID used to globally identify an import group under a project.
	instanceID := fmt.Sprintf("%s_%s", projectID, *manifest.ImportGroups[0].Name)

	attributes := map[string]string{
		"instance_id":                instanceID,
		"custom_manifest_path":       bigstoreConfigPath,
		"bigstore_data_directory":    bigstoreDataDirectory,
		"bigstore_cache_directory":   bigstoreCacheDirectory,
		"bigstore_control_directory": bigstoreControlDirectory,
		"produce_sv_and_svg_mcfs":    "true",
	}
	log.Printf("Using PubSub topic: %s", controllerTriggerTopic)
	return Publish(ctx, controllerTriggerTopic, attributes)
}

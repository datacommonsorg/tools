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

// Package gcf runs a GCF function that triggers in 2 scenarios:
//
//  1. completion of prophet-flume job in borg. On triggering it sets up new
//     cloud BT table, scales up BT cluster (if needed) and starts a dataflow job.
//  2. completion of BT cache ingestion dataflow job. It scales BT cluster down
//     (if needed).
//
// There are two set of trigger functions defined:
// - ProdBTImportController
// - PrivateBTImportController
// which targets on production imports and private imports. The folder structure
// are different for the two scenarios.
// The environment variables for deployments are stored in (prod|private)/*.yaml
package custom

import (
	"context"
	"log"
	"path/filepath"
	"strings"

	"cloud.google.com/go/storage"
	"github.com/pkg/errors"
	"google.golang.org/api/iterator"
)

// FindFolders find all the folders
// Note: files in <pathPrefix> are ignored.
// Returns a list of folder names under pathPrefix.
func FindFolders(ctx context.Context, c *storage.Client, bucket, pathPrefix string) ([]string, error) {
	it := c.Bucket(bucket).Objects(ctx, &storage.Query{Prefix: pathPrefix})
	folders := []string{}
	for {
		attrs, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return nil, err
		}
		// skip files and the pathPrefix folder itself.
		if !strings.HasSuffix(attrs.Name, "/") || attrs.Name == pathPrefix {
			continue
		}
		pathSuffix := strings.TrimSuffix(strings.TrimPrefix(attrs.Name, pathPrefix), "/")
		// kgnore subfolders
		if len(strings.Split(pathSuffix, "/")) > 1 {
			continue
		}
		log.Printf("FindFolders in  %s got %s", pathPrefix, attrs.Name)
		folders = append(folders, attrs.Name)
	}
	return folders, nil
}

func FindFiles(ctx context.Context, c *storage.Client, bucket, pathPrefix string) ([]string, error) {
	it := c.Bucket(bucket).Objects(ctx, &storage.Query{Prefix: pathPrefix})
	files := []string{}
	for {
		attrs, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return nil, err
		}
		// skip folders
		if strings.HasSuffix(attrs.Name, "/") {
			continue
		}
		log.Printf("FindFiles in %s got %s", pathPrefix, attrs.Name)
		files = append(files, attrs.Name)
	}
	return files, nil
}

func BigStorePath(bucket, path string) string {
	return filepath.Join("/bigstore", bucket, path)
}

// Find the root directory for data imports on gcs.
// For data import directory structures, please refer to
// https://docs.datacommons.org/custom_dc/upload_data.html
//
// Root directory in the above example is "gcs_folder"
// Example:
// findRootImportDirectory("/somepath/gcs_folder/internal/control/trigger.txt")
// returns "/somepath/gcs_folder/"
//
// Note manifest generator requires the "/" at the end.
func FindRootImportDirectory(triggerPath string) (string, error) {
	if filepath.Base(triggerPath) != ControllerTriggerFile {
		return "", errors.Errorf("Expected trigger file %s, got %s", ControllerTriggerFile, filepath.Base(triggerPath))
	}
	pathList := strings.Split(triggerPath, "/")
	if len(pathList) < 4 {
		return "", errors.Errorf("Expected pattern <folder>/internal/control/%s, got %s", ControllerTriggerFile, triggerPath)
	}
	if pathList[len(pathList)-2] != "control" {
		return "", errors.Errorf("Trigger path not under control folder: %s", triggerPath)
	}
	if pathList[len(pathList)-3] != "internal" {
		return "", errors.Errorf("control folder not under internal folder: %s", triggerPath)
	}
	return strings.Join(pathList[:len(pathList)-3], "/"), nil
}

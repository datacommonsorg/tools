// Copyright 2023 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//	https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
package lib

import (
	"fmt"
	"log"
	"path/filepath"
	"strings"

	"github.com/pkg/errors"
)

const (
	ControllerTriggerFile = "trigger.txt"
)

// DataFiles represent a logical unit of files for a single dataset.
type DataFiles struct {
	TMCFPath string
	CSVPaths []string
}

// ImportGroupFiles represent the collection of paths for a single import group.
type ImportGroupFiles struct {
	Source2Datasets   map[string][]string
	Dataset2DataFiles map[string]DataFiles
	ImportGroupName   string
}

// CollectImportFiles takes a list of gcs file paths and construct ImportGroupFiles.
// Caller is responsible for passing in paths all starting with the same top level path.
// The top level path should be relative to the import root
// Example:
// Suppose data.tmcf lives here.
// <bucket>/some/folder/to/root/data/source1/dataset1/data.tmcf
// Then the corresponding path in args should be "root/data/source1/dataset1/data.tmcf".
func CollectImportFiles(paths []string) (*ImportGroupFiles, error) {

	Source2Datasets := map[string][]string{}
	Dataset2DataFiles := map[string]DataFiles{}

	if len(paths) == 0 {
		return nil, errors.New("No path found in import group files")
	}
	importGroupName := strings.Split(paths[0], "/")[0]

	for _, path := range paths {
		// Path is expected to be like the following:
		// 	"demo/data/source2/solar/output.csv"
		folderList := strings.SplitN(path, "/", 5)
		if folderList[0] != importGroupName {
			return nil, fmt.Errorf("file for import group %s is not under %s/", importGroupName, importGroupName)
		}

		if len(folderList) < 5 {
			log.Printf("[Import group %s] ignoring a file not in the format of <group>/data/<source>/<dataset>/<file>: %s", importGroupName, path)
			continue
		}

		if folderList[1] != "data" {
			log.Printf("[Import group %s] found a file not under 'data/'. Ignoring %s", importGroupName, path)
			continue
		}

		dataSource := folderList[2]
		datasetName := folderList[3]
		if len(folderList) > 5 {
			log.Printf("[Import group %s] ignoring a file, likely because tmcf/csv is not directly under \"%s/\"%s", importGroupName, datasetName, path)
		}

		// Add to data source -> dataset name mapping only if the dataset has not been seen before.
		if _, datasetFound := Dataset2DataFiles[datasetName]; !datasetFound {
			Source2Datasets[dataSource] = append(Source2Datasets[dataSource], datasetName)
		}

		df := DataFiles{}
		if _, ok := Dataset2DataFiles[datasetName]; ok {
			df = Dataset2DataFiles[datasetName]
		}

		if filepath.Ext(path) == ".tmcf" {
			// Only 1 tmcf file per dataset.
			if len(df.TMCFPath) > 0 {
				return nil, fmt.Errorf("[Import group %s] Multiple tmcf found under dataset %s", importGroupName, datasetName)
			}
			df.TMCFPath = path
		} else if filepath.Ext(path) == ".csv" {
			df.CSVPaths = append(df.CSVPaths, path)
		} else {
			log.Printf("[Import group %s] Found non tmcf/csv file in dataset %s, ignoring %s", importGroupName, datasetName, path)
		}
		Dataset2DataFiles[datasetName] = df
	}

	// Validation.
	for datasetName, dataFiles := range Dataset2DataFiles {
		if len(dataFiles.TMCFPath) == 0 {
			return nil, fmt.Errorf("[Import group %s] TMCF not found in dataset %s", importGroupName, datasetName)
		}
		if len(dataFiles.CSVPaths) == 0 {
			return nil, fmt.Errorf("[Import group %s] csv files not found in dataset %s", importGroupName, datasetName)
		}
	}

	// IMPORTANT NOTE: importGroupName has a character constraint of 21 due to internal limitations.
	if len(importGroupName) > 20 {
		importGroupName = importGroupName[:20]
	}

	return &ImportGroupFiles{
		Source2Datasets:   Source2Datasets,
		Dataset2DataFiles: Dataset2DataFiles,
		ImportGroupName:   importGroupName,
	}, nil
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

// StripUntilRootDir trims one up folder of importRootDir from pathFromBucket.
// Example:
// StripUntilRootDir("some/path/to/root/data/source/dataset/a.tmcf", "some/path/to/root")
// -> "root/data/source/dataset/a.tmcf"
func StripUntilRootDir(pathFromBucket, importRootDir string) string {
	return strings.TrimPrefix(pathFromBucket, fmt.Sprintf("%s/", filepath.Dir(importRootDir)))
}

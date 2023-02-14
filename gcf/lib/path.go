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
	"errors"
	"fmt"
	"log"
	"path/filepath"
	"strings"
)

// DataFiles represent a logical unit of files for a single dataset.
type DataFiles struct {
	TMCFPath string
	CSVPaths []string
}

// ImportGroupFiles represent the collection of paths for a single import group.
type ImportGroupFiles struct {
	DataSource2DatasetNames map[string][]string
	DatasetName2DataFiles   map[string]DataFiles
	ImportGroupName         string
}

// CollectImportFiles takes a list of gcs file paths and construct ImportGroupFiles.
func CollectImportFiles(paths []string) (*ImportGroupFiles, error) {

	dataSource2DatasetNames := map[string][]string{}
	datasetName2DataFiles := map[string]DataFiles{}

	if len(paths) == 0 {
		return nil, errors.New("No path found in import group files")
	}
	// IMPORTANT NOTE: importGroupName has a character limit of 21
	importGroupName := strings.Split(paths[0], "/")[0]
	if len(importGroupName) > 20 {
		importGroupName = importGroupName[:20]
	}

	for _, path := range paths {
		// Path is expected to be like the following:
		// 	"demo/data/source2/solar/output.csv"
		// 	"demo/data/source1/smokepm/subfolder/data.tmcf"
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

		// Add to data source -> dataset name mapping only if the dataset has not been seen before.
		if _, datasetFound := datasetName2DataFiles[datasetName]; !datasetFound {
			dataSource2DatasetNames[dataSource] = append(dataSource2DatasetNames[dataSource], datasetName)
		}

		df := DataFiles{}
		if _, ok := datasetName2DataFiles[datasetName]; ok {
			df = datasetName2DataFiles[datasetName]
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
		datasetName2DataFiles[datasetName] = df
	}

	// Validation.
	for datasetName, dataFiles := range datasetName2DataFiles {
		if len(dataFiles.TMCFPath) == 0 {
			return nil, fmt.Errorf("[Import group %s] TMCF not found in dataset %s", importGroupName, datasetName)
		}
		if len(dataFiles.CSVPaths) == 0 {
			return nil, fmt.Errorf("[Import group %s] csv files not found in dataset %s", importGroupName, datasetName)
		}
	}

	return &ImportGroupFiles{
		DataSource2DatasetNames: dataSource2DatasetNames,
		DatasetName2DataFiles:   datasetName2DataFiles,
		ImportGroupName:         importGroupName,
	}, nil
}

func BigStorePath(bucket, path string) string {
	return filepath.Join("/bigstore", bucket, path)
}

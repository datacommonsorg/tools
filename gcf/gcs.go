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
package gcf

import (
	"context"
	"fmt"
	"log"
	"path/filepath"
	"strings"

	"cloud.google.com/go/storage"
	"google.golang.org/api/iterator"

	pb "github.com/datacommonsorg/tools/gcf/proto"
	"github.com/pkg/errors"
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

// pathToDataFolder is the "gs://"-prefixed folder that contains raw data.
// For the folder structure that is expected, please see,
// https://docs.datacommons.org/custom_dc/upload_data.html
func GenerateManifest(ctx context.Context, bucket, pathToDataFolder string) (*pb.DataCommonsManifest, error) {
	client, err := storage.NewClient(ctx)
	if err != nil {
		return nil, err
	}

	// IMPORTANT NOTE: importGroupName has a character limit of 21
	rootFolder := filepath.Base(filepath.Dir(strings.TrimSuffix(pathToDataFolder, "/")))
	if len(rootFolder) > 20 {
		rootFolder = rootFolder[:20]
	}
	importGroupName := rootFolder

	// Construct a list of Manifest imports and data sources as we
	// walk through the data folder in GCS.
	dataSourceParams := []*DataSourceParams{}
	importParams := []*ImportParams{}

	// Find all sources
	sources, err := FindFolders(ctx, client, bucket, pathToDataFolder)
	for _, source := range sources {

		sourceName := filepath.Base(strings.TrimSuffix(source, "/"))
		log.Printf("Found source: %s\n", sourceName)
		datasetNames := []string{}

		// Find file groups
		fileGroups, err := FindFolders(ctx, client, bucket, source)
		if err != nil {
			return nil, err
		}

		// Find all tmcf csvs in a file group
		for _, fileGroup := range fileGroups {

			datasetName := filepath.Base(strings.TrimSuffix(fileGroup, "/"))
			datasetNames = append(datasetNames, datasetName)
			log.Printf("Found dataset: %s\n", datasetName)

			// all subfolders are tmcf csv files.
			tmcfCSVs, err := FindFiles(ctx, client, bucket, fileGroup)
			if err != nil {
				return nil, err
			}

			var tmcfPath string
			csvPaths := []string{}
			for _, tmcfCSV := range tmcfCSVs {
				if filepath.Ext(tmcfCSV) == ".tmcf" {
					// There should only be 1 TMCF file
					if len(tmcfPath) > 0 {
						return nil, errors.Errorf("more than 1 tmcf file found in %s", fileGroup)
					}
					tmcfPath = BigStorePath(bucket, tmcfCSV)
					log.Printf("Found tmcf: %s\n", tmcfPath)
					continue
				}
				if filepath.Ext(tmcfCSV) == ".csv" {
					csvPath := BigStorePath(bucket, tmcfCSV)
					csvPaths = append(csvPaths, csvPath)
					log.Printf("Found csv: %s\n", csvPath)
					continue
				}
				// all other file types are ignored.
			}

			mcfProtoUrl := BigStorePath(bucket, fmt.Sprintf("%s%s", fileGroup, "graph.tfrecord@*.gz"))

			importParams = append(importParams, &ImportParams{
				ImportName:      datasetName, // Use datasetName for import name.
				ImportGroupName: importGroupName,
				DatasetName:     datasetName,
				DataSourceName:  sourceName,
				MCFProtoURL:     mcfProtoUrl,
				TMCFPath:        tmcfPath,
				CSVPaths:        csvPaths,
			})

		}

		dataSourceParams = append(dataSourceParams, &DataSourceParams{
			DataSourceName: sourceName,
			URL:            "https://datacommons.org/",
			DatasetNames:   datasetNames,
		})

	}

	manifestParams := &ManifestParams{
		ImportsParams:     importParams,
		DataSourcesParams: dataSourceParams,
		ImportGroupName:   importGroupName,
	}

	return manifestParams.ManifestProto(), nil
}

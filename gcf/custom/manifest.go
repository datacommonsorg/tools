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
	"path/filepath"
	"strings"

	"cloud.google.com/go/storage"
	pb "github.com/datacommonsorg/tools/gcf/proto"
	"github.com/pkg/errors"
	"google.golang.org/protobuf/proto"
)

// pathToDataFolder is the "gs://"-prefixed folder that contains raw data.
// For the folder structure that is expected, please see,
// https://docs.datacommons.org/custom_dc/upload_data.html
func GenerateManifest(ctx context.Context, bucket, pathToDataFolder string) (
	*pb.DataCommonsManifest, error,
) {
	client, err := storage.NewClient(ctx)
	if err != nil {
		return nil, err
	}

	// IMPORTANT NOTE: importGroupName has a character limit of 21
	rootFolder := filepath.Base(
		filepath.Dir(strings.TrimSuffix(pathToDataFolder, "/")))
	if len(rootFolder) > 20 {
		rootFolder = rootFolder[:20]
	}
	importGroupName := rootFolder

	// Construct a list of Manifest imports and data sources as we
	// walk through the data folder in GCS.
	datasetSources := []*pb.DataCommonsManifest_DatasetSource{}
	imports := []*pb.DataCommonsManifest_Import{}

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

			imports = append(imports, &pb.DataCommonsManifest_Import{
				ImportName:               proto.String(datasetName), // Use datasetName for import name.
				Category:                 pb.DataCommonsManifest_STATS.Enum(),
				ProvenanceUrl:            proto.String("https://datacommons.org/"), // Dummy URL
				McfProtoUrl:              []string{mcfProtoUrl},
				ImportGroups:             []string{importGroupName},
				ResolutionInfo:           &pb.ResolutionInfo{UsesIdResolver: proto.Bool(true)},
				DatasetName:              proto.String(datasetName),
				AutomatedMcfGenerationBy: proto.String(importGroupName),
				Table: []*pb.ExternalTable{
					{
						MappingPath: proto.String(tmcfPath),
						CsvPath:     csvPaths,
					},
				},
			})

		}

		ds := &pb.DataCommonsManifest_DatasetSource{
			Url:      proto.String("https://datacommons.org/"),
			Name:     proto.String(sourceName),
			Datasets: []*pb.DataCommonsManifest_DatasetInfo{},
		}
		for _, datasetName := range datasetNames {
			ds.Datasets = append(ds.Datasets, &pb.DataCommonsManifest_DatasetInfo{
				Name: proto.String(datasetName),
				Url:  ds.Url, // Dummy URL
			})
		}
		datasetSources = append(datasetSources, ds)
	}

	importGroups := []*pb.DataCommonsManifest_ImportGroup{
		{
			Name:        proto.String(importGroupName),
			IsCustomDc:  proto.Bool(true),
			Description: proto.String("Custom DC import group"),
		},
	}

	return &pb.DataCommonsManifest{
		Import:        imports,
		DatasetSource: datasetSources,
		ImportGroups:  importGroups,
	}, nil
}

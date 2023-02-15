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
	"log"
	"path/filepath"
	"strings"

	"cloud.google.com/go/storage"
	"github.com/datacommonsorg/tools/gcf/lib"
	pb "github.com/datacommonsorg/tools/gcf/proto"
	"github.com/pkg/errors"
	"google.golang.org/api/iterator"
	"google.golang.org/protobuf/proto"
)

func importFilesToManifest(
	importGroupFiles *lib.ImportGroupFiles,
	bucket string,
) (*pb.DataCommonsManifest, error) {
	datasetImports := []*pb.DataCommonsManifest_Import{}
	datasetSources := []*pb.DataCommonsManifest_DatasetSource{}

	for dataSource, datasetNames := range importGroupFiles.Source2Datasets {
		ds := &pb.DataCommonsManifest_DatasetSource{
			Url:  proto.String("https://datacommons.org/"),
			Name: proto.String(dataSource),
		}

		ds.Datasets = make([]*pb.DataCommonsManifest_DatasetInfo, len(datasetNames))
		for i, datasetName := range datasetNames {
			ds.Datasets[i] = &pb.DataCommonsManifest_DatasetInfo{
				Name: proto.String(datasetName),
				Url:  ds.Url, // Dummy URL
			}

			for datasetName, dataFiles := range importGroupFiles.Dataset2DataFiles {
				// Note: mcf proto url must be under bigstore_data_directory.
				tmcfDir := filepath.Dir(dataFiles.TMCFPath)
				mcfProtoUrl := lib.BigStorePath(bucket, filepath.Join(tmcfDir, "graph.tfrecord@*.gz"))

				var tables []*pb.ExternalTable
				tables = append(tables, &pb.ExternalTable{
					MappingPath: proto.String(dataFiles.TMCFPath),
					CsvPath:     dataFiles.CSVPaths,
				})

				datasetImports = append(datasetImports, &pb.DataCommonsManifest_Import{
					ImportName:               proto.String(datasetName), // Use datasetName for import name.
					Category:                 pb.DataCommonsManifest_STATS.Enum(),
					ProvenanceUrl:            proto.String("https://datacommons.org/"), // Dummy URL
					McfProtoUrl:              []string{mcfProtoUrl},
					ImportGroups:             []string{importGroupFiles.ImportGroupName},
					ResolutionInfo:           &pb.ResolutionInfo{UsesIdResolver: proto.Bool(true)},
					DatasetName:              proto.String(datasetName),
					AutomatedMcfGenerationBy: proto.String(importGroupFiles.ImportGroupName),
					Table:                    tables,
				})
			}
		}
		datasetSources = append(datasetSources, ds)
	}

	importGroups := []*pb.DataCommonsManifest_ImportGroup{
		{
			Name:        proto.String(importGroupFiles.ImportGroupName),
			IsCustomDc:  proto.Bool(true),
			Description: proto.String("Custom DC import group"),
		},
	}

	return &pb.DataCommonsManifest{
		Import:        datasetImports,
		DatasetSource: datasetSources,
		ImportGroups:  importGroups,
	}, nil
}

// pathToDataFolder is the "gs://"-prefixed folder that contains raw data.
// For the folder structure that is expected, please see,
// https://docs.datacommons.org/custom_dc/upload_data.html
func GenerateManifest(
	ctx context.Context,
	bucket, importRootDir string,
) (*pb.DataCommonsManifest, error) {
	client, err := storage.NewClient(ctx)
	if err != nil {
		return nil, err
	}

	it := client.Bucket(bucket).Objects(ctx, &storage.Query{Prefix: importRootDir})
	paths := []string{}
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
		log.Printf("[Import root %s] Found %s", importRootDir, attrs.Name)
		paths = append(paths, attrs.Name)
	}

	importGroupFiles, err := lib.CollectImportFiles(paths)
	if err != nil {
		return nil, errors.Wrap(err, "Found errors with files in data folder")
	}
	return importFilesToManifest(importGroupFiles, bucket)
}

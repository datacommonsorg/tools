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
	"path"
	"path/filepath"
	"sort"

	pb "github.com/datacommonsorg/tools/gcf/proto"
	"google.golang.org/protobuf/proto"
)

func computeTable(bucket, root, im, tab string, table *Table) *pb.ExternalTable {
	bigstoreTmcf := filepath.Join("/bigstore", bucket, root, "data", im, tab, table.tmcf)
	bigstoreCsv := []string{}
	for _, csv := range table.csv {
		bigstoreCsv = append(
			bigstoreCsv,
			filepath.Join("/bigstore", bucket, root, "data", im, tab, csv),
		)
	}
	return &pb.ExternalTable{
		MappingPath: proto.String(bigstoreTmcf),
		CsvPath:     bigstoreCsv,
	}
}

func ComputeManifest(
	bucket string,
	layout *Layout,
) (*pb.DataCommonsManifest, error) {
	root := layout.root
	importGroup := path.Base(root)
	// IMPORTANT NOTE:
	// importGroup has a character constraint of 21 due to internal limitations.
	if len(importGroup) > 20 {
		importGroup = importGroup[:20]
	}

	manifest := &pb.DataCommonsManifest{
		Import:        []*pb.DataCommonsManifest_Import{},
		DatasetSource: []*pb.DataCommonsManifest_DatasetSource{},
		ImportGroups: []*pb.DataCommonsManifest_ImportGroup{
			{
				Name:        proto.String(importGroup),
				IsCustomDc:  proto.Bool(true),
				Description: proto.String("Custom DC import group"),
			},
		},
	}
	// TODO: update sources data based on provenance.json
	for im, importFolder := range layout.imports {
		manifest.DatasetSource = append(
			manifest.DatasetSource,
			&pb.DataCommonsManifest_DatasetSource{
				Url:  proto.String("https://datacommons.org/"),
				Name: proto.String(im),
				Datasets: []*pb.DataCommonsManifest_DatasetInfo{
					{
						Name: proto.String(im),
						Url:  proto.String("https://datacommons.org/"),
					},
				},
			})
		manifestImport := &pb.DataCommonsManifest_Import{
			ImportName:               proto.String(im), // Use datasetName for import name.
			Category:                 pb.DataCommonsManifest_STATS.Enum(),
			ProvenanceUrl:            proto.String("https://datacommons.org/"), // Dummy URL
			McfProtoUrl:              []string{},
			ImportGroups:             []string{importGroup},
			ResolutionInfo:           &pb.ResolutionInfo{UsesIdResolver: proto.Bool(true)},
			DatasetName:              proto.String(im),
			AutomatedMcfGenerationBy: proto.String(importGroup),
			Table:                    []*pb.ExternalTable{},
		}
		tabList := []string{}
		for tab := range importFolder.tables {
			tabList = append(tabList, tab)
		}
		sort.Strings(tabList)
		for _, tab := range tabList {
			tableFolder := importFolder.tables[tab]
			if tableFolder == nil {
				continue
			}
			manifestImport.Table = append(
				manifestImport.Table,
				computeTable(bucket, root, im, tab, tableFolder),
			)
			sort.SliceStable(manifestImport.Table, func(i, j int) bool {
				return *(manifestImport.Table[i].MappingPath) < *(manifestImport.Table[j].MappingPath)
			})
			manifestImport.McfProtoUrl = append(
				manifestImport.McfProtoUrl,
				filepath.Join("/bigstore", bucket, root, "data", im, tab, "graph.tfrecord@*.gz"),
			)
		}
		manifest.Import = append(manifest.Import, manifestImport)
		sort.SliceStable(manifest.Import, func(i, j int) bool {
			return *(manifest.Import[i].ImportName) < *(manifest.Import[j].ImportName)
		})
	}
	return manifest, nil
}

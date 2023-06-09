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
	"path"
	"path/filepath"
	"sort"

	pb "github.com/datacommonsorg/tools/gcf/proto"
	"google.golang.org/protobuf/encoding/protojson"
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

func computeDataMCF(bucket, root, im, tab string, mcf []string) []string {
	bigstoreMCFs := make([]string, len(mcf))
	for i, m := range mcf {
		bigstoreMCFs[i] = filepath.Join("/bigstore", bucket, root, "data", im, tab, m)
	}
	return bigstoreMCFs
}

func computeSource(
	ctx context.Context, reader Reader, bucket, root, provFile string,
) (
	*pb.DataCommonsManifest_DatasetSource, error,
) {
	// Populate data source that should be specified at import group level.
	if provFile != "" {
		provJSON, err := reader.ReadObject(
			ctx, bucket, path.Join(root, "data", provFile))
		if err != nil {
			return nil, err
		}
		datasetSource := &pb.DataCommonsManifest_DatasetSource{}
		err = protojson.Unmarshal(provJSON, datasetSource)
		if err != nil {
			return nil, err
		}
		return datasetSource, nil
	}

	return &pb.DataCommonsManifest_DatasetSource{
		Url:  proto.String("https://datacommons.org"),
		Name: proto.String(path.Base(root)),
	}, nil
}

func computeDataset(
	ctx context.Context, reader Reader,
	bucket, root, im, provFile, sourceUrl string,
) (
	*pb.DataCommonsManifest_DatasetInfo, error,
) {
	// Populate data source that should be specified at import group level.
	if provFile != "" {
		provJSON, err := reader.ReadObject(
			ctx, bucket, path.Join(root, "data", im, provFile))
		if err != nil {
			return nil, err
		}
		dataset := &pb.DataCommonsManifest_DatasetInfo{}
		err = protojson.Unmarshal(provJSON, dataset)
		if err != nil {
			return nil, err
		}
		return dataset, nil
	}
	return &pb.DataCommonsManifest_DatasetInfo{
		Url:  proto.String(sourceUrl),
		Name: proto.String(im),
	}, nil
}

func ComputeManifest(
	ctx context.Context,
	reader Reader,
	bucket string,
	layout *Layout,
) (*pb.DataCommonsManifest, error) {
	root := layout.root
	importGroup := path.Base(root)
	// IMPORTANT NOTE:
	// importGroup has a character constraint of 20 due to internal limitations.
	if len(importGroup) > 20 {
		importGroup = importGroup[:20]
	}

	// Init manifest
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
	source, err := computeSource(ctx, reader, bucket, root, layout.prov)
	if err != nil {
		return nil, err
	}
	manifest.DatasetSource = []*pb.DataCommonsManifest_DatasetSource{source}

	schemaImportMCFUrls := []string{}
	imList := []string{}
	for im := range layout.imports {
		imList = append(imList, im)
	}
	sort.Strings(imList)

	// Process each import group
	for _, im := range imList {
		importFolder := layout.imports[im]
		// Compute dataset
		dataset, err := computeDataset(
			ctx, reader, bucket, root, im, layout.imports[im].prov, *source.Url)
		if err != nil {
			return nil, err
		}
		manifest.DatasetSource[0].Datasets = append(
			manifest.DatasetSource[0].Datasets,
			dataset,
		)
		// Gather all the schema mcf in each imports into a schema import
		if len(importFolder.schemas) > 0 {
			schemaImportMCFUrls = append(
				schemaImportMCFUrls,
				filepath.Join("/bigstore", bucket, root, "data", im, "*.mcf*"))
		}
		// Construct stat import
		statImport := &pb.DataCommonsManifest_Import{
			ImportName:     proto.String(*dataset.Name),
			Category:       pb.DataCommonsManifest_STATS.Enum(),
			ProvenanceUrl:  dataset.Url,
			McfProtoUrl:    []string{},
			ImportGroups:   []string{importGroup},
			ResolutionInfo: &pb.ResolutionInfo{UsesIdResolver: proto.Bool(true)},
			DatasetName:    proto.String(*dataset.Name),
			Table:          []*pb.ExternalTable{},
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
			if len(tableFolder.tmcf) > 0 && len(tableFolder.csv) > 0 {
				// Only set automated_mcf_generation_by for tmcf/csv imports.
				// Setting this flag for mcf based imports will error out.
				statImport.AutomatedMcfGenerationBy = proto.String(importGroup)
				statImport.Table = append(
					statImport.Table,
					computeTable(bucket, root, im, tab, tableFolder),
				)
				// Only tmcf/csv imports have tf record generated.
				statImport.McfProtoUrl = append(
					statImport.McfProtoUrl,
					filepath.Join("/bigstore", bucket, root, "data", im, tab, "graph.tfrecord@*.gz"),
				)
			}
			if len(tableFolder.mcf) > 0 {
				statImport.McfUrl = computeDataMCF(bucket, root, im, tab, tableFolder.mcf)
			}
		}
		// Stat import entry is added if there is data files.
		if len(statImport.McfProtoUrl) > 0 {
			manifest.Import = append(manifest.Import, statImport)
		}
	}

	// Schema import entry is added if at least 1 dataset has schemas.
	if len(schemaImportMCFUrls) > 0 {
		// Schema import
		schemaImport := &pb.DataCommonsManifest_Import{
			ImportName:    proto.String("schema"),
			Category:      pb.DataCommonsManifest_SCHEMA.Enum(),
			ProvenanceUrl: source.Url,
			McfUrl:        schemaImportMCFUrls,
			ImportGroups:  []string{importGroup},
			DatasetName:   proto.String(importGroup),
		}
		manifest.Import = append(manifest.Import, schemaImport)
	}
	return manifest, nil
}

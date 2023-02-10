package gcf

import (
	pb "github.com/datacommonsorg/tools/bigtable_automation/gcf/proto"
	"google.golang.org/protobuf/proto"
)

type ImportParams struct {
	ImportName      string
	ImportGroupName string
	DatasetName     string
	DataSourceName  string
	MCFProtoURL     string
	TMCFPath        string
	CSVPaths        []string
}

type DataSourceParams struct {
	DataSourceName string
	URL            string
	DatasetNames   []string
}

type ManifestParams struct {
	ImportsParams     []*ImportParams
	DataSourcesParams []*DataSourceParams
	ImportGroupName   string
}

func (ip *ImportParams) ImportProto() *pb.DataCommonsManifest_Import {
	return &pb.DataCommonsManifest_Import{
		ImportName:               proto.String(ip.ImportName),
		Category:                 pb.DataCommonsManifest_STATS.Enum(),
		ProvenanceUrl:            proto.String("https://datacommons.org/"), // Dummy URL
		McfProtoUrl:              []string{ip.MCFProtoURL},
		ImportGroups:             []string{ip.ImportGroupName},
		ResolutionInfo:           &pb.ResolutionInfo{UsesIdResolver: proto.Bool(true)},
		DatasetName:              proto.String(ip.DatasetName),
		AutomatedMcfGenerationBy: proto.String(ip.ImportGroupName),
		Table: []*pb.ExternalTable{
			&pb.ExternalTable{
				MappingPath: proto.String(ip.TMCFPath),
				CsvPath:     ip.CSVPaths,
			},
		},
	}
}

func (dsp *DataSourceParams) DataSourceProto() *pb.DataCommonsManifest_DatasetSource {
	datasets := make([]*pb.DataCommonsManifest_DatasetInfo, len(dsp.DatasetNames))
	for i, datasetName := range dsp.DatasetNames {
		datasets[i] = &pb.DataCommonsManifest_DatasetInfo{
			Name: proto.String(datasetName),
			// Dummy URL
			Url: proto.String(dsp.URL),
		}
	}

	return &pb.DataCommonsManifest_DatasetSource{
		Name: proto.String(dsp.DataSourceName),
		// Dummy URL
		Url:      proto.String(dsp.URL),
		Datasets: datasets,
	}
}

func NewManifestParams() *ManifestParams {
	manifestParams := &ManifestParams{}
	return manifestParams
}

func (mp *ManifestParams) ImportsProto() []*pb.DataCommonsManifest_Import {
	importsProto := make([]*pb.DataCommonsManifest_Import, len(mp.ImportsParams))
	for i, ip := range mp.ImportsParams {
		importsProto[i] = ip.ImportProto()
	}
	return importsProto
}

func (mp *ManifestParams) DataSourcesProto() []*pb.DataCommonsManifest_DatasetSource {
	dataSourcesProto := make([]*pb.DataCommonsManifest_DatasetSource, len(mp.DataSourcesParams))
	for i, dsp := range mp.DataSourcesParams {
		dataSourcesProto[i] = dsp.DataSourceProto()
	}
	return dataSourcesProto
}

func (mp *ManifestParams) ImportGroupsProto() []*pb.DataCommonsManifest_ImportGroup {
	return []*pb.DataCommonsManifest_ImportGroup{
		&pb.DataCommonsManifest_ImportGroup{
			Name:        proto.String(mp.ImportGroupName),
			IsCustomDc:  proto.Bool(true),
			Description: proto.String("Custom DC import group"),
		},
	}
}

func (mp *ManifestParams) ManifestProto() *pb.DataCommonsManifest {
	return &pb.DataCommonsManifest{
		Import:        mp.ImportsProto(),
		DatasetSource: mp.DataSourcesProto(),
		ImportGroups:  mp.ImportGroupsProto(),
	}
}

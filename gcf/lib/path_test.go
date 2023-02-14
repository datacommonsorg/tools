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
//
//	How to run:
//	go test path.go path_test.go
package lib

import (
	"testing"

	"github.com/go-test/deep"
)

func TestCollectImportFiles(t *testing.T) {
	for _, c := range []struct {
		title   string
		input   []string
		want    *ImportGroupFiles
		errWant string
	}{
		{
			"Basic test",
			[]string{
				"demo/data/source1/smokepm/data.tmcf",
				"demo/data/source1/smokepm/output.csv",
				"demo/data/source2/solar/data.tmcf",
				"demo/data/source2/solar/output.csv",
			},
			&ImportGroupFiles{
				Source2Datasets: map[string][]string{
					"source1": {"smokepm"},
					"source2": {"solar"},
				},
				Dataset2DataFiles: map[string]DataFiles{
					"smokepm": {
						TMCFPath: "demo/data/source1/smokepm/data.tmcf",
						CSVPaths: []string{"demo/data/source1/smokepm/output.csv"},
					},
					"solar": {
						TMCFPath: "demo/data/source2/solar/data.tmcf",
						CSVPaths: []string{"demo/data/source2/solar/output.csv"},
					},
				},
				ImportGroupName: "demo",
			},
			"",
		},
		{
			"Multiple tmcf should fail",
			[]string{
				"demo/data/source1/smokepm/data.tmcf",
				"demo/data/source1/smokepm/bad.tmcf",
				"demo/data/source1/smokepm/output.csv",
			},
			nil,
			"[Import group demo] Multiple tmcf found under dataset smokepm",
		},
		{
			"Missing tmcf",
			[]string{
				"demo/data/source1/smokepm/output.csv",
			},
			nil,
			"[Import group demo] TMCF not found in dataset smokepm",
		},
		{
			"Missing csvs",
			[]string{
				"demo/data/source1/smokepm/data.tmcf",
			},
			nil,
			"[Import group demo] csv files not found in dataset smokepm",
		},
		{
			"Extra files should be ignored",
			[]string{
				"demo/data/source1/smokepm/data.tmcf",
				"demo/data/source1/smokepm/output.csv",
				"demo/data/source1/random.csv",
				"demo/not_data/source1/somkepm/other.csv",
			},
			&ImportGroupFiles{
				Source2Datasets: map[string][]string{
					"source1": {"smokepm"},
				},
				Dataset2DataFiles: map[string]DataFiles{
					"smokepm": {
						TMCFPath: "demo/data/source1/smokepm/data.tmcf",
						CSVPaths: []string{"demo/data/source1/smokepm/output.csv"},
					},
				},
				ImportGroupName: "demo",
			},
			"",
		},
		{
			"Long imort group names should be truncated",
			[]string{
				"somethingreallyreallylong/data/source1/smokepm/data.tmcf",
				"somethingreallyreallylong/data/source1/smokepm/output.csv",
			},
			&ImportGroupFiles{
				Source2Datasets: map[string][]string{
					"source1": {"smokepm"},
				},
				Dataset2DataFiles: map[string]DataFiles{
					"smokepm": {
						TMCFPath: "somethingreallyreallylong/data/source1/smokepm/data.tmcf",
						CSVPaths: []string{"somethingreallyreallylong/data/source1/smokepm/output.csv"},
					},
				},
				ImportGroupName: "somethingreallyreall",
			},
			"",
		},
	} {
		got, err := CollectImportFiles(c.input)
		if len(c.errWant) == 0 && err != nil {
			t.Errorf("[%s] CollectImportFiles unexpectedly errored out: %v", c.title, err)
			continue
		} else if len(c.errWant) > 0 && c.errWant != err.Error() {
			t.Errorf("[%s] Expected err msg \"%s\", got \"%s\"", c.title, c.errWant, err.Error())
			continue
		}

		if diff := deep.Equal(got, c.want); diff != nil {
			t.Errorf("[%s] ImportFiles got diff %v", c.title, diff)
		}
	}
}

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
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
)

func TestLayout(t *testing.T) {
	for _, c := range []struct {
		title   string
		RootDir string
		input   []string
		want    *Layout
		errWant string
	}{
		{
			"Basic test",
			"demo",
			[]string{
				"demo/data/",
				"demo/data/source1/",
				"demo/data/source1/schema.mcf",
				"demo/data/source1/empty/",
				"demo/data/source1/smokepm/",
				"demo/data/source1/smokepm/data.tmcf",
				"demo/data/source1/smokepm/graph.tfrecord.tz",
				"demo/data/source1/smokepm/output.csv",
				"demo/data/source2/",
				"demo/data/source2/schema.mcf",
				"demo/data/source2/solar/",
				"demo/data/source2/solar/data.tmcf",
				"demo/data/source1/solar/graph.tfrecord.tz",
				"demo/data/source2/solar/output.csv",
			},
			&Layout{
				root: "demo",
				imports: map[string]*Import{
					"source1": {
						mcf: "schema.mcf",
						tables: map[string]*Table{
							"empty": nil,
							"smokepm": {
								tmcf: "data.tmcf",
								csv:  []string{"output.csv"},
							},
						},
					},
					"source2": {
						mcf: "schema.mcf",
						tables: map[string]*Table{
							"solar": {
								tmcf: "data.tmcf",
								csv:  []string{"output.csv"},
							},
						},
					},
				},
			},
			"",
		},
		{
			"No folders",
			"imports/root",
			[]string{
				"imports/root/data/california_distribution_grid/dataset1/california_distribution_lines.tmcf",
				"imports/root/data/california_distribution_grid/dataset1/california_distribution_lines.csv",
			},
			&Layout{
				root: "imports/root",
				imports: map[string]*Import{
					"california_distribution_grid": {
						tables: map[string]*Table{
							"empty": nil,
							"dataset1": {
								tmcf: "california_distribution_lines.tmcf",
								csv:  []string{"california_distribution_lines.csv"},
							},
						},
					},
				},
			},
			"",
		},
		{
			"Multiple tmcf should fail",
			"demo",
			[]string{
				"demo/data/",
				"demo/data/source1/",
				"demo/data/source1/smokepm/",
				"demo/data/source1/smokepm/data.tmcf",
				"demo/data/source1/smokepm/bad.tmcf",
				"demo/data/source1/smokepm/output.csv",
			},
			nil,
			"[Multiple TMCF] source1/smokepm",
		},
		{
			"Missing tmcf",
			"demo",
			[]string{
				"demo/data/",
				"demo/data/source1/",
				"demo/data/source1/smokepm/",
				"demo/data/source1/smokepm/output.csv",
			},
			&Layout{
				root: "demo",
				imports: map[string]*Import{
					"source1": {
						tables: map[string]*Table{
							"smokepm": nil,
						},
					},
				},
			},
			"",
		},
		{
			"Missing csv",
			"demo",
			[]string{
				"demo/data/",
				"demo/data/source1/",
				"demo/data/source1/smokepm/",
				"demo/data/source1/smokepm/schema.tmcf",
			},
			&Layout{
				root: "demo",
				imports: map[string]*Import{
					"source1": {
						tables: map[string]*Table{
							"smokepm": nil,
						},
					},
				},
			},
			"",
		},
		{
			"Extra files should be ignored",
			"some/dir/root",
			[]string{
				"some/dir/root/data/",
				"some/dir/root/data/source1/",
				"some/dir/root/data/source1/random.csv",
				"some/dir/root/data/source1/smokepm/",
				"some/dir/root/data/source1/smokepm/data.tmcf",
				"some/dir/root/data/source1/smokepm/output.csv",
			},
			&Layout{
				root: "some/dir/root",
				imports: map[string]*Import{
					"source1": {
						tables: map[string]*Table{
							"smokepm": {
								tmcf: "data.tmcf",
								csv:  []string{"output.csv"},
							},
						},
					},
				},
			},
			"",
		},
	} {
		got, err := BuildLayout(c.RootDir, c.input)
		if err != nil && c.errWant == "" {
			t.Errorf("[%s] Build() unexpectedly errored out: %v", c.title, err)
			continue
		}
		if c.errWant != "" && c.errWant != err.Error() {
			t.Errorf("[%s] Expected err msg \"%s\", got \"%s\"", c.title, c.errWant, err.Error())
			continue
		}
		if diff := cmp.Diff(got, c.want, cmpopts.IgnoreUnexported(Layout{})); diff != "" {
			t.Errorf("[%s] Build() got diff %v", c.title, diff)
		}
	}
}

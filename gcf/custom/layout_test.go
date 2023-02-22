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
				"demo/data/provenance.json",
				"demo/data/smokepm/",
				"demo/data/smokepm/schema.mcf",
				"demo/data/smokepm/empty/",
				"demo/data/smokepm/table1/",
				"demo/data/smokepm/provenance.json",
				"demo/data/smokepm/table1/data.tmcf",
				"demo/data/smokepm/table1/graph.tfrecord.tz",
				"demo/data/smokepm/table1/output.csv",
				"demo/data/solar/",
				"demo/data/solar/schema.mcf",
				"demo/data/solar/table1/",
				"demo/data/solar/table1/data.tmcf",
				"demo/data/smokepm/table1/graph.tfrecord.tz",
				"demo/data/solar/table1/output.csv",
			},
			&Layout{
				root: "demo",
				prov: "provenance.json",
				imports: map[string]*Import{
					"smokepm": {
						schema: "schema.mcf",
						prov:   "provenance.json",
						tables: map[string]*Table{
							"table1": {
								tmcf: "data.tmcf",
								csv:  []string{"output.csv"},
							},
						},
					},
					"solar": {
						schema: "schema.mcf",
						tables: map[string]*Table{
							"table1": {
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
				"demo/data/smokepm/",
				"demo/data/smokepm/table1/",
				"demo/data/smokepm/table1/data.tmcf",
				"demo/data/smokepm/table1/bad.tmcf",
				"demo/data/smokepm/table1/output.csv",
			},
			nil,
			"[Multiple TMCF] smokepm/table1",
		},
		{
			"Missing tmcf",
			"demo",
			[]string{
				"demo/data/",
				"demo/data/smokepm/",
				"demo/data/smokepm/table1/",
				"demo/data/smokepm/table1/output.csv",
			},
			&Layout{
				root: "demo",
				imports: map[string]*Import{
					"smokepm": {
						tables: map[string]*Table{
							"table1": nil,
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
				"demo/data/smokepm/",
				"demo/data/smokepm/table1/",
				"demo/data/smokepm/table1/schema.tmcf",
			},
			&Layout{
				root: "demo",
				imports: map[string]*Import{
					"smokepm": {
						tables: map[string]*Table{
							"table1": nil,
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
				"some/dir/root/data/smokepm/",
				"some/dir/root/data/smokepm/random.csv",
				"some/dir/root/data/smokepm/table1/",
				"some/dir/root/data/smokepm/table1/data.tmcf",
				"some/dir/root/data/smokepm/table1/output.csv",
			},
			&Layout{
				root: "some/dir/root",
				imports: map[string]*Import{
					"smokepm": {
						tables: map[string]*Table{
							"table1": {
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
			"Data MCFs",
			"demo",
			[]string{
				"demo/data/smokepm/table1/data1.mcf",
				"demo/data/smokepm/table1/data2.mcf",
			},
			&Layout{
				root: "demo",
				imports: map[string]*Import{
					"smokepm": {
						tables: map[string]*Table{
							"table1": {
								mcf: []string{"data1.mcf", "data2.mcf"},
							},
						},
					},
				},
			},
			"",
		},
		{
			"Globbed MCFs",
			"demo",
			[]string{
				"demo/data/smokepm/table1/data1.mcf",
				"demo/data/smokepm/table1/data2.mcf",
				"demo/data/smokepm/table1/data3.mcf",
				"demo/data/smokepm/table1/data4.mcf",
				"demo/data/smokepm/table1/data5.mcf",
				"demo/data/smokepm/table1/data6.mcf",
			},
			&Layout{
				root: "demo",
				imports: map[string]*Import{
					"smokepm": {
						tables: map[string]*Table{
							"table1": {
								mcf: []string{"*.mcf"},
							},
						},
					},
				},
			},
			"",
		},
		{
			"No mixing of TMCF/CSV and MCF",
			"demo",
			[]string{
				"demo/data/smokepm/table1/data.mcf",
				"demo/data/smokepm/table1/data.tmcf",
				"demo/data/smokepm/table1/data.csv",
			},
			nil,
			"[Datasource smokepm, Dataset table1] Mix of TMCF/CSV and data MCF are not supported",
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
		if diff := cmp.Diff(
			got,
			c.want,
			cmp.AllowUnexported(Layout{}, Import{}, Table{}),
		); diff != "" {
			t.Errorf("[%s] Build() got diff %v", c.title, diff)
		}
	}
}

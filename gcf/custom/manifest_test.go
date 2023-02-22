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
	"os"
	"path"
	"runtime"
	"testing"

	pb "github.com/datacommonsorg/tools/gcf/proto"
	"github.com/google/go-cmp/cmp"
	"google.golang.org/protobuf/encoding/prototext"
	"google.golang.org/protobuf/testing/protocmp"
)

func TestComputeManifest(t *testing.T) {
	for _, c := range []struct {
		bucket     string
		input      *Layout
		goldenFile string
	}{
		{
			"test-bucket",
			&Layout{
				root: "demo",
				imports: map[string]*Import{
					"import1": {
						schema: "schema.mcf",
						tables: map[string]*Table{
							"empty": nil,
							"smokepm": {
								tmcf: "data.tmcf",
								csv:  []string{"1.csv", "2.csv"},
							},
							"ocean": {
								tmcf: "sea.tmcf",
								csv:  []string{"river.csv", "lake.csv"},
							},
						},
					},
					"import2": {
						schema: "schema.mcf",
						tables: map[string]*Table{
							"solar": {
								tmcf: "data.tmcf",
								csv:  []string{"output.csv"},
							},
						},
					},
				},
			},
			"golden.textproto",
		},
		{
			"test-bucket",
			&Layout{
				root: "schemaless",
				imports: map[string]*Import{
					"import1": {
						tables: map[string]*Table{
							"empty": nil,
							"smokepm": {
								tmcf: "data.tmcf",
								csv:  []string{"1.csv", "2.csv"},
							},
							"ocean": {
								tmcf: "sea.tmcf",
								csv:  []string{"river.csv", "lake.csv"},
							},
						},
					},
				},
			},
			"schemaless.textproto",
		},
		{
			"test-bucket",
			&Layout{
				root: "datamcf",
				imports: map[string]*Import{
					"import1": {
						tables: map[string]*Table{
							"empty": nil,
							"smokepm": {
								mcf: []string{"1.mcf", "2.mcf"},
							},
						},
					},
				},
			},
			"datamcf.textproto",
		},
	} {
		_, filename, _, _ := runtime.Caller(0)
		testDataDir := path.Join(path.Dir(filename), "test_data")
		bytes, err := os.ReadFile(path.Join(testDataDir, c.goldenFile))
		if err != nil {
			t.Errorf("Error read golden file %v", err)
			continue
		}
		want := pb.DataCommonsManifest{}
		err = prototext.Unmarshal(bytes, &want)
		if err != nil {
			t.Errorf("Error unmarshal golden file %v", err)
			continue
		}
		got, err := ComputeManifest(c.bucket, c.input)
		if err != nil {
			t.Errorf("ComputeManifest() got err: %v", err)
			continue
		}
		if diff := cmp.Diff(got, &want, protocmp.Transform()); diff != "" {
			t.Errorf("ComputeManifest() got diff %v", diff)
		}
	}
}

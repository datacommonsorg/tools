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
	"fmt"
	"log"
	"strings"
)

const provFile = "provenance.json"

// Only one of (mcf, (tmcf, csv)) should be set.
type Table struct {
	tmcf string
	csv  []string
	mcf  []string
}

type Import struct {
	schemas []string
	prov    string
	tables  map[string]*Table
}

type Layout struct {
	root    string
	prov    string
	imports map[string]*Import
}

func logging(msg string, parts []string) {
	log.Printf("[%s]: %s", msg, strings.Join(parts, "/"))
}

// objectBody get body parts of an object by removing root and "data"
func objectBody(root, object string) []string {
	body := strings.TrimPrefix(object, root+"/data")
	body = strings.Trim(body, "/")
	return strings.Split(body, "/")
}

func BuildLayout(root string, objects []string) (*Layout, error) {
	layout := &Layout{
		root:    root,
		imports: map[string]*Import{},
	}
	// object is in the form of "{root}/data/..."
	// Trim out {root} and "data", then split the remainder (body) part by "/"
	files := [][]string{}
	for _, o := range objects {
		if strings.HasSuffix(o, "/") {
			continue
		}
		files = append(files, objectBody(root, o))
	}
	// Put files under each Import
	for _, parts := range files {
		if len(parts) == 1 {
			if parts[0] == provFile {
				layout.prov = provFile
				logging("Add Provenance", parts)
			}
			logging("Ignore file", parts)
			continue
		}
		im := parts[0]
		if _, imExists := layout.imports[im]; !imExists {
			layout.imports[im] = &Import{
				tables: map[string]*Table{},
			}
		}

		// <import>/schema.mcf, <import>/provenance.json
		if len(parts) == 2 {
			fileName := parts[1]
			// Only .mcf and provenance.json file can be directly under an import folder
			// mcf files may be sharded, hence "Contains" as opposed to "HasSuffix"
			if strings.Contains(fileName, ".mcf") {
				layout.imports[im].schemas = append(layout.imports[im].schemas, parts[1])
				logging("Add Schema MCF", parts)
			} else if fileName == provFile {
				layout.imports[im].prov = provFile
				logging("Add Provenance", parts)
			} else {
				logging("Ignore file", parts)
			}
			continue
		}
		// <import>/<table>/stat.csv
		// <import>/<table>/data.tmcf
		if len(parts) == 3 {
			tab := parts[1]
			if _, tabExists := layout.imports[im].tables[tab]; !tabExists {
				layout.imports[im].tables[tab] = &Table{}
			}

			fileName := parts[2]
			tables := layout.imports[im].tables
			if strings.HasSuffix(fileName, ".tmcf") {
				if tables[tab].tmcf != "" {
					return nil, fmt.Errorf(
						"[Multiple TMCF] %s", strings.Join(parts[0:2], "/"))
				}
				tables[tab].tmcf = fileName
				logging("Add TMCF", parts)
			} else if strings.HasSuffix(fileName, ".csv") {
				tables[tab].csv = append(tables[tab].csv, fileName)
				logging("Add CSV", parts)
			} else if strings.HasSuffix(fileName, ".mcf") {
				tables[tab].mcf = append(tables[tab].mcf, fileName)
				logging("Add data MCF", parts)
			} else {
				logging("Ignore file", parts)
			}
			continue
		}
		logging("Ignore file", parts)
	}

	// Post processing after iterating through data files.
	for im, importFolders := range layout.imports {
		for tab, tableFolders := range importFolders.tables {
			hasTMCFCSV := len(tableFolders.tmcf) > 0 && len(tableFolders.csv) > 0
			hasDataMCF := len(tableFolders.mcf) > 0
			// Validate that only one of TMCF/CSV, data MCFs are set.
			if hasTMCFCSV && hasDataMCF {
				return nil, fmt.Errorf("[Datasource %s, Dataset %s] Mix of TMCF/CSV and data MCF are not supported", im, tab)
			}

			// Prune shards into glob patterns to prevent large config files.
			if hasTMCFCSV {
				if len(tableFolders.csv) > 5 {
					tableFolders.csv = []string{"*.csv"}
				}
				continue
			}

			if hasDataMCF {
				if len(tableFolders.mcf) > 5 {
					tableFolders.mcf = []string{"*.mcf"}
				}
				continue
			}

			// Trim invalid folders with either no TMCF and CSV, or no data MCFs.
			layout.imports[im].tables[tab] = nil
			logging("Trim folder", []string{root, "data", im, tab})
		}
	}
	return layout, nil
}

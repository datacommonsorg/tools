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
	"sort"
	"strings"
)

type Table struct {
	tmcf string
	csv  []string
}

type Import struct {
	mcf    string
	tables map[string]*Table
}

type Layout struct {
	root    string
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
	// object is in the form of "{root}/data/..."
	// Trim out {root} and "data", then split the remainder (body) part by "/"
	folders := [][]string{}
	files := [][]string{}
	for _, o := range objects {
		if strings.HasSuffix(o, "/") {
			folders = append(folders, objectBody(root, o))
		} else {
			files = append(files, objectBody(root, o))
		}
	}
	// Sort folders by the number of sub folders
	sort.SliceStable(folders, func(i, j int) bool {
		return len(folders[i]) < len(folders[j])
	})
	layout := &Layout{
		root:    root,
		imports: map[string]*Import{},
	}
	// Build the source and tmcf folders
	for _, parts := range folders {
		im := parts[0]
		// This corresponds to the "data" folder
		if im == "" {
			continue
		}
		if len(parts) == 1 {
			layout.imports[im] = &Import{
				tables: map[string]*Table{},
			}
		} else if len(parts) == 2 {
			layout.imports[im].tables[parts[1]] = &Table{}
		}
	}
	// Put file under each folder
	for _, parts := range files {
		if len(parts) < 2 {
			logging("Ignore file", parts)
			continue
		}
		im := parts[0]
		// source1/schema.mcf
		if len(parts) == 2 {
			fileName := parts[1]
			// Only .mcf file can be directly under a source folder
			if strings.HasSuffix(fileName, ".mcf") {
				layout.imports[im].mcf = parts[1]
				logging("Add MCF", parts)
			} else {
				logging("Ignore file", parts)
			}
			continue
		}
		// source1/folder1/stat.csv
		// source1/folder1/data.tmcf
		if len(parts) == 3 {
			tab := parts[1]
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
			} else {
				logging("Ignore file", parts)
			}
			continue
		}
		logging("Ignore file", parts)
	}
	// Trim invalid folders with no TMCF or CSV
	for im, importFolders := range layout.imports {
		for tab, tableFolders := range importFolders.tables {
			if tableFolders.tmcf == "" || len(tableFolders.csv) == 0 {
				layout.imports[im].tables[tab] = nil
				logging("Trim folder", []string{root, "data", im, tab})
			}
		}
	}
	return layout, nil
}

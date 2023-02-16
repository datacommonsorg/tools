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
	"path"

	"cloud.google.com/go/storage"
	"google.golang.org/api/iterator"
)

type Reader interface {
	ReadObjects(context.Context, string, string) ([]string, error)
}

type GCSReader struct{}

func (g GCSReader) ReadObjects(ctx context.Context, bucket, rootDir string) ([]string, error) {
	client, err := storage.NewClient(ctx)
	if err != nil {
		return nil, err
	}
	// Read all the objects under /.../rootDir/data/
	it := client.Bucket(bucket).Objects(
		ctx,
		&storage.Query{Prefix: path.Join(rootDir, "data")},
	)
	objects := []string{}
	for {
		attrs, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return nil, err
		}
		log.Printf("Found object: %s", attrs.Name)
		objects = append(objects, attrs.Name)
	}
	return objects, nil
}

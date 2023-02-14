// Copyright 2022 Google LLC
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

// Package gcf runs a GCF function that triggers in 2 scenarios:
//
//  1. completion of prophet-flume job in borg. On triggering it sets up new
//     cloud BT table, scales up BT cluster (if needed) and starts a dataflow job.
//  2. completion of BT cache ingestion dataflow job. It scales BT cluster down
//     (if needed).
//
// There are two set of trigger functions defined:
// - ProdBTImportController
// - PrivateBTImportController
// which targets on production imports and private imports. The folder structure
// are different for the two scenarios.
// The environment variables for deployments are stored in (prod|private)/*.yaml
package lib

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"cloud.google.com/go/bigtable"
	"cloud.google.com/go/storage"
	"github.com/pkg/errors"
)

const (
	createTableRetries = 3
	columnFamily       = "csv"
	gsScheme           = "gs://"
)

// GCSEvent is the payload of a GCS event.
type GCSEvent struct {
	Name   string `json:"name"` // File name in the control folder
	Bucket string `json:"bucket"`
}

// parsePath returns the GCS bucket and object from path in the form of gs://<bucket>/<object>
func ParsePath(path string) (string, string, error) {
	parts := strings.Split(path, "/")
	if parts[0] != "gs:" || parts[1] != "" || len(parts) < 3 {
		return "", "", errors.Errorf("Unexpected path: %s", path)
	}
	return parts[2], strings.Join(parts[3:], "/"), nil
}

func DoesObjectExist(ctx context.Context, path string) (bool, error) {
	bucket, object, err := ParsePath(path)
	if err != nil {
		return false, err
	}
	gcsClient, err := storage.NewClient(ctx)
	if err != nil {
		return false, errors.Wrap(err, "Failed to create gcsClient")
	}
	_, err = gcsClient.Bucket(bucket).Object(object).Attrs(ctx)
	if err == storage.ErrObjectNotExist {
		return false, nil
	}
	return true, nil
}

func WriteToGCS(ctx context.Context, path, data string) error {
	bucket, object, err := ParsePath(path)
	if err != nil {
		return err
	}
	gcsClient, err := storage.NewClient(ctx)
	if err != nil {
		return errors.Wrap(err, "Failed to create gcsClient")
	}
	w := gcsClient.Bucket(bucket).Object(object).NewWriter(ctx)
	defer w.Close()
	_, err = fmt.Fprint(w, data)
	return errors.WithMessagef(err, "Failed to write data to %s/%s", bucket, object)
}

func SetupBT(ctx context.Context, btProjectID, btInstance, tableID string) error {
	adminClient, err := bigtable.NewAdminClient(ctx, btProjectID, btInstance)
	if err != nil {
		return errors.Wrap(err, "Unable to create a table admin client")
	}
	// Create table. We retry 3 times in 1 minute intervals.
	dctx, cancel := context.WithDeadline(ctx, time.Now().Add(10*time.Minute))
	defer cancel()
	var ok bool
	for ii := 0; ii < createTableRetries; ii++ {
		log.Printf("Creating new bigtable table (%d): %s/%s", ii, btInstance, tableID)
		err = adminClient.CreateTable(dctx, tableID)
		if err != nil {
			log.Printf("Error creating table %s, retry...", err)
		} else {
			ok = true
			break
		}
		time.Sleep(1 * time.Minute)
	}
	if !ok {
		return errors.Errorf("Unable to create table: %s, got error: %v", tableID, err)
	}
	// Create table columnFamily.
	log.Printf("Creating column family %s in table %s/%s", columnFamily, btInstance, tableID)
	if err := adminClient.CreateColumnFamily(dctx, tableID, columnFamily); err != nil {
		return errors.WithMessagef(err, "Unable to create column family: csv for table: %s, got error: %v", tableID)
	}
	return nil
}

func DeleteBTTable(ctx context.Context, projectID, instance, table string) error {
	adminClient, err := bigtable.NewAdminClient(ctx, projectID, instance)
	if err != nil {
		return errors.Wrap(err, "Unable to create a table admin client")
	}
	return adminClient.DeleteTable(ctx, table)
}

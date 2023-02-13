#!/bin/bash
# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# Test GCF locally.
set -x

if [[ $# != 1 ]]; then
  echo "Usage: $0 (init|completed|cleanup)" >&2
  exit 1
fi

CACHE_NAME=dcbranch_2022_05_06_16_16_13

gcloud config set project google.com:datcom-store-dev

if [[ "$1" == "init" ]]; then
  curl localhost:8080 \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{
        "context": {
          "eventId": "1147091835525187",
          "timestamp": "2021-01-23T07:38:57.772Z",
          "eventType": "google.storage.object.finalize",
          "resource": {
             "service": "storage.googleapis.com",
             "name": "projects/_/buckets/automation_control_test/branch/'"$CACHE_NAME"'/init.txt",
             "type": "storage#object"
          }
        },
        "data": {
          "bucket": "automation_control_test",
          "contentType": "text/plain",
          "kind": "storage#object",
          "md5Hash": "...",
          "metageneration": "1",
          "name": "branch/'"$CACHE_NAME"'/init.txt",
          "size": "0",
          "storageClass": "MULTI_REGIONAL",
          "timeCreated": "2020-04-23T07:38:57.230Z",
          "timeStorageClassUpdated": "2020-04-23T07:38:57.230Z",
          "updated": "2020-04-23T07:38:57.230Z"
        }
      }'
elif [[ "$1" == "completed" ]]; then
  curl localhost:8080 \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{
        "context": {
          "eventId": "1147091835525187",
          "timestamp": "2021-01-23T07:38:57.772Z",
          "eventType": "google.storage.object.finalize",
          "resource": {
             "service": "storage.googleapis.com",
             "name": "projects/_/buckets/automation_control_test/branch/'"$CACHE_NAME"'/completed.txt",
             "type": "storage#object"
          }
        },
        "data": {
          "bucket": "automation_control_test",
          "contentType": "text/plain",
          "kind": "storage#object",
          "md5Hash": "...",
          "metageneration": "1",
          "name": "branch/'"$CACHE_NAME"'/completed.txt",
          "size": "0",
          "storageClass": "MULTI_REGIONAL",
          "timeCreated": "2020-04-23T07:38:57.230Z",
          "timeStorageClassUpdated": "2020-04-23T07:38:57.230Z",
          "updated": "2020-04-23T07:38:57.230Z"
        }
      }'
elif [[ "$1" == "cleanup" ]]; then
  gsutil rm gs://automation_control_test/"$CACHE_NAME"/completed.txt
  gsutil rm gs://automation_control_test/"$CACHE_NAME"/launched.txt
  cbt -instance prophet-test deletetable "$CACHE_NAME"
else
  echo "Usage: $0 (init|completed)" >&2
  exit 1
fi

#!/bin/bash
#
# Test GCF locally.
#

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
             "name": "projects/_/buckets/automation_control_test/base/branch_2021_01_08_13_25_48/init.txt",
             "type": "storage#object"
          }
        },
        "data": {
          "bucket": "automation_control_test",
          "contentType": "text/plain",
          "kind": "storage#object",
          "md5Hash": "...",
          "metageneration": "1",
          "name": "base/branch_2021_01_08_13_25_48/init.txt",
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
             "name": "projects/_/buckets/automation_control_test/base/branch_2021_01_08_13_25_48/completed.txt",
             "type": "storage#object"
          }
        },
        "data": {
          "bucket": "automation_control_test",
          "contentType": "text/plain",
          "kind": "storage#object",
          "md5Hash": "...",
          "metageneration": "1",
          "name": "base/branch_2021_01_08_13_25_48/completed.txt",
          "size": "0",
          "storageClass": "MULTI_REGIONAL",
          "timeCreated": "2020-04-23T07:38:57.230Z",
          "timeStorageClassUpdated": "2020-04-23T07:38:57.230Z",
          "updated": "2020-04-23T07:38:57.230Z"
        }
      }'
else
  echo "Usage: $0 (init | completed)" >&2
fi

#!/bin/bash
#
# Test GCF locally.
#
set -x

if [[ $# != 2 ]]; then
  echo "Usage: $0 <CACHE_NAME> (init|completed|cleanup)" >&2
  exit 1
fi

CACHE_NAME=$1
if [[ "$2" == "init" ]]; then
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
             "name": "projects/_/buckets/automation_control_test/base/'"$CACHE_NAME"'/init.txt",
             "type": "storage#object"
          }
        },
        "data": {
          "bucket": "automation_control_test",
          "contentType": "text/plain",
          "kind": "storage#object",
          "md5Hash": "...",
          "metageneration": "1",
          "name": "base/'"$CACHE_NAME"'/init.txt",
          "size": "0",
          "storageClass": "MULTI_REGIONAL",
          "timeCreated": "2020-04-23T07:38:57.230Z",
          "timeStorageClassUpdated": "2020-04-23T07:38:57.230Z",
          "updated": "2020-04-23T07:38:57.230Z"
        }
      }'
elif [[ "$2" == "completed" ]]; then
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
             "name": "projects/_/buckets/automation_control_test/base/'"$CACHE_NAME"'/completed.txt",
             "type": "storage#object"
          }
        },
        "data": {
          "bucket": "automation_control_test",
          "contentType": "text/plain",
          "kind": "storage#object",
          "md5Hash": "...",
          "metageneration": "1",
          "name": "base/'"$CACHE_NAME"'/completed.txt",
          "size": "0",
          "storageClass": "MULTI_REGIONAL",
          "timeCreated": "2020-04-23T07:38:57.230Z",
          "timeStorageClassUpdated": "2020-04-23T07:38:57.230Z",
          "updated": "2020-04-23T07:38:57.230Z"
        }
      }'
elif [[ "$2" == "cleanup" ]]; then
  gsutil rm gs://automation_control_test/base/"$CACHE_NAME"/completed.txt
  gsutil rm gs://automation_control_test/base/"$CACHE_NAME"/launched.txt
  cbt -instance prophet-cache-test deletetable "$CACHE_NAME"
else
  echo "Usage: $0 <CACHE_NAME> (init|completed)" >&2
  exit 1
fi

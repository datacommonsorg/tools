#!/bin/bash
# Copyright 2023 Google LLC
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
  echo "Usage: $0 (publish)" >&2
  exit 1
fi

# Test import notification pubsub message has the correct format.
# Mock a GCS file event to local GCF while publishing to a real PubSub topic.
if [[ "$1" == "publish" ]]; then
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
             "name": "projects/_/buckets/custom-dc-test-resources/demo/internal/control/trigger.txt",
             "type": "storage#object"
          }
        },
        "data": {
          "bucket": "custom-dc-test-resources",
          "contentType": "text/plain",
          "kind": "storage#object",
          "md5Hash": "...",
          "metageneration": "1",
          "name": "demo/internal/control/trigger.txt",
          "size": "0",
          "storageClass": "MULTI_REGIONAL",
          "timeCreated": "2020-04-23T07:38:57.230Z",
          "timeStorageClassUpdated": "2020-04-23T07:38:57.230Z",
          "updated": "2020-04-23T07:38:57.230Z"
        }
      }' && sleep 5

  # Note: This should match the topic in local.yaml
  SUB=projects/datcom-204919/subscriptions/custom-import-notification-test-sub

  GOT=$(gcloud pubsub subscriptions pull $SUB --auto-ack --format=json | jq  -r .[].message.data | base64 -d)
  WANT=$(cat custom_dc/import_notification_pubsub_msg_want.txt)

  set +x
  if [[ "$WANT" == "$GOT" ]]; then
    echo "###########################################################################"
    echo "Test passed: Publish to controller got expected pubusb message."
    echo "###########################################################################"
  else
    echo "###########################################################################"
    echo "Test failed: Publish to controller, got unexpected pubsub message from gcf."
    echo "###########################################################################"
  fi

fi

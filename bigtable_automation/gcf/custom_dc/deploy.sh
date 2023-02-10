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


DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ROOT="$(dirname "$DIR")"

PROJECT_ID=$(yq eval '.projectID' custom_dc/local.yaml)
BUCKET=$(yq eval '.bucket' custom_dc/local.yaml)

## TODO: move all of these as one-time setup
gcloud config set project $PROJECT_ID

gcloud functions deploy prophet-cache-trigger \
  --region 'us-central1' \
  --entry-point CustomBTImportController \
  --runtime go116 \
  --trigger-bucket $BUCKET \
  --env-vars-file custom_dc/local.yaml \
  --timeout 300


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

PROJECT_ID=$(yq eval '.projectID' $DIR/config/$1.yaml)
GCF_SA=$(yq eval '.gcfSA' $DIR/config/$1.yaml)


# Need to provide project to run script.
if [[ $1 != $PROJECT_ID ]]; then
  echo "Invalid project $1" >&2
  exit 1
fi

BUCKET=$(yq eval '.bucket' $DIR/config/$PROJECT_ID.yaml)

gcloud config set project $PROJECT_ID

cd $DIR
cd ../..

gcloud functions deploy prophet-cache-trigger \
  --region 'us-central1' \
  --entry-point CustomController \
  --runtime go116 \
  --trigger-bucket $BUCKET \
  --service-account $GCF_SA \
  --env-vars-file $DIR/config/$PROJECT_ID.yaml \
  --timeout 300


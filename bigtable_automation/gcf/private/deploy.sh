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


if [[ $# != 1 ]]; then
  echo "Usage: $0 (website-dev|mixer-autopush|datcom-stanford)" >&2
  exit 1
fi

if [[ $1 != "website-dev" && $1 != "mixer-autopush" && $1 != "datcom-stanford" ]]; then
  echo "Usage: $0 (website-dev|mixer-autopush|datcom-stanford)" >&2
  exit 1
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ROOT="$(dirname "$DIR")"

cd $DIR
PROJECT_ID=$(yq eval '.projectID' $1.yaml)
BUCKET=$(yq eval '.bucket' $1.yaml)

cd $ROOT
## TODO: move all of these as one-time setup
gcloud config set project $PROJECT_ID

gcloud services enable cloudbuild.googleapis.com

gcloud services enable dataflow.googleapis.com

gcloud compute networks subnets update default \
--region=us-central1 \
--enable-private-ip-google-access

gcloud functions deploy prophet-cache-trigger-$1 \
  --region 'us-central1' \
  --entry-point PrivateBTImportController \
  --runtime go116 \
  --trigger-bucket $BUCKET \
  --env-vars-file private/$1.yaml \
  --timeout 300

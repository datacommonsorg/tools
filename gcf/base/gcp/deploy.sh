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
  echo "Usage: $0 (base|branch)" >&2
  exit 1
fi

ENV=$1

if [[ $ENV != "base" && $ENV != "branch" ]]; then
  echo "Usage: $0 (base|branch)" >&2
  exit 1
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

PROJECT_ID=$(yq eval '.projectID' $DIR/config/$ENV.yaml)
BUCKET=$(yq eval '.controlPath' $DIR/config/$ENV.yaml | cut -f3 -d'/')

gcloud config set project $PROJECT_ID


cd $DIR
cd ../..
gcloud functions deploy prophet-cache-trigger-$ENV \
  --region 'us-central1' \
  --entry-point BaseController \
  --runtime go116 \
  --trigger-bucket $BUCKET \
  --env-vars-file $DIR/config/$ENV.yaml \
  --timeout 300

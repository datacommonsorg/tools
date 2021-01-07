#!/bin/bash

# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

# Change variable if deploying to different project.
export GOOGLE_CLOUD_PROJECT="datcom-tools-staging"

# Set the project on gcloud.
gcloud config set project $GOOGLE_CLOUD_PROJECT

# App Engine only understands static files, so build these files.
npm install
npm run build

# Deploy to App Engine.
gcloud app deploy ../dispatch.yaml ../default/app.yaml dashboard.yaml

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

set -x

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR

export projectID="datcom-mixer-encode"
export instance="dc-graph"
export cluster="dc-graph-c1"
export dataflowTemplate="gs://datcom-templates/templates/flex/csv_to_bt_0.0.3.json"
export tempLocation="gs://datcom-mixer-encode-resources/dataflow/tmp"
export controllerTriggerTopic="projects/datcom-204919/topics/private-import-notification-dev"
export bucket="datcom-mixer-encode-resources"

go run main.go
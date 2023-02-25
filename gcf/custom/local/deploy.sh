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
#
# To run custom gcf locally, call ./deploy.sh from local directory.
#
# To trigger the local gcf to mimick "trigger.txt" in gcs,
# first change the context and data objects in trigger.sh to match
# The environment variables below, and then call ./trigger.sh

set -x

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR


# Local GCF can access real cloud resources as long the environment variables
# below are set correctly.
# To run GCF locally with other projects, please change the values below.
export projectID="datcom-stanford"
export instance="dc-graph"
export cluster="dc-graph-c1"
export dataflowTemplate="gs://datcom-templates/templates/flex/csv_to_bt_0.0.3.json"
export tempLocation="gs://datcom-stanford-resources/dataflow/tmp"
export controllerTriggerTopic="projects/datcom-204919/topics/private-import-notification-dev"
export bucket="datcom-stanford-resources"
# Comment out the line below to trigger controllers from local gcf.
# export isLocal="true"

go run main.go

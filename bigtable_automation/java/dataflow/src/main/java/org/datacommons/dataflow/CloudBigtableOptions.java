// Copyright 2024 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package org.datacommons.dataflow;

import org.apache.beam.runners.dataflow.options.DataflowPipelineOptions;
import org.apache.beam.sdk.options.Description;
import org.apache.beam.sdk.options.ValueProvider;

public interface CloudBigtableOptions extends DataflowPipelineOptions {
  @Description("The Google Cloud project ID for the Cloud Bigtable instance.")
  ValueProvider<String> getBigtableProjectId();

  @SuppressWarnings("unused")
  void setBigtableProjectId(ValueProvider<String> bigtableProjectId);

  @Description("The Google Cloud Bigtable instance ID .")
  ValueProvider<String> getBigtableInstanceId();

  @SuppressWarnings("unused")
  void setBigtableInstanceId(ValueProvider<String> bigtableInstanceId);

  @Description("The Cloud Bigtable table ID in the instance." )
  ValueProvider<String> getBigtableTableId();

  @SuppressWarnings("unused")
  void setBigtableTableId(ValueProvider<String> bigtableTableId);

  @Description("The App Profile to use for Bigtable writes.")
  ValueProvider<String> getBigtableAppProfileId();

  @SuppressWarnings("unused")
  void setBigtableAppProfileId(ValueProvider<String> bigtableAppProfileId);

  @Description("The maximum number of workers for Dataflow jobs.")
  ValueProvider<String> getDataflowMaxNumWorkers();

  @SuppressWarnings("unused")
  void setDataflowMaxNumWorkers(ValueProvider<String> dataflowMaxNumWorkers);
}

/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
terraform {
  backend "gcs" {}
}

locals {
    resource_suffix = (
        var.resource_suffix != null ?
        format("-%s", var.resource_suffix) : ""
    )

    bt_instance   = format("dc-graph%s", local.resource_suffix)
    bt_cluster_id = "dc-graph-c1"
}

# BigTable instance used to store cache tables.
resource "google_bigtable_instance" "bt_cache" {
  count = var.enable_bigtable_instance ? 1 : 0

  name           = local.bt_instance
  project        = var.project_id

  deletion_protection = false

  cluster {
    # There will be one cluster. Constant seems appropriate for now.
    cluster_id   = local.bt_cluster_id
    zone         = var.bt_instance_zone

    autoscaling_config {
      min_nodes  = var.bt_autoscaling_min_nodes
      max_nodes  = var.bt_autoscaling_max_nodes
      cpu_target = var.bt_autoscaling_cpu_target
    }
  }
}

data "archive_file" "bt_automation_go_source" {
  type        = "zip"
  source_dir  = "${path.module}/../../gcf"
  output_path = "${path.module}/source/bt_automation_go_source.zip"
}

# Upload zipped go source. Consumed by gcf.
resource "google_storage_bucket_object" "bt_automation_archieve" {
    # Relative path in the resource bucket to upload the archieve.
    name   = "cloud_functions/bt_automation_go_source_${data.archive_file.bt_automation_go_source.output_md5}.zip"
    source = "${path.module}/source/bt_automation_go_source.zip"
    bucket = var.dc_resource_bucket

    depends_on = [
        data.archive_file.bt_automation_go_source
    ]
}

resource "google_cloudfunctions_function" "bt_automation" {
  name        = format(
      "prophet-cache-trigger%s", local.resource_suffix)
  project        = var.project_id
  description = "For triggering BT cache build on gcs file writes."
  runtime     = "go116"
  region      = var.region

  timeout                      = 300
  entry_point                  = "CustomController"

  service_account_email        = var.service_account_email

  source_archive_bucket = google_storage_bucket_object.bt_automation_archieve.bucket
  source_archive_object = google_storage_bucket_object.bt_automation_archieve.name

  dynamic "event_trigger" {
      for_each  = [1]
      content {
          # Triggered on blob write to objects in the resource bucket.
          event_type = "google.storage.object.finalize"
          resource   = var.dc_resource_bucket
      }
  }

  environment_variables = {
    projectID        = var.project_id
    bucket           = var.dc_resource_bucket

    # Variables from BT instance created from this file.
    instance         = local.bt_instance
    cluster          = local.bt_cluster_id
    nodesLow         = var.bt_autoscaling_min_nodes
    nodesHigh        = var.bt_autoscaling_max_nodes

    dataflowTemplate = var.csv2bt_template_path
    tempLocation     = format("gs://%s/dataflow/tmp", var.dc_resource_bucket)

    bucket           = var.dc_resource_bucket
    controllerTriggerTopic = "projects/datcom-204919/topics/private-import-notification-prod"

  }

  depends_on = [
      google_storage_bucket_object.bt_automation_archieve
  ]
}

resource "google_project_iam_member" "bt_automation_iam" {
  for_each = toset([
    "roles/bigtable.admin",
    "roles/dataflow.admin",
    "roles/storage.admin",
    # Web robot is also used for Cloud Function jobs, which launches Dataflow jobs.
     # It needs permission to impersonate Dataflow worker principal.
    "roles/iam.serviceAccountUser"
  ])
  role    = each.key
  member  = "serviceAccount:${var.service_account_email}"
  project = var.project_id
}

data "google_compute_default_service_account" "default" {
  project = var.project_id
}

resource "google_project_iam_member" "dataflow_worker_iam" {
  role    = "roles/storage.objectAdmin" # For running csv -> BT table jobs.
  member  = "serviceAccount:${data.google_compute_default_service_account.default.email}"
  project = var.project_id
}

# Permissions needed to communicate with graph processor.
resource "google_project_iam_member" "bt_automation_controller_iam" {
  for_each = toset([
    "roles/pubsub.editor",
    "roles/storage.admin"
  ])
  role    = each.key
  member  = "serviceAccount:datacommons-controller-runner-pod@system.gserviceaccount.com"
  project = var.project_id
}

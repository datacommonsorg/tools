# ---------------------------------------------------------------------------
# App-plane runtime identity
#
# The only service account this module creates. A second one, "<instance>-runtime",
# used to exist for the cdc data-plane container -- it held cloudsql.client and
# objectAdmin on the data bucket, neither of which the app plane has ever needed.
# The container is gone and so is the identity.
#
# What remains needs Gemini keys, the config bucket, and (granted in main.tf)
# invoker on the data plane when that plane is a private DCP service.
# ---------------------------------------------------------------------------
resource "google_service_account" "app" {
  project      = var.project_id
  account_id   = "${var.instance}-app"
  display_name = "${var.instance} app plane (agent + UI)"
}

resource "google_project_iam_member" "app_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_storage_bucket_iam_member" "app_config_reader" {
  bucket = var.config_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "app_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "app_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# ---------------------------------------------------------------------------
# App-plane runtime identity. The only service account this module creates.
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

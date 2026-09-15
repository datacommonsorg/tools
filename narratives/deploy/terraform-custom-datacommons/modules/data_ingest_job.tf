# Cloud Run Job wrapping the upstream `datacommons-data` image.
#
# Run after Cloud SQL exists but BEFORE the Cloud Run service starts. Reads
# source CSVs from `INPUT_DIR`, writes:
#   - MySQL schema + observations to Cloud SQL
#   - NL embeddings to `OUTPUT_DIR/datacommons/nl/embeddings/`
#   - Custom variable catalog to `OUTPUT_DIR/datacommons/`
#
# the README invokes this job via `gcloud run jobs execute`.

# CDC only. DCP ingests through Workflows + Dataflow, driven by
# `datacommons-cli admin ingest start` -- there is no Job to create here.
resource "google_cloud_run_v2_job" "data_ingest" {
  count = local.is_cdc ? 1 : 0

  name                = "${var.instance}-data-ingest"
  location            = var.region
  deletion_protection = var.deletion_protection

  template {
    template {
      timeout         = "3600s"
      service_account = google_service_account.datacommons.email
      max_retries     = 0

      containers {
        # Upstream data ingest image; same release cadence as services:stable.
        image = "gcr.io/datcom-ci/datacommons-data:stable"

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        env {
          name  = "USE_CLOUDSQL"
          value = "true"
        }
        env {
          name  = "USE_SQLITE"
          value = "false"
        }
        env {
          name  = "CLOUDSQL_INSTANCE"
          value = local.cloudsql_connection_name
        }
        env {
          name  = "DB_NAME"
          value = google_sql_database.dc[0].name
        }
        env {
          name  = "DB_USER"
          value = local.db_user
        }
        env {
          name = "DB_PASS"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.db_pass[0].secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "DC_API_KEY"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.dc_api_key.secret_id
              version = "latest"
            }
          }
        }
        env {
          name  = "INPUT_DIR"
          value = local.input_dir
        }
        env {
          name  = "OUTPUT_DIR"
          value = local.output_dir
        }
        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }
        env {
          name  = "GOOGLE_CLOUD_REGION"
          value = var.region
        }
        env {
          name  = "FLASK_ENV"
          value = "custom"
        }
        # Tell the ingest to write its outputs (embeddings, catalog) AND the
        # MySQL schema. Default mode is "schemaupdate" + "data".
        env {
          name  = "DATA_UPDATE_MODE"
          value = "schemaupdate"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [local.cloudsql_connection_name]
        }
      }
    }
  }


}

output "ingest_job_name" {
  description = "Name of the Cloud Run Job to invoke for data ingestion."
  value       = local.is_cdc ? google_cloud_run_v2_job.data_ingest[0].name : ""
}

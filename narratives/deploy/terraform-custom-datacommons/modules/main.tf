# Core resources for one Custom Data Commons instance. Each instance is a
# fully independent deployment in its own GCP project — no shared resources
# across instances.
#
#   - One Cloud Run v2 service: the public app plane (agent + SPA). The data
#     plane is public Data Commons
#   - Per-instance Secret Manager entries (DC_API_KEY, GEMINI_API_KEY)
#   - Uptime checks + alert policies
#
# The per-instance config bucket (gs://<project>-config/) and the Artifact
# Registry repo are created out-of-band by deploy.sh
# before terraform apply. The tfvars provide the image paths, the config
# bucket name, and the brand_config_url only.

locals {
  data_plane_url = var.public_dc_url
  mcp_url        = "${local.data_plane_url}/mcp"

  # Where the BROWSER's data routes go. These are two hosts: api.datacommons.org
  # serves the versioned REST API and /mcp, while the routes the chart web
  # components call -- /api/observations/series, /api/place/name,
  # /core/api/... -- exist only on datacommons.org.
  #
  # Collapsing both onto data_plane_url meant every chart request got a Cloud
  # Endpoints 404 ("The current request is not defined by this API"). The agent
  # answered correctly and no chart ever rendered.
  data_plane_web_url = var.public_dc_web_url

  app_service_name = "${var.instance}-app"
}

# Reference to the per-instance config bucket (NOT managed here — created out-of-band
# by deploy.sh before terraform apply). One bucket per instance.
data "google_storage_bucket" "config" {
  name = var.config_bucket
}

# ---------------------------------------------------------------------------
# Secrets
#   - DC_API_KEY is project-wide (shared across instances) — referenced via data source.
#   - GEMINI_API_KEY is per-instance (<instance>-gemini-api-key).
#   - All secrets must have an enabled version BEFORE `terraform apply` —
#     `deploy.sh --bootstrap-secrets` puts them there.
# ---------------------------------------------------------------------------

data "google_secret_manager_secret" "dc_api_key" {
  secret_id = var.dc_api_key_secret_id
}

# Per-instance secrets are created out-of-band before first apply.
# Rationale: secret rotation is an operational task; we don't want a tfstate
# diff every time a key is rotated.
data "google_secret_manager_secret" "gemini_api_key" {
  secret_id = var.gemini_api_key_secret_id
}

# ---------------------------------------------------------------------------
# APP PLANE — the agent API plus the compiled SPA, in one container.
#
# This is the only public surface. It serves the UI, runs the chat
# orchestration, and reverse-proxies the browser's data routes to the data
# plane so everything stays on one origin (required by IAP and by the two
# same-origin iframe tools).
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "dc_app_service" {
  provider = google-beta

  name                = local.app_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  # Whether IAP fronts this service. Beta-only, which is why this resource uses
  # the google-beta provider. Set explicitly rather than omitted: the attribute
  # is optional but NOT computed, so leaving it out makes Terraform send false
  # and switch IAP off on every apply.
  iap_enabled = var.access_mode == "iap"

  template {
    service_account = google_service_account.app.email
    timeout         = "600s"

    scaling {
      min_instance_count = var.app_min_instances
      max_instance_count = var.app_max_instances
    }

    # Bound how many requests Cloud Run stacks into one instance. Unset, this
    # defaults to 80 — and a chat response is an SSE stream held open for tens
    # of seconds, so 80 concurrent requests means 80 parked threads on one
    # vCPU. Scale out with instances rather than in with threads.
    max_instance_request_concurrency = var.app_concurrency

    containers {
      name  = "app"
      image = var.dc_agent_image

      ports {
        container_port = 8080
      }

      resources {
        # All CPU-hungry work happens inside a request: the SSE stream holds
        # the request open for its duration, and the chart-config thread is
        # joined before the generator returns. Startup is covered by the boost.
        cpu_idle = true
        limits = {
          cpu    = var.agent_cpu
          memory = var.agent_memory
        }
        startup_cpu_boost = true
      }

      env {
        name  = "AGENT_PORT"
        value = "8080"
      }
      # Where the MCP tool loop and the /dcproxy reverse proxy send their
      # traffic. Both point at the data plane's own URL now, not localhost.
      env {
        name  = "MCP_SERVER_URL"
        value = local.mcp_url
      }
      env {
        name  = "DATA_PLANE_URL"
        value = local.data_plane_url
      }
      env {
        name  = "DATA_PLANE_WEB_URL"
        value = local.data_plane_web_url
      }
      env {
        name  = "TIMEZONE"
        value = var.timezone
      }
      env {
        name  = "ALLOWED_ORIGIN"
        value = var.allowed_origin
      }
      env {
        name  = "AGENT_CONFIG_MODE"
        value = var.agent_config_mode
      }
      env {
        name  = "BRAND_CONFIG_URL"
        value = var.brand_config_url
      }
      env {
        name  = "CONFIG_URL"
        value = "${var.brand_config_url}/agent-config.json"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GEMINI_API_KEY_SECRET"
        value = data.google_secret_manager_secret.gemini_api_key.secret_id
      }
      # Public Data Commons authenticates with an API key. gcp_auth only sends
      # it to *.datacommons.org.
      env {
        name = "DC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.dc_api_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 10
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 30
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  # Container env is deliberately NOT ignored here. On the coupled service it
  # was, and that silently swallowed real changes — a secret binding added in
  # config never reached the deployed service. The cost is that an apply after
  # `deploy.sh --config-only` shows a diff for the FORCE_RESTART cache-buster
  # that step sets out of band. The value is never read, so that is noise
  # rather than a problem.
}

# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

# Humans reach the app plane, not the data plane. Replaces a hardcoded
# individual account, which meant a rebuild from state alone produced a service
# only one person could open.
# Public exposure, opt-in.
resource "google_cloud_run_v2_service_iam_member" "app_public" {
  count = var.access_mode == "public" ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dc_app_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Direct invoker rights, "private" mode only.
#
# Deliberately not granted in iap mode: a member holding run.invoker can call
# the Cloud Run URL directly with an identity token and never see the sign-in,
# which defeats the mode. In iap mode the only principal with run.invoker is
# IAP's own service agent, below.
resource "google_cloud_run_v2_service_iam_member" "app_invokers" {
  for_each = var.access_mode == "private" ? toset(var.authorized_members) : toset([])

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dc_app_service.name
  role     = "roles/run.invoker"
  member   = each.value
}


# ---------------------------------------------------------------------------
# Artifact Registry — referenced, not created (shared across instances).
# deploy.sh creates it; by hand it is:
#   gcloud artifacts repositories create dc-images \
#     --repository-format=docker --location=<region>
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Uptime checks + alert policies
# ---------------------------------------------------------------------------

# Checks the app plane, the only service this module runs.
#
# Path is /agent/health, not /healthz: Cloud Run's frontend reserves /healthz
# and answers it itself without forwarding to the container, so a check against
# it would pass without proving anything about the app. The startup probe still
# uses /healthz because probes hit the container port directly, bypassing the
# frontend — which is the only place it needs to work.
resource "google_monitoring_uptime_check_config" "homepage" {
  display_name = "${local.app_service_name}-health"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path           = "/agent/health"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"
    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      # The Cloud Run URL is computed at runtime; the uptime check is wired
      # via host below.
      host = trimprefix(google_cloud_run_v2_service.dc_app_service.uri, "https://")
    }
  }
}

resource "google_monitoring_alert_policy" "uptime" {
  count        = length(var.alert_notification_channels) > 0 ? 1 : 0
  display_name = "${local.app_service_name} uptime check failing"
  combiner     = "OR"

  conditions {
    display_name = "Uptime check failed"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.labels.check_id=\"${google_monitoring_uptime_check_config.homepage.uptime_check_id}\""
      duration        = "60s"
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_FRACTION_TRUE"
      }
    }
  }

  notification_channels = var.alert_notification_channels
}

# ---------------------------------------------------------------------------
# Identity-Aware Proxy (IAP) Access Control
# ---------------------------------------------------------------------------

# Who may sign in, scoped to THIS service.
#
# This was google_iap_web_iam_member, which is PROJECT-level: it granted access
# to every IAP-fronted app in the project, and two Terraform states both owning
# it meant `terraform destroy` on one revoked access for the other. That is what
# manage_iap_bindings existed to work around, and why it is now gone -- a
# service-scoped binding cannot collide.
resource "google_iap_web_cloud_run_service_iam_member" "iap_accessors" {
  for_each = var.access_mode == "iap" ? toset(var.authorized_members) : toset([])

  project                = var.project_id
  location               = var.region
  cloud_run_service_name = google_cloud_run_v2_service.dc_app_service.name
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}

# IAP forwards requests as its own service agent, so that agent needs to be
# allowed to invoke the service.
#
# Without this every request is refused with a 403 AFTER the user has signed in
# successfully -- which reads as a bug in the app rather than a missing IAM
# binding, and is the single most confusing way this mode fails.
resource "google_cloud_run_v2_service_iam_member" "iap_agent_invoker" {
  count = var.access_mode == "iap" ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dc_app_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

# Needed for the IAP service agent's address, which is keyed by project NUMBER.
data "google_project" "current" {
  project_id = var.project_id
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "service_url" {
  description = "App-plane URL — the public entry point. Share this one."
  value       = google_cloud_run_v2_service.dc_app_service.uri
}

output "data_plane_url" {
  description = "Data-plane URL the app plane is configured with, for debugging."
  value       = local.data_plane_url
}

output "app_service_account" {
  description = "App-plane runtime service account."
  value       = google_service_account.app.email
}

output "config_bucket" {
  description = "Per-instance GCS config bucket (object-versioned, public read for branding.json access)."
  value       = data.google_storage_bucket.config.name
}

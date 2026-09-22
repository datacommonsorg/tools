# The app plane for one Custom Data Commons instance: one Cloud Run service
# (agent + SPA), optionally a VPC subnet for reaching a private data plane, and
# uptime checks. Each instance is its own GCP project; nothing is shared.
#
# The data plane is not built here. It is either a DCP service provisioned
# elsewhere or public datacommons.org.
#
# The config bucket, the Artifact Registry repo and the secrets all exist
# before apply; deploy.sh creates them. The tfvars supply their names.

locals {
  # Every count below reads these rather than re-testing var.data_backend, so
  # a new backend means one more local, not an audit of every resource.
  is_dcp = var.data_backend == "dcp"

  # Which backend collapses to this URL, plus the auth attached at runtime.
  data_plane_url = local.is_dcp ? var.dcp_service_url : var.public_dc_url
  mcp_url        = "${local.data_plane_url}/mcp"

  # Where the browser's chart routes go. On dcp, one container serves both, so
  # this is the same URL. On "none" they are two hosts: /mcp and the REST API
  # are on api.datacommons.org, but the routes the chart components call
  # (/api/observations/series, /api/place/name, /core/api/...) exist only on
  # datacommons.org. Point both at data_plane_url and every chart 404s.
  data_plane_web_url = local.is_dcp ? local.data_plane_url : var.public_dc_web_url

  # Turn on only for a data plane with ingress=internal. Reaching one over a
  # VPC needs egress=ALL_TRAFFIC, which routes every outbound call through the
  # subnet; Private Google Access keeps Gemini and GCS working, but a public
  # host like api.datacommons.org needs Cloud NAT and is otherwise unreachable.
  # Defaults off, because this module cannot see the ingress of a data plane
  # it does not build.
  needs_vpc_egress = coalesce(var.enable_vpc_egress, false)

  app_service_name = "${var.instance}-app"
}

# The config bucket is created by deploy.sh before apply, not managed here.
data "google_storage_bucket" "config" {
  name = var.config_bucket
}

# ---------------------------------------------------------------------------
# Secrets. Both must already hold an enabled version at apply time;
# `deploy.sh --bootstrap-secrets` puts them there.
# ---------------------------------------------------------------------------

data "google_secret_manager_secret" "dc_api_key" {
  secret_id = var.dc_api_key_secret_id
}

data "google_secret_manager_secret" "gemini_api_keys" {
  secret_id = var.gemini_api_keys_secret_id
}

# ---------------------------------------------------------------------------
# Private network for app-plane egress.
#
# Reaching an ingress=internal service means the caller's traffic has to
# originate inside a VPC in this project. Direct VPC egress does that without
# the old Serverless VPC Access connector (a managed instance group — extra
# hop, extra cost).
#
# egress must be ALL_TRAFFIC, not PRIVATE_RANGES_ONLY: *.run.app resolves to a
# public IP, so private-ranges-only would send the call down the default path
# and the internal-ingress service would refuse it with a 403 that looks like
# an IAM problem and is not. Private Google Access on the subnet covers the
# app plane's other outbound (Gemini, GCS, Secret Manager) without Cloud NAT.
# ---------------------------------------------------------------------------
resource "google_compute_network" "app" {
  count = local.needs_vpc_egress ? 1 : 0

  project                 = var.project_id
  name                    = "${var.instance}-app-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "app" {
  count = local.needs_vpc_egress ? 1 : 0

  project                  = var.project_id
  name                     = "${var.instance}-app-subnet"
  region                   = var.region
  network                  = google_compute_network.app[0].id
  ip_cidr_range            = var.app_subnet_cidr
  private_ip_google_access = true
}

# ---------------------------------------------------------------------------
# APP PLANE — the agent API plus the compiled SPA, in one container.
#
# The only public surface. Serves the UI, runs the chat orchestration, and
# reverse-proxies the browser's data routes to the data plane so everything
# stays on one origin -- required by IAP and by the same-origin iframe tools.
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

    dynamic "vpc_access" {
      for_each = local.needs_vpc_egress ? [1] : []
      content {
        network_interfaces {
          network    = google_compute_network.app[0].id
          subnetwork = google_compute_subnetwork.app[0].id
        }
        egress = "ALL_TRAFFIC"
      }
    }

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
        name  = "PROXY_PORT"
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
        name  = "GEMINI_API_KEYS_SECRET"
        value = data.google_secret_manager_secret.gemini_api_keys.secret_id
      }
      # Needed only when data_backend = "none": public Data Commons
      # authenticates with an API key, not with our service account. Harmless
      # on the other backends -- gcp_auth only sends it to *.datacommons.org.
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

resource "google_cloud_run_v2_service_iam_member" "app_invokes_dcp" {
  # The DCP services instance is created outside this module by
  # datacommons-cli, so it is referenced by name rather than by resource.
  count = local.is_dcp && var.dcp_service_name != "" ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = var.dcp_service_name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.app.email}"
}

# Fail at plan time on a half-configured backend rather than at runtime with an
# app plane pointed at an empty string -- which presents as every chat turn
# answering "no data", with nothing to indicate the cause.
resource "terraform_data" "backend_preconditions" {
  lifecycle {
    precondition {
      condition     = !local.is_dcp || var.dcp_service_url != ""
      error_message = "data_backend = \"dcp\" requires dcp_service_url (from `terraform output datacommons_service_url` in the datacommons-cli scaffold)."
    }
    precondition {
      condition     = !local.is_dcp || var.dcp_service_name != ""
      error_message = "data_backend = \"dcp\" requires dcp_service_name, so the app plane's service account can be granted run.invoker on the DCP backend. Without it every MCP call is refused."
    }
  }
}

# Public exposure, opt-in. Scoped to the app plane, so it can never expose a
# private data plane however it is set.
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

# Checks the app plane, which is the only externally reachable service. The
# data plane is ingress=internal and cannot be probed from outside by design.
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
  description = "Data-plane URL. ingress=internal by default, so this is not reachable from a browser — it is here for the app plane's env and for debugging from inside the VPC."
  value       = local.data_plane_url
}

output "app_service_account" {
  description = "App-plane runtime service account. This is the identity that must hold run.invoker on the data plane."
  value       = google_service_account.app.email
}

output "config_bucket" {
  description = "Per-instance GCS config bucket (object-versioned, public read for branding.json access)."
  value       = data.google_storage_bucket.config.name
}

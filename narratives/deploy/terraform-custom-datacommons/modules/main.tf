# Core resources for one Custom Data Commons instance. Each instance is a
# fully independent deployment in its own GCP project — no shared resources
# across instances.
#
#   - Two Cloud Run v2 services: a public app plane (agent + SPA) and an
#     internal-only data plane (services image), each scaling independently
#   - A VPC subnet so the app plane can reach the internal data plane
#   - Cloud SQL HA (MySQL) for the upstream Mixer
#   - Per-instance GCS data bucket
#   - Per-instance Secret Manager entries (DC_API_KEY, MAPS_API_KEY, DB_PASS, GEMINI_API_KEYS)
#   - Uptime checks + alert policies
#
# The per-instance config bucket (gs://<project>-config/) and the Artifact
# Registry repo are created out-of-band by deploy.sh
# before terraform apply. The tfvars provide the image paths, the config
# bucket name, and the brand_config_url only.

locals {
  # A single place that decides what exists. Every count below reads these
  # rather than re-testing var.data_backend, so adding a backend later means
  # adding one local, not auditing every resource.
  is_cdc = var.data_backend == "cdc"
  is_dcp = var.data_backend == "dcp"

  # The one value the app plane actually needs. Everything about "which
  # backend" collapses to this URL plus the auth attached to it at runtime.
  data_plane_url = (
    local.is_cdc ? google_cloud_run_v2_service.dc_data_service[0].uri :
    local.is_dcp ? var.dcp_service_url :
    var.public_dc_url
  )
  mcp_url = "${local.data_plane_url}/mcp"

  # Where the BROWSER's data routes go. On cdc and dcp one container serves both
  # MCP and the website, so this is the same URL. On "none" they are two hosts:
  # api.datacommons.org serves the versioned REST API and /mcp, while the routes
  # the chart web components call -- /api/observations/series, /api/place/name,
  # /core/api/... -- exist only on datacommons.org.
  #
  # Collapsing both onto data_plane_url meant every chart request on the "none"
  # backend got a Cloud Endpoints 404 ("The current request is not defined by
  # this API"). The agent answered correctly and no chart ever rendered.
  data_plane_web_url = (
    local.is_cdc || local.is_dcp ? local.data_plane_url : var.public_dc_web_url
  )

  # Direct VPC egress exists for exactly one reason: to reach a data plane whose
  # ingress is internal. It is NOT free to switch on -- Cloud Run requires
  # egress=ALL_TRAFFIC to reach a *.run.app host through a VPC, which routes
  # EVERY outbound call through that subnet. Private Google Access covers
  # *.googleapis.com, so Gemini and GCS still work, but a genuinely public host
  # such as api.datacommons.org becomes unreachable without Cloud NAT.
  #
  # So only turn it on when the data plane is actually private. On "none" the
  # backend IS api.datacommons.org, and enabling this would black-hole it.
  needs_vpc_egress = coalesce(
    var.enable_vpc_egress,
    local.is_cdc && var.data_plane_ingress != "INGRESS_TRAFFIC_ALL"
  )

  # Two services since the split. The data plane keeps the historical name so
  # the existing Cloud SQL instance, buckets and dashboards keep matching it;
  # the app plane is the new, public one.
  data_service_name = "${var.instance}-datacommons"
  app_service_name  = "${var.instance}-app"
  # Data bucket naming convention: <instance>-data-<project>,
  # e.g. india-data-<project_id>.
  data_bucket_name = "${var.instance}-data-${var.project_id}"
  # Cloud SQL connection name + DB user — switch to an override when sharing
  # a populated instance during the POC; otherwise use the module-created one.
  cloudsql_connection_name = var.cloudsql_instance_override != "" ? var.cloudsql_instance_override : (local.is_cdc ? google_sql_database_instance.dc[0].connection_name : "")
  db_user                  = var.db_user_override != "" ? var.db_user_override : (local.is_cdc ? google_sql_user.dc[0].name : "")
  output_dir               = var.output_dir != "" ? var.output_dir : (local.is_cdc ? "gs://${google_storage_bucket.data[0].name}/output" : "")
  input_dir                = var.input_dir != "" ? var.input_dir : (local.is_cdc ? "gs://${google_storage_bucket.data[0].name}/input" : "")
}

# ---------------------------------------------------------------------------
# Per-instance data bucket (created here)
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "data" {
  # Ingest input/output. DCP brings its own artifacts bucket; "none" has no data.
  count = local.is_cdc ? 1 : 0

  name                        = local.data_bucket_name
  location                    = var.region
  force_destroy               = var.force_destroy
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# Reference to the per-instance config bucket (NOT managed here — created out-of-band
# by deploy.sh before terraform apply). One bucket per instance.
data "google_storage_bucket" "config" {
  name = var.config_bucket
}

# ---------------------------------------------------------------------------
# Cloud SQL
# ---------------------------------------------------------------------------

resource "google_sql_database_instance" "dc" {
  count = local.is_cdc ? 1 : 0

  name                = "dc-${var.instance}-mysql"
  database_version    = "MYSQL_8_0"
  region              = var.region
  deletion_protection = var.deletion_protection

  settings {
    tier              = var.cloudsql_tier
    availability_type = var.cloudsql_availability_type
    disk_autoresize   = true
    disk_size         = 20
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled                        = true
      binary_log_enabled             = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
    }

    ip_configuration {
      ipv4_enabled = true
      # Authorised networks left empty — Cloud Run connects via the
      # CloudSQL Auth Proxy / direct VPC egress, not via public IP allowlist.
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = false
    }
  }
}

resource "google_sql_database" "dc" {
  count = local.is_cdc ? 1 : 0

  name     = "datacommons"
  instance = google_sql_database_instance.dc[0].name
}

resource "google_sql_user" "dc" {
  count = local.is_cdc ? 1 : 0

  name     = "dc_runtime"
  instance = google_sql_database_instance.dc[0].name
  password = data.google_secret_manager_secret_version.db_pass[0].secret_data
}

# ---------------------------------------------------------------------------
# Secrets
#   - DC_API_KEY is project-wide (shared across instances) — referenced via data source.
#   - MAPS_API_KEY / DB_PASS / GEMINI_API_KEYS are per-instance, namespaced
#     by var.secret_prefix (e.g. CDC_POC_INDIA_).
#   - All secrets must have an enabled version BEFORE `terraform apply` —
#     see docs/deployment.md Stage 1.
# ---------------------------------------------------------------------------

data "google_secret_manager_secret" "dc_api_key" {
  secret_id = var.dc_api_key_secret_id
}

# Per-instance secrets are created out-of-band before first apply.
# Rationale: secret rotation is an operational task; we don't want a tfstate
# diff every time a key is rotated.
data "google_secret_manager_secret" "maps_api_key" {
  # CDC only. The Maps key is consumed by the data-plane container, which is
  # count = 0 on dcp and none -- but a data source is read regardless of who
  # uses it, so leaving this ungated made every deployment create a Maps secret
  # that nothing would ever read, purely to satisfy a lookup.
  count = local.is_cdc ? 1 : 0

  secret_id = var.maps_api_key_secret_id
}

data "google_secret_manager_secret" "db_pass" {
  count = local.is_cdc ? 1 : 0

  secret_id = var.db_pass_secret_id
}

data "google_secret_manager_secret" "gemini_api_keys" {
  secret_id = var.gemini_api_keys_secret_id
}

# Read DB_PASS for the SQL user resource above. The version must exist before
# `terraform apply`.
data "google_secret_manager_secret_version" "db_pass" {
  count = local.is_cdc ? 1 : 0

  secret  = data.google_secret_manager_secret.db_pass[0].secret_id
  version = "latest"
}

# ---------------------------------------------------------------------------
# DATA PLANE — nginx + Flask + Mixer + MCP + NL server, over Cloud SQL.
#
# ingress = INTERNAL_ONLY: the browser no longer reaches this service at all.
# The app plane is the sole public front door and reverse-proxies the data
# routes here, so Mixer, MCP and the Flask pages can drop off the internet
# entirely. That is a better posture than the coupled deployment had, and it
# falls out of the split for free.
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "dc_data_service" {
  # Only the CDC plane is ours to run. DCP's equivalent is created by Google's
  # module via datacommons-cli; "none" needs no data plane at all.
  count = local.is_cdc ? 1 : 0

  name     = local.data_service_name
  location = var.region
  ingress  = var.data_plane_ingress
  # POC stamp — allow Terraform to delete/replace freely. Bump to true once
  # demo traffic is routed at this service.
  deletion_protection = false

  template {
    service_account = google_service_account.datacommons.email
    timeout         = "600s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    # Bound how many requests Cloud Run stacks into one instance. Unset, this
    # takes Cloud Run's default of 80 -- and multiplied by max_instances that is
    # several hundred concurrent requests against a single Cloud SQL instance
    # that has no connection-pool sizing configured anywhere. MySQL answers that
    # with "too many connections", not with slow queries.
    #
    # Not needed on the Spanner backend, which uses session pools and has no
    # fixed connection ceiling -- but harmless there, and one less thing to
    # remember when switching data_backend.
    max_instance_request_concurrency = var.data_concurrency

    containers {
      name  = "services"
      image = var.dc_web_service_image

      ports {
        container_port = 8080
      }

      resources {
        cpu_idle = false
        limits = {
          cpu    = var.services_cpu
          memory = var.services_memory
        }
        startup_cpu_boost = true
      }

      env {
        name  = "FLASK_ENV"
        value = "custom"
      }
      env {
        name  = "ENABLE_MODEL"
        value = "true"
      }
      env {
        name  = "ENABLE_MCP"
        value = "true"
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
        name  = "DC_API_ROOT"
        value = "https://api.datacommons.org"
      }
      env {
        name  = "DC_SEARCH_SCOPE"
        value = "base_and_custom"
      }
      env {
        name  = "DISABLE_GOOGLE_MAPS"
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
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_REGION"
        value = var.region
      }
      env {
        name  = "BRAND_CONFIG_URL"
        value = var.brand_config_url
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
        name = "DC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.dc_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "MAPS_API_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.maps_api_key[0].secret_id
            version = "latest"
          }
        }
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

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 30
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 30
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [local.cloudsql_connection_name]
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
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
# This is the only public surface. It serves the UI, runs the chat
# orchestration, and reverse-proxies the browser's data routes to the data
# plane so everything stays on one origin (required by IAP and by the two
# same-origin iframe tools).
#
# There is deliberately no circular reference between the two services: the
# data plane no longer needs to know the app plane's URL, because nginx has
# stopped proxying /agent. Only this direction exists, so Terraform can order
# the two on its own.
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

# THE binding that makes a private data plane work: the app plane's service
# account may invoke it. Without this every MCP call and every /dcproxy request
# is refused, which surfaces as "no data" and blank charts.
# THE grant that makes a private data plane work: the app plane's service
# account may invoke it. Without this every MCP call and every /dcproxy request
# is refused, which surfaces as "no data" and blank charts rather than as an
# obvious permissions error.
#
# Two variants, because the service is ours on CDC and Google's on DCP -- but
# the binding is identical either way, and both are scoped to a single service,
# so unlike the project-level IAP bindings these are safe to hold in two
# Terraform states at once.
resource "google_cloud_run_v2_service_iam_member" "app_invokes_data" {
  count = local.is_cdc ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dc_data_service[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.app.email}"
}

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

# Humans reach the app plane, not the data plane. Replaces a hardcoded
# individual account, which meant a rebuild from state alone produced a service
# only one person could open.
# Public exposure, opt-in. Scoped to the app plane only -- the data plane stays
# ingress=internal in every mode, so this cannot expose Mixer, MCP or the Flask
# pages however it is set.
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
# Create out-of-band in Stage 1 with:
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

output "cloudsql_connection_name" {
  description = "Connection name for the Cloud SQL instance, used by env CLOUDSQL_INSTANCE."
  value       = local.is_cdc ? google_sql_database_instance.dc[0].connection_name : ""
}

output "config_bucket" {
  description = "Per-instance GCS config bucket (object-versioned, public read for branding.json access)."
  value       = data.google_storage_bucket.config.name
}

output "data_bucket" {
  description = "GCS data bucket for the upstream ingest job."
  value       = local.is_cdc ? google_storage_bucket.data[0].name : ""
}

output "runtime_service_account" {
  description = "Email of the runtime SA. Reference in any per-instance IAM grants."
  value       = google_service_account.datacommons.email
}

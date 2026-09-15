# Inputs for the Custom Data Commons multi-container Cloud Run module.
# Per-instance tfvars override these in deploy/terraform-custom-datacommons/<instance>.tfvars.

variable "project_id" {
  description = "GCP project ID hosting the Cloud Run service and Cloud SQL. Each state instance can share a platform project or get its own; the module is project-agnostic."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Cloud SQL, Artifact Registry, GCS, Secret Manager replication. Pick one close to the user base."
  type        = string
  default     = "us-central1"
}

variable "instance" {
  description = "Short instance namespace, e.g. \"india\", \"karnataka\". Used to name resources and (with var.region) the Cloud Run service URL."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.instance))
    error_message = "instance must be a DNS-safe lowercase label (RFC 1123)."
  }
}

variable "dc_web_service_image" {
  description = "Artifact Registry path to the services overlay image (image/Dockerfile output). Tag is the short git SHA from build.sh."
  type        = string
}

variable "dc_agent_image" {
  description = "Artifact Registry path to the sidecar agent image (agent/Dockerfile output)."
  type        = string
}

variable "brand_config_url" {
  description = "HTTPS URL (no trailing slash) where this instance's config bucket contents are served, e.g. https://storage.googleapis.com/<project>-config. The React UI fetches branding.json from this base; the agent fetches agent-config.json. Points at the bucket ROOT — no <instance>/v1/ subpath."
  type        = string
}

variable "agent_config_mode" {
  description = "Whether the agent serves a writable config panel (dev) or hides it (prod). Identical schema in both modes."
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["dev", "prod"], var.agent_config_mode)
    error_message = "agent_config_mode must be \"dev\" or \"prod\"."
  }
}

variable "timezone" {
  description = "IANA timezone the agent uses when rendering {{CURRENT_DATETIME}}. Override per-instance (e.g. \"Asia/Kolkata\" for India)."
  type        = string
  default     = "UTC"
}

variable "cloudsql_tier" {
  description = "Cloud SQL machine tier. db-g1-small is a reasonable POC default; bump to db-custom-2-7680 for production load."
  type        = string
  default     = "db-g1-small"
}

variable "cloudsql_availability_type" {
  description = "Cloud SQL availability mode. REGIONAL is HA (multi-zone); ZONAL is single-zone (cheaper, no failover)."
  type        = string
  default     = "REGIONAL"
  validation {
    condition     = contains(["REGIONAL", "ZONAL"], var.cloudsql_availability_type)
    error_message = "cloudsql_availability_type must be REGIONAL or ZONAL."
  }
}

variable "min_instances" {
  description = "Cloud Run min instances. min=1 eliminates cold starts; min=0 saves cost when idle."
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Cloud Run max instances. Cap on autoscale headroom."
  type        = number
  default     = 10
}

variable "services_cpu" {
  description = "vCPU for the services container."
  type        = string
  default     = "2"
}

variable "services_memory" {
  description = "Memory for the services container."
  type        = string
  default     = "2Gi"
}

variable "agent_cpu" {
  description = "vCPU for the agent sidecar container."
  type        = string
  default     = "1"
}

variable "agent_memory" {
  description = "Memory for the agent sidecar container."
  type        = string
  default     = "512Mi"
}

variable "allowed_origin" {
  description = "Comma-separated CORS origins for the agent. In single-URL Cloud Run deployments, set this to the Cloud Run service URL (or custom domain). Default \"*\" is fine for dev but should be tightened in prod."
  type        = string
  default     = "*"
}

variable "alert_notification_channels" {
  description = "Cloud Monitoring notification channel IDs for uptime / error-rate alerts. Leave empty to skip alert creation."
  type        = list(string)
  default     = []
}

variable "config_bucket" {
  description = "Name (not URL) of the per-instance config bucket. Holds branding.json, agent-config.json, prompts/ and assets/ at the bucket root. One bucket per instance — not shared across states. Created out-of-band by deploy.sh before terraform apply."
  type        = string
}

# Explicit per-secret IDs. All four must already exist (created out-of-band)
# with at least one enabled version. The module reads via data sources;
# rotations are an operational task, not a tfstate diff.

variable "dc_api_key_secret_id" {
  description = "Secret Manager ID for DC_API_KEY (Data Commons API)."
  type        = string
}

variable "maps_api_key_secret_id" {
  description = "Secret Manager ID for MAPS_API_KEY (Google Maps)."
  type        = string
}

variable "db_pass_secret_id" {
  description = "Secret Manager ID for the Cloud SQL user password."
  type        = string
}

variable "gemini_api_keys_secret_id" {
  description = "Secret Manager ID for GEMINI_API_KEYS (JSON array of keys for rotation)."
  type        = string
}

# Data-layer overrides — for sharing an existing populated Cloud SQL across
# instances during the POC. Leave empty to use the SQL instance created by
# this module.

variable "cloudsql_instance_override" {
  description = "If set, Cloud Run uses this Cloud SQL connection name instead of the module-created instance. Format: project:region:instance."
  type        = string
  default     = ""
}

variable "db_user_override" {
  description = "If set, Cloud Run uses this DB_USER instead of dc_runtime (created by the module)."
  type        = string
  default     = ""
}

variable "output_dir" {
  description = "OUTPUT_DIR env var for the services container. Use gs:// URL pointing at the data + embeddings bucket. If empty, the per-instance data bucket is used."
  type        = string
  default     = ""
}

variable "input_dir" {
  description = "INPUT_DIR env var. If empty, defaults to the per-instance data bucket."
  type        = string
  default     = ""
}

variable "extra_data_buckets" {
  description = "Additional GCS bucket names the runtime SA should be granted objectViewer on (e.g. a shared cdc-dev data bucket during the POC)."
  type        = list(string)
  default     = []
}

variable "authorized_members" {
  description = <<-EOT
    Who may reach the app plane, as group: or user: principals.

    What they are granted depends on access_mode:
      "iap"      roles/iap.httpsResourceAccessor, scoped to THIS service. They
                 sign in with Google and IAP forwards the request.
      "private"  roles/run.invoker directly, so they can reach the service with
                 an identity token or through `gcloud run services proxy`.
      "public"   nothing -- allUsers already covers everyone. Leave empty.

    Deliberately NOT granted run.invoker in iap mode: that would let a listed
    member bypass IAP by calling the Cloud Run URL directly with an identity
    token, which defeats the sign-in requirement the mode exists for.
  EOT
  type        = list(string)
  default     = []
}

variable "deletion_protection" {
  description = "Whether to enable deletion protection on the Cloud SQL database instance."
  type        = bool
  default     = true
}

variable "force_destroy" {
  description = "Whether to force destroy the GCS data bucket if it contains objects."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# App-plane / data-plane split
# ---------------------------------------------------------------------------

variable "data_plane_ingress" {
  description = <<-EOT
    Cloud Run ingress for the data plane. INGRESS_TRAFFIC_INTERNAL_ONLY is the
    intended setting: the browser reaches the app plane, which proxies here, so
    Mixer/MCP/the Flask pages need no public surface. Widen to
    INGRESS_TRAFFIC_ALL only to debug from outside the VPC.
  EOT
  type        = string
  default     = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  validation {
    condition = contains([
      "INGRESS_TRAFFIC_INTERNAL_ONLY",
      "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER",
      "INGRESS_TRAFFIC_ALL",
    ], var.data_plane_ingress)
    error_message = "data_plane_ingress must be a valid Cloud Run ingress value."
  }
}

variable "app_subnet_cidr" {
  description = "CIDR for the app plane's Direct VPC egress subnet. Must not overlap anything else in the project."
  type        = string
  default     = "10.90.0.0/24"
}

variable "app_min_instances" {
  description = "Minimum app-plane instances. 0 lets it scale to zero; 1 removes cold starts from the chat path."
  type        = number
  default     = 0
}

variable "app_max_instances" {
  description = "Maximum app-plane instances. Sized independently of the data plane — that is the point of the split."
  type        = number
  default     = 10
}

variable "app_concurrency" {
  description = <<-EOT
    Simultaneous requests Cloud Run will send to one app-plane instance.
    Unset, Cloud Run defaults to 80 — and a chat response is an SSE stream held
    open for tens of seconds, so 80 means 80 parked threads on one vCPU. Keep
    this modest and scale out with instances instead.
  EOT
  type        = number
  default     = 12
}


variable "data_concurrency" {
  description = <<-EOT
    Simultaneous requests Cloud Run will send to one data-plane instance.

    Unset, Cloud Run defaults to 80; multiplied by max_instances that is several
    hundred concurrent requests against one Cloud SQL instance with no pool
    sizing configured. Sized deliberately here instead. Raise it on the Spanner
    backend, which has no fixed connection ceiling.
  EOT
  type        = number
  default     = 30
}

# ---------------------------------------------------------------------------
# Which data plane this instance runs against
# ---------------------------------------------------------------------------

variable "data_backend" {
  description = <<-EOT
    Which Data Commons data plane serves this instance.

      "dcp"  (default) Google's Data Commons Platform -- Spanner, managed
             ingestion, no NL server. Provisioned OUTSIDE this module by
             datacommons-cli (see dcp_service_url); nothing here creates it,
             because the Spanner instance, the BigQuery reservation, the
             Workflows orchestrator and the Dataflow flex template are Google's
             artifacts and cannot be reproduced.

      "cdc"  The legacy self-hosted plane -- our services image over Cloud SQL,
             with an ingest Job. Everything is created here.

      "none" No data plane. The app plane talks to public datacommons.org.
             Cheapest; cannot serve your own datasets.

    The app plane is identical in all three cases. It receives a URL and an auth
    mode; it has no notion of which backend is behind them.
  EOT
  type        = string
  default     = "dcp"

  validation {
    condition     = contains(["dcp", "cdc", "none"], var.data_backend)
    error_message = "data_backend must be one of: dcp, cdc, none."
  }
}

variable "dcp_service_url" {
  description = <<-EOT
    Base URL of the DCP services instance, when data_backend = "dcp".

    Comes from `terraform output datacommons_service_url` in the scaffold that
    datacommons-cli generates. Required for "dcp"; ignored otherwise.
  EOT
  type        = string
  default     = ""
}

variable "public_dc_url" {
  description = "Public Data Commons origin, used when data_backend = \"none\"."
  type        = string
  default     = "https://api.datacommons.org"
}

variable "public_dc_web_url" {
  description = "Public Data Commons WEB origin for browser data routes when data_backend = \"none\". Distinct from public_dc_url: api.datacommons.org serves the versioned REST API and /mcp, while the website routes the chart components call (/api/observations/series, /api/place/name, /core/api/...) are only served by datacommons.org."
  type        = string
  default     = "https://datacommons.org"
}

variable "dcp_service_name" {
  description = <<-EOT
    Cloud Run service name of the DCP backend, when data_backend = "dcp".

    From `terraform output datacommons_service_name` in the datacommons-cli
    scaffold (conventionally "<namespace>-dc-datacommons-service"). Needed so
    the app plane's service account can be granted run.invoker on it -- that
    single binding is what makes a private DCP backend reachable.
  EOT
  type        = string
  default     = ""
}

variable "access_mode" {
  description = <<-EOT
    How the APP PLANE is exposed. The data plane is ingress=internal regardless,
    so Mixer, MCP and the Flask pages are never reachable in any mode.

      "public"   allUsers gets run.invoker. Anyone with the URL can use it,
                 including the chat endpoint, which spends Gemini quota on every
                 request. Frequently refused outright by Domain Restricted
                 Sharing -- deploy.sh --preflight checks the org policy before
                 you find out the hard way.

      "iap"      Google sign-in in front of the service. authorized_members get
                 roles/iap.httpsResourceAccessor scoped to this service, and the
                 IAP service agent gets run.invoker so it can forward requests.
                 Requires an OAuth consent screen in the project -- a one-time
                 console step that Terraform cannot do; --preflight checks it.

      "private"  No public binding and no sign-in. authorized_members get
                 run.invoker directly; reach it with
                 `gcloud run services proxy <instance>-app --port=8080`.
  EOT
  type        = string

  validation {
    condition     = contains(["public", "iap", "private"], var.access_mode)
    error_message = "access_mode must be one of: public, iap, private."
  }
}

variable "enable_vpc_egress" {
  description = <<-EOT
    Force Direct VPC egress on or off for the app plane. Leave null to derive it.

    Derived rule: on only when the data plane is a private Cloud Run service --
    that is the sole reason it exists. It is not a free switch: reaching a
    *.run.app host through a VPC requires egress=ALL_TRAFFIC, which routes every
    outbound call through the subnet. Private Google Access covers
    *.googleapis.com (Gemini, GCS, Secret Manager), but a genuinely public host
    like api.datacommons.org becomes unreachable without Cloud NAT.

    Set true when data_backend="dcp" and the DCP service is private -- then add
    Cloud NAT if the agent must also reach non-Google hosts.
  EOT
  type        = bool
  default     = null
}

# Inputs for the Custom Data Commons app-plane Cloud Run module.
# Per-instance tfvars override these in deploy/terraform-custom-datacommons/<instance>.tfvars.

variable "project_id" {
  description = "GCP project ID hosting the Cloud Run service. Each state instance can share a platform project or get its own; the module is project-agnostic."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Artifact Registry, GCS, Secret Manager replication. Pick one close to the user base."
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

# Explicit per-secret IDs. Both must already exist (created out-of-band)
# with at least one enabled version. The module reads via data sources;
# rotations are an operational task, not a tfstate diff.

variable "dc_api_key_secret_id" {
  description = "Secret Manager ID for DC_API_KEY (Data Commons API)."
  type        = string
}

variable "gemini_api_key_secret_id" {
  description = "Secret Manager ID for GEMINI_API_KEY (the bare key, not JSON)."
  type        = string
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

# ---------------------------------------------------------------------------
# App-plane / data-plane split
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Which data plane this instance runs against
# ---------------------------------------------------------------------------

variable "public_dc_url" {
  description = "Public Data Commons origin."
  type        = string
  default     = "https://api.datacommons.org"
}

variable "public_dc_web_url" {
  description = "Public Data Commons WEB origin for browser data routes. Distinct from public_dc_url: api.datacommons.org serves the versioned REST API and /mcp, while the website routes the chart components call (/api/observations/series, /api/place/name, /core/api/...) are only served by datacommons.org."
  type        = string
  default     = "https://datacommons.org"
}

variable "access_mode" {
  description = <<-EOT
    How the APP PLANE is exposed. No mode exposes the data plane.

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

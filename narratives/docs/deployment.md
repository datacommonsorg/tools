# Deployment & Customization Guide

This guide covers configuring, deploying, customizing, verifying, and
troubleshooting a Narratives instance on Google Cloud Run.

For a high-level overview of the application, see
[`../README.md`](../README.md). For local development and testing, see
[`development.md`](development.md). For system architecture and protocols, see
[`architecture.md`](architecture.md).

## Contents

- [Deployment model](#deployment-model)
- [Prerequisites](#prerequisites)
- [Step 1: Configure `config/instance.env`](#step-1-configure-configinstanceenv)
- [Step 2: Bootstrap secrets](#step-2-bootstrap-secrets)
- [Step 3: Deploy to Cloud Run](#step-3-deploy-to-cloud-run)
- [Step 4: Verify the deployment](#step-4-verify-the-deployment)
- [Customizing your instance](#customizing-your-instance)
- [Managing deployments & updates](#managing-deployments--updates)
- [Troubleshooting](#troubleshooting)

## Deployment model

Narratives separates upstream application code from per-instance deployment
configuration using three directories:

| Directory | Purpose | Edit for deployment? |
| :--- | :--- | :--- |
| `defaults/` | Upstream baseline branding, agent config, and system prompts | No |
| `schemas/` | JSON Schemas and example files used to validate configuration | No |
| `config/` | Instance-specific settings and overrides for your deployment | **Yes** |

- **Customizing settings:** Edit files in `config/` to customize your instance.
  Any setting you omit in `config/` falls back to the baseline value in
  `defaults/`.
- **Managing multiple environments:** `config/instance.env` targets one
  deployed instance at a time. Use separate Git branches or clones for staging
  and production environments.

## Prerequisites

Run all deployment commands from the `narratives/` directory.

### Tools and credentials

| Requirement | Notes |
| :--- | :--- |
| Google Cloud project | Billing must be enabled |
| `gcloud` CLI | Authenticate both user credentials (`gcloud auth login`) and Application Default Credentials (`gcloud auth application-default login`) for Terraform |
| `terraform`, `pnpm`, `python3`, `uv` | Required on `PATH` (container images build remotely in Cloud Build; local Docker is not required) |
| Node.js 24 | Compiles the React UI (`nvm use`) |
| [Data Commons API key](https://apikeys.datacommons.org) | Stored in Secret Manager during bootstrap |
| [Gemini API key](https://aistudio.google.com) | Stored in Secret Manager during bootstrap |

### Required IAM roles

The deploying principal needs **Owner**, or the following granular roles on the
target Google Cloud project:

- Service Usage Admin (`roles/serviceusage.serviceUsageAdmin`)
- Service Account Admin (`roles/iam.serviceAccountAdmin`)
- Project IAM Admin (`roles/resourcemanager.projectIamAdmin`)
- Storage Admin (`roles/storage.admin`)
- Cloud Run Admin (`roles/run.admin`)
- Secret Manager Admin (`roles/secretmanager.admin`)

## Step 1: Configure `config/instance.env`

Edit `config/instance.env` to define where the service runs and who can access
it. Do not place API keys or secrets in this file.

| Variable | Required | Description |
| :--- | :--- | :--- |
| `PROJECT_ID` | Yes | Target Google Cloud project ID |
| `REGION` | Yes | Google Cloud region for Cloud Run and storage resources (for example, `us-central1`) |
| `INSTANCE` | Yes | Lowercase, DNS-safe identifier used to prefix all cloud resources and the Terraform state path |
| `ACCESS_MODE` | Yes | Access control mode: `public`, `iap`, or `private` (see [Access modes](#access-modes)) |
| `AUTHORIZED_MEMBERS` | For `iap` & `private` | Comma-separated IAM principals granted access (for example, `user:alice@example.com,group:team@example.com`) |
| `PUBLIC_DC_URL` | No | Data Commons API and MCP host used by the backend agent (defaults to `https://api.datacommons.org`) |

### Access modes

`ACCESS_MODE` controls how the Cloud Run service is exposed:

#### `public`

Grants `roles/run.invoker` to `allUsers` so anyone with the URL can access the
application without signing in.

> [!WARNING]
> Before choosing `public`:
> - **Set Gemini API spend limits:** Unauthenticated visitors can submit chat
>   queries that consume your Gemini quota.
> - **Verify org policy support:** Run `./deploy.sh --preflight` to confirm your
>   GCP organization permits `allUsers`. If blocked by **Domain Restricted
>   Sharing**, switch `ACCESS_MODE` to `iap` or `private`.

#### `iap`

Places Google Identity-Aware Proxy (IAP) sign-in in front of the Cloud Run
service:

- Principals in `AUTHORIZED_MEMBERS` receive `roles/iap.httpsResourceAccessor`
  scoped to this specific Cloud Run service.
- The IAP service agent receives `roles/run.invoker` so it can forward
  authenticated requests to the container.
- **One-time project prerequisite:** IAP requires an OAuth consent screen in the
  Google Cloud console, which Terraform cannot create automatically.
  `./deploy.sh --preflight` checks for the consent screen and prints the console
  setup URL if it is missing.

#### `private`

Requires IAM authentication with no public access and no browser sign-in flow.
Principals in `AUTHORIZED_MEMBERS` receive `roles/run.invoker` directly and can
access the service through the local `gcloud` proxy:

```sh
gcloud run services proxy <instance>-app --region=<region> --port=8080
```

## Step 2: Bootstrap secrets

Store your Data Commons and Gemini API keys in Google Cloud Secret Manager once
per deployment:

```sh
DC_API_KEY="<your-dc-key>" GEMINI_API_KEY="<your-gemini-key>" \
  ./deploy.sh --bootstrap-secrets
```

`--bootstrap-secrets` reads the keys from the command environment, writes them
to Secret Manager, and never persists them to disk. Subsequent deployments
automatically reference the existing secrets.

## Step 3: Deploy to Cloud Run

1. Run preflight checks to validate credentials, billing, organization policies,
   and IAP prerequisites without creating any resources:

   ```sh
   ./deploy.sh --preflight
   ```

2. (Optional) Preview the Terraform execution plan:

   ```sh
   ./deploy.sh --plan
   ```

   > [!WARNING]
   > For a new deployment, the plan summary should report `0 to change, 0 to
   > destroy`. If Terraform proposes destroying existing resources, stop and
   > verify that `INSTANCE` in `config/instance.env` does not collide with
   > another deployment's state.

3. Run the full deployment:

   ```sh
   ./deploy.sh
   ```

   `./deploy.sh` enables required Google Cloud APIs, provisions the Terraform
   state bucket and Artifact Registry, verifies secrets, builds the UI and
   container image in Cloud Build, syncs the merged `defaults/` + `config/`
   directory to the private config bucket, runs `terraform apply`, and executes
   post-deploy smoke tests. The initial deployment takes approximately 10
   minutes.

### `deploy.sh` command reference

| Task | Command |
| :--- | :--- |
| Run preflight validation checks | `./deploy.sh --preflight` |
| Preview the Terraform plan | `./deploy.sh --plan` |
| Full build and deployment | `./deploy.sh` |
| Update configuration only (`branding.json`, `agent-config.json`, `prompts/`) | `./deploy.sh --config-only --restart` |
| Rebuild and deploy committed code changes (`agent/` and `ui/`) | `./deploy.sh --agent-only` |
| Apply Terraform infrastructure changes only | `./deploy.sh --infra-only` |
| Tear down all Terraform-managed resources | `./deploy.sh --destroy` |

## Step 4: Verify the deployment

Run the post-deploy smoke test suite and inspect `/agent/health`:

```sh
# Public deployment
bash deploy/smoke.sh "$URL"
curl -s "$URL/agent/health" | jq

# Private or IAM-gated deployment
BEARER_TOKEN="$(gcloud auth print-identity-token)" bash deploy/smoke.sh "$URL"
```

In the `/agent/health` response, `mcp.generation` and
`mcp.supports_source_attribution` report the discovered upstream MCP tool
surface.

## Customizing your instance

All visual and behavioral customization lives in `config/`:

```
config/
├── instance.env        Required: GCP project, region, instance, access mode
├── branding.json       Optional: UI identity, theme colors, nav, metrics
├── agent-config.json   Optional: Gemini model, thinking levels, template vars
├── prompts/            Optional: Prompt overrides (classify, mcp, ...)
└── assets/             Optional: Custom logos, favicons, and static assets
```

Both `branding.json` and `agent-config.json` are validated against
`schemas/branding.schema.json` and `schemas/agent-config.schema.json` with
`additionalProperties: false`, so unrecognized or misspelled keys fail
validation immediately during `./deploy.sh`.

### Branding and UI configuration (`config/branding.json`)

You only need to include the keys you want to override in
`config/branding.json`; omitted keys inherit from `defaults/branding.json`:

```json
{
  "instance_name": "Acme Data Commons",
  "logo": "assets/acme.svg",
  "colors": { "primary": "#0B6E8F" }
}
```

| Category | Configurable keys |
| :--- | :--- |
| **Identity** | `instance_name`, `headline`, `tagline`, `logo`, `logo_text`, `logo_height`, `logo_alt`, `favicon` |
| **Theme** | `colors` (`primary`, text, surfaces, borders, `gradient_border_stop_1`–`_4` for the prompt glow ring), `radius` (`card`, `input`, `chip`), `fonts` |
| **Content** | `suggestions` (landing page starter prompts), `footer` (text and links) |
| **Structure** | `navigation` (header links), `metrics.tabs` (Key Metrics dashboard tiles), `analytics.ga_tag_id` |

Starter templates are available in `schemas/`:

- `schemas/branding.neutral.example.json` — Neutral color palette
- `schemas/branding.base-dc.example.json` — Base Data Commons theme
- `schemas/branding.example.json` — Reference listing all supported fields

#### Header navigation (`navigation`)

The `navigation` key supports three distinct states:

| Value in `config/branding.json` | Behavior |
| :--- | :--- |
| Key omitted | Inherits the default navigation links from `defaults/branding.json` |
| `[]` (empty array) | Hides the header navigation menu completely |
| `[{"label": "...", "href": "..."}, ...]` | Renders the specified navigation links |

### System prompts (`config/prompts/*.md`) and template variables

System prompts for query classification (`classify.md`), the MCP tool loop
(`mcp.md`), answer synthesis (`synthesis.md`), and follow-up generation
(`follow_up.md`) can be overridden in `config/prompts/`. When customizing
prompts, start from the baseline files in `defaults/prompts/` and add your
domain or regional guidance.

The default prompts in `defaults/prompts/*.md` are always loaded first. A file
in `config/prompts/` (uploaded to the config bucket by `./deploy.sh`) replaces
the default prompt for that slot, and a non-empty `prompts.<slot>` entry in
`agent-config.json` replaces both. If a prompt object in the bucket is missing,
fails to download, or is empty once its HTML comments are stripped, the default
prompt applies to that slot and the agent logs a warning naming it, so a
bucket-side failure never leaves a phase without its system instruction.

`classify.md` governs the admission phase that runs at the start of every turn
to decide whether a question is served, refused, or answered with a
clarification question, and which analytical pattern it follows. The classify
phase runs on the model configured in `gemini.classify_model` in
`agent-config.json` (which defaults to `gemini-3.5-flash-lite`), while the tool
loop, synthesis, chart selection, and follow-up generation use
`gemini.mcp_model`.

Prompts support runtime template placeholders:

| Placeholder | Substitution |
| :--- | :--- |
| `{{CURRENT_DATETIME}}` | Current date and time in the `TIMEZONE` environment variable's zone |
| `{{instance.<key>}}` | Matching key from `template_vars` in `agent-config.json` (keys starting with `_` are ignored) |

For example, given `config/agent-config.json`:

```json
{
  "template_vars": {
    "name": "Example Data Commons",
    "region": "the world",
    "states_term": "regions",
    "fiscal_year_start": "01-01"
  }
}
```

A prompt containing `**Deployment**: {{instance.name}}, covering
{{instance.region}}.` renders with those values before being sent to Gemini. Any
placeholder without a matching key in `template_vars` is left unchanged so
missing variables are immediately visible during testing.

### Applying configuration changes

To push changes in `config/` without rebuilding the container image or running
Terraform:

```sh
./deploy.sh --config-only --restart
```

Always include `--restart`. The agent loads configuration into memory once at
startup, so syncing the GCS config bucket takes effect only when a new Cloud Run
revision starts.

## Managing deployments & updates

### Running multiple deployments in one project

Each deployment uses `INSTANCE` in `config/instance.env` to namespace its Cloud
Run service, service accounts, buckets, and Terraform state prefix. Multiple
clones (such as `acme-staging` and `acme-prod`) can safely share a single Google
Cloud project. Before applying or destroying resources, `./deploy.sh` verifies
that the remote Terraform state belongs to the configured `INSTANCE`.

### Keeping a deployment repository private

If you commit `config/instance.env` to a repository to track your deployment
settings, keep that repository **private** — `config/instance.env` records your
Google Cloud project ID, region, and `AUTHORIZED_MEMBERS` emails.

### Pulling upstream updates

If you have modified only files under `config/`, you can pull upstream code and
default updates without merge conflicts:

```sh
git remote add upstream https://github.com/datacommonsorg/tools.git   # once
git pull upstream main
./deploy.sh
```

### Tearing down a deployment

To destroy all Terraform-managed resources for the instance:

```sh
./deploy.sh --destroy
```

For safety, `--destroy` prompts you to confirm the instance name and leaves the
GCS config bucket and Secret Manager entries intact so you can redeploy later
without re-entering API keys. Delete the bucket and secrets manually in Google
Cloud if you want to remove them permanently.

## Troubleshooting

### Deployment & configuration

**`No configuration at 'config/instance.env'` or
`config/instance.env is incomplete`**

Restore the file if missing (`git checkout config/instance.env`), fill in all
required variables (`PROJECT_ID`, `REGION`, `INSTANCE`, and `ACCESS_MODE`), and
run `./deploy.sh --preflight`.

**`These secrets have no value in Secret Manager`**

API keys have not been initialized for this instance yet. Run
`DC_API_KEY="..." GEMINI_API_KEY="..." ./deploy.sh --bootstrap-secrets` (see
[Step 2: Bootstrap secrets](#step-2-bootstrap-secrets)).

**`Refusing to apply: the state loaded for 'x' describes another instance`**

The remote Terraform state prefix belongs to a different deployment. Verify that
`INSTANCE` in `config/instance.env` matches the intended environment before
re-running `./deploy.sh`.

**Changes to `branding.json`, `agent-config.json`, or `prompts/` do not appear**

The agent reads configuration only once at container startup. Run
`./deploy.sh --config-only --restart` so Cloud Run starts a new revision with
the updated configuration.

**Code changes deployed with `--agent-only` do not take effect**

Container images are tagged with `git rev-parse --short HEAD`, so uncommitted
changes reuse the existing image tag. Commit your changes first, then re-run
`./deploy.sh --agent-only`.

**Header navigation tabs are missing**

`navigation` is set to `[]` in `config/branding.json`, which hides the header
menu. Remove the `navigation` key to restore the default links, or provide an
array of `{"label": "...", "href": "..."}` objects.

### Authentication & access

**Deployment succeeds in `public` mode, but all requests return `403`**

Your Google Cloud organization enforces **Domain Restricted Sharing**, which
blocks the `allUsers` IAM binding. Set `ACCESS_MODE=iap` or
`ACCESS_MODE=private` in `config/instance.env` and redeploy.

**Users cannot sign in when `ACCESS_MODE=iap`**

The Google Cloud project does not have an OAuth consent screen configured yet.
Run `./deploy.sh --preflight` and open the printed Google Cloud console link to
configure the consent screen once for the project.

**Requests return `403` *after* signing in with IAP**

The IAP service agent is missing `roles/run.invoker` on the Cloud Run service.
Re-run `./deploy.sh --infra-only` and verify that the `iap_agent_invoker`
binding is present in the Terraform plan.

### Monitoring

**External uptime checks against `/healthz` fail**

Cloud Run intercepts `/healthz` at the frontend layer and does not forward it to
the container. Configure external uptime checks to query `/agent/health`
instead.

### Inspecting Cloud Run logs

For further diagnostics, inspect the Cloud Run service logs. Each completed chat
turn writes a structured `chat_turn` JSON log entry keyed by `turn_id`,
containing the terminal state, error reason (if any), phase latencies, MCP tool
names, token usage, and the analytical `pattern` assigned by the `classify`
phase (user query text is never logged). On a `refused` turn, `error_type` holds
the refusal reason (`adversarial`, `off_domain`, or `safety_blocked`) and
`pattern` is omitted; if the classifier call itself fails, the turn falls
through with `pattern` set to `exploratory`.

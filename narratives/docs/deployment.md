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
| Node.js 24.22.1 or later 24.x | Compiles the React UI (`nvm use`) |
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
| `DC_WEB_COMPONENT_URL` | No | Browser-side chart web component bundle URL (defaults to `https://datacommons.org/datacommons.js`) |
| `DC_WEB_COMPONENT_API_ROOT` | No | Origin the chart web components fetch data from (defaults to `https://datacommons.org`) |

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
| Update configuration only (`theme.json`, `agent-config.json`, `prompts/`) | `./deploy.sh --config-only --restart` |
| Rebuild and deploy committed code changes (`agent/` and `ui/`) | `./deploy.sh --agent-only` |
| Apply Terraform infrastructure changes only | `./deploy.sh --infra-only` |
| Deploy over a renamed service (its URL changes) | `./deploy.sh --accept-service-rename` |
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

Among its checks, `deploy/smoke.sh` confirms that the HTML shell carries a
`Content-Security-Policy` with `frame-ancestors` and with neither
`'unsafe-inline'` nor `'unsafe-eval'` in `script-src`, and that `/agent/health`
carries the HTTP security headers (see
[architecture.md](architecture.md#http-security-headers)).

In the `/agent/health` response, `mcp.support`,
`mcp.supports_source_attribution`, and `mcp.missing_tools` report the upstream
MCP tool surface. The agent requires six tools (`search_indicators`,
`search_child_indicators`, `get_variable_metadata`, `get_observations`,
`get_child_observations`, and `get_multi_entity_observations`), and
`mcp.missing_tools` lists any that are missing. `mcp.support` is one of three
values:

- `supported`: all six required tools are available.
- `unsupported`: the server lists tools, but at least one required tool is
  missing.
- `unknown`: the tool list is empty, either because it has not been loaded yet
  (for example, on a fresh instance before the first fetch finishes) or because
  the server listed no tools. In both cases, `mcp.missing_tools` lists all six
  tools.

When required tools are missing, the agent logs a warning on every chat turn
and continues the turn with the tools the server provides, and
`deploy/smoke.sh` fails its capability check.

The `/agent/health` response also reports `debug_report` (`"off"`, `"flag"`, or
`"on"`), the effective turn debug report mode: `DEBUG_REPORT` when it is set,
and otherwise `debug.report` in `agent-config.json` (see
[Turn debug reports](#turn-debug-reports-debug_report-and-build_sha)).

## Customizing your instance

All visual and behavioral customization lives in `config/`:

```
config/
├── instance.env        Required: GCP project, region, instance, access mode
├── theme.json          Optional: UI identity, theme colors, nav, metrics
├── agent-config.json   Optional: Gemini models, thinking, template vars, chat
├── prompts/            Optional: Prompt overrides (classify, discovery, ...)
└── assets/             Optional: Custom logos, favicons, and static assets
```

Both `theme.json` and `agent-config.json` are validated against
`schemas/theme.schema.json` and `schemas/agent-config.schema.json` with
`additionalProperties: false`, so unrecognized or misspelled keys fail
validation immediately during `./deploy.sh`.

### Branding and UI configuration (`config/theme.json`)

You only need to include the keys you want to override in
`config/theme.json`; omitted keys inherit from `defaults/theme.json`:

```json
{
  "instance_name": "Acme Data Commons",
  "logo": "https://acme.example/acme.svg",
  "colors": { "primary": "#0B6E8F" }
}
```

| Category | Configurable keys |
| :--- | :--- |
| **Identity** | `instance_name`, `headline`, `tagline`, `tagline_link`, `logo`, `logo_text`, `logo_height`, `logo_alt`, `logo_href`, `favicon` |
| **Theme** | `colors` (`primary`, text, surfaces, borders, `gradient_border_stop_1`–`_4` for the prompt glow ring), `radius` (`card`, `input`, `chip`), `fonts` |
| **Content** | `suggestions` (landing page starter prompts), `footer` (text and links) |
| **Structure** | `navigation` (header links), `metrics.tabs` (Key Metrics dashboard tiles), `analytics.ga_tag_id` |

`logo`, `favicon`, and the `splash_assets` indicators take a same-origin path
starting with a single `/` or an http(s) URL. `navigation` and `footer` link
targets and `logo_href` also accept a `#` route. Validation during
`./deploy.sh` rejects any other value, such as `assets/logo.png`.

`logo_href` sets where the header logo links, `/` by default. When the app is
served at the site root, the logo links only to an http(s) URL, since a
same-origin link would reload the app and clear the current chat.

Starter templates are available in `schemas/`:

- `schemas/theme.neutral.example.json`: Neutral color palette
- `schemas/theme.base-dc.example.json`: Base Data Commons theme
- `schemas/theme.example.json`: Reference listing all supported fields

#### Header navigation (`navigation`)

The `navigation` key supports three distinct states:

| Value in `config/theme.json` | Behavior |
| :--- | :--- |
| Key omitted | Inherits the default navigation links from `defaults/theme.json` |
| `[]` (empty array) | Hides the header navigation menu completely |
| `[{"label": "...", "href": "..."}, ...]` | Renders the specified navigation links |

### System prompts (`config/prompts/*.md`) and template variables

System prompts for query classification (`classify.md`), the discovery tool loop
(`discovery.md`), answer synthesis (`synthesis.md`), and follow-up generation
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

`discovery.md` holds the domain and geographic guidance for the discovery phase
(the agent's role and geographic defaults). The tool surface, the fetch and
specification workflow, the analytical scripts, and the fallback rules live in a
code-owned contract (`workflows/contracts/discovery.md`, composed by
`workflows/prompt_contracts.py`) and per-pattern directives
(`workflows/pattern_guidance.py`) that the server appends after the configured
`discovery` prompt on every request and that cannot be overridden. An override
in `config/prompts/discovery.md` should add instance-specific domain and
regional guidance rather than restating the tool or specification rules.

`synthesis.md` holds the narrative role, input description, and grounding rules
for the synthesis phase. The `[n]` and `[n, m]` citation markers, answer-writing
rules, and fenced `chart` block grammar live in a code-owned contract
(`workflows/contracts/synthesis.md`, composed by `workflows/prompt_contracts.py`
together with the per-pattern synthesis directive from
`workflows/pattern_guidance.py`) that the server appends after the configured
`synthesis` prompt on every request and that cannot be overridden. So does the
answer's title line: its format and the rule that it names only the data the
answer presents live in `workflows/contracts/synthesis_title.md`, while the
"Title rules" section of `synthesis.md` holds only editorial guidance on its
wording, which an override may replace. An override
in `config/prompts/synthesis.md` should add instance-specific tone, domain, or
grounding guidance rather than restating the citation or chart-block grammar.

`classify.md` governs the admission phase that runs at the start of every turn
to decide whether a question is served, refused, or answered with a
clarification question, and which analytical pattern it follows. A short
code-owned contract (`workflows/contracts/classify.md`) is appended after it on
every request and tells the model which current date to use. Each LLM stage
reads its own model key under `gemini` in `agent-config.json`:
`gemini.classify_model` (default `gemini-3.5-flash-lite`), and
`gemini.discovery_model`, `gemini.synthesis_model`, `gemini.follow_up_model`,
and `gemini.compaction_model` (each defaulting to `gemini-3.8-flash`).

Prompts support runtime template placeholders:

| Placeholder | Substitution |
| :--- | :--- |
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

### Chart hosts (`DC_WEB_COMPONENT_URL` and `DC_WEB_COMPONENT_API_ROOT`)

Charts are drawn in the browser by the Data Commons web components, which the
browser loads and which fetch their own data, without passing through the
agent. Two environment variables on the container set the hosts they use:

| Variable | Default | Sets |
| :--- | :--- | :--- |
| `DC_WEB_COMPONENT_URL` | `https://datacommons.org/datacommons.js` | Script URL |
| `DC_WEB_COMPONENT_API_ROOT` | `https://datacommons.org` | Data origin |

`DC_WEB_COMPONENT_URL` is the full URL of `datacommons.js`.
`DC_WEB_COMPONENT_API_ROOT` is the origin the charts fetch their data from,
passed to each component as its `apiroot`. It must name a Data Commons website
host, such as `https://datacommons.org`, not `https://api.datacommons.org`,
which requires an API key that the browser cannot hold. A custom Data Commons
that serves its own data sets it to the instance's own host.

The server stamps both values into the page, so a change needs a restart but
no UI rebuild. The page's `Content-Security-Policy` allows scripts from the
origin of `DC_WEB_COMPONENT_URL` and connections to
`DC_WEB_COMPONENT_API_ROOT`, so the browser blocks a chart host that these
variables do not name.

The server refuses to start when either value is malformed.
`DC_WEB_COMPONENT_URL` must be an absolute `http` or `https` URL with a
hostname. `DC_WEB_COMPONENT_API_ROOT` must be an `http` or `https` origin: a
scheme, a hostname, and an optional port, with no path other than a trailing
slash (which is removed), no query, and no fragment. In both, the hostname is
ASCII letters, digits, hyphens, and dots (no wildcard, percent-encoding, or
IPv6 literal), a port, when present, is a number, and the value contains no
user information, whitespace, semicolon, comma, quote, or control character,
so that it is also a valid source in a response header.

The autopush and staging deployments must set both variables to their own
hosts (for example `https://autopush.datacommons.org/datacommons.js` and
`https://autopush.datacommons.org`) to show their own data; with the defaults,
their charts show production data.

- **Cloud Run:** set `DC_WEB_COMPONENT_URL` and `DC_WEB_COMPONENT_API_ROOT` in
  `config/instance.env` and apply with `./deploy.sh --infra-only` (which passes
  them into Terraform's `dc_web_component_url` and `dc_web_component_api_root`
  variables). Out-of-band updates via `gcloud run services update` take effect
  immediately, as with `ENABLE_CHAT` below, and are overwritten on the next
  `./deploy.sh` run unless mirrored in `config/instance.env`.

- **GKE (`datacommons-website`):** set the variables in the Narratives Helm
  values for the environment.
- **Local development:** set them in `.env.local` (see
  `.env.local.example`).

### Disabling chat (emergency off switch)

You can temporarily disable new chat turns while keeping the static React UI,
Key Metrics dashboard, and shared stories online — for example, during:

- **Unexpected traffic spikes or runaway model spend:** Automated scraping or
  burst traffic driving up Gemini token usage or exhausting project quota.
- **Upstream service outages:** Sustained errors or latency in Vertex AI /
  Gemini or the Data Commons MCP server where failing fast is preferable to
  hanging requests.
- **Safety or quality incidents:** Investigating a prompt-injection vector or a
  regression in generated answers without taking down the entire site.

Chat availability is set by `chat.enabled` (default `true`),
`chat.unavailable_title` (default `"High demand right now"`), and
`chat.unavailable_message` in `config/agent-config.json`. The default message
is:

```text
Due to high traffic, this feature is temporarily paused. Capacity is being scaled to restore service as quickly as possible. Please try again later, or explore other [tools in Data Commons](https://datacommons.org).
```

The Data Agent route shows the message under the plain-text heading
`chat.unavailable_title`, over a page whose header and navigation are disabled,
and the message is also the error of any chat turn sent while chat is disabled.
In both places where the message appears, Markdown links (`[label](https://…)`)
render as links and other Markdown renders as plain text. Include at least one
link in `chat.unavailable_message`, because it is the only way off the Data
Agent route:

```json
{
  "chat": {
    "enabled": false,
    "unavailable_title": "Scheduled maintenance",
    "unavailable_message": "Chat is paused for maintenance until 14:00 UTC. See [Data Commons](https://datacommons.org)."
  }
}
```

The agent reads these values at startup, so apply a change with
`./deploy.sh --config-only --restart`. A `chat` value that is not an object,
or a `chat.enabled` that is not a JSON boolean (for example `"false"` or `0`),
is logged as an error and disables chat.

While chat is enabled, the server also sends `chat.unavailable_message`,
without a retry button, when an instance's daily Gemini token budget is
exhausted or when a turn's query permanently cannot be screened
(`reason: "model_armor_unavailable"` or `"classifier_unavailable"`, see
[Monitoring](#monitoring)). If you set a time-specific maintenance notice in
`chat.unavailable_message` or `UNAVAILABLE_MESSAGE` while disabling chat, reset
or clear it when re-enabling chat so later non-retryable turns do not display
stale maintenance text.

The `ENABLE_CHAT`, `UNAVAILABLE_TITLE`, and `UNAVAILABLE_MESSAGE` environment
variables override these values when set, in either direction, and take effect
without a configuration sync. Setting `ENABLE_CHAT=true` forces chat on
regardless of `chat.enabled`, so remove the variable to return control to
`agent-config.json`. While chat is disabled, `POST /agent/chat/stream`
immediately returns a terminal error event (`reason: "chat_disabled"`,
`is_retryable: false`) carrying the unavailable message, before invoking the
classifier, MCP tool loop, or synthesis models, so the UI shows the message
without a retry button. The server stamps the effective `enable_chat`,
`unavailable_title`, and `unavailable_message` values into the
`#runtime-config` element of the HTML shell on every request. On page load,
the UI reads that element through `getRuntimeConfig()` and replaces the chat
prompt with an unavailable view showing `unavailable_title` and
`unavailable_message` over a disabled header and navigation bar, while other
routes such as Key Metrics (`#/metrics`) remain reachable by URL. A local
`pnpm dev:ui` copies the element from the agent at `AGENT_URL`, so set
`ENABLE_CHAT`, `UNAVAILABLE_TITLE`, and `UNAVAILABLE_MESSAGE` on the agent,
since Vite does not read them. `/healthz` and `/agent/health` keep answering
`200`.

- **Cloud Run:**

  ```sh
  # Disable chat immediately
  gcloud run services update <instance>-app --region=<region> \
    --update-env-vars=ENABLE_CHAT=false

  # Remove the override so `chat.enabled` in agent-config.json applies again
  gcloud run services update <instance>-app --region=<region> \
    --remove-env-vars=ENABLE_CHAT
  ```

- **GKE (`datacommons-website`):**

  ```sh
  # Disable chat immediately (<30s rollout, no PR required)
  kubectl set env deployment/website-agentic-apps -n website \
    -c discover ENABLE_CHAT=false

  # Remove the override so `chat.enabled` in agent-config.json applies again
  kubectl set env deployment/website-agentic-apps -n website \
    -c discover ENABLE_CHAT-
  ```

  To keep chat disabled across subsequent Cloud Deploy releases on GKE, also
  set `agentic.discover.enableChat: false` in
  `deploy/helm_charts/envs/<env>.yaml` in the `datacommons-website` repository.
  An `ENABLE_CHAT` value that the deployment always sets, such as `true`, takes
  precedence over `chat.enabled` in `agent-config.json`.

### Daily Gemini token budget (optional)

Set `DAILY_TOKEN_BUDGET_PER_INSTANCE` to a positive integer to cap the total
Gemini tokens (`total_token_count`, including prompt, output, and thinking
tokens) that each agent instance may spend per UTC calendar day. When the
variable is unset or blank, budget enforcement is disabled. A zero, negative,
or non-integer value fails startup validation so a misconfigured deployment
does not start unguarded.

Once an instance reaches or exceeds its daily limit, `POST /agent/chat/stream`
immediately ends new turns with a non-retryable terminal error frame
(`reason: "daily_token_budget_exhausted"`, `is_retryable: false`) carrying the
effective `chat.unavailable_message` (or `UNAVAILABLE_MESSAGE`), before calling
Model Armor, Gemini, or MCP. `/healthz` and `/agent/health` keep answering
`200`. In a multi-replica environment, an exhausted instance still receives
routed requests and returns this error even while sibling replicas still have
tokens remaining for the day; uneven errors are expected under per-instance
tracking until global token tracking is introduced.

Turns already in flight finish and record tokens from their completed Gemini
calls in `finally`. Because the SDK reports token counts only on the final
chunk of a streamed call or after a non-streaming call returns, tokens from
streams canceled by client disconnect before the final chunk or from timed-out
model calls are not added to the instance's counter even though Gemini or
Vertex AI may bill them. The `chat_turn` record of a turn counts its
discovery and synthesis calls that were cut off in this way in
`tokens.interrupted_stream_calls` (see
[The `chat_turn` record](#the-chat_turn-record)). Counters reset
automatically when the UTC date advances.

- **Cloud Run:**

  ```sh
  # Set a per-instance daily token cap
  gcloud run services update <instance>-app --region=<region> \
    --update-env-vars=DAILY_TOKEN_BUDGET_PER_INSTANCE=<tokens>

  # Disable token-budget enforcement
  gcloud run services update <instance>-app --region=<region> \
    --remove-env-vars=DAILY_TOKEN_BUDGET_PER_INSTANCE
  ```

  `deploy/terraform-custom-datacommons/modules/main.tf` manages container `env`
  without `ignore_changes` and does not yet include
  `DAILY_TOKEN_BUDGET_PER_INSTANCE`. Until it is wired through
  `config/instance.env` and Terraform, the next `./deploy.sh` run (including
  `--agent-only` or `--infra-only`) drops an out-of-band value and leaves the
  service uncapped.

- **GKE (`datacommons-website`):**

  ```sh
  # Set or adjust the per-instance cap immediately (restarts pods)
  kubectl set env deployment/website-agentic-apps -n website \
    -c discover DAILY_TOKEN_BUDGET_PER_INSTANCE=<tokens>

  # Disable token-budget enforcement
  kubectl set env deployment/website-agentic-apps -n website \
    -c discover DAILY_TOKEN_BUDGET_PER_INSTANCE-
  ```

  Out-of-band `kubectl set env` changes are overwritten on subsequent Cloud
  Deploy releases unless the budget is configured in the environment's
  `datacommons-website` Helm values.

- **Sizing across replicas and Cloud Run scale-to-zero:** Counters live in
  process memory (one Uvicorn worker per container). For fixed-replica GKE
  deployments, set the per-instance cap to `global daily cap / replicas`; pod
  restarts, rollouts, or changing the variable via `kubectl set env` reset each
  restarted instance's counter to zero for the current UTC day. On Cloud Run,
  where `app_min_instances` defaults to `0` and the service scales down and
  starts fresh containers at zero repeatedly over a day, the cap bounds tokens
  per container instance lifetime (at most one UTC day) rather than total daily
  service spend. Pair this cap with a project-level Vertex AI token alert or
  quota to bound total daily spend, and use `ENABLE_CHAT=false` for an
  immediate stop across all instances.
- **Model and thinking-level changes:** Because the budget counts tokens rather
  than dollars, re-size `DAILY_TOKEN_BUDGET_PER_INSTANCE` (and any project-level
  Vertex AI alert threshold) whenever changing Gemini models or raising thinking
  levels in `agent-config.json`.
- **Threshold telemetry:** Each instance emits at most one structured
  `daily_token_budget` JSON record to stdout at 80% usage (`state: "warning"`,
  severity `WARNING`) and one at 100% (`state: "exhausted"`, severity `ERROR`)
  per UTC day, suitable for Cloud Logging alerts.

### Screening prompts with Google Cloud Model Armor (optional)

By default, Narratives screens incoming queries with its built-in regex
pre-filter (`workflows/prefilter.py`) and Gemini's safety filters. To add
[Google Cloud Model Armor](https://cloud.google.com/security-command-center/docs/model-armor-overview)
screening before the `classify` Gemini call:

1. Enable the Model Armor API (`modelarmor.googleapis.com`) and create a Model
   Armor template in your Google Cloud project (for example, in `us-central1`).
2. Grant `roles/modelarmor.user` to the runtime service account
   (`<instance>-app` on Cloud Run, or the GKE Workload Identity service
   account).
3. Set the `MODEL_ARMOR_TEMPLATE` environment variable on the container to the
   template's resource path
   (`projects/<project>/locations/<location>/templates/<template>`).

When `MODEL_ARMOR_TEMPLATE` is unset, Model Armor screening is skipped. When
set, it works with both `GEMINI_API_KEY` and Vertex AI deployments.

Once `MODEL_ARMOR_TEMPLATE` is set, chat depends on Model Armor being
available in the template's region. A turn that Model Armor cannot screen
ends with an error (`reason: "model_armor_unavailable"`) rather than
continuing unscreened. Transient failures (timeouts, network or token-refresh
errors, HTTP 408/429/499/5xx, and responses that are neither a match nor a
complete pass) are retryable. Permanent rejections (other HTTP 4xx statuses
such as 403 or 404, and missing Application Default Credentials) return
`chat.unavailable_message` without a retry button. A complete pass reports
`filterMatchState` `NO_MATCH_FOUND` and `invocationResult` `SUCCESS`, so a
response in which some filters did not run, or that omits either field, ends
the turn. See [Monitoring](#monitoring) for the log filter that finds these
turns.

### Protecting traffic with reCAPTCHA Enterprise (optional)

Public deployments behind Cloud Armor or an external Application Load Balancer
can configure Google Cloud reCAPTCHA Enterprise public site keys through
optional container environment variables:

- `RECAPTCHA_SESSION_SITE_KEY`: Public WAF session-token site key injected as
  `recaptcha_session_site_key` in `#runtime-config`. When set and chat is
  enabled, the UI loads Google's `enterprise.js?render=<key>&waf=session`
  script on the Data Agent view so browsers silently mint and refresh the
  `recaptcha-ca-t` session cookie.
- `RECAPTCHA_CHECKBOX_SITE_KEY`: Public WAF checkbox site key injected as
  `recaptcha_checkbox_site_key` in `#runtime-config`. When set and a chat
  `POST /agent/chat/stream` returns HTTP `403`, the UI pauses the pending turn,
  opens an in-app checkbox verification dialog (`RecaptchaModal`), caches the
  solved token in memory for 25 minutes, and retries the same request once with
  the `X-Recaptcha-Token` header. Subsequent turns within that 25-minute window
  attach the cached `X-Recaptcha-Token` automatically; any HTTP `403` clears
  the cached token.

When serving `index.html`, the backend includes any non-empty
`RECAPTCHA_SESSION_SITE_KEY` and `RECAPTCHA_CHECKBOX_SITE_KEY` values inside
`<script id="runtime-config" type="application/json">` alongside `enable_chat`,
`unavailable_title`, `unavailable_message`, and the chart hosts, recomputing
the response `ETag`.
When both variables are unset or blank, those keys are omitted from
`#runtime-config`.

When either reCAPTCHA site key is configured at startup, `spa.py` automatically
adds Google's reCAPTCHA endpoints to the HTML shell's `Content-Security-Policy`
(`script-src`, `frame-src`, and `connect-src`) — and omits them when neither
key is set:

- `https://www.google.com/recaptcha/`
- `https://www.gstatic.com/recaptcha/`
- `https://recaptcha.google.com/recaptcha/`

### Turn debug reports (`DEBUG_REPORT` and `BUILD_SHA`)

The agent can emit a typed `debug_report` SSE frame at the end of each chat
turn to expose operational telemetry, timings, token counts, cached tables,
tool calls, rejected specifications, and prompt hashes.

The report mode is set by `debug.report` (default `"off"`) in
`config/agent-config.json`:

```json
{
  "debug": {
    "report": "flag"
  }
}
```

- `off`: reports are never emitted.
- `flag`: reports are emitted only when the chat request sets `"debug": true`
  (typically via the `?debug` URL parameter in the browser).
- `on`: reports are emitted on every turn and the UI debug drawer opens
  without requiring `?debug`. Because the report carries prompts and
  configuration details, `on` exposes them to every browser.

The agent reads this value at startup, so apply a change with
`./deploy.sh --config-only --restart`. A `debug` value that is not an object,
or a `debug.report` that is not one of the three modes, is logged as an error
and turns the report off.

The `DEBUG_REPORT` environment variable overrides `debug.report` when set, in
either direction, and takes effect without a configuration sync. Setting
`DEBUG_REPORT=off` turns the report off regardless of `debug.report`, so
remove the variable to return control to `agent-config.json`.

- `BUILD_SHA`: Optional commit or build identifier (supplied at build time with
  `--build-arg BUILD_SHA=...` or as a runtime environment variable) surfaced in
  debug reports to identify the deployed revision.

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

**`Refusing to apply: the state loaded describes a different deployment`**

The remote Terraform state prefix belongs to a different deployment. Verify that
`INSTANCE` in `config/instance.env` matches the intended environment before
re-running `./deploy.sh`.

**`Refusing to apply: it DESTROYS the service above and its URL`**

The state holds this deployment's service under the name the module used
before, `<instance>-datacommons`. Applying replaces it with `<instance>-app`,
and the service URL changes. Run `./deploy.sh --plan` to see the plan, then
re-run with `./deploy.sh --accept-service-rename` once the new URL is
acceptable.

**Changes to `theme.json`, `agent-config.json`, or `prompts/` do not appear**

The agent reads configuration only once at container startup. Run
`./deploy.sh --config-only --restart` so Cloud Run starts a new revision with
the updated configuration.

**Code changes deployed with `--agent-only` do not take effect**

Container images are tagged with `git rev-parse --short HEAD`, so uncommitted
changes reuse the existing image tag. Commit your changes first, then re-run
`./deploy.sh --agent-only`.

**Header navigation tabs are missing**

`navigation` is set to `[]` in `config/theme.json`, which hides the header
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

**Chat turns end with an error because a question could not be screened**

A turn ends with an error, before any data is fetched, when Model Armor or the
query classifier cannot screen the question. The `chat_turn` log entry of such
a turn has severity `ERROR` and one of two `outcome_reason` values:

- `model_armor_unavailable`: `MODEL_ARMOR_TEMPLATE` is set and Model Armor
  did not return a complete result. Check that the template exists in its
  region, that the runtime service account holds `roles/modelarmor.user`, and
  that Model Armor is available in that region.
- `classifier_unavailable`: the `classify` Gemini call failed twice, Gemini
  rejected the request permanently (for example, an invalid API key or model
  name), or the `classify` prompt is empty. The Gemini client logs the
  upstream error in a separate entry.

Use this Cloud Logging filter to find these turns or to alert on them:

```text
jsonPayload.event="chat_turn" AND jsonPayload.outcome_reason=("model_armor_unavailable" OR "classifier_unavailable")
```

### Inspecting Cloud Run logs

For further diagnostics, inspect the Cloud Run service logs. The server
writes structured JSON entries to stdout, each on one line. The `chat_turn`
and `transcript_rejected` records start with the keys `severity`, `message`,
`event`, and `schema_version`. `event` names the kind of entry.
`schema_version` changes when a key of that entry is renamed or removed, or
when the type or the meaning of a key changes. Adding a key does not change
it. When `DAILY_TOKEN_BUDGET_PER_INSTANCE` is configured, each instance also
writes `daily_token_budget` JSON entries (`state: "warning"` at 80% and
`state: "exhausted"` at 100%, once each per UTC day, described in
[Daily Gemini token budget](#daily-gemini-token-budget-optional)).

The entries do not contain text from the conversation. The server never logs
the user's query, the answer, the model's thoughts, tool arguments, tool
results, chart titles, or the display names of variables, places, or sources.
Every string in an entry is a code that the server defines, an identifier that
the server creates, a configured model name, the build SHA, the ID of an
analysis step (`s1`, `s2`, and so on), or a verified Data Commons identifier
(DCID), facet ID, place type, or observation date from a fetched table that
returned rows.

A container runtime splits a line that is longer than 16 KiB across multiple
log entries, and Cloud Logging cannot parse a split line as one JSON entry.
The server therefore keeps every `chat_turn` record at 14 KiB or less. When
a record would be longer, the server drops items from the ends of its lists
and names the shortened lists in `truncated_lists` (see the note on
`truncated_lists` below). The part of a record outside those lists is about
2 KiB at most, so the limit holds for every turn. If a structured record of
another kind is longer than 14 KiB, the server writes it anyway and logs a
warning with the name of the record and the size of the line.

#### The `chat_turn` record

The server writes one `chat_turn` record (`schema_version` 2) when a chat
turn ends. It writes the record for turns that complete, turns that it
refuses, turns that fail, turns that the client cancels, and turns that end
because chat is disabled or the instance's daily token budget is exhausted.
Every record has every key. A value that does not apply is `null`, `false`,
`0`, or an empty list.

| Key | Type | Value |
| :--- | :--- | :--- |
| `severity` | string | `ERROR` when the turn failed, otherwise `INFO` |
| `message` | string | `chat turn <terminal_state>` |
| `event` | string | `chat_turn` |
| `schema_version` | integer | `2` |
| `build_sha` | string or null | `BUILD_SHA` of the deployment, up to 256 characters |
| `turn_id` | string | ID that the server creates for the turn |
| `conversation_id` | string | ID of the turn's conversation |
| `turn_index` | integer | Index of the turn in its conversation |
| `is_signed` | boolean | Whether the server signed the turn |
| `was_compacted` | boolean | Whether signing compacted the conversation |
| `terminal_state` | string | `complete`, `refused`, `error`, or `canceled` |
| `outcome` | string | How the turn ended |
| `outcome_reason` | string or null | Reason code of a refused or failed turn |
| `refusal_stage` | string or null | Where the server refused the turn |
| `has_data` | boolean | Whether the turn's analysis produced data |
| `is_clarification` | boolean | Whether the answer is a clarification question |
| `is_truncated` | boolean | Whether the search for data stopped at a limit |
| `title_outcome` | string | `emitted`, `omitted`, or `not_requested` |
| `follow_ups_emitted` | integer | Number of follow-up questions emitted, 0 to 3 |
| `follow_ups_canceled` | boolean | Whether the client disconnected during follow-ups |
| `pattern` | string or null | Analytical pattern from the `classify` phase |
| `duration_ms` | number | Duration of the turn |
| `phase_durations` | list | Duration of each phase that ran |
| `tokens` | object | Token totals of the turn |
| `token_calls` | list | Token counts of each model call |
| `mcp_iterations` | integer | Number of discovery rounds |
| `tool_call_count` | integer | Number of tool calls by the model and the server |
| `tool_call_counts` | list | Number of calls of each tool by each actor |
| `tables_fetched` | integer | Number of observation tables fetched |
| `total_rows_fetched` | integer | Number of observation rows fetched |
| `tables_truncated` | boolean | Whether fetched tables were left out of `tables` |
| `tables` | list | Fetched observation tables that returned rows |
| `highlighted_places` | list | Places that the turn's analysis highlighted |
| `specification_origin` | string or null | `model`, `default`, or `null` |
| `scripts` | list of strings | Analytical scripts that ran, in step order |
| `script_steps` | list | Outcome of each analysis step that ran |
| `processing_retries` | integer | Specifications returned to the model |
| `rejected_submissions` | list | Specifications that the server rejected |
| `charts_emitted` | integer | Charts in the answer |
| `charts_rejected` | integer | Charts that the server dropped |
| `charts` | list | Charts in the answer |
| `chart_rejections` | list | Chart blocks that the server dropped |
| `truncated_lists` | list of strings | Lists that the server shortened |

More detail on some keys:

- **`build_sha`:** The record holds the first 256 characters of a longer
  `BUILD_SHA`.

- **`conversation_id` and `turn_index`:** The turns of one conversation share
  a `conversation_id` (see
  [architecture.md](architecture.md#conversation-id)). `turn_index` is the
  index that the turn has when it is signed. An unsigned turn has the index
  that it would have had, so the next signed turn of the conversation has
  the same index.
- **`was_compacted`:** The value is `true` when signing the turn compacted
  the oldest turns of the conversation into a summary (see
  [architecture.md](architecture.md#keeping-conversation-history-compact)).
- **`outcome`:** The value is `answered_with_data`, `answered_without_data`
  (the server did not find data to answer from), `clarified`, `refused`,
  `error`, or `canceled` (the client disconnected before the turn
  finished).
- **`outcome_reason`:** On a `refused` turn, the reason is `adversarial`,
  `off_domain`, `safety_blocked`, `chat_disabled`, or
  `daily_token_budget_exhausted`. On an `error` turn, it is the `reason` of
  the turn's `terminal` event, such as `mcp_timeout`,
  `model_armor_unavailable`, or `classifier_unavailable` (see
  [Monitoring](#monitoring)).
- **`refusal_stage`:** The value is `availability` (chat is disabled or the
  instance's daily token budget is exhausted, so the turn did not run any
  phase), `classify`, `discovery`, or `synthesis`.
- **`has_data`:** On a `complete` turn, `has_data` says whether the server
  wrote the answer from data. A turn that fails or is refused after its
  analysis can also have `has_data` set to `true`.
- **`title_outcome`:** `omitted` means that the model did not write a usable
  title on a turn with data. `not_requested` means that the turn did not
  have data or did not reach synthesis. Read `emitted` and `omitted` only on
  `complete` turns. When synthesis fails part-way, the server records the
  outcome that it had reached.
- **`follow_ups_emitted` and `follow_ups_canceled`:** `follow_ups_emitted`
  is the number of follow-up questions that the `follow_ups` phase emitted
  in its `follow_ups` SSE frame (queued for delivery, matching
  `charts_emitted` and `title_outcome`). It is `0` when the turn did not
  reach the follow-up phase, and when the follow-up call failed, timed out,
  or did not return a question. `follow_ups_canceled` is `true` only when
  the turn task was canceled while the `follow_ups` phase was generating
  questions, before emitting that frame. Such a turn has already emitted its
  `terminal` frame, so its `terminal_state` is `complete` and its `outcome`
  does not change. A turn that the client cancels earlier has the
  `terminal_state` `canceled` and `follow_ups_canceled` `false`. The record
  does not hold the text of a question.
- **`pattern`:** The value is `null` on a `refused` turn and on a turn that
  ended before the `classify` phase assigned a pattern (including
  `model_armor_unavailable` and `classifier_unavailable`).
- **`phase_durations`:** The list has one item for each phase that ran, in
  the order `classify`, `discovery`, `processing`, `synthesis`, `finalize`,
  `follow_ups`. Each item has `phase`, `duration_ms`, and `is_nested`.
  `is_nested` is `true` for `processing`, because its time is also counted
  in `discovery`. Leave the nested items out of a sum of the durations.
- **`tokens` and `token_calls`:** `tokens` holds `prompt_token_count`,
  `candidates_token_count`, `thoughts_token_count`, `total_token_count`,
  `call_count`, and `interrupted_stream_calls`. `call_count` is the number
  of model calls that reported token counts. A call reported token counts
  when its response held at least one of the four counts, including a count
  of `0`. `token_calls` has one item for each of those calls, unless the
  server shortened the list (see `truncated_lists`). Each item of
  `token_calls` has `role` (`classify`, `discovery`, `synthesis`,
  `follow_up`, or `compaction`), `model`, `round_number` (the discovery
  round, or `null` outside discovery), and the same four token counts.
  `interrupted_stream_calls` is the number of discovery and synthesis calls
  that stopped before their end and before any token counts had arrived.
  Gemini reports the token counts of such a streamed call on the last chunk
  of the stream, so a call that is cut off does not have counts, and Gemini
  may still bill it. On Vertex AI, each earlier chunk carries usage
  metadata without any of the four counts, and the server does not read
  that as reported counts. A call counts when its stream fails after the
  first chunk, and when the server stops reading it: a chunk does not
  arrive within the synthesis timeout, the search for data reaches its time
  limit, or the client disconnects. A request that fails before its first
  chunk does not count. A call is counted either in `token_calls` or in
  `interrupted_stream_calls`, and the token totals do not include the calls
  that were cut off. The `classify`, `follow_up`, and `compaction` calls are
  not streamed, so the server does not count them here when they time out.
- **`tool_call_count` and `tool_call_counts`:** `tool_call_counts` has one
  item for each pair of a tool and an actor that occurred, with `tool`,
  `actor`, and `count`, sorted by tool name and then by actor. `actor` is
  `model` when the model asked for the call, and `server` when the server
  made the call on its own. For `model`, the server counts each call that
  finished with a tool response or a tool-level error record, and it does
  not count a call that an MCP transport failure or a cancellation stopped
  before it produced a record (or a terminal call in the same round after
  such a failure). The server makes two kinds of calls on its own:
  `get_variable_metadata`, where it counts each request that it dispatches
  before a specification runs (including requests that fail or time out),
  and `report_unavailable`, when it files the no-data report itself after
  the search for data did not find any. `tool` is one of the three MCP
  discovery tools, the three fetch functions, `submit_specification`,
  `report_unavailable`, or `unknown` for a name that the server did not
  declare to the model. `tool_call_count` is the sum over all items, for
  both actors.
- **`tables` and `tables_truncated`:** `tables` lists up to 20 fetched
  observation tables that returned at least one row, in fetch order. Derived
  tables and empty fetches are left out, while `tables_fetched` still counts
  every fetch. Each item has `table_id`, `used_in_answer`, `variable_dcid`,
  `facet_id`, `row_count`, `parent_place_dcid`, `child_place_type`,
  `places_with_data_count`, `place_dcids`, `earliest_date`, and `latest_date`.
  `used_in_answer` is `true` when the specification that answered the turn read
  the table. When a table covers a child-place cohort (both `parent_place_dcid`
  and `child_place_type` are valid), `place_dcids` is empty because the parent
  and child type identify the cohort. Otherwise `parent_place_dcid` and
  `child_place_type` are `null`, and `place_dcids` lists up to 25 sorted place
  DCIDs that have rows in the table. When a turn has more than 20 qualifying
  tables, or when the server drops tables to keep the record within 14 KiB
  (see `truncated_lists`), the server leaves tables out from the end of
  `tables` and sets `tables_truncated` to `true`. Capping `place_dcids` at
  25 inside one table does not set `tables_truncated`.
- **`highlighted_places`:** The list has up to 25 distinct places from the
  steps of the turn's analysis that succeeded, in step order. The server
  includes only places that have rows in a non-empty fetched table of the
  turn, including fetched tables left out of `tables` by truncation. Each item
  has `place_dcid` and `source`, and a place that appears more than once keeps
  the `source` of its first appearance. `source` is `ranked_focal`,
  `ranked_top`, or `ranked_bottom` from `rank_cohort`, `distribution_focal`,
  `distribution_max`, or `distribution_min` from `summarize_distribution`,
  `related_highest` or `related_lowest` from `relate_cohorts`, `timeseries`
  from `analyze_timeseries`, or `composition` from `compute_composition`. On
  ranking and distribution steps, focal places come before the top, bottom,
  maximum, and minimum places.
- **`specification_origin`:** An analysis specification lists the analytical
  scripts to run over the fetched tables. The value is `model` when the server
  accepted a specification that the model submitted. It is `default` when the
  search for data ended without an accepted specification, and the server built
  one itself over the fetched tables. It is `null` when the turn does not have
  a specification. Like `has_data`, the value describes the turn's analysis, so
  a turn that fails or is refused after its analysis keeps `model` or
  `default`.
- **`script_steps`:** The list has one item for each step of that specification
  that ran, in step order. Each item has `step_index` (the position of the
  step, from 0), `step_id`, `script`, `status` (`ok` or `refused`), and
  `refusal_reason`. `refusal_reason` is `null` on an `ok` step. On a `refused`
  step, it is `insufficient_coverage`, `no_observations`, `unit_mismatch`,
  `scaling_mismatch`, `invalid_parameters`, or `components_exceed_total`. A run
  stops at the first step that refuses, so a `refused` step is always the last
  item. Only a `default` specification can have a `refused` step, because the
  server rejects a specification from the model when one of its steps refuses.
  The list is empty when the run exceeded its time limit, because the server
  cannot tell which steps finished. `scripts` still lists every step of the
  specification.
- **`rejected_submissions`:** The list has up to three specifications that the
  server rejected, in the order in which the model submitted them. The server
  returns a rejected specification to the model at most twice, and a third
  rejection ends the search for data. Each item has `round_number` (the
  discovery round), `reason`, `scripts`, `failed_step_id`, `failed_script`,
  `refusal_reason`, and `timed_out`. `reason` is `schema_invalid` (the
  specification did not parse, so `scripts` is empty), `reference_invalid` (the
  specification did not match the fetched tables), or `processing_failed` (the
  specification ran and failed). When a step refused, `failed_step_id`,
  `failed_script`, and `refusal_reason` describe that step. Otherwise all three
  are `null`. `timed_out` is `true` when the run exceeded its time limit.
- **`charts`:** The list has up to four charts, in the order in which they
  appear in the answer. Each item has `index` (from 0), `kind` (`line`, `bar`,
  `map`, `ranking`, `scatter`, or `highlight`), `origin`, `variables`,
  `parent_place_dcid`, `child_place_type`, `place_dcids`, and `per_capita`.
  `origin` is `model` when the model wrote the chart, and `default` when the
  server added a chart because the answer did not have one. `variables` lists
  up to 10 variables in the chart's order. Each item has `variable_dcid` and
  `facet_id`. `facet_id` names the facet that the chart draws that variable
  from, and it is `null` when the chart does not pin the variable to one
  facet. When a chart draws every place of one type inside a parent
  place (a child-place cohort, such as the counties of a state),
  `parent_place_dcid` and `child_place_type` identify that group and
  `place_dcids` is empty. Otherwise both are `null`, and `place_dcids` lists up
  to 25 places in the chart's order. `per_capita` is `true` when the chart
  divides its values by population. The server includes a variable or a place
  only when a non-empty fetched table of the turn holds it. It includes a
  facet only when such a table reports it for the same variable, and a parent
  place with its child place type only when such a table covers that group.
  Fetched tables left out of `tables` by truncation count as well. The record
  does not hold the title or the unit of a chart.
- **`chart_rejections`:** The list has up to ten chart blocks of the answer
  that the server dropped, in the order in which it dropped them.
  `charts_rejected` still counts every dropped block. Each item has `index`
  (the position among the turn's dropped blocks, from 0), `kind`, and
  `reason`. `kind` is the chart kind of the block, or `null` when the server
  dropped the block before it parsed it. `reason` is `unknown_table`,
  `table_unavailable`, `derived_table_not_chartable`,
  `mixed_per_capita_and_raw`, `unit_mismatch`, `scaling_mismatch`,
  `cohort_required`, `cohort_mismatch`, `unknown_place`,
  `place_count_out_of_range`, `insufficient_line_dates`, `no_value_at_date`,
  `no_value_for_place`, `empty_ranked_slice`, `date_not_shared`,
  `variable_count_mismatch`, `empty_title`, `window_date_required`,
  `chart_limit_reached`, `invalid_specification` (the block is not valid
  JSON or does not match the chart grammar), `unclosed_block` (a completed
  answer ended inside the block), `turn_without_data`, or
  `table_not_in_answer`. When a synthesis stream fails or is canceled
  part-way, the record includes only chart blocks that closed and were
  rejected before the stream stopped, and it does not count a fence that
  was still open at that moment. A default chart that the server builds and
  cannot draw is not a chart block of the answer, so it does not add an
  item. The record does not hold any text of a dropped block.
- **`truncated_lists`:** The list is empty for a record that fits in 14 KiB.
  Otherwise the server drops whole items from the ends of eight lists until
  the record fits, and `truncated_lists` names the lists that lost an item,
  in the order of the keys above. The server shortens the lists in three
  groups, and it empties every list of a group before it shortens a list of
  the next group:
  1. `tables`, `charts`, and `highlighted_places`, which hold the Data
     Commons identifiers that make up most of a long record.
  2. `chart_rejections`, `rejected_submissions`, `script_steps`, and
     `tool_call_counts`, which say how the turn ran.
  3. `token_calls`.

  Within a group, the server takes each item from the list whose items are
  the largest in total at that moment. The server does not shorten a list
  inside an item, and it does not change a count: `tokens.call_count`,
  `tool_call_count`, `tables_fetched`, `processing_retries`,
  `charts_emitted`, and `charts_rejected` keep their values. A count that is
  larger than its list, together with the name of the list in
  `truncated_lists`, means that the server left items out for size.

#### The `transcript_rejected` record

When the server rejects the conversation history of a request (HTTP 400
`transcript_invalid`), it writes one `transcript_rejected` record
(`schema_version` 1):

| Key | Value |
| :--- | :--- |
| `severity` | `WARNING` |
| `message` | `transcript rejected` |
| `event` | `transcript_rejected` |
| `schema_version` | `1` |
| `reason` | Reason code of the rejection |

`reason` is `invalid_window` (the history does not match its schema or
exceeds a size limit), `summary_without_turns`,
`conversation_id_without_turns`, `turns_without_conversation_id`,
`window_start_mismatch` (the history starts at turn 0 with a summary, or
starts after turn 0 without a summary), `non_contiguous_turns`,
`duplicate_idempotency_key`, or `signature_mismatch`. The record does not
include the conversation ID or any other value from the request, because a
rejected request does not have a verified conversation ID.

#### The turn span

The turn span (`narratives.turn`) carries some of the same fields as
attributes: `narratives.terminal_state`, `narratives.pattern`,
`narratives.scripts`, `narratives.tables_fetched`,
`narratives.total_rows_fetched`, `narratives.processing_retries`,
`narratives.charts_emitted`, `narratives.charts_rejected`,
`narratives.title_outcome`, `narratives.tool_call_count`, and
`narratives.tool_names`. `narratives.tool_call_count` is the number of tool
calls by the model and by the server, as `tool_call_count` in the record,
and `narratives.tool_names` lists each tool name once, sorted. The span does
not say which actor made a call. The span does not carry the turn ID. It
shares a trace ID with the HTTP request span, and a load balancer log can
hold that trace ID next to the client's address. With the turn ID on the
span, someone could join a `chat_turn` record to a client address.

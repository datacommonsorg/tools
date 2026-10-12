# Custom Data Commons

A themed, conversational Data Commons instance: a React UI and a Gemini agent in
one container, running against public `datacommons.org`.

**The theme is a configuration value, not a branch.**

**One clone of this repository is one deployment.** Clone it, fill in
`config/instance.env`, change what you want to look different, and deploy. For a
second deployment, clone it again — there is no `--instance` flag and no way to
run two from one checkout.

Everything you edit lives in `config/`. Nothing else needs touching, and nothing
you do there requires TypeScript or Python.

---

## Contents

- [How it fits together](#how-it-fits-together)
- [Quickstart](#quickstart) — a working deployment in ~10 minutes, nothing to provision
- [Prerequisites](#prerequisites)
- [Setting up your deployment](#setting-up-your-deployment)
- [Customizing it](#customizing-it) — theme, prompts, agent config
- [Secrets](#secrets)
- [Deploying](#deploying)
- [Access modes](#access-modes)
- [Developer guide](#developer-guide)
- [Local development](#local-development)
- [Testing](#testing)
- [Verifying a deployment](#verifying-a-deployment)
- [Troubleshooting](#troubleshooting)
- [Repository layout](#repository-layout)
- [Design notes](#design-notes) — why it is built this way

---

## How it fits together

```
                     ┌──────────────────────────────────────┐
   browser ─────────►│  APP PLANE                           │
                     │  one container: agent API + SPA      │
                     │                                      │
                     │   MCP client ─ capability probe      │
                     │   /dcproxy   ─ → DATA_PLANE_URL      │
                     │   auth       ─ strategy chosen by    │
                     │                host                  │
                     └──────────────┬───────────────────────┘
                                    │  DATA_PLANE_URL
                                    ▼
                          public datacommons.org
                          nothing to run
```

The app plane has a URL, an API key, and a tool surface it **discovers** at
startup by probing `tools/list` — `/agent/health` reports what it found.

**This module exposes only the app plane.** The data plane is the public Data
Commons API.

---

## Quickstart

The deployment runs against public `datacommons.org`. No database, no
ingestion, no bill — and it exercises the whole application: chat, charts,
theming, citations.

```sh
# 1. Clone. This clone IS the deployment.
git clone <repo-url> acme-dc && cd acme-dc

# 2. Fill in the four required values. None has a default.
$EDITOR config/instance.env

# 3. Check everything before creating anything.
./deploy.sh --preflight

# 4. Put the keys in Secret Manager — once, ever.
DC_API_KEY=... GEMINI_API_KEY=... ./deploy.sh --bootstrap-secrets

# 5. Deploy.
./deploy.sh
```

Then open it, according to the `ACCESS_MODE` you chose:

```sh
# private
gcloud run services proxy acme-app --region=<your-region> --port=8080

# public or iap — the deploy prints the URL
```

**`--preflight` is the step worth not skipping.** It checks the things that
otherwise fail late or silently: credentials, billing, whether your organization
even permits public access, and whether IAP has a consent screen to sign people
in with. It creates nothing.

---

## Prerequisites

| Need | Notes |
| :--- | :--- |
| A GCP project with **billing enabled** | |
| `gcloud`, authenticated | `gcloud auth login` **and** `gcloud auth application-default login` — separate; Terraform uses ADC |
| `terraform`, `pnpm`, `python3` on PATH | Images build in **Cloud Build**, so no local Docker is needed |
| A **Data Commons API key** | https://apikeys.datacommons.org |
| A **Gemini API key** | https://aistudio.google.com |
| [`uv`](https://docs.astral.sh/uv/) | The agent's dependencies |

**Python 3.14.** The agent declares its direct dependencies in
`agent/pyproject.toml` and resolves the whole graph into `agent/uv.lock`.
`uv sync` creates `agent/.venv` from that lockfile, and commands run as
`uv run <command>`. Regenerate the lockfile with `uv lock` after a dependency
change, and never hand-edit it. The container pins `python:3.14-slim`.

**Node 24** for the UI.

**IAM roles:** Owner, or Service Usage Admin, Service Account Admin, Project IAM
Admin, Storage Admin, Run Admin and Secret Manager Admin.

---

## Setting up your deployment

Everything this deployment owns lives in `config/`:

```
config/
  instance.env       where it runs, who can reach it — NO secrets
  theme.json         OPTIONAL — only the keys you want to change
  agent-config.json  OPTIONAL — only the keys you want to change
  prompts/           OPTIONAL — only the prompts you want to change
  assets/            OPTIONAL — your logo and favicon
```

Only `instance.env` is required. Everything else is an **override**: at deploy
time `defaults/` is laid down first and `config/` is copied over the top, so you
carry only your differences and inherit every upstream improvement when you pull.

The required values in `config/instance.env` have **no default**. That is
deliberate — each one decides where your data lives, what it costs, or who can
reach it, and a default is a decision made on your behalf that you would not see
until the bill or the latency showed up. `REGION` in particular.

Required always:

| | |
| :--- | :--- |
| `PROJECT_ID` | Your GCP project. Billing must be enabled. |
| `REGION` | Where everything runs. Check your data-residency obligations first — moving later means recreating everything. |
| `INSTANCE` | Lowercase, DNS-safe. Names every resource and the Terraform state prefix. |
| `ACCESS_MODE` | `public`, `iap` or `private` |

Required depending on those choices, and `--preflight` tells you which:

| | |
| :--- | :--- |
| `AUTHORIZED_MEMBERS` | for `iap` and `private` |

Optional: `PUBLIC_DC_URL` and `PUBLIC_DC_WEB_URL` — **two different hosts**, see
below.

### Public Data Commons needs two URLs, not one

The agent and the browser talk to **different hosts**, and it is worth
understanding before you change them:

| | Value | Used by |
| :--- | :--- | :--- |
| `PUBLIC_DC_URL` | `https://api.datacommons.org` | the **agent** — the versioned REST API, and `/mcp` |
| `PUBLIC_DC_WEB_URL` | `https://datacommons.org` | the **browser** — `/api/observations/series`, `/api/place/name`, `/core/api/...` |

The agent's MCP endpoint is `PUBLIC_DC_URL` with `/mcp` appended.

Point both at the API host and you get a deployment that looks like it works:
chat answers correctly, every number is right, and **no chart ever renders**. The
browser's requests reach a host that does not serve those routes and come back as
Cloud Endpoints 404s, which nothing surfaces server-side.

Left empty, both take the standard values above. Change them only if you are
pointing at a different public Data Commons deployment.

### A second deployment

Clone the repository again. `INSTANCE` namespaces every resource and the
Terraform state prefix, so `acme-prod` and `acme-staging` can share one GCP
project without touching each other.

Two clones pointed at the same project are safe: before applying, the deploy
reads the deployment name back out of the loaded Terraform state and refuses if
it belongs to something else. Applying over another deployment's state would
rename its resources, and Terraform renames by destroying and recreating.

### Keep your clone private

`config/` is committed — that is what makes this clone *your* deployment rather
than a copy you have to re-derive. So `config/instance.env` is in your git
history, and it names your project, your region and everyone allowed in.

That is disclosure. **A deployment repository should be private.**

API keys are the exception that never applies: they are not in any file. They go
to Secret Manager once, via `--bootstrap-secrets`, which reads them from your
shell and writes nothing to disk.

### Staying up to date

```sh
git remote add upstream <upstream-url>   # once
git pull upstream main
./deploy.sh
```

Upstream never touches `config/`, so this does not conflict. Code fixes, prompt
fixes, and theme defaults all arrive; your overrides stay yours.

**Change only `config/`.** The moment a deployment edits code, every later pull
conflicts and it stops being updatable. If you need a code change, make it
upstream.

---

## Customizing it

Everything visual and behavioral is configuration. Three directories, with
clearly different jobs:

| Directory | Owned by | Edit it? |
| :--- | :--- | :--- |
| `schemas/` | upstream | No — the JSON Schemas that validate the other two |
| `defaults/` | upstream | No — the baseline every deployment inherits |
| `config/` | **you** | Yes — only the keys you want to differ |

At deploy time `defaults/` is laid down and `config/` is copied over the top. So
you write only your differences, and an upstream prompt or theme fix reaches
you on the next `git pull` instead of sitting unnoticed in a file you copied
once and forgot.

| What you can override | Validated by | Controls |
| :--- | :--- | :--- |
| `config/theme.json` | `schemas/theme.schema.json` | identity, appearance, content, structure |
| `config/agent-config.json` | `schemas/agent-config.schema.json` | models, thinking levels, template vars |
| `config/prompts/*.md` | — | `mcp`, `synthesis`, `follow_up` |
| `config/assets/` | — | logo, favicon |

Both schemas set `additionalProperties: false`, so an unrecognized key is an
error rather than a silently ignored one — a typo'd color name fails loudly.

### Theme

**How the theme is applied.** The default (Base Data Commons) theme is built
directly into the UI: colors, fonts, and corner radii are found in
`ui/src/index.css` as the fallback values of `--theme-*` CSS variables, and the
default logo, headline, navigation, and starter suggestions are in
`ui/src/config/instance_config.ts`. `ui/index.html` includes two empty
placeholder elements (`<style id="theme-tokens">` and
`<script id="instance-config">`) as the seam for per-instance theming. When
populated, they override those defaults at page load without any runtime
network requests.

> **Status:** The deploy step that populates `<style id="theme-tokens">` and
> `<script id="instance-config">` from `theme.json` has not been wired up yet.
> `deploy.sh` validates `theme.json` against `schemas/theme.schema.json` and
> uploads it to the config bucket (including during
> `./deploy.sh --config-only`), but nothing writes it into `index.html`, and
> `--restart` only reloads `agent-config.json` and `prompts/`. Until that step
> lands, every deployment renders the built-in Base Data Commons theme.

Start from a complete example:

```sh
cp schemas/theme.neutral.example.json config/theme.json
$EDITOR config/theme.json
```

Or specify only the keys you want to change; everything else comes from
`defaults/theme.json`:

```json
{
  "instance_name": "Acme Data Commons",
  "logo": "/dc-logo.svg",
  "colors": { "primary": "#0B6E8F" }
}
```

| Group | Keys |
| :--- | :--- |
| Identity | `instance_name`, `headline`, `tagline`, `logo`, `logo_text`, `logo_height`, `logo_alt`, `favicon` |
| Appearance | `colors` (primary, accent, text, surfaces, borders, containers…), `radius` (card / input / chip), `fonts` |
| Content | `suggestions` (starter chips); `splash_assets` (thinking and done indicators); `footer` text and links *(reserved; not read by the UI)* |
| Structure | `navigation` (header tabs); `metrics.tabs`; `analytics.ga_tag_id` *(reserved; not read by the UI)* |

Two complete examples ship as starting points:
`schemas/theme.neutral.example.json` (neutral theme) and
`schemas/theme.base-dc.example.json` (Google blue, no header menu).
`schemas/theme.example.json` lists every field with placeholder values.

**`navigation` controls the header tabs:**

| Value | Result |
| :--- | :--- |
| key absent or `[]` | **no header menu** (the Base Data Commons default) |
| `[{label, href}, …]` | exactly these tabs |

The UI unit tests pin this mapping.

**Assets.** Image fields (`logo` and `splash_assets`) in `#instance-config`
accept a same-origin path starting with `/` (such as the bundled
`/dc-logo.svg`) or an `http(s)` URL. Any other value, including `data:` URIs,
is rejected with a console warning and falls back to the built-in asset.
`deploy.sh` also uploads `config/assets/` to the config bucket and the schema
allows config-bucket-relative paths like `assets/acme.svg`, for use once the
deploy-time injection step rewrites them.

### Prompts

`prompts/mcp.md` and `prompts/synthesis.md` are where instance-specific knowledge
lives — which DCIDs exist, what the place hierarchy looks like, what vocabulary to
use.

**Start from the neutral prompts and add your knowledge; do not start from
another client's and try to remove theirs.** A region-scoped synthesis prompt run
against a different dataset once produced *"I don't have this specific data"* for
data the tool had already returned in full: a rule of the form
`if alternative_sources:[] treat as UNAVAILABLE` misfires, because custom data has
a valid `source_id` and no alternatives.

**Placeholders.** Prompts are rendered before they reach Gemini:

| Placeholder | Substituted with |
| :--- | :--- |
| `{{CURRENT_DATETIME}}` | now, in the `TIMEZONE` env var's zone |
| `{{instance.<key>}}` | the matching key from `agent-config.json`'s `template_vars` |

So one prompt serves every deployment:

```json
"template_vars": {
  "name": "Example Data Commons",
  "region": "the world",
  "states_term": "regions",
  "fiscal_year_start": "01-01"
}
```

```
**Deployment**: {{instance.name}}, covering {{instance.region}}.
```

A placeholder with no matching key is left in the prompt **verbatim** rather than
blanked — a visible `{{instance.region}}` in an answer is a far louder failure
than a sentence that has silently lost its subject. Keys beginning with `_` are
never substituted, so the `_comment` convention is safe.

### Applying a config change

```sh
./deploy.sh --config-only --restart
```

`--restart` is **not optional**. `agent-config.json` and the prompts are read
**once at agent startup** and held in process memory thereafter. There is no
TTL and no runtime refetch, so a bucket sync alone changes nothing until a new
revision starts serving.

---

## Secrets

```sh
DC_API_KEY=... GEMINI_API_KEY=... \
  ./deploy.sh --bootstrap-secrets
```

Values are read from **this process's environment**, written to Secret Manager,
and never persisted to disk. Every later deploy needs no keys at all. If you skip
this, the deploy stops and tells you which secrets are missing.

**Why there is no gitignored `secret.env`.** The keys already live in Secret
Manager after the first deploy, so a local plaintext copy is redundant — and on a
public repo a redundant secret file is a liability: one `git add -f`, one edited
`.gitignore`, and a scraper has it. A new operator needs GCP access, not a file
someone has to send them.

`instance.env` is excluded from the config-bucket sync, so instance metadata
cannot reach a bucket that may be readable more widely than intended.

---

## Deploying

```sh
./deploy.sh --preflight     # check everything, create nothing
./deploy.sh                 # deploy
```

Roughly, in order: enable APIs → create the state bucket and Artifact Registry →
verify secrets → build the UI and bake it into the app image → compose the
config bucket from `defaults/` + `config/` and sync it → `terraform apply` →
smoke tests.

First run is ~10 minutes.

**Preview the plan before an apply into a project that already has resources:**

```sh
./deploy.sh --plan
```

Every line should read `will be created`, and the summary should read
**`0 to change, 0 to destroy`**. **If anything says `will be destroyed`, stop** —
the state prefix or `INSTANCE` did not take, and you are pointed at another
deployment's state. Applying would rename, that is destroy and recreate, its
resources.

One exception: a stack first deployed before the `cdc` backend was removed will
show `<instance>-runtime` and its five IAM bindings as `will be destroyed`. That
service account belonged to the old data service; nothing uses it now, so those
destroys are expected.

### Everyday commands

| | |
| :--- | :--- |
| Check before deploying | `./deploy.sh --preflight` |
| Prompts, agent-config | `./deploy.sh --config-only --restart` |
| Agent or UI code | `./deploy.sh --agent-only` |
| Terraform only | `./deploy.sh --infra-only` |
| Preview the plan | `./deploy.sh --plan` |
| Everything | `./deploy.sh` |
| Tear it all down | `./deploy.sh --destroy` |

`--frontend-only` is an alias for `--agent-only`, since the UI is baked into the
app image.

> `IMAGE_TAG` is `git rev-parse --short HEAD`, so **uncommitted work rebuilds to
> the same tag** and Cloud Run keeps the cached image. Commit before
> `--agent-only`, or the deploy reports success and the change is not live.

### Starting over

```sh
./deploy.sh --destroy
```

Asks you to type the deployment name, then destroys everything Terraform
created. The config bucket and the Secret Manager entries are left alone, so a
later redeploy does not need the keys again; delete them separately if you want
them gone.

It runs the same state-ownership guard as the apply path, so it cannot destroy
resources belonging to another deployment.

---

## Access modes

How the app is exposed, set by `ACCESS_MODE`.

### `public`

`allUsers` gets `run.invoker`. Anyone with the URL can use it — **including the
chat endpoint, so anyone with the URL spends your Gemini quota.**

Many organizations forbid this outright through Domain Restricted Sharing. When
they do, the deploy still succeeds and the binding is simply refused, leaving a
URL that returns 403 to everyone. `--preflight` checks the org policy and tells
you to use `iap` instead, before you deploy rather than after.

### `iap`

Google sign-in in front of the app. `AUTHORIZED_MEMBERS` get
`roles/iap.httpsResourceAccessor` **scoped to this service**, and IAP's own
service agent gets `run.invoker` so it can forward requests.

Three things this gets right, each learned the hard way:

1. **The IAP service agent needs `run.invoker`.** Without it every request is
   refused with a 403 *after* the user has signed in successfully — which reads
   as a bug in the application rather than a missing IAM binding.
2. **Members are not given `run.invoker`.** That is deliberate: a member holding
   it could call the Cloud Run URL directly with an identity token and never see
   the sign-in, defeating the mode entirely.
3. **The grant is scoped to this service**, not project-wide. An earlier version
   used a project-level binding, which granted access to every IAP-fronted app in
   the project and meant two deployments fought over it — destroying one revoked
   the other's access. That is also why there is no longer a
   `MANAGE_IAP_BINDINGS` setting to get wrong.

**One manual step, once per project.** IAP needs an OAuth consent screen, and
creating one is a console action Terraform cannot perform. `--preflight` checks
for it and prints the link. Until it exists, IAP has nothing to sign people in
with and the service stays unreachable.

`/dcproxy` strips the IAP identity headers before forwarding. With IAP in front,
Cloud Run hands the container IAP's own `Authorization` token, whose audience is
*this* service; forwarding it would hand the user's sign-in to Data Commons.
Handled in code; if you add another proxy hop, it must do the same.

### `private`

No public binding and no sign-in. `AUTHORIZED_MEMBERS` get `run.invoker`
directly, so they can reach it with an identity token or through the proxy:

```sh
gcloud run services proxy <instance>-app --region=<region> --port=8080
```

Right for a pilot you drive yourself, and the safe choice when you are not yet
sure which of the other two you need.

---

## Developer guide

All commands run from the root of the `/narratives` directory.

### Installation

```bash
nvm use        # switch to the Node version pinned in .nvmrc (or run 'nvm install' if not yet installed)
corepack enable
pnpm i
```

### Scripts

| Command | What it does |
| --- | --- |
| `pnpm dev:ui` | Start the frontend Vite development server on port 3000 (`ui/`) |
| `pnpm dev:agent` | Stage config and start the Python agent development server on port 5001 (`agent/`) |
| `pnpm build` | Build the React UI and stage compiled assets into `agent/static/` |
| `pnpm build:ui` | Build the React UI bundle into `ui/dist/` without staging |
| `pnpm test` | Run unit tests and lint checks across packages (Vitest + Pytest + `pnpm lint`) |
| `pnpm test:ui` | Run the frontend Vitest suite |
| `pnpm test:agent` | Run the backend Pytest suite |
| `pnpm lint` | Run all lint, formatting, and type checks (UI, agent, and deployment) |
| `pnpm fix` | Auto-fix formatting and lint issues (Biome, Ruff, and Terraform) |

> [!TIP]
> Always run `pnpm test` (and `pnpm build` for UI changes) before opening or
> updating a PR. If lint checks fail, run `pnpm fix` to format and auto-fix.

---

## Local development

Two paths. Pick by what you are changing.

### Path A — UI only (the fast loop)

A hot-reloading Vite dev server proxying every backend call to a deployed
instance. Real Gemini, real MCP tools, real charts.

```sh
pnpm install

# Point at your deployed Cloud Run instance
cp .env.local.example .env.local
$EDITOR .env.local
# Set AGENT_URL to your deployed instance:
#   AGENT_URL=https://<your-instance>.run.app

pnpm dev:ui         # http://localhost:3000
```

Vite's `server.proxy` (in `vite.config.ts`) forwards `/agent/*` and the data
routes to `AGENT_URL` (unless `BACKEND_URL` is set separately); it is
**dev-only**, so `vite build` ignores it. Default is `localhost:5001` if unset.
Vite picks up `.env.local` changes on **restart**, not live.

You need Node 24 and nothing else — no Docker, no Python, no gcloud.

### Path B — the agent locally

Run commands in this section from `narratives/`.

**Install dependencies:**

```sh
(cd agent && uv sync)   # creates agent/.venv and installs from uv.lock
```

There is nothing to activate: `uv sync` creates `.venv` itself, and `uv run`
uses it.

**1. Configure local environment:**

Copy `.env.local.example` to `.env.local` and add your Gemini API key:

```sh
cp .env.local.example .env.local
$EDITOR .env.local      # Add your GEMINI_API_KEY="..."
```

The template is pre-configured with public Data Commons endpoints:
```sh
MCP_SERVER_URL="https://api.datacommons.org/mcp"
DATA_PLANE_URL="https://api.datacommons.org"
DATA_PLANE_WEB_URL="https://datacommons.org"
AGENT_URL="http://localhost:5001"
```

*(If pointing at a custom deployed data plane instead, update `MCP_SERVER_URL`
and `DATA_PLANE_URL` to your Cloud Run service URL, and remove
`DATA_PLANE_WEB_URL` so it falls back to `DATA_PLANE_URL`.)*

**2. Start local development:**

Run the agent and UI in two separate terminals:

```sh
# Terminal 1: backend agent (port 5001)
pnpm dev:agent

# Terminal 2: frontend Vite dev server (port 3000)
pnpm dev:ui
```

`pnpm dev:agent` (or `uv run narratives-agent-dev`) loads `.env.local` and
stages `agent/config.json` from `defaults/` + `config/` + `prompts/`
(incorporating your `GEMINI_API_KEY`) before starting the Uvicorn server with
auto-reload.

**Config and keys:**

```sh
export CONFIG_URL="https://storage.googleapis.com/<bucket>/agent-config.json"
```

The Gemini key is **not** an environment variable. `get_gemini_api_key()` resolves
`GEMINI_API_KEY_SECRET` through Secret Manager and falls back to
`gemini.api_key` in the config document — which is the local path, since Secret
Manager needs credentials the laptop may not have:

```json
{ "gemini": { "api_key": "your-key" } }
```

The secret payload stores the bare API key string rather than JSON. If Secret
Manager still holds a legacy `["<key>"]` JSON array, the loader rejects it and
logs an error instructing you to re-run `./deploy.sh --bootstrap-secrets`.

Do not commit a real key in `agent-config.json`; the checked-in files define
the schema shape only.

**Transcript signing key** (optional locally):

```sh
export TRANSCRIPT_HMAC_SECRET="$(openssl rand -hex 32)"
```

The browser holds the conversation and sends it with every request; the agent
signs each completed turn with this key and rejects a transcript whose
signatures do not verify. When the variable is unset, the agent signs with a
random key generated at startup, which is enough for one local process: a
restart invalidates the transcripts the browser holds, and the UI then clears
the earlier context and asks the user to repeat the question. On Cloud Run,
where requests reach several instances, every instance must share one secret;
the agent logs a warning when `K_SERVICE` is set and the secret is not.

**Serve the SPA from the agent**, so routing matches production:

```sh
pnpm build
```

Skip it if you only care about the API — `/` will 404 and `/agent/*` still works.

**Start the server:**

```sh
(cd agent && uv run narratives-agent-dev)   # http://localhost:5001
```

It listens on `127.0.0.1` and restarts when a source file changes. Set
`AGENT_PORT` to use another port. Stop it with Ctrl+C.

**Check it**, from a second terminal:

```sh
curl -s localhost:5001/agent/health | jq    # mcp_url is the resolved MCP endpoint
curl -sN -X POST localhost:5001/agent/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is the population of France?","turns":[]}'
```

The server does not contact MCP at startup, and `/agent/health` never does:
it reports the resolved `mcp_url` and the cached tool surface, which is empty
until a chat turn has listed the tools. The chat request is therefore the first
call to reach MCP.

The stream uses typed Server-Sent Events. Every frame names its `event:` and
carries a JSON `data:` payload, and every frame except `heartbeat` carries an
`id:` counting up from 1:

| Event | Payload |
|---|---|
| `status` | `{phase, message}` (`mcp`, `synthesis`, or `chart_config`) |
| `thought` | `{thought, phase}` (a reasoning summary from `mcp` or `synthesis`) |
| `content` | one of `{text}`, `{tool_call}`, `{sources}`, `{data_status}`, `{chart_config}` |
| `terminal` | `{state, idempotency_key, error?, reason?}`, plus `{turn_index, hmac, state_slots, compacted_summary, window}` on a signed `complete` |
| `follow_ups` | `{follow_up_questions}`, sent after `terminal` when any are generated |
| `heartbeat` | `{}`, sent every 15 seconds so proxies keep the connection open |

A turn is finished only by its single `terminal` frame, whose `state` is
`complete` or `error` (with a user-safe `error` and a machine-readable `reason`
such as `mcp_unavailable`, `mcp_timeout`, or `synthesis_empty`). A stream that
ends without a `terminal` frame was cut off, and the UI displays the turn as
interrupted. MCP is a hard dependency: when no tools can be listed or a tool
call fails at the transport layer, the turn ends in `error` rather than
answering without data. A disconnected client receives no terminal frame; the
turn is canceled and recorded as `canceled`. The request may carry an
`idempotency_key`, which the UI generates per submission and the terminal
frame echoes. A healthy local turn emits `content` frames carrying
`tool_call`, then the answer `text`, and then a `complete` terminal frame.

**Multi-turn context**: A follow-up request carries the signed window from the
previous `complete` frame:

```json
{
  "message": "And for Germany?",
  "idempotency_key": "b7e0...",
  "turns": [
    {
      "turn_index": 0,
      "idempotency_key": "3f1c...",
      "user_query": "What is the population of France?",
      "model_response": "<the streamed answer text, exactly>",
      "state_slots": {"scopes": [...]},
      "hmac": "<64 hex characters>"
    }
  ],
  "compacted_summary": null
}
```

Each turn's `hmac` chains it to the previous turn. Before the stream opens,
the agent rejects:

| Status | When |
|---|---|
| 413 (`request_too_large`) | the body exceeds 4 MiB |
| 400 (`transcript_invalid`) | the window was altered, reordered, or spliced, or is outside its schema or caps: more than 6 turns, a 32,000-character answer, or an 8,000-character summary |
| 422 | the body is not JSON, or `message` (at most 4,000 characters) or `idempotency_key` is invalid |

The UI recovers from a 400 by clearing the signatures it holds, so the next
question starts without earlier context. The window holds at most 6 turns:
when a seventh completes, the oldest is folded into `compacted_summary` by a
model call (falling back to a structured summary after 5 seconds) and the
whole window is re-signed, so the `complete` frame of such a turn can arrive
up to 5 seconds after the answer finishes streaming. The client replaces the
signatures it holds with those listed in the frame's `window` and drops any
turn that `window` does not list. `state_slots` records the places,
variables, and dates each turn retrieved, which later turns use to resolve
references such as "them" or "that period". A `complete` frame without
`hmac` marks a turn that was not signed, because its answer exceeded the cap
or signing failed; the client leaves it out of later requests. Signing and
compaction are timed as the `finalize` phase in telemetry. The summary and
scopes reach the model inside a delimited background block; they are not yet
screened by Model Armor.

Production runs `uvicorn narratives_agent.server.app:app`; `dev.py` is the
development path.

---

## Testing

Nothing is mocked that matters.

```sh
# Run all unit tests and lint checks across UI, agent, and deployment:
pnpm test

# Or run by component:
pnpm test:ui                               # Vitest UI suite
pnpm test:agent                            # Pytest agent suite
pnpm lint                                  # All lint, format, and type checks
pnpm fix                                   # Auto-fix formatting and lint issues
```

Agent tests are pytest modules named `*_test.py`, colocated beside the module
under test inside `src/narratives_agent/`. `uv run` executes them in the locked
environment, so there is nothing to activate and nothing to install by hand.

Linting, formatting, and static type-checking can also be run by layer (`pnpm
lint:ui`, `pnpm lint:agent`, `pnpm lint:deploy`), and CI fails on any of them:

```sh
pnpm lint:ui                               # tsc --noEmit + Biome
pnpm lint:agent                            # Ruff format/lint + mypy --strict
pnpm lint:deploy                           # Terraform fmt/validate + ShellCheck + Hadolint
```

> The agent type-checks under `mypy --strict`, tests included, with no
> per-module exemptions.

The agent suites cover six behaviors whose failure is **silent**:

- **MCP session recovery** when the data plane scales. Sessions are bound to the
  process that minted them and Cloud Run has no affinity, so a session created
  against instance 1 gets presented to instance 2, which has never seen it.
- **Both server generations parsing correctly** — including the empty response
  that used to report `has_data=true` for no data. A 1.3.x server signals "no
  data" as `{"data": {}}`, which the old substring check did not match, so the
  agent narrated numbers it never received.
- **Auth chosen by target host** — API key for public Data Commons hosts,
  nothing for any other. Widening the host list to make another host work is a
  security regression, not a fix.
- **Prompt placeholder substitution** — an unsubstituted `{{instance.*}}` reaches
  the user inside an answer.
- **Gemini non-200 reporting and credential redaction** — a rejected request or
  proxy error page fails closed with `key=...` redacted rather than being parsed
  as an empty candidate list or leaking the API key.
- **Chart suppression when validation gives no verdict** — an empty candidate
  list, non-object or malformed JSON, or missing `data_found` boolean hides
  charts rather than rendering charts beneath an answer that declined.

---

## Verifying a deployment

```sh
bash docs/smoke.sh "$URL"
curl -s "$URL/agent/health" | jq
```

`mcp.generation` and `mcp.supports_source_attribution` tell you which MCP surface
the agent actually found. If `supports_source_attribution` is false, answers carry
weaker provenance — no named source, no license.

To confirm that the served HTML shell includes the `<style id="theme-tokens">`
and `<script id="instance-config">` placeholder elements (which `docs/smoke.sh`
also verifies):

```sh
curl -s "$URL/" | grep -E 'id="(theme-tokens|instance-config)"'
```

---

## Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `No configuration at 'config/instance.env'` | File missing or moved | `git checkout config/instance.env` |
| `config/instance.env is incomplete` | Required values unset | Fill in what it lists, then `./deploy.sh --preflight` |
| `--instance is gone` | Old command form | One clone is one deployment; settings are in `config/instance.env` |
| Deploy succeeds, everyone gets 403 | `ACCESS_MODE=public` refused by Domain Restricted Sharing | `./deploy.sh --preflight` detects this; use `ACCESS_MODE=iap` |
| IAP mode, nobody can sign in | No OAuth consent screen in the project | Create it once in the console; `--preflight` prints the link |
| IAP mode, 403 on every request *after* sign-in | IAP service agent lacks `run.invoker` | Should not happen — Terraform grants it. Check `iap_agent_invoker` in the plan |
| `These secrets have no value in Secret Manager` | Bootstrap not run | [Secrets](#secrets) |
| Charts blank, chat fine | `/dcproxy` failing | Agent logs — `401/403` is the API key, `404` is a path the data plane does not serve |
| Charts blank, `{"code":404,"message":"The current request is not defined by this API"}` | Chart routes are on a **different host** to MCP | Terraform sets `DATA_PLANE_WEB_URL` for this. Chat keeps working either way, so only the browser sees the fault |
| `agent-config.json` or `prompts/` change has no effect | Agent loads config once at startup | `./deploy.sh --config-only --restart` |
| `config/theme.json` is ignored | Deploy-time theme injection is not wired up yet | Not yet supported; see [Theme](#theme) |
| `Refusing to apply: the state loaded for 'x' describes another instance` | `deploy.sh` caught a wrong state prefix | Do **not** override. Re-`init` with the right prefix |
| A deploy reports success but the change is not live | Uncommitted work rebuilds to the same `IMAGE_TAG` | Commit, then redeploy |
| Every chart 401s *after* a successful IAP sign-in | IAP identity headers reaching the backend | Should not happen — `/dcproxy` strips them. Suspect an added proxy hop |
| Public access binding refused | Domain Restricted Sharing | Use IAP or the proxy |
| `/healthz` works but the uptime check does not | Cloud Run's frontend reserves `/healthz` and answers it itself | External checks must use `/agent/health` |

For anything else, start with the app plane's Cloud Run logs. Each chat turn
writes one structured `chat_turn` record (terminal state, error type, phase
durations, tool names, and token counts, never user content) keyed by a
server-minted `turn_id` that also tags the turn's trace spans.

---

## Repository layout

```
README.md                  this file — the only prose doc in the repo
deploy.sh                  the one deploy entry point; no --instance flag
.env.local.example         template for local .env.local development settings

config/                    YOURS — this deployment's settings and overrides
  instance.env             required: project, region, access
  theme.json               optional override
  agent-config.json        optional override
  prompts/  assets/        optional overrides
defaults/                  upstream baseline; config/ is laid over this
schemas/                   JSON Schemas + example themes — code, not config
scripts/                   build-time static asset staging (stage_static.mjs)

agent/                     app plane — API + SPA, one uvicorn process
  pyproject.toml           direct dependencies; ruff, mypy and pytest config
  uv.lock                  the resolved graph; generated by uv lock
  src/narratives_agent/    the Python package; imports are narratives_agent.*
    dev.py                 dev entry point: uv run narratives-agent-dev
    server/app.py          the app; production serves it with uvicorn
    server/routes/         spa · chat · system · dcproxy
    mcp/                   client · capabilities · schema · data_utils
    workflows/             chat_pipeline · mcp_loop · chart_config · follow_up
    gemini/                client · schemas
    *_test.py              pytest, colocated beside the module under test

ui/                        React source; built and baked into the agent image
  src/components/          presentational units
  src/config/              instance config and navigation routing
  src/hooks/               chat session, SSE, hash routing
  src/utils/               PDF export, turn inspection, DC web components

deploy/terraform-…/        one module tree
deploy/*.py                deploy-time guards: state ownership, theme schema
cloudbuild/                PR validation, deploy stamps
docs/smoke.sh              post-deploy checks
docs/architecture.drawio   editable source for the architecture diagram
```

Two things are deliberately **not** here: API keys, which live only in Secret
Manager, and a second deployment path — `deploy.sh` is the only one.

And one thing deliberately **is**: `config/`. It is committed, because that is
what makes this clone a deployment rather than a copy whose settings have to be
re-derived. Which is exactly why the clone must be private.

---

## Design notes

### Two seams, and only one is stable

**Agent → backend, over MCP: stable, abstract here.** The agent uses the
official `mcp` SDK to send `initialize`, `notifications/initialized`, `ping`,
`tools/list`, and `tools/call` requests over Streamable HTTP. The session ID is
sent in the `Mcp-Session-Id` header, and the protocol version is chosen during
`initialize`. This works unchanged across both server generations.

**Browser → backend, over HTTP: not stable, proxy it, do not translate it.** The
two REST generations return different shapes (`data[var][entity].series` +
`facets` versus `byVariable[v].byEntity`), and the chart web components read
their own data from the page origin. So: **one origin, one reverse proxy, no
shape translation.** The browser always talks to the app plane; the app plane
replays to whichever data plane is configured.

### Capability discovery, not declaration

The tool surface is probed from `tools/list` at boot rather than declared. A
hardcoded union of tool names lets the model call `get_variable_metadata` against
a 1.2.x server, which answers "Unknown tool" and burns an iteration; and if the
server is 1.2.x, source attribution is unavailable **silently**. Probing makes
that visible in `/agent/health` instead.

---

## Contributing

Before opening a PR, run what CI runs:

```sh
pnpm test
pnpm build

cd agent && uv sync --frozen \
  && uv run ruff format --check . && uv run ruff check . \
  && uv run mypy

cd .. && bash -n deploy.sh
cd deploy/terraform-custom-datacommons/modules \
  && terraform fmt -check -recursive . && terraform init -backend=false && terraform validate
```

Two rules that are easy to break by accident:

- **Keep a deployment clone private.** `config/` is committed by design, and
  `config/instance.env` names the project, the region, a service URL that embeds
  the project number, and everyone allowed in. That is disclosure on its own.
- **Change only `config/` in a deployment clone.** Anything else and every later
  `git pull upstream main` conflicts, and the clone stops being updatable. Code
  changes belong upstream.
- **Never commit a key.** Every `*_API_KEY` is empty in committed files; real
  values live only in Secret Manager.

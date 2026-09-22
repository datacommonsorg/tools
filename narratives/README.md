# Custom Data Commons

A branded, conversational Data Commons instance: a React UI and a Gemini agent in
one container, running against **any** Data Commons backend — Google's Data
Commons Platform (Spanner), the legacy Custom DC plane (Cloud SQL), or public
`datacommons.org`.

**The backend is a configuration value, not a branch. So is the branding.**

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
- [Choosing a data plane](#choosing-a-data-plane)
- [Setting up your deployment](#setting-up-your-deployment)
- [Customising it](#customising-it) — branding, prompts, agent config
- [Secrets](#secrets)
- [Deploying](#deploying)
- [Access modes](#access-modes)
- [Attaching to a Data Commons instance that already exists](#attaching-to-a-data-commons-instance-that-already-exists)
- [Provisioning a new DCP data plane](#provisioning-a-new-dcp-data-plane)
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
   browser ─────────►│  APP PLANE — identical, any backend  │
                     │  one container: agent API + SPA      │
                     │                                      │
                     │   MCP client ─ capability probe      │
                     │   /dcproxy   ─ → DATA_PLANE_URL      │
                     │   auth       ─ strategy chosen by    │
                     │                host                  │
                     └──────────────┬───────────────────────┘
                                    │  DATA_PLANE_URL
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
   DCP / Spanner              CDC / Cloud SQL         public datacommons.org
   Google's terraform         this repo's terraform   nothing to run
      DEFAULT
```

The app plane never knows which backend it is talking to. It has a URL, an auth
mode, and a tool surface it **discovers** at startup by probing `tools/list` —
`/agent/health` reports what it found. That is the whole abstraction; there is no
backend flag threaded through the code.

**The data plane is `ingress = internal` in every case.** Mixer, MCP and the
Flask pages are never reachable from the internet. Only the app plane is.

---

## Quickstart

The fastest path to something working is `DATA_BACKEND=none`, which runs against
public `datacommons.org`. No database, no ingestion, no bill — and it exercises
the whole application: chat, charts, branding, citations.

```sh
# 1. Clone. This clone IS the deployment.
git clone <repo-url> acme-dc && cd acme-dc

# 2. Fill in the five required values. Nothing has a default.
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

Move to `dcp` once that works. Changing backend is editing one line in
`config/instance.env` and redeploying.

**`--preflight` is the step worth not skipping.** It checks the things that
otherwise fail late or silently: credentials, billing, whether your organisation
even permits public access, and whether IAP has a consent screen to sign people
in with. It creates nothing.

---

## Prerequisites

| Need | Notes |
| :--- | :--- |
| A GCP project with **billing enabled** | |
| `gcloud`, authenticated | `gcloud auth login` **and** `gcloud auth application-default login` — separate; Terraform uses ADC |
| `terraform`, `npm`, `python3` on PATH | Images build in **Cloud Build**, so no local Docker is needed |
| A **Data Commons API key** | https://apikeys.datacommons.org |
| A **Gemini API key** | https://aistudio.google.com |
| [`uv`](https://docs.astral.sh/uv/) | The agent's dependencies; also `uv tool install datacommons-cli`, to provision a *new* DCP plane |

**Python 3.14.** The agent declares its direct dependencies in
`agent/pyproject.toml` and resolves the whole graph into `agent/uv.lock`.
`uv sync` creates `agent/.venv` from that lockfile, and commands run as
`uv run <command>`. Regenerate the lockfile with `uv lock` after a dependency
change, and never hand-edit it. The container pins `python:3.14-slim`.

**Node 20+** for the UI.

**IAM roles:** Owner, or the combination from the DCP documentation — Service
Usage Admin, Service Account Admin, Project IAM Admin, Storage Admin, Run Admin,
Secret Manager Admin, plus Cloud SQL Admin for the `cdc` backend.

---

## Choosing a data plane

One variable decides what gets created. The app plane is identical in all three
cases — it receives a URL and an auth mode, and has no notion of what is behind
them.

| `DATA_BACKEND` | What serves the data | Created by | Use when |
| :--- | :--- | :--- | :--- |
| **`dcp`** *(default)* | Google's Data Commons Platform — Spanner, managed ingestion, no NL server | `datacommons-cli`, **separately** — or already running, see [attaching](#attaching-to-a-data-commons-instance-that-already-exists) | You need your own data and want Google to run the plumbing |
| `cdc` | The legacy plane — this repo's services image over Cloud SQL, plus an ingest Job | This deploy | An existing instance that cannot move yet |
| `none` | Public `datacommons.org` | Nothing | Demos, pilots, review stacks |

Switching backends is editing `DATA_BACKEND` in `instance.env` and redeploying.
No code changes, no branch.

### Why DCP is the default

**Cloud SQL is the first hard wall, and Spanner does not have that wall.** There
is no connection-pool sizing configured anywhere in the Terraform, the tier
defaults to shared-core `db-g1-small`, and Cloud Run's default concurrency allows
a large number of simultaneous requests against it. MySQL fails with "too many
connections" rather than merely slow queries. Spanner uses session pools and has
no fixed connection ceiling.

Secondary: DCP has no NL server to run, ingestion is managed, and the Mixer
defaults to stale reads so ingestion causes no downtime.

---

## Setting up your deployment

Everything this deployment owns lives in `config/`:

```
config/
  instance.env       where it runs, which backend, who can reach it — NO secrets
  branding.json      OPTIONAL — only the keys you want to change
  agent-config.json  OPTIONAL — only the keys you want to change
  prompts/           OPTIONAL — only the prompts you want to change
  assets/            OPTIONAL — your logo, favicon, CSS
```

Only `instance.env` is required. Everything else is an **override**: at deploy
time `defaults/` is laid down first and `config/` is copied over the top, so you
carry only your differences and inherit every upstream improvement when you pull.

`config/instance.env` has ten variables and **none of them has a default**. That
is deliberate — each one decides where your data lives, what it costs, or who can
reach it, and a default is a decision made on your behalf that you would not see
until the bill or the latency showed up. `REGION` in particular.

Required always:

| | |
| :--- | :--- |
| `PROJECT_ID` | Your GCP project. Billing must be enabled. |
| `REGION` | Where everything runs. Check your data-residency obligations first — moving later means recreating everything. |
| `INSTANCE` | Lowercase, DNS-safe. Names every resource and the Terraform state prefix. |
| `DATA_BACKEND` | `none`, `dcp` or `cdc` |
| `ACCESS_MODE` | `public`, `iap` or `private` |

Required depending on those choices, and `--preflight` tells you which:

| | |
| :--- | :--- |
| `AUTHORIZED_MEMBERS` | for `iap` and `private` |
| `PUBLIC_DC_URL`, `PUBLIC_DC_WEB_URL` | for `none` — **two different hosts**, see below |
| `DCP_SERVICE_URL`, `DCP_SERVICE_NAME` | for `dcp` |
| `CLOUDSQL_TIER`, `CLOUDSQL_AVAILABILITY_TYPE` | for `cdc` — these bill by the hour, so they are explicit |

### The `none` backend needs two URLs, not one

This is the only backend where the agent and the browser talk to **different
hosts**, and it is worth understanding before you fill it in:

| | Value | Used by |
| :--- | :--- | :--- |
| `PUBLIC_DC_URL` | `https://api.datacommons.org` | the **agent** — the versioned REST API, and `/mcp` |
| `PUBLIC_DC_WEB_URL` | `https://datacommons.org` | the **browser** — `/api/observations/series`, `/api/place/name`, `/core/api/...` |

The agent's MCP endpoint is `PUBLIC_DC_URL` with `/mcp` appended.

Point both at the API host and you get a deployment that looks like it works:
chat answers correctly, every number is right, and **no chart ever renders**. The
browser's requests reach a host that does not serve those routes and come back as
Cloud Endpoints 404s, which nothing surfaces server-side. They were Terraform
defaults until now, which meant the split was invisible from the configuration.

Use the standard values unless you are pointing at a different public Data
Commons deployment.

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
history, and it names your project, your region, your data-plane URL (which
embeds the project number) and everyone allowed in.

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
fixes and branding defaults all arrive; your overrides stay yours.

**Change only `config/`.** The moment a deployment edits code, every later pull
conflicts and it stops being updatable. If you need a code change, make it
upstream.

---

## Customising it

Everything visual and behavioural is configuration. Three directories, with
clearly different jobs:

| Directory | Owned by | Edit it? |
| :--- | :--- | :--- |
| `schemas/` | upstream | No — the JSON Schemas that validate the other two |
| `defaults/` | upstream | No — the baseline every deployment inherits |
| `config/` | **you** | Yes — only the keys you want to differ |

At deploy time `defaults/` is laid down and `config/` is copied over the top. So
you write only your differences, and an upstream prompt or branding fix reaches
you on the next `git pull` instead of sitting unnoticed in a file you copied
once and forgot.

| What you can override | Validated by | Controls |
| :--- | :--- | :--- |
| `config/branding.json` | `schemas/branding.schema.json` | identity, theme, content, structure |
| `config/agent-config.json` | `schemas/agent-config.schema.json` | models, thinking levels, template vars |
| `config/prompts/*.md` | — | `mcp`, `synthesis`, `follow_up` |
| `config/assets/` | — | logo, favicon, CSS overrides |

Both schemas set `additionalProperties: false`, so an unrecognised key is an
error rather than a silently ignored one — a typo'd colour name fails loudly.

### Branding

```sh
cp schemas/branding.neutral.example.json config/branding.json
$EDITOR config/branding.json
./deploy.sh --config-only --restart
```

You do not have to start from a full file. `config/branding.json` can contain
only the keys you want to change — everything else comes from `defaults/`:

```json
{
  "instance_name": "Acme Data Commons",
  "logo": "assets/acme.svg",
  "colors": { "primary": "#0B6E8F" }
}
```

| Group | Keys |
| :--- | :--- |
| Identity | `instance_name`, `headline`, `tagline`, `logo`, `logo_text`, `logo_height`, `logo_alt`, `favicon` |
| Theme | `colors` (primary, accent, text, surfaces, borders, containers…), `radius` (card / input / chip), `fonts` |
| Content | `suggestions` — the starter chips; `footer` text and links |
| Structure | `navigation` — header tabs; `metrics.tabs`; `analytics.ga_tag_id` |

Two complete examples ship as starting points: `schemas/branding.neutral.example.json`
(neutral theme) and `schemas/branding.base-dc.example.json` (Google blue, no header
menu). `schemas/branding.example.json` lists every field with placeholder values.

**`navigation` has three meanings**, and the distinction is load-bearing:

| Value | Result |
| :--- | :--- |
| key absent | keep the tabs this deployment ships (`NAV_CONFIG`) |
| `[]` | **no header menu at all** |
| `[{label, href}, …]` | exactly these tabs |

Pinned by `ui/src/config/nav_config.test.ts`, because a default that carried a
navigation value once collapsed the first case into the second and silently
removed every tab on any instance without a `branding.json`.

**Assets.** Put images in `config/assets/` and reference them
relatively — `{ "logo": "assets/logo.png" }`. The agent pulls them into memory at
startup and serves them from `/agent/brand/assets/<name>`, rewriting the paths
before the document leaves the process. **The browser never reads the config
bucket**, so the bucket stays private. Absolute and `data:` URIs pass through
untouched.

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

`--restart` is **not optional**. Config and branding are read **once at agent
startup** and served from process memory thereafter. There is no TTL and no
runtime refetch, so a bucket sync alone changes nothing until a new revision
starts serving.

### How branding reaches the browser

Four routes, all served out of the same startup-loaded memory:

| Route | What | Cache |
| :--- | :--- | :--- |
| `/agent/brand.css` | CSS custom properties for the colours | `no-store` |
| `/agent/brand.js` | the whole document as `window.__BRAND__` | `no-store` |
| `/agent/brand` | the same document as JSON, for the runtime fetch | `no-store` |
| `/agent/brand/assets/<n>` | mirrored images | immutable |

`brand.css` and `brand.js` are **blocking tags in `<head>`**, so branding is
correct on the *first* frame. `brand.js` is deliberately a **classic** script,
not a module — Vite warns about this on every build, and the warning is correct
but the behaviour is intentional: a module would be deferred, which defeats the
point. Without it only the colours pre-paint, and the shipped headline, wordmark,
logo, tabs and chips render first and visibly flip once `/agent/brand` resolves.

Four safety properties worth knowing before you put a client's config in a
bucket:

- **Credential scrubbing.** The loaded document is scanned for credential-shaped
  values, by key name (`api_key`, `secret`, `token`, `password`, …) and by value
  format. Matches are dropped and logged at error level, so a key pasted into
  `branding.json` degrades the theme instead of reaching every visitor.
- **The bucket URL is not disclosed.** `/agent/brand` deliberately omits it.
- **CORS fails closed.** In a deployed environment with no origin configured the
  allow-list is empty and the condition is logged, rather than defaulting to `*`.
- **Failures are non-fatal.** An unset, unreachable, non-JSON or non-object
  config leaves the UI on its shipped design tokens rather than stopping the
  server from starting.

---

## Secrets

```sh
DC_API_KEY=... GEMINI_API_KEY=... \
  ./deploy.sh --bootstrap-secrets
```

Values are read from **this process's environment**, written to Secret Manager,
and never persisted to disk. Every later deploy needs no keys at all. If you skip
this, the deploy stops and tells you which secrets are missing.

Add `MAPS_API_KEY=...` only for `DATA_BACKEND=cdc` — it is the only backend that
reads it.

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
verify secrets → build the UI and bake it into the app image (plus the services
image, **only** on `cdc`) → compose the config bucket from `defaults/` +
`config/` and sync it → `terraform apply` → smoke tests.

First run is ~10 minutes, or ~20 on `cdc` because Cloud SQL is slow to create.

**Preview the plan before an apply into a project that already has resources:**

```sh
./deploy.sh --plan
```

Every line should read `will be created`, and the summary should read
**`0 to change, 0 to destroy`**. **If anything says `will be destroyed`, stop** —
the state prefix or `INSTANCE` did not take, and you are pointed at another
deployment's state. Applying would rename, that is destroy and recreate, its
resources.

### Everyday commands

| | |
| :--- | :--- |
| Check before deploying | `./deploy.sh --preflight` |
| Branding, prompts, agent-config | `./deploy.sh --config-only --restart` |
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

Asks you to type the deployment name, then destroys everything Terraform created
— on `cdc` that includes the Cloud SQL instance and its data. The config bucket
and the Secret Manager entries are left alone, so a later redeploy does not need
the keys again; delete them separately if you want them gone.

It runs the same state-ownership guard as the apply path, so it cannot destroy
resources belonging to another deployment.

---

## Access modes

How the app is exposed, set by `ACCESS_MODE`. Independent of which backend you
chose. In every mode the data plane stays `ingress=internal`, so Mixer, MCP and
the Flask pages are never reachable from the internet.

### `public`

`allUsers` gets `run.invoker`. Anyone with the URL can use it — **including the
chat endpoint, so anyone with the URL spends your Gemini quota.**

Many organisations forbid this outright through Domain Restricted Sharing. When
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
*this* service; forwarded alongside the service-account token it gives the data
plane a mixed identity and it refuses — a 401 on every chart, after a successful
sign-in. Handled in code; if you add another proxy hop, it must do the same.

### `private`

No public binding and no sign-in. `AUTHORIZED_MEMBERS` get `run.invoker`
directly, so they can reach it with an identity token or through the proxy:

```sh
gcloud run services proxy <instance>-app --region=<region> --port=8080
```

Right for a pilot you drive yourself, and the safe choice when you are not yet
sure which of the other two you need.

---

## Attaching to a Data Commons instance that already exists

The common enterprise case: a Data Commons / Spanner instance is already running
and loaded, and you want to put this UI and agent in front of it **without
touching the data layer at all**.

Nothing needs to be provisioned. Point an instance at it:

```sh
# config/instance.env
DATA_BACKEND="dcp"
DCP_SERVICE_URL="https://<existing-service>-uc.a.run.app"
DCP_SERVICE_NAME="<existing-service>"
```

**What this deploy does to the existing data plane: one additive IAM binding, and
nothing else.**

The app plane needs `run.invoker` on the existing service so it may call MCP.
That is expressed as `google_cloud_run_v2_service_iam_member` — an *additive
member* resource, not `..._iam_policy`. It adds one member and leaves every other
binding untouched. The service, its revisions, its Spanner data, its ingestion and
its own callers are never in scope.

Confirm that before applying, rather than trusting it:

```sh
./deploy.sh --plan
```

Every line must read **`will be created`**, and the summary must read
**`0 to change, 0 to destroy`**.

Two things to expect:

- **The tool surface is whatever that server serves, and it is probably not what
  you assume.** A live DCP instance measured during this work served **two** MCP
  tools (1.2.x), not the six of 1.3.0. `/agent/health` reports what it found.
  `supports_source_attribution: false` follows from the absence of
  `get_variable_metadata`, and means answers carry a bare domain rather than a
  named source and licence. That is correct behaviour, not a failure.

**The name matters as much as the URL** — `DCP_SERVICE_NAME` is what the app
plane's service account is granted `run.invoker` on. Without that grant a private
DCP backend refuses every MCP call, and it presents as "no data" rather than as an
error. `deploy.sh` refuses to start without both.

---

## Provisioning a new DCP data plane

DCP's data plane is **not** created by this repo, and cannot be: the Spanner
instance, the BigQuery reservation, the Workflows orchestrator and the Dataflow
flex template are Google's artifacts. `datacommons-cli` is irreducible for
`admin init-db` (Spanner DDL) and `admin ingest start` (a Workflows execution,
not a resource).

```sh
uvx datacommons-cli admin init --project-id "$PROJECT_ID" \
    --instance-name "<namespace>" --dc-api-key "$DC_API_KEY"
cd <namespace> && terraform init && terraform apply
uvx datacommons-cli admin init-db          # creates the Spanner schema
```

Then take the two values into `instance.env`:

```sh
terraform output datacommons_service_url    # -> DCP_SERVICE_URL
terraform output datacommons_service_name   # -> DCP_SERVICE_NAME
```

To load data: upload to the artifacts bucket and
`uvx datacommons-cli admin ingest start --imports <dir>`. Three things from the
DCP docs worth repeating:

- **Re-ingesting an import wipes and rebuilds all of it.** No incremental imports
  — always upload the complete file set.
- **Every provenance's `Source` must be defined in your MCF.** It is not resolved
  from base Data Commons.
- **The BigQuery reservation is one per project per region**, shared by every
  deployment. A second one breaks ingestion for all of them.

---

## Local development

Two paths. Pick by what you are changing.

There is deliberately **no "run the whole data plane locally" path**. Cloud SQL,
Spanner, Workflows and Dataflow are not reproducible on a laptop, and the DCP
ingestion pipeline cannot be run locally at all. Point at a deployed backend
instead — or at public Data Commons, which needs nothing provisioned.

### Path A — UI only (the fast loop)

A hot-reloading Vite dev server proxying every backend call to a deployed
instance. Real Gemini, real MCP tools, real charts.

```sh
cd ui
npm install

cat > .env.local <<'EOF'
BACKEND_URL=https://<your-instance>.run.app
AGENT_URL=https://<your-instance>.run.app
EOF

npm run dev      # http://localhost:3000
```

Both URLs normally point at the same Cloud Run service. Vite's `server.proxy`
(in `vite.config.ts`) forwards `/agent/*` and the data routes; it is **dev-only**,
so `vite build` ignores it. Defaults are `localhost:5001` and `localhost:8080` if
unset. Vite picks up `.env.local` changes on **restart**, not live.

You need Node 20+ and nothing else — no Docker, no Python, no gcloud.

### Path B — the agent locally

```sh
cd agent
uv sync          # creates .venv and installs from uv.lock
```

There is nothing to activate: `uv sync` creates `.venv` itself, and `uv run`
uses it.

Choose what it talks to — the same three backends, selected the same way, by URL.

**Public Data Commons.** Nothing to provision, but note it takes **two** hosts:

```sh
export MCP_SERVER_URL="https://api.datacommons.org/mcp"
export DC_API_KEY="..."
export DATA_PLANE_URL="https://api.datacommons.org"      # MCP + versioned REST
export DATA_PLANE_WEB_URL="https://datacommons.org"      # website routes the charts call
```

`api.datacommons.org` serves `/v1`, `/v2` and `/mcp`. It does **not** serve the
website routes the chart web components fetch — `/api/observations/series`,
`/api/place/name`, `/core/api/...` — which live on `datacommons.org` only. Set
only `DATA_PLANE_URL` and the agent answers correctly with real numbers while
every chart silently 404s, because the failure is entirely browser-side:

```json
{"message":"The current request is not defined by this API.","code":404}
```

`DATA_PLANE_WEB_URL` defaults to `DATA_PLANE_URL`, so a deployed plane needs only
the one URL — one container serves both MCP and the website.

**A deployed data plane:**

```sh
export MCP_SERVER_URL="https://<data-plane>-uc.a.run.app/mcp"
export DATA_PLANE_URL="https://<data-plane>-uc.a.run.app"
```

> A private data plane expects a Google-signed ID token, which the agent mints
> from the **metadata server** — unavailable off GCP, so `attach_auth` is a no-op
> on a laptop and the call is refused. Either widen that service's ingress
> temporarily, or run against public Data Commons. Local development against a
> private backend is not a supported path.

**Config and keys:**

```sh
export CONFIG_URL="https://storage.googleapis.com/<bucket>/agent-config.json"
export BRAND_CONFIG_URL="https://storage.googleapis.com/<bucket>"
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

**Serve the SPA from the agent**, so routing matches production:

```sh
(cd ui && npm ci && npm run build)
export STATIC_ROOT="$(cd ui/dist && pwd)"
```

Skip it if you only care about the API — `/` will 404 and `/agent/*` still works.

**Run and check:**

```sh
cd agent && uv run python main.py      # http://localhost:5001

curl -s localhost:5001/agent/health | jq    # mcp.tool_count is the probed tool surface
curl -sN -X POST localhost:5001/agent/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is the population of France?","history":[]}'
```

The stream should carry `session_id`, `mcp_start`, tool events, text, and `done`.
Production runs `gunicorn main:app`; `main.py` is the development path.

---

## Testing

Nothing is mocked that matters.

```sh
# Agent — from agent/
cd agent
uv sync                                    # once, and after a dependency change
uv run pytest

# UI — from ui/
cd ui
npx tsc --noEmit
npx vitest run                             # 9 files, 108 tests
```

Agent tests are pytest modules named `*_test.py`, colocated beside the module
under test inside `src/narratives_agent/`. `uv run` executes them in the locked
environment, so there is nothing to activate and nothing to install by hand.

Style and types are separate checks, and CI fails on any of them:

```sh
cd agent
uv run ruff format --check .               # formatting
uv run ruff check .                        # lint
uv run mypy                                # types, strict
```

> The agent type-checks under `mypy --strict`. Modules written before that
> standard are exempted one at a time in `agent/pyproject.toml`, and each
> exemption names the branch that rewrites or deletes the module it covers. An
> exemption is retired by deleting that module, never by annotating code that is
> about to be replaced — the list only shrinks.

The agent suites cover four behaviors whose failure is **silent**:

- **MCP session recovery** when the data plane scales. Sessions are bound to the
  process that minted them and Cloud Run has no affinity, so a session created
  against instance 1 gets presented to instance 2, which has never seen it.
- **Both server generations parsing correctly** — including the empty response
  that used to report `has_data=true` for no data. A 1.3.x server signals "no
  data" as `{"data": {}}`, which the old substring check did not match, so the
  agent narrated numbers it never received.
- **Auth chosen by target host** — API key for public hosts, minted ID token for
  private ones. Widening the host list to make a backend work is a security
  regression, not a fix.
- **Prompt placeholder substitution** — an unsubstituted `{{instance.*}}` reaches
  the user inside an answer.

---

## Verifying a deployment

```sh
bash docs/smoke.sh "$URL"
curl -s "$URL/agent/health" | jq
```

`mcp.generation` and `mcp.supports_source_attribution` tell you which MCP surface
the agent actually found. If `supports_source_attribution` is false, answers carry
weaker provenance — no named source, no licence.

> The smoke suite's data check queries `Count_Person` / `country/IND`, which is
> **base** Data Commons data served through the passthrough. It passes on any
> backend and therefore proves nothing about *your* ingested data. For `dcp`,
> confirm that in Spanner: `SELECT COUNT(*) FROM Observation`.

Branding:

```sh
curl -s "$URL/agent/brand" | jq '.branding.instance_name, .branding.navigation'
curl -sI "$URL/agent/brand.css" | grep -i cache    # expect no-store
curl -s "$URL/agent/brand" | grep -ci bucket       # expect 0 — URL not disclosed
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
| `data_backend = "dcp" requires dcp_service_url` | Missing DCP outputs | [Provisioning](#provisioning-a-new-dcp-data-plane) |
| Chat answers "no data" for everything | App SA lacks `run.invoker` on the data plane, or `DCP_SERVICE_NAME` is wrong | Check `app_invokes_dcp` in the plan; look for `dcproxy: … -> HTTP 403` in agent logs |
| Charts blank, chat fine | `/dcproxy` failing | Agent logs — `401/403` is IAM or ingress, `404` is a path the data plane does not serve |
| Charts blank on `none`, `{"code":404,"message":"The current request is not defined by this API"}` | Chart routes are on a **different host** to MCP | Terraform sets `DATA_PLANE_WEB_URL` for this. Chat keeps working either way, so only the browser sees the fault |
| Charts blank on `cdc` after idle, first load only | Data plane scaled to zero; a cold container takes ~6s | Set `min_instances = 1`, or accept the first-request penalty |
| Config or branding change does nothing | Read once at startup | `--config-only --restart` |
| Theme flashes on load | `brand.js` not running | Check it is in `<head>` and `/agent/brand.js` returns 200 |
| Every tab vanished | `navigation: []` in branding.json | Remove the key to restore the shipped tabs |
| Locally the theme is the default | No reachable `BRAND_CONFIG_URL` | Correct behaviour, not a bug |
| A colour is ignored | Not in the schema, or fails the safe-value pattern | Check the agent log for a rejection |
| Logo is a broken image | Path not under `config/assets/`, or `AGENT_API_PREFIX` disagrees with what `brand.py` rewrites | |
| `Refusing to apply: the state loaded for 'x' describes another instance` | `deploy.sh` caught a wrong state prefix | Do **not** override. Re-`init` with the right prefix |
| A deploy reports success but the change is not live | Uncommitted work rebuilds to the same `IMAGE_TAG` | Commit, then redeploy |
| Every chart 401s *after* a successful IAP sign-in | IAP identity headers reaching the backend | Should not happen — `/dcproxy` strips them. Suspect an added proxy hop |
| Public access binding refused | Domain Restricted Sharing | Use IAP or the proxy |
| `/healthz` works but the uptime check does not | Cloud Run's frontend reserves `/healthz` and answers it itself | External checks must use `/agent/health` |
| A private backend refuses everything locally | No metadata server on a laptop | Expected — see Path B |
| Ingestion fails: missing `Source` | MCF incomplete | Define every provenance's `Source` node |
| Ingestion fails: BigQuery reservation | A second one in the project+region | Reuse the existing reservation |
| `403 iam.serviceAccounts.getOpenIdToken` on `init-db` | IAM propagation | Wait a minute, retry |

For anything else, start with the app plane's Cloud Run logs — session events are
structured JSON queryable by `session_id` and `event_type`.

---

## Repository layout

```
README.md                  this file — the only prose doc in the repo
deploy.sh                  the one deploy entry point; no --instance flag

config/                    YOURS — this deployment's settings and overrides
  instance.env             required: project, region, backend, access
  branding.json            optional override
  agent-config.json        optional override
  prompts/  assets/        optional overrides
defaults/                  upstream baseline; config/ is laid over this
schemas/                   JSON Schemas + example branding — code, not config

agent/                     app plane — API + SPA, one gunicorn process
  main.py                  dev entry point; production runs gunicorn main:app
  pyproject.toml           direct dependencies; ruff, mypy and pytest config
  uv.lock                  the resolved graph; generated by uv lock
  src/narratives_agent/    the Python package; imports are narratives_agent.*
    server/routes/         spa · brand · chat · system · dcproxy
    mcp/                   client · capabilities · schema · data_utils
    workflows/             chat_pipeline · mcp_loop · chart_config · follow_up
    gemini/                client · schemas
    *_test.py              pytest, colocated beside the module under test

ui/                        React source; built and baked into the agent image
  src/components/          presentational units
  src/hooks/               branding, chat session, SSE, hash routing
  src/utils/               PDF export, turn inspection, DC web components

image/                     CDC data-plane overlay (nginx routing only; cdc backend)
deploy/terraform-…/        one module tree; `data_backend` selects the plane
deploy/*.py                deploy-time guards: state ownership, branding schema
cloudbuild/                PR validation, image promotion, deploy stamps
docs/smoke.sh              post-deploy checks
docs/architecture.drawio   editable source for the architecture diagram
sample-data/               seed CSVs for the cdc ingest job
```

Two things are deliberately **not** here: API keys, which live only in Secret
Manager, and a second deployment path — `deploy.sh` is the only one.

And one thing deliberately **is**: `config/`. It is committed, because that is
what makes this clone a deployment rather than a copy whose settings have to be
re-derived. Which is exactly why the clone must be private.

---

## Design notes

### Two seams, and only one is stable

**Agent → backend, over MCP: stable, abstract here.** Four JSON-RPC methods —
`initialize`, `notifications/initialized`, `tools/list`, `tools/call` — over
Streamable-HTTP, session in the `Mcp-Session-Id` header, protocol version
config-driven. This genuinely works unchanged across every backend.

**Browser → backend, over HTTP: not stable, proxy it, do not translate it.** The
two REST generations return different shapes (`data[var][entity].series` +
`facets` versus `byVariable[v].byEntity`), and the chart web components read
their own data from the page origin. So: **one origin, one reverse proxy, no
shape translation.** The browser always talks to the app plane; the app plane
replays to whichever data plane is configured.

### Why the app plane is a separate container

Google's `stack` module hard-wires the services container's environment — there
is no env pass-through. Baking the agent into that image and injecting env
afterwards with `gcloud run services update` **gets silently wiped**, because the
module sets `FORCE_RESTART = timestamp()`, guaranteeing a diff on every apply,
which reconciles the container spec and drops the injected vars. The symptom
(`"Backend config not loaded"`) arrives later, on an unrelated apply.

A decoupled app plane never asks Google's service to carry our configuration.

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
cd agent && uv sync --frozen \
  && uv run ruff format --check . && uv run ruff check . \
  && uv run mypy && uv run pytest

cd ../ui && npm ci && npx tsc --noEmit && npx vitest run

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

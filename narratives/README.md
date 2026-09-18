# Custom Data Commons

A branded, conversational Data Commons instance: a React UI and a Gemini agent in
one container, running against **any** Data Commons backend — Google's Data
Commons Platform (Spanner) or public `datacommons.org`.

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
- [Troubleshooting](#troubleshooting)
- [Repository layout](#repository-layout)

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
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
           DCP / Spanner                    public datacommons.org
           Google's terraform               nothing to run
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

Move to `dcp` once that works. The DCP data plane is not created by this
repository — you point at one that is already running, which is three lines in
`config/instance.env` and a redeploy. See
[attaching](#attaching-to-a-data-commons-instance-that-already-exists).

No code changes, no branch.

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
| `terraform`, `npm`, `python3`, `curl` on PATH | Images build in **Cloud Build**, so no local Docker is needed. `curl` is what validates your API keys |
| A **Data Commons API key** | https://apikeys.datacommons.org |
| A **Gemini API key** | https://aistudio.google.com |

**Python 3.11–3.13.** The agent's pinned `grpcio-status==1.71.2` cannot resolve
on Python 3.14 (`google-api-core` requires `>=1.75.1` there), so
`pip install -r requirements.txt` fails outright. The container pins
`python:3.11-slim`, so this only bites local work.

**Node 20+** for the UI.

**IAM roles:** Owner, or the combination from the DCP documentation — Service
Usage Admin, Service Account Admin, Project IAM Admin, Storage Admin, Run Admin,
Secret Manager Admin.

---

## Choosing a data plane

One variable decides what gets created. The app plane is identical either way —
it receives a URL and an auth mode, and has no notion of what is behind them.

| `DATA_BACKEND` | What serves the data | Created by | Use when |
| :--- | :--- | :--- | :--- |
| **`dcp`** *(default)* | Google's Data Commons Platform — Spanner, managed ingestion, no NL server | Not this repository — it must already exist, see [attaching](#attaching-to-a-data-commons-instance-that-already-exists) | You need your own data and want Google to run the plumbing |
| `none` | Public `datacommons.org` | Nothing | Demos, pilots, review stacks |

Switching backends is editing `DATA_BACKEND` in `instance.env` and redeploying.
No code changes, no branch.

**The DCP data plane is not created by this repository.** If you are choosing
`dcp`, read
[attaching to an instance that already exists](#attaching-to-a-data-commons-instance-that-already-exists)
before you fill anything in.


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
| `DATA_BACKEND` | `none` or `dcp` |
| `ACCESS_MODE` | `public`, `iap` or `private` |

Required depending on those choices, and `--preflight` tells you which:

| | |
| :--- | :--- |
| `AUTHORIZED_MEMBERS` | for `iap` and `private` |
| `PUBLIC_DC_URL`, `PUBLIC_DC_WEB_URL` | for `none` — **two different hosts**, see below |
| `DCP_SERVICE_URL`, `DCP_SERVICE_NAME` | for `dcp` |

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

| What you can override | Start from | Validated by | Controls |
| :--- | :--- | :--- | :--- |
| `config/branding.json` | `schemas/branding.neutral.example.json` | `schemas/branding.schema.json` | identity, theme, content, structure |
| `config/agent-config.json` | `schemas/agent-config.example.json` | `schemas/agent-config.schema.json` | models, thinking levels, RAG, template vars |
| `config/prompts/*.md` | `defaults/prompts/*.md` | — | `mcp`, `synthesis`, `kb`, `follow_up` |
| `config/assets/` | — | — | logo, favicon, CSS overrides |

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
| Identity | `instance_name`, `headline`, `tagline`, `logo`, `logo_text`, `logo_height`, `favicon` |
| Theme | `colors` (primary, accent, text, surfaces, borders, containers…), `radius` (card / input / chip), `fonts` |
| Content | `suggestions` — the starter chips; `footer` text and links |
| Structure | `navigation` — header tabs; `metrics.tabs` |

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

### Agent config

```sh
cp schemas/agent-config.example.json config/agent-config.json
$EDITOR config/agent-config.json
./deploy.sh --config-only --restart
```

Same rule as branding: keep only the keys you want to differ and delete the rest.
The example lists every field with placeholder values, so it is a reference to
read, not a file to ship as-is.

| Group | Keys | What it decides |
| :--- | :--- | :--- |
| `thinking` | `mcp_level`, `synthesis_level` — `low` / `medium` / `high` | **The cost and latency dial.** `mcp_level` budgets the tool-planning loop, `synthesis_level` the final answer. Both are `medium` by default |
| `gemini` | `mcp_model`, `kb_model`, `api_base` | Which model runs each phase, and a regional endpoint if you need one |
| `template_vars` | `name`, `region`, `states_term`, plus anything you add | Substituted into `{{instance.*}}` in prompts — see [Prompts](#prompts) |
| `knowledge_base` | `enabled` | Turns the File Search RAG phase on or off |
| `gemini.filestores` | corpus IDs | Which corpora that phase searches |
| `mcp` | `enabled` | `false` runs synthesis-only with no tool loop — a chat-only fallback for when the data plane is down |
| `query_param_key` | a token you choose | Gates `?demo=true` and the model / thinking overrides. **Omitted by default, which disables both outright** |

A minimal override is as small as this:

```json
{
  "thinking": { "mcp_level": "high" },
  "template_vars": { "name": "Acme Data Commons", "region": "the UK" }
}
```

**No key is ever a value here.** `gemini.api_keys` and `gemini.demo_api_keys` are
in the schema as a *shape contract*. Real keys reach the agent from Secret
Manager via [`--bootstrap-secrets`](#secrets); the committed files carry an empty
array, and anything credential-shaped in the loaded document is scrubbed and
logged at error level before it can be served.

**`query_param_key` is a soft gate, not authentication.** Set it only if you want
demo links, never reuse one across deployments, and make it non-guessable — it
hands the caller your demo API key pool.

**Turning on the knowledge base (RAG).** Four steps, and the first two are not in
this repository:

1. Provision a Gemini File Search corpus at https://aistudio.google.com
2. Upload your reference documents to it
3. Put its ID in `gemini.filestores` — `["fileSearchStores/<id>"]`
4. Set `knowledge_base.enabled` to `true`, then `./deploy.sh --config-only --restart`

Left `false`, the KB pipeline is skipped entirely. With no corpus that is the
correct state, not a failure.

**`mcp.server_url` in the defaults is ignored once deployed.** Terraform sets
`MCP_SERVER_URL` from the data plane it configured and the environment variable
wins. The `127.0.0.1:8082` is there so a laptop run finds a local server; it is
never the value that ships.

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
  "states_term": "regions"
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
verify secrets → build the UI and bake it into the app image → compose the config
bucket from `defaults/` + `config/` and sync it → `terraform apply` → smoke tests.

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

Asks you to type the deployment name, then destroys everything Terraform created.
The config bucket and the Secret Manager entries are left alone, so a later
redeploy does not need the keys again; delete them separately if you want them
gone.

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
| `data_backend = "dcp" requires dcp_service_url` | Missing DCP outputs | [Attaching](#attaching-to-a-data-commons-instance-that-already-exists) |
| Chat answers "no data" for everything | App SA lacks `run.invoker` on the data plane, or `DCP_SERVICE_NAME` is wrong | Check `app_invokes_dcp` in the plan; look for `dcproxy: … -> HTTP 403` in agent logs |
| Charts blank, chat fine | `/dcproxy` failing | Agent logs — `401/403` is IAM or ingress, `404` is a path the data plane does not serve |
| Charts blank on `none`, `{"code":404,"message":"The current request is not defined by this API"}` | Chart routes are on a **different host** to MCP | Terraform sets `DATA_PLANE_WEB_URL` for this. Chat keeps working either way, so only the browser sees the fault |
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
| A private backend refuses everything locally | No metadata server on a laptop | Expected off GCP — the agent cannot mint an ID token there. Run against public Data Commons instead |
| `pip install -r requirements.txt` fails with `ResolutionImpossible` | Python 3.14 | Use Python 3.11–3.13 |

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
  src/server/routes/       spa · brand · chat · tools · system · dcproxy
  src/mcp/                 client · capabilities · schema · data_utils
  src/workflows/           chat_pipeline · mcp_loop · kb_search · follow_up
  src/gemini/              client · schemas
  tests/                   framework-free; needs requirements.txt installed

ui/                        React source; built and baked into the agent image
  src/components/          presentational units
  src/hooks/               branding, chat session, SSE, hash routing
  src/utils/               PDF export, turn inspection, DC web components

deploy/modes/              the four modes that are not the deploy path:
                           preflight · bootstrap-secrets · config-sync · destroy
deploy/terraform-…/        one module tree; `data_backend` selects the plane
deploy/*.py                deploy-time guards: state ownership, branding schema
cloudbuild/                PR validation, deploy stamps
docs/smoke.sh              post-deploy checks
```

Two things are deliberately **not** here: API keys, which live only in Secret
Manager, and a second deployment path — `deploy.sh` is the only one.

And one thing deliberately **is**: `config/`. It is committed, because that is
what makes this clone a deployment rather than a copy whose settings have to be
re-derived. Which is exactly why the clone must be private.


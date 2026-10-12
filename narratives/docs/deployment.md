# Deployment & Customization Guide

This guide covers configuring, customizing, deploying, verifying, and
troubleshooting a Narratives instance on Google Cloud Run.

For a high-level overview of the application, see
[`../README.md`](../README.md). For local development and testing, see
[`development.md`](development.md). For system internals, see
[`architecture.md`](architecture.md).

---

## Contents

- [Core deployment model](#core-deployment-model)
- [Prerequisites](#prerequisites)
- [Setting up your deployment](#setting-up-your-deployment)
- [Customizing your instance](#customizing-your-instance)
- [Secrets](#secrets)
- [Deploying](#deploying)
- [Access modes](#access-modes)
- [Verifying a deployment](#verifying-a-deployment)
- [Troubleshooting](#troubleshooting)

---

## Core deployment model

- **The branding is a configuration value, not a branch.** Everything you edit
  for a deployment lives in `config/`. Nothing else needs touching, and nothing
  you do there requires TypeScript or Python.
- **One clone of this repository is one deployment.** Clone it, fill in
  `config/instance.env`, change what you want to look different, and deploy. For
  a second deployment, clone it again — there is no `--instance` flag and no way
  to run two from one checkout.

---

## Prerequisites

| Need | Notes |
| :--- | :--- |
| A GCP project with **billing enabled** | |
| `gcloud`, authenticated | `gcloud auth login` **and** `gcloud auth application-default login` — separate; Terraform uses ADC |
| `terraform`, `pnpm`, `python3` on PATH | Images build in **Cloud Build**, so no local Docker is needed |
| A **Data Commons API key** | https://apikeys.datacommons.org |
| A **Gemini API key** | https://aistudio.google.com |
| [`uv`](https://docs.astral.sh/uv/) | Manages Python 3.14 dependencies (`agent/pyproject.toml` and `agent/uv.lock`) |
| **Node 24** | Compiles the React UI (`ui/`) |

**IAM roles:** Owner, or Service Usage Admin, Service Account Admin, Project IAM
Admin, Storage Admin, Run Admin, and Secret Manager Admin.

---

## Setting up your deployment

Everything this deployment owns lives in `config/`:

```
config/
  instance.env       where it runs, who can reach it — NO secrets
  branding.json      OPTIONAL — only the keys you want to change
  agent-config.json  OPTIONAL — only the keys you want to change
  prompts/           OPTIONAL — only the prompts you want to change
  assets/            OPTIONAL — your logo, favicon, CSS
```

Only `instance.env` is required. Everything else is an **override**: at deploy
time `defaults/` is laid down first and `config/` is copied over the top, so you
carry only your differences and inherit every upstream improvement when you
pull.

The required values in `config/instance.env` have **no default**. That is
deliberate — each one decides where your data lives, what it costs, or who can
reach it, and a default is a decision made on your behalf that you would not see
until the bill or the latency showed up. `REGION` in particular.

Required always:

| Variable | Description |
| :--- | :--- |
| `PROJECT_ID` | Your GCP project. Billing must be enabled. |
| `REGION` | Where everything runs. Check your data-residency obligations first — moving later means recreating everything. |
| `INSTANCE` | Lowercase, DNS-safe. Names every resource and the Terraform state prefix. |
| `ACCESS_MODE` | `public`, `iap`, or `private`. |

Required depending on those choices, and `--preflight` tells you which:

| Variable | Description |
| :--- | :--- |
| `AUTHORIZED_MEMBERS` | Required for `iap` and `private`. |

Optional: `PUBLIC_DC_URL` and `PUBLIC_DC_WEB_URL` — **two different hosts**, see
below.

### Public Data Commons needs two URLs, not one

The agent and the browser talk to **different hosts**, and it is worth
understanding before you change them:

| Variable | Default value | Used by |
| :--- | :--- | :--- |
| `PUBLIC_DC_URL` | `https://api.datacommons.org` | the **agent** — the versioned REST API, and `/mcp` |
| `PUBLIC_DC_WEB_URL` | `https://datacommons.org` | the **browser** — `/api/observations/series`, `/api/place/name`, `/core/api/...` |

The agent's MCP endpoint is `PUBLIC_DC_URL` with `/mcp` appended.

Point both at the API host and you get a deployment that looks like it works:
chat answers correctly, every number is right, and **no chart ever renders**.
The browser's requests reach a host that does not serve those routes and come
back as Cloud Endpoints 404s, which nothing surfaces server-side.

Left empty, both take the standard values above. Change them only if you are
pointing at a different Data Commons deployment.

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
history, and it names your project, your region, and everyone allowed in.

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
fixes, and branding defaults all arrive; your overrides stay yours.

**Change only `config/`.** The moment a deployment edits code, every later pull
conflicts and it stops being updatable. If you need a code change, make it
upstream.

---

## Customizing your instance

Everything visual and behavioral is configuration. Three directories, with
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

Both schemas set `additionalProperties: false`, so an unrecognized key is an
error rather than a silently ignored one — a typo'd color name fails loudly.

### Branding and UI configuration

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
  "logo": "/assets/acme.svg",
  "colors": { "primary": "#0B6E8F" }
}
```

| Group | Keys |
| :--- | :--- |
| Identity | `instance_name`, `headline`, `tagline`, `logo`, `logo_text`, `logo_height`, `logo_alt`, `favicon` |
| Theme | `colors` (primary, accent, text, surfaces, borders, containers…), `radius` (card / input / chip), `fonts` |
| Content | `suggestions` — the starter chips; `footer` text and links |
| Structure | `navigation` — header tabs; `metrics.tabs`; `analytics.ga_tag_id` |

Two complete examples ship as starting points:
`schemas/branding.neutral.example.json` (neutral theme) and
`schemas/branding.base-dc.example.json` (Google blue, no header menu).
`schemas/branding.example.json` lists every field with placeholder values.

**`navigation` has three meanings**, and the distinction is load-bearing:

| Value | Result |
| :--- | :--- |
| key absent | keep the default navigation configuration (`NAV_CONFIG`) |
| `[]` | **no header menu at all** |
| `[{label, href}, …]` | render these tabs |

Pinned by `ui/src/config/nav_config.test.ts`, because a default that carried a
navigation value once collapsed the first case into the second and silently
removed every tab on any instance without a `branding.json`.

### Prompts

`prompts/mcp.md` and `prompts/synthesis.md` are where instance-specific
knowledge lives — which DCIDs exist, what the place hierarchy looks like, what
vocabulary to use.

**Start from the neutral prompts and add your knowledge; do not start from
another client's and try to remove theirs.** A region-scoped synthesis prompt
run against a different dataset once produced *"I don't have this specific
data"* for data the tool had already returned in full: a rule of the form
`if alternative_sources:[] treat as UNAVAILABLE` misfires, because custom data
has a valid `source_id` and no alternatives.

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

A placeholder with no matching key is left in the prompt **verbatim** rather
than blanked — a visible `{{instance.region}}` in an answer is a far louder
failure than a sentence that has silently lost its subject. Keys beginning with
`_` are never substituted, so the `_comment` convention is safe.

### Applying a config change

```sh
./deploy.sh --config-only --restart
```

`--restart` is **not optional**. Configuration is read **once at agent startup**
and served from process memory thereafter. There is no TTL and no runtime
refetch, so a bucket sync alone changes nothing until a new revision starts
serving.

---

## Secrets

```sh
DC_API_KEY=... GEMINI_API_KEY=... \
  ./deploy.sh --bootstrap-secrets
```

Values are read from **this process's environment**, written to Secret Manager,
and never persisted to disk. Every later deploy needs no keys at all. If you
skip this, the deploy stops and tells you which secrets are missing.

**Why there is no gitignored `secret.env`.** The keys already live in Secret
Manager after the first deploy, so a local plaintext copy is redundant — and on
a public repo a redundant secret file is a liability: one `git add -f`, one
edited `.gitignore`, and a scraper has it. A new operator needs GCP access, not
a file someone has to send them.

`instance.env` is excluded from the config-bucket sync, so instance metadata
cannot reach a bucket that may be readable more widely than intended.

---

## Deploying

```sh
./deploy.sh --preflight     # check everything, create nothing
./deploy.sh                 # deploy
```

**`--preflight` is the step worth not skipping.** It checks the things that
otherwise fail late or silently: credentials, billing, whether your organization
permits public access, and whether IAP has a consent screen to sign people in
with. It creates nothing.

Roughly, in order, `./deploy.sh` runs: enable APIs → create the state bucket and
Artifact Registry → verify secrets → build the UI and bake it into the app image
→ compose the config bucket from `defaults/` + `config/` and sync it →
`terraform apply` → smoke tests.

First run is ~10 minutes.

**Preview the plan before an apply into a project that already has resources:**

```sh
./deploy.sh --plan
```

Every line should read `will be created`, and the summary should read
**`0 to change, 0 to destroy`**. **If anything says `will be destroyed`, stop**
— the state prefix or `INSTANCE` did not take, and you are pointed at another
deployment's state. Applying would rename (destroy and recreate) its resources.

One exception: a stack first deployed before the `cdc` backend was removed will
show `<instance>-runtime` and its five IAM bindings as `will be destroyed`. That
service account belonged to the old data service; nothing uses it now, so those
destroys are expected.

### Everyday commands

| Task | Command |
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

> [!IMPORTANT]
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

How the app is exposed, set by `ACCESS_MODE` in `config/instance.env`.

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
   used a project-level binding, which granted access to every IAP-fronted app
   in the project and meant two deployments fought over it — destroying one
   revoked the other's access. That is also why there is no longer a
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

## Verifying a deployment

```sh
bash docs/smoke.sh "$URL"
curl -s "$URL/agent/health" | jq
```

`mcp.generation` and `mcp.supports_source_attribution` tell you which MCP
surface the agent actually found. If `supports_source_attribution` is false,
answers carry weaker provenance — no named source, no license.

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
| `These secrets have no value in Secret Manager` | Bootstrap not run | See [Secrets](#secrets) |
| Charts blank, chat fine | `/dcproxy` failing | Agent logs — `401/403` is the API key, `404` is a path the data plane does not serve |
| Charts blank, `{"code":404,"message":"The current request is not defined by this API"}` | Chart routes are on a **different host** to MCP | Terraform sets `DATA_PLANE_WEB_URL` for this. Chat keeps working either way, so only the browser sees the fault |
| Config change does nothing | Read once at startup | `./deploy.sh --config-only --restart` |
| Every tab vanished | `navigation: []` in branding/instance config | Remove the key or provide `[{label, href}, …]` |
| `Refusing to apply: the state loaded for 'x' describes another instance` | `deploy.sh` caught a wrong state prefix | Do **not** override. Re-`init` with the right prefix |
| A deploy reports success but the change is not live | Uncommitted work rebuilds to the same `IMAGE_TAG` | Commit, then redeploy |
| Every chart 401s *after* a successful IAP sign-in | IAP identity headers reaching the backend | Should not happen — `/dcproxy` strips them. Suspect an added proxy hop |
| Public access binding refused | Domain Restricted Sharing | Use IAP or the proxy |
| `/healthz` works but the uptime check does not | Cloud Run's frontend reserves `/healthz` and answers it itself | External checks must use `/agent/health` |

For anything else, start with the app plane's Cloud Run logs. Each chat turn
writes one structured `chat_turn` record (terminal state, error type, phase
durations, tool names, and token counts, never user content) keyed by a
server-minted `turn_id` that also tags the turn's trace spans.

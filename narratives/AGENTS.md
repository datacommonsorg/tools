# Narratives — app guide

Layout, commands, and conventions for the `narratives/` application. General
engineering rules live in [`../CODING_GUIDELINES.md`](../CODING_GUIDELINES.md)
and frontend rules in [`../FRONTEND.md`](../FRONTEND.md) plus the local
[`FRONTEND.md`](FRONTEND.md); read the root copy first, then the local one,
which takes precedence where the two differ.

[`README.md`](README.md) is the primary reference for architecture, config,
secrets, deployment, and access modes. This document covers only what an agent
or a new contributor needs to build, check, and test the code.

## What this is

A self-contained deployable, not a library. **One clone of the repository is
one deployment.** There is no `--instance` flag; a second deployment is a
second clone.

It splits into two planes:

* **App plane** — a React SPA (`ui/`) and a Python agent (`agent/`) in one
  container. Identical regardless of backend.
* **Data plane** — selected by the `DATA_BACKEND` config value: `dcp`
  (Spanner, the default), `cdc` (Cloud SQL), or `none` (public
  `datacommons.org`). The app plane receives a URL and an auth mode and has no
  notion of what is behind them.

Switching backends is a configuration edit, never a code change or a branch.

## Directory ownership

Editing an upstream directory breaks a deployment's ability to pull updates.

| Directory | Owner |
|---|---|
| `config/` | The deployment — edit freely |
| `defaults/` | Upstream baseline |
| `schemas/` | Upstream |
| `ui/`, `agent/` | Upstream code |
| `deploy/`, `image/`, `cloudbuild/`, `docs/` | Upstream |

At deploy time `defaults/` is laid down first and `config/` copied over the
top, so a deployment carries only its differences.

## Toolchain

> [!IMPORTANT]
> The UI uses **npm**, not pnpm, and its `package-lock.json` lives in `ui/`,
> not at `narratives/`. Running `pnpm` here produces a second, conflicting
> lockfile.

* **Node 20+** for the UI. Nothing enforces this — there is no `.nvmrc` and no
  `engines` field — so check `node -v` before running npm commands.
* **Python 3.14** for the agent, managed by [uv](https://docs.astral.sh/uv/).
  Dependencies are declared in `agent/pyproject.toml` and resolved in
  `agent/uv.lock`. Never hand-edit the lockfile; regenerate it with `uv lock`.
* **ruff** formats and lints the Python at 80 columns; **mypy** type-checks it
  in strict mode. Both are configured in `agent/pyproject.toml`.

## Commands

UI, from `ui/`:

| Command | Effect |
|---|---|
| `npm install` | Install dependencies |
| `npm run dev` | Vite dev server on port 3000 |
| `npm run build` | Production build into `dist/` |
| `npm run lint` | Type-check only (`tsc --noEmit`) |
| `npm run test` | Vitest, single run |

> [!WARNING]
> `npm run lint` runs the TypeScript compiler and nothing else. There is no
> ESLint, Biome, or Stylelint in this app, so no tool catches a style or
> correctness issue that type-checking misses. Apply the guidelines by hand.

Agent, from `agent/`:

| Command | Effect |
|---|---|
| `uv sync` | Create `.venv` and install from the lockfile |
| `uv run python main.py` | Development server on port 5001 |
| `uv run pytest` | Run the test suite |
| `uv run ruff format .` | Format |
| `uv run ruff check .` | Lint |
| `uv run mypy` | Type-check |
| `uv lock` | Regenerate the lockfile after a dependency change |

Production runs `gunicorn main:app`; `main.py` is the development path.

Deployment, from `narratives/`:

| Command | Effect |
|---|---|
| `./deploy.sh --preflight` | Check credentials, billing, org policy, IAP |
| `./deploy.sh --bootstrap-secrets` | Read keys from the environment into Secret Manager |
| `./deploy.sh --plan` | Preview the Terraform plan |
| `./deploy.sh --config-only --restart` | Apply a branding or config change |
| `./deploy.sh --agent-only` | Agent or UI code |
| `./deploy.sh --infra-only` | Terraform only |
| `./deploy.sh` | Everything |
| `./deploy.sh --destroy` | Tear down |

> [!CAUTION]
> `--restart` is **not optional** on a config change. Config and branding are
> read once at agent startup and served from process memory; there is no TTL
> and no runtime refetch, so a bucket sync alone changes nothing.

> [!CAUTION]
> `IMAGE_TAG` is `git rev-parse --short HEAD`, so **uncommitted work rebuilds
> to the same tag** and Cloud Run keeps the cached image. Commit before
> `--agent-only`, or the deploy reports success while the change is not live.

## Python typing

The agent type-checks under `mypy --strict`, and CI fails on any error.

New and rewritten modules are annotated as they are written. They are never
added to the exemption list.

`agent/pyproject.toml` carries a set of `[[tool.mypy.overrides]]` entries with
`ignore_errors = true`, covering the modules that predate the standard. Each
entry names the branch that rewrites or deletes the module. An exemption is
retired by deleting the module it covers, never by annotating code that is
about to be replaced. **The list only shrinks.**

## Layout — `ui/`

* `src/api/` — Data Commons REST callers.
* `src/components/` — a **flat** directory of presentational and feature
  components. Narratives does not use the layered structure found in
  `dataweaver/`.
* `src/hooks/` — hooks and React context providers.
* `src/config/`, `src/types/`, `src/utils/` — navigation config, shared types,
  helpers.
* `src/index.css` — the design system: Tailwind v4 theme and `--color-*`
  tokens. Tailwind is the only styling stack.

## Layout — `agent/`

* `main.py` — entry point; `main:app` is what gunicorn serves.
* `src/narratives_agent/` — the Python package.
  * `config.py` — config loading, prompt rendering, credentials.
  * `gcp_auth.py` — credential selection by target host.
  * `server/` — the Flask app and its routes.
  * `workflows/` — chat pipeline, MCP loop, follow-ups, chart config.
  * `mcp/` — MCP client, schema, capabilities, data utilities.
  * `gemini/` — Gemini client and response schemas.
* Tests are colocated as `*_test.py` beside the module under test.

## Local development

Two paths, chosen by what you are changing. There is deliberately **no "run the
whole data plane locally" path** — point at a deployed backend, or at public
Data Commons.

**Path A — UI only.** From `ui/`: `npm install`, set `BACKEND_URL` and
`AGENT_URL` in `.env.local`, then `npm run dev`. Vite's `server.proxy` forwards
`/agent/*` and the data routes. It is dev-only, so `vite build` ignores it and
production behavior comes from `image/nginx.conf`. Vite picks up `.env.local`
changes on restart, not live.

**Path B — the agent.** From `agent/`: `uv sync`, export `MCP_SERVER_URL`,
`DATA_PLANE_URL`, and `DC_API_KEY`, then `uv run python main.py`.

> [!WARNING]
> Against **public** Data Commons the agent needs **two** hosts:
> `DATA_PLANE_URL=https://api.datacommons.org` for MCP and versioned REST, and
> `DATA_PLANE_WEB_URL=https://datacommons.org` for the website routes the chart
> web components call. Set only the first and the agent answers correctly with
> real numbers while **every chart silently 404s**, because the failure is
> entirely browser-side. `DATA_PLANE_WEB_URL` defaults to `DATA_PLANE_URL`,
> which is correct for a deployed plane and wrong for public DC.

> [!CAUTION]
> No API key or secret may reach the client bundle. All model calls go through
> the server-side agent proxy under `/agent/*`; keys live in Secret Manager and
> are resolved by the agent at startup.

## Verification before submitting

`cloudbuild/pr-validate.yaml` is the authoritative gate. Run its checks
locally first:

1. **Agent**, from `agent/`: `uv sync --frozen`, `uv run ruff format --check .`,
   `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
2. **UI**, from `ui/`: `npx tsc --noEmit`, then `npx vitest run`.
3. **Terraform**, if `deploy/` changed:
   `terraform fmt -check -recursive deploy/terraform-custom-datacommons/`,
   then `terraform validate` in
   `deploy/terraform-custom-datacommons/modules`.
4. **Schemas**, if a schema or example changed: validate each example against
   its schema with `ajv-cli`.

CI also builds both images for `linux/amd64` and fails on the wrong
architecture.

## Ingestion pipeline operations

These two rules are unrelated to the application code, and both describe
failures that hang silently rather than erroring.

### Ingestion `config.json`

Always use the dictionary format with explicit `columnMappings`. The array
format — `{"inputFiles": [{"csv": "data.csv"}]}` — makes the preprocessing
container deadlock without output.

```json
{
  "inputFiles": {
    "observations.csv": {
      "columnMappings": {
        "Date": "ObservationDate"
      }
    },
    "schema.mcf": {}
  }
}
```

### Running the preprocessing job

Never batch datasets. Passing a comma-separated list to
`dcapp-dc-ingestion-preprocessing-job` deadlocks the container immediately
after the "Merging config" step, and it hangs forever. Run one dataset per
invocation, looping if there are several.

```sh
gcloud run jobs execute dcapp-dc-ingestion-preprocessing-job \
  --args=--imports=dataset_name \
  --project custom-data-commons \
  --region us-central1 \
  --wait
```

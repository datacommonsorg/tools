# Developer & Maintainer Guide

This guide covers local development workflows, workspace scripts, testing,
linting, and repository layout for contributors working on Narratives.

For engineering and code style rules, read [`../AGENTS.md`](../AGENTS.md),
[`../FRONTEND.md`](../FRONTEND.md), and the repository-root
[`../../CODING_GUIDELINES.md`](../../CODING_GUIDELINES.md). For system
internals, see [`architecture.md`](architecture.md).

---

## Contents

- [Prerequisites & installation](#prerequisites--installation)
- [Workspace scripts](#workspace-scripts)
- [Local development workflows](#local-development-workflows)
- [Testing & linting](#testing--linting)
- [Repository layout](#repository-layout)
- [Contributing](#contributing)

---

## Prerequisites & installation

All commands run from the root of the `narratives/` directory unless noted.

- **Node 24** and **pnpm** (pinned via `.nvmrc` and `packageManager` in
  `package.json`).
- **Python 3.14** and **[`uv`](https://docs.astral.sh/uv/)**. The agent declares
  its direct dependencies in `agent/pyproject.toml` and resolves the full graph
  into `agent/uv.lock`. `uv sync` creates `agent/.venv` from that lockfile, and
  commands run via `uv run <command>`. Regenerate the lockfile with `uv lock`
  after a dependency change, and never hand-edit it.

```sh
nvm use        # switch to the Node version pinned in .nvmrc (or 'nvm install')
corepack enable
pnpm i
(cd agent && uv sync)
```

---

## Workspace scripts

| Command | What it does |
| :--- | :--- |
| `pnpm dev:ui` | Start the frontend Vite development server on port 3000 (`ui/`) |
| `pnpm dev:agent` | Stage config and start the Python agent development server on port 5001 (`agent/`) |
| `pnpm build` | Build the React UI and stage compiled assets into `agent/static/` and `defaults/` into `agent/defaults/` |
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

## Local development workflows

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

Vite's `server.proxy` (in `ui/vite.config.ts`) forwards `/agent/*` and the data
routes to `AGENT_URL` (unless `BACKEND_URL` is set separately); it is
**dev-only**, so `vite build` ignores it. Default is `http://localhost:5001` if
unset. Vite picks up `.env.local` changes on **restart**, not live.

You need Node 24 and nothing else — no Docker, no Python, no `gcloud`.

### Path B — Full stack locally (agent + UI)

Run commands in this section from `narratives/`.

**1. Install agent dependencies:**

```sh
(cd agent && uv sync)   # creates agent/.venv and installs from uv.lock
```

There is nothing to activate: `uv sync` creates `.venv` itself, and `uv run`
uses it.

**2. Configure local environment:**

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

**3. Start local development:**

Run the agent and UI in two separate terminals:

```sh
# Terminal 1: backend agent (port 5001)
pnpm dev:agent

# Terminal 2: frontend Vite dev server (port 3000)
pnpm dev:ui
```

`pnpm dev:agent` (or `uv run narratives-agent-dev`) loads `.env.local` and
stages `agent/config.json` from `defaults/` + `config/` + `prompts/`
(incorporating your `GEMINI_API_KEY`) before starting the Uvicorn server on
`127.0.0.1:5001` with auto-reload. Set `AGENT_PORT` to use another port.

**Optional — Serve the compiled SPA directly from the agent:**

To test production static routing (`server/routes/spa.py`) directly on port
5001:

```sh
pnpm build
```

Skip this if you are using `pnpm dev:ui` on port 3000 or only testing `/agent/*`
endpoints (`/` will 404 when `agent/static/` has not been staged, while
`/agent/*` still works).

**Optional — Smoke-test the local agent with `curl`:**

```sh
curl -s localhost:5001/agent/health | jq    # inspect resolved mcp_url
curl -sN -X POST localhost:5001/agent/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is the population of France?","turns":[]}'
```

For details on the SSE stream events and multi-turn request format, see
[`architecture.md`](architecture.md#chat-pipeline--typed-sse-protocol).

---

## Testing & linting

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
under test inside `agent/src/narratives_agent/`. UI tests are Vitest modules
named `*.test.ts` or `*.test.tsx`, colocated inside `ui/src/`.

Linting, formatting, and static type-checking can also be run by layer (`pnpm
lint:ui`, `pnpm lint:agent`, `pnpm lint:deploy`), and CI fails on any of them:

```sh
pnpm lint:ui                    # tsc --noEmit + Biome
pnpm lint:agent                 # Ruff format/lint + mypy --strict
pnpm lint:deploy                # Terraform + ShellCheck + Hadolint
```

> [!NOTE]
> The agent type-checks under `mypy --strict`, tests included, with no
> per-module exemptions.

---

## Repository layout

```
README.md                  overview and local/cloud quickstarts
AGENTS.md                  agent and contributor guide (commands, conventions)
FRONTEND.md                Tailwind v4, theme tokens, and React conventions
deploy.sh                  the single deploy entry point; no --instance flag
.env.local.example         template for local .env.local development settings

docs/                      documentation and verification scripts
  deployment.md            GCP deployment, customization, secrets, and ops
  development.md           local workflows, scripts, testing, repository layout
  architecture.md          system seams, SSE protocol, HMAC transcripts, config
  smoke.sh                 post-deploy smoke checks

config/                    YOURS — this deployment's settings and overrides
  instance.env             required: project, region, access
  branding.json            optional override
  agent-config.json        optional override
  prompts/  assets/        optional overrides
defaults/                  upstream baseline; config/ is laid over this
schemas/                   JSON Schemas + example branding — code, not config
scripts/                   build-time static asset staging (stage_static.mjs)

agent/                     app plane — API + SPA, one uvicorn process
  pyproject.toml           direct dependencies; ruff, mypy, and pytest config
  uv.lock                  the resolved graph; generated by uv lock
  src/narratives_agent/    the Python package; imports are narratives_agent.*
    dev.py                 dev entry point: uv run narratives-agent-dev
    server/app.py          the FastAPI app; production serves it with uvicorn
    server/routes/         spa · chat · system · dcproxy
    mcp/                   client · capabilities · schema · data_utils
    workflows/             chat_pipeline · mcp_loop · chart_config · follow_up
    gemini/                client · schemas
    *_test.py              pytest, colocated beside the module under test

ui/                        React 19 + Vite SPA; staged into agent/static/
  src/api/                 Data Commons REST callers
  src/components/          presentational and feature components
  src/config/              instance and navigation config
  src/hooks/               chat session, SSE, hash routing, autosize
  src/utils/               PDF export, turn inspection, DC web components

deploy/terraform-…/        Terraform module tree
deploy/*.py                deploy-time guards: state ownership, branding schema
cloudbuild/                PR validation and deploy pipelines
```

Two things are deliberately **not** here: API keys, which live only in Secret
Manager (or gitignored `.env.local` for local dev), and a second deployment path
— `deploy.sh` is the only one.

---

## Contributing

Before opening a PR, run what CI runs:

```sh
pnpm test
pnpm build
```

If you modified `schemas/` or `defaults/`, also validate each example and
default config against its JSON Schema in `schemas/` (see
[`cloudbuild/pr-validate.yaml`](../cloudbuild/pr-validate.yaml)).

Three rules that are easy to break by accident:

- **Keep a deployment clone private.** `config/` is committed by design, and
  `config/instance.env` names the project, the region, a service URL that embeds
  the project number, and everyone allowed in.
- **Change only `config/` in a deployment clone.** Anything else and every later
  `git pull upstream main` conflicts, and the clone stops being updatable. Code
  changes belong upstream.
- **Never commit a key.** Every `*_API_KEY` is empty in committed files; real
  values live only in Secret Manager or your local gitignored `.env.local`.

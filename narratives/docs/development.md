# Local Development Guide

This guide covers local setup, development workflows, workspace scripts,
testing, linting, and repository structure for Narratives.

For coding standards and UI conventions, see [`../AGENTS.md`](../AGENTS.md),
[`../FRONTEND.md`](../FRONTEND.md), and
[`../../CODING_GUIDELINES.md`](../../CODING_GUIDELINES.md). For system
architecture and protocols, see [`architecture.md`](architecture.md).

## Contents

- [Prerequisites & installation](#prerequisites--installation)
- [Running locally](#running-locally)
- [Workspace scripts](#workspace-scripts)
- [Testing & linting](#testing--linting)
- [Repository layout](#repository-layout)
- [Contributing](#contributing)

## Prerequisites & installation

Run all commands from the `narratives/` directory unless noted otherwise.

### Required tools

- **Node.js 24.22.1 or later 24.x** (pinned in `.nvmrc`) and **pnpm** (pinned
  via `packageManager` in `package.json`). `.npmrc` sets `engine-strict=true`,
  so `pnpm install` fails on a Node.js release outside the `engines` range in
  `package.json` rather than only warning.
- **Python 3.14** and **[`uv`](https://docs.astral.sh/uv/)**. Python
  dependencies are declared in `agent/pyproject.toml` and locked in
  `agent/uv.lock`.

### Install dependencies

```sh
nvm use        # or 'nvm install' if Node 24 is not yet installed
corepack enable
pnpm i
(cd agent && uv sync)
```

> [!NOTE]
> `uv sync` creates and manages `agent/.venv` automatically, and `uv run`
> executes commands inside that environment without manual activation. If you
> modify `agent/pyproject.toml`, run `uv lock` to update `agent/uv.lock` (never
> edit `uv.lock` by hand).

## Running locally

You can run both the frontend and backend locally, or run only the frontend
against an already-deployed Cloud Run backend.

### Option 1: Full stack (UI + local agent)

1. Copy `.env.local.example` to `.env.local` and set your
   [Gemini API key](https://aistudio.google.com):

   ```sh
   cp .env.local.example .env.local
   $EDITOR .env.local      # Set GEMINI_API_KEY="<your-key>"
   ```

   By default, `.env.local.example` points to the public Data Commons MCP
   endpoint:

   ```sh
   MCP_SERVER_URL="https://api.datacommons.org/mcp"
   AGENT_URL="http://localhost:5001"
   ```

2. Start the backend agent and frontend dev server in two separate terminals:

   ```sh
   # Terminal 1: Start the Python agent on http://127.0.0.1:5001
   pnpm dev:agent

   # Terminal 2: Start the Vite UI server on http://localhost:3000
   pnpm dev:ui
   ```

   `pnpm dev:agent` loads `.env.local`, composes `agent/config.json` from
   `defaults/` + `config/`, and starts Uvicorn with auto-reload. Set
   `AGENT_PORT` to override port `5001`.

3. Open `http://localhost:3000` in your browser.

#### Optional: Verify the local agent API directly

You can query the local agent endpoints directly with `curl`:

```sh
# Check health and the resolved MCP endpoint
curl -s http://localhost:5001/agent/health | jq

# Stream a chat response over Server-Sent Events (SSE)
curl -sN -X POST http://localhost:5001/agent/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is the population of France?","turns":[]}'
```

#### Optional: Serve the compiled SPA from the Python server

In production, the FastAPI server serves the compiled UI from `agent/static/`.
To test production static file routing locally on `http://localhost:5001`:

```sh
pnpm build
pnpm dev:agent
```

### Option 2: UI only (against a deployed backend)

If you are only making frontend changes and have a deployed Cloud Run instance,
you can run the Vite dev server without starting the local Python agent:

1. Copy `.env.local.example` to `.env.local` and set `AGENT_URL` to your Cloud
   Run service URL:

   ```sh
   cp .env.local.example .env.local
   $EDITOR .env.local      # Set AGENT_URL="https://<your-instance>.run.app"
   ```

2. Start the Vite dev server:

   ```sh
   pnpm dev:ui             # http://localhost:3000
   ```

Vite's development proxy (`ui/vite.config.ts`) forwards `/agent/*` to
`AGENT_URL`. Restart `pnpm dev:ui` after editing `.env.local`.

## Workspace scripts

All scripts run from `narratives/`:

| Command | Description |
| :--- | :--- |
| `pnpm dev:ui` | Start the Vite frontend dev server on port 3000 (`ui/`) |
| `pnpm dev:agent` | Stage config and start the Python agent dev server on port 5001 (`agent/`) |
| `pnpm build` | Compile the React UI (`ui/dist/`) and stage assets into `agent/static/` and `agent/defaults/` |
| `pnpm build:ui` | Compile the React UI into `ui/dist/` without staging into `agent/` |
| `pnpm test` | Run all unit tests and lint checks (`test:ui`, `test:agent`, and `lint`) |
| `pnpm test:ui` | Run the frontend Vitest unit test suite |
| `pnpm test:agent` | Run the backend Pytest unit test suite |
| `pnpm lint` | Run all type-checking, linting, and formatting checks across UI, agent, and deploy |
| `pnpm lint:ui` | Run TypeScript (`tsc --noEmit`) and Biome checks (`biome check`) |
| `pnpm lint:agent` | Run Ruff (`ruff format --check`, `ruff check`) and `mypy --strict` |
| `pnpm lint:deploy` | Run Terraform (`fmt -check`, `validate`), ShellCheck, and Hadolint |
| `pnpm fix` | Auto-fix formatting and lint issues across UI (Biome), Python (Ruff), and Terraform |

## Testing & linting

Run the full verification suite before opening or updating a pull request:

```sh
pnpm test
```

If formatting or lint checks fail, auto-fix them with:

```sh
pnpm fix
```

### Test organization

- **Frontend (`ui/`):** Vitest unit tests are colocated with source files as
  `*.test.ts` and `*.test.tsx` under `ui/src/`.
- **Backend (`agent/`):** Pytest unit tests are colocated with source modules as
  `*_test.py` under `agent/src/narratives_agent/`. All backend modules and test
  files are type-checked under `mypy --strict`.

## Repository layout

```
narratives/
├── README.md                  Overview and local/cloud quickstarts
├── AGENTS.md                  Coding conventions and commands for contributors
├── FRONTEND.md                Tailwind v4, theme tokens, and React conventions
├── deploy.sh                  Deployment CLI for Google Cloud Run and Terraform
├── .env.local.example         Template for local development environment vars
├── docs/
│   ├── development.md         Local development, testing, and repo layout
│   ├── deployment.md          Cloud Run deployment, customization, and ops
│   └── architecture.md        System architecture, SSE protocol, and state
├── config/                    Instance-specific deployment overrides
│   ├── instance.env           Project, region, instance name, and access mode
│   ├── branding.json          Optional UI theme and branding overrides
│   ├── agent-config.json      Optional model and template variable overrides
│   ├── prompts/               Optional system prompt overrides (*.md)
│   └── assets/                Optional static assets (logos, icons)
├── defaults/                  Default branding, agent config, and prompts
├── schemas/                   JSON Schemas and example configuration files
├── scripts/
│   └── stage_static.mjs       Copies ui/dist/ and defaults/ into agent/
├── agent/                     Python 3.14 FastAPI backend (managed with uv)
│   ├── pyproject.toml         Dependencies and ruff, mypy, and pytest config
│   ├── uv.lock                Locked Python dependency graph
│   └── src/narratives_agent/
│       ├── dev.py             Local dev server entry point
│       ├── config.py          Config, prompt rendering, and Secret Manager
│       ├── config_model.py    Typed AgentConfig dataclasses and their parser
│       ├── gcp_auth.py        Host-based authentication helpers
│       ├── settings.py        Environment variable settings
│       ├── telemetry.py       OpenTelemetry and structured logging
│       ├── server/            FastAPI app and routes (spa, chat, system)
│       ├── mcp/               MCP client, capabilities, schemas, and parsers
│       ├── workflows/         Agent loop, classify, MCP loop, charts, follow-up
│       ├── analytics/         Tables, alignment, summaries, digest, scripts
│       └── gemini/            Gemini SDK client and Pydantic schemas
├── ui/                        React 19 + Vite frontend (managed with pnpm)
│   └── src/
│       ├── api/               Data Commons REST API callers
│       ├── components/        React UI components
│       ├── config/            Instance and navigation configuration
│       ├── hooks/             Session state, SSE streaming, and routing hooks
│       ├── types/             Shared TypeScript interfaces
│       └── utils/             PDF export, formatting, and web component helpers
├── deploy/                    Terraform modules and validation scripts
└── cloudbuild/                Cloud Build CI and deployment pipeline configs
```

## Contributing

Before submitting a pull request:

1. Ensure your changes follow
   [`../../CODING_GUIDELINES.md`](../../CODING_GUIDELINES.md),
   [`../FRONTEND.md`](../FRONTEND.md), and [`../AGENTS.md`](../AGENTS.md).
2. Run the full test and lint suite:

   ```sh
   pnpm test
   ```

3. If your changes affect the UI or build pipeline, verify the production build
   succeeds:

   ```sh
   pnpm build
   ```

4. If you modified files in `schemas/` or `defaults/`, validate the example and
   default configuration files against their JSON Schemas (see
   [`../cloudbuild/pr-validate.yaml`](../cloudbuild/pr-validate.yaml)).
5. Never commit API keys or secrets. Keep local keys in `.env.local` (which is
   gitignored) and production keys in Google Cloud Secret Manager.

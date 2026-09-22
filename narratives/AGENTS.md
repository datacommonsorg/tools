# narratives — agent guide

Root of the `/narratives` directory inside the `dc-tools` monorepo. All paths
and commands below are relative to `/narratives` (or to `/narratives/ui` and
`/narratives/agent` where noted).

The application consists of two components packaged into a single container in
production:
- `ui/` — React 19 + Vite single-page application (npm).
- `agent/` — Python 3.14 server that hosts the `/agent/*` API, serves the
  compiled SPA (`server/routes/spa.py`), and reverse-proxies Data Commons data
  routes (`server/routes/dcproxy.py`) to the configured `DATA_PLANE_URL` (uv).

## Required reading

Read these before writing code, in this order:

1. [`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md) (repository root) —
   general engineering rules for all languages: simplicity, file organization,
   naming, TypeScript and Python standards, error handling, testing, security,
   and Data Commons pipeline conventions. Narratives has no local copy, so the
   root document applies in full.
2. [`FRONTEND.md`](FRONTEND.md) (this directory) — frontend conventions for
   React, Tailwind v4 tokens, component structure, and accessibility. It
   augments the repository-root [`FRONTEND.md`](../FRONTEND.md); where the two
   differ, the copy in this directory takes precedence.
3. This file — layout, commands, code style, testing, and local development.

Deployment, configuration, and secrets reference: [`README.md`](README.md).
Contribution process and PR expectations:
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Layout

- `ui/` — React + Vite SPA (`package-lock.json` lives in `ui/`; use **npm**,
  not pnpm):
  - `src/api/` — Data Commons REST callers.
  - `src/components/` — flat directory of presentational and feature
    components (does not use the layered `primitives / elements / scopes /
    foundations` structure from `dataweaver/`).
  - `src/hooks/` — hooks and React context providers.
  - `src/config/`, `src/types/`, `src/utils/` — navigation config, shared
    types, and helpers.
  - `src/index.css` — Tailwind v4 theme and `--color-*` design tokens.
- `agent/` — Python 3.14 server managed with [uv](https://docs.astral.sh/uv/):
  - `pyproject.toml`, `uv.lock` — dependencies and tool configuration (`ruff`,
    `mypy`, `pytest`).
  - `main.py` — server entry point (`gunicorn main:app` in production).
  - `src/narratives_agent/` — installable Python package (`config.py`,
    `gcp_auth.py`, `server/`, `workflows/`, `mcp/`, `gemini/`).
- `defaults/` — baseline `branding.json`, `agent-config.json`, and `prompts/`.
- `config/` — instance-specific overrides layered over `defaults/` at deploy
  time.
- `schemas/` — JSON Schemas and example configuration files.
- `deploy/`, `cloudbuild/` — Terraform modules, `deploy.sh`, and Cloud Build
  pipelines.

## Commands

UI, from `narratives/ui/` (requires **Node 20+**):

- `npm install` — install dependencies.
- `npm run dev` — start the Vite dev server on port 3000.
- `npm run build` — build production assets into `ui/dist/`.
- `npm run lint` — type-check (`tsc --noEmit`).
- `npm run test` — run unit tests once (`vitest run`).

Agent, from `narratives/agent/` (requires **Python 3.14** and **uv**):

- `uv sync` — create `.venv` and install dependencies from `uv.lock`.
- `uv run python main.py` — start the development server on port 5001.
- `uv run pytest` — run the Python unit test suite.
- `uv run ruff format .` — format Python files.
- `uv run ruff check .` — lint Python files.
- `uv run mypy` — run strict static type-checking.
- `uv lock` — regenerate `uv.lock` after editing `pyproject.toml` (never edit
  `uv.lock` by hand).

## Code style

Repo-wide rules live in [`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md);
frontend rules in [`FRONTEND.md`](FRONTEND.md). What is specific to this app:

- **Enforcement (UI)** — `npm run lint` currently runs only the TypeScript
  compiler (`tsc --noEmit`). ESLint, Biome, and Stylelint are not yet configured
  (linting is to follow), so style rules outside type-checking must be verified
  manually.
- **Enforcement (Agent)** — formatted and linted with `ruff` at 80 columns and
  type-checked with `mypy --strict`, both configured in `agent/pyproject.toml`.
- **Python typing** — all new and rewritten modules must pass `mypy --strict`
  and must never be added to `[[tool.mypy.overrides]]`. Legacy modules slated
  for deletion or rewrite in upcoming migration PRs are temporarily exempted
  with `ignore_errors = true` in `agent/pyproject.toml`; remove each exemption
  entry when the module is deleted or rewritten.
- **File naming** — `snake_case` for all source files (`card_response.tsx`,
  `use_branding.ts`, `chat_pipeline.py`) and category-first naming
  (`card_response.tsx`, not `response_card.tsx`).

## Tests

- **Agent (`pytest`)** — colocated as `*_test.py` beside the module under test
  in `agent/src/narratives_agent/`. Test files are type-checked by `mypy` and
  must include full type annotations. Use `monkeypatch` fixtures rather than
  mutating module globals directly, and follow the structured
  `# Test / # Situation / # Expectation` comment format in
  [`CODING_GUIDELINES.md` §13](../CODING_GUIDELINES.md#13-testing).
- **UI (`vitest`)** — colocated as `*.test.ts` / `*.test.tsx` in `ui/src/`.
  Stub environment variables with `vi.stubEnv` / `vi.unstubAllEnvs` and globals
  with `vi.stubGlobal` / `vi.unstubAllGlobals` per
  [`CODING_GUIDELINES.md` §6](../CODING_GUIDELINES.md#6-typescript).

## Local development

Choose the workflow below based on which component you are changing. The MCP server is 
not run as part of this deployment; connect either to a deployed backend, public Data
Commons or a local MCP server as preferred.

- **UI (`narratives/ui/`)** — run `npm install`, configure `BACKEND_URL` and
  `AGENT_URL` in `ui/.env.local`, and run `npm run dev`. In development, Vite's
  `server.proxy` (`ui/vite.config.ts`) forwards `/agent/*` and Data Commons
  routes to those URLs; in production, the Python server in `agent/` serves the
  compiled SPA (`server/routes/spa.py`) and proxies Data Commons routes
  (`server/routes/dcproxy.py`). Restart Vite after editing `.env.local`.
- **Agent (`narratives/agent/`)** — run `uv sync`, export `MCP_SERVER_URL`,
  `DATA_PLANE_URL`, and `DC_API_KEY`, and run `uv run python main.py`. When
  pointing at public Data Commons, set both
  `DATA_PLANE_URL=https://api.datacommons.org` (for MCP and versioned REST) and
  `DATA_PLANE_WEB_URL=https://datacommons.org` (for website routes used by the
  chart web components).
- **Secrets** — never place API keys or secrets in the client bundle. All
  model and data-plane credentials stay server-side in `agent/`.

## Verify

Run the full verification suite locally before opening or updating a PR (mirrors
[`cloudbuild/pr-validate.yaml`](cloudbuild/pr-validate.yaml)):

1. **Agent** (from `narratives/agent/`):
   `uv sync --frozen`, `uv run ruff format --check .`, `uv run ruff check .`,
   `uv run mypy`, and `uv run pytest`.
2. **UI** (from `narratives/ui/`):
   `npx tsc --noEmit && npx vitest run` (plus `npm run build` for UI changes).
3. **Terraform** (if `deploy/` changed):
   `terraform fmt -check -recursive deploy/terraform-custom-datacommons/` and
   `terraform validate` in `deploy/terraform-custom-datacommons/modules`.
4. **Schemas** (if `schemas/` or `defaults/` changed):
   validate each example and default config against its JSON Schema in
   `schemas/` with `ajv-cli`.

## Self-maintenance

When a change affects project structure, dependencies, commands, or
architecture, update this file, [`FRONTEND.md`](FRONTEND.md), and
[`README.md`](README.md) to match. Put each rule in one place: general rules in
[`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md), shared frontend rules in
[`../FRONTEND.md`](../FRONTEND.md), and Narratives-specific conventions here or
in the local [`FRONTEND.md`](FRONTEND.md).

## Ingestion pipeline operations

These two operational rules apply when running the Data Commons ingestion jobs
in GCP:

### Ingestion `config.json`

Always use the dictionary format with explicit `columnMappings`. The array
format (`{"inputFiles": [{"csv": "data.csv"}]}`) causes the preprocessing
container to deadlock without output.

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

Never pass a comma-separated list of datasets to
`dcapp-dc-ingestion-preprocessing-job`; batching multiple datasets in one
invocation deadlocks the container after the "Merging config" step. Execute one
dataset per invocation:

```sh
gcloud run jobs execute dcapp-dc-ingestion-preprocessing-job \
  --args=--imports=dataset_name \
  --project custom-data-commons \
  --region us-central1 \
  --wait
```

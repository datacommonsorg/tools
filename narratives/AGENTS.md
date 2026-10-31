# narratives — agent guide

Root of the `/narratives` directory inside the `dc-tools` monorepo. All paths
and commands below are relative to `/narratives` (or to `/narratives/ui` and
`/narratives/agent` where noted).

The application consists of two components packaged into a single container in
production:
- `ui/` — React 19 + Vite single-page application (pnpm).
- `agent/` — Python 3.14 server that hosts the `/agent/*` API and serves the
  compiled SPA (`server/routes/spa.py`) (uv).

## Required reading

Read these before writing code, in this order:

1. [`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md) (repository root) —
   general engineering rules for all languages: simplicity, preparatory
   refactoring, file organization, software design and module boundaries,
   naming, TypeScript and Python standards, error handling, testing, security,
   and Data Commons pipeline conventions. Narratives has no local copy, so the
   root document applies in full.
2. [`FRONTEND.md`](FRONTEND.md) (this directory) — frontend conventions for
   React, Tailwind v4 tokens, component structure, and accessibility. It
   augments the repository-root [`FRONTEND.md`](../FRONTEND.md); where the two
   differ, the copy in this directory takes precedence.
3. This file — layout, commands, code style, testing, and local development.

Overview and quickstarts: [`README.md`](README.md). Deployment, configuration,
and secrets reference: [`docs/deployment.md`](docs/deployment.md). Developer
workflows: [`docs/development.md`](docs/development.md). System architecture
and protocols: [`docs/architecture.md`](docs/architecture.md). Contribution
process and PR expectations: [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Layout

- `ui/` — React + Vite SPA (workspace package managed with **pnpm**):
  - `src/api/` — Data Commons REST callers.
  - `src/components/` — flat directory of presentational and feature
    components (does not use the layered `primitives / elements / scopes /
    foundations` structure from `dataweaver/`).
  - `src/hooks/` — hooks and React context providers.
  - `src/config/`, `src/types/`, `src/utils/` — instance and navigation config,
    shared types, and helpers.
  - `src/index.css` — Tailwind v4 theme and `--color-*` design tokens.
- `agent/` — Python 3.14 server managed with [uv](https://docs.astral.sh/uv/):
  - `pyproject.toml`, `uv.lock` — dependencies and tool configuration (`ruff`,
    `mypy`, `pytest`).
  - `src/narratives_agent/` — installable Python package (`config.py`,
    `config_model.py`, `gcp_auth.py`, `json_value.py`, `secret_manager.py`,
    `telemetry.py`, `server/`, `workflows/`, `mcp/`, `gemini/`, `analytics/`).
    - `server/app.py` — the FastAPI application
      (`uvicorn narratives_agent.server.app:app` in production).
    - `workflows/`: agent loop orchestration (`chat_pipeline.py`), the
      admission pre-filter, query classification, and pattern guidance
      (`prefilter.py`, `classify.py`, `pattern_guidance.py`), the code-owned
      prompt contracts appended after the configured guidance
      (`prompt_contracts.py`, with packaged contracts under `contracts/`),
      the discovery loop (`mcp_loop.py`), the per-turn cache of
      `CachedTable`s (`t<n>` fetched, `s<n>` derived), the merged
      `VariableMetadataEnrichment`, and the locked facets (`turn_cache.py`),
      the Pydantic fetch request models
      and the server-side fetch functions (`fetch_observations`,
      `fetch_child_observations`, `fetch_multi_entity_observations`), with
      their generated Gemini declarations and the date rules the fetches
      apply (`fetch_requests.py`, `fetch.py`), the `AnalysisSpecification`
      and `UnavailableReport` models (`submit_specification`,
      `report_unavailable`), their generated Gemini declarations, their
      validation against the cache, and the default specification
      (`specification.py`), the bounded processing phase that runs a
      specification and returns an `AnalysisDigest` or a
      `ProcessingDiagnostic` (`processing.py`), the chart grammar,
      resolver, and wire serializer (`charts.py`),
      the default chart floor (`chart_defaults.py`),
      the synthesis prompt builder (`synthesis.py`),
      the streaming block splitter (`blocks.py`),
      follow-up generation (`follow_up.py`),
      user-visible messages (`messages.py`), the typed SSE frames the agent
      loop sends (`sse_frames.py`), the turn's state slots
      (`state_slots.py`), and signed transcripts (`transcript.py`). Of the
      agent's subpackages, it may import `analytics/`, `mcp/`, and
      `gemini/`.
    - `mcp/`: MCP transport and tool-result decoding (`client.py`), server
      capability discovery and the required-tool check (`capabilities.py`),
      schema helpers (`schema.py`), Pydantic wire models of MCP observation
      payloads and of the observation tools' arguments, and payload
      validation (`wire.py`), observation table parsing and payload outlines
      (`observations.py`), and source and variable metadata readers
      (`metadata.py`). Of the agent's subpackages, it may import only
      `analytics/`; it never imports `workflows/` or `gemini/`.
    - `analytics/`: the deterministic analytics library, holding observation
      tables and provenance models (`tables.py`, `provenance.py`), cohort
      alignment and unit checks (`alignment.py`), the table summary
      (`summarize.py`), the digest and metric types (`digest.py`,
      `metrics.py`), the analytical scripts (`timeseries.py`, `ranking.py`,
      `distribution.py`, `composition.py`, `derived.py`, `relations.py`),
      the input checks and refusals they share (`script_inputs.py`), and the
      golden fixture under `golden/` with its regeneration script. It
      imports only the Python standard library, other `analytics/` modules,
      and `json_value.py`.
    - `config.py`: loads `agent-config.json` (or the local `config.json`),
      layers the prompts, and returns the result as an `AgentConfig`.
    - `config_model.py`: the frozen `AgentConfig` dataclasses, the parser
      that applies the defaults, and the per-role Gemini model, temperature,
      and thinking-level settings (`GeminiRole`,
      `AgentConfig.resolve_role_config`); the workflows read configuration
      from it.
    - `dev.py` — local development server (`uv run narratives-agent-dev`).
    - `json_value.py`: the `JsonValue` and `JsonObject` aliases for data
      that is JSON by nature, such as MCP tool arguments and results, and
      `json_safe`, which converts typed values back into a `JsonValue`.
    - `secret_manager.py`: reads secrets from Google Cloud Secret Manager,
      caches results, and provides test resets.
    - `settings.py` — every environment variable the agent reads (`Settings`).
- `defaults/` — baseline `theme.json`, `agent-config.json`, and `prompts/`.
- `config/` — instance-specific overrides layered over `defaults/` at deploy
  time.
- `schemas/` — JSON Schemas and example configuration files.
- `Dockerfile` — multi-stage container build (React UI builder + Python
  runtime).
- `scripts/` — local non-container staging of `ui/dist/` into `agent/static/`
  and `defaults/` into `agent/defaults/` (`stage_static.mjs`).
- `.env.local.example` — template for local `.env.local` development settings.
- `deploy/`, `cloudbuild/` — Terraform modules, `deploy.sh` and its modes
  (`deploy/modes/`), `deploy/smoke.sh`, and Cloud Build pipelines.

## Commands

Run from the root of the `/narratives` directory:

- `nvm use` (or `nvm install`) — switch to the Node version pinned in `.nvmrc`.
- `corepack enable && pnpm i` — install workspace dependencies (the pnpm version is
  pinned via `packageManager`).
- `pnpm dev:ui` — start the frontend Vite development server on port 3000
  (`pnpm -C ui dev`).
- `pnpm dev:agent` — stage config and start the Python agent development server
  on port 5001 (`uv run narratives-agent-dev`).
- `pnpm build` — compile the React UI and stage `ui/dist/` into `agent/static/`
  and `defaults/` into `agent/defaults/`.
- `pnpm build:ui` — compile the React UI bundle into `ui/dist/` without staging.
- `pnpm test` — run unit tests and lint checks across the whole application
  (`pnpm test:ui`, `pnpm test:agent`, and `pnpm lint`).
- `pnpm test:ui` — run the UI unit test suite (`vitest run`).
- `pnpm test:agent` — run the Python agent unit test suite (`uv run pytest`).
- `pnpm lint` — run all lint, formatting, and type checks across UI, agent, and
  deployment (`lint:ui`, `lint:agent`, `lint:deploy`).
- `pnpm lint:ui` — run TypeScript type-checking (`tsc --noEmit`) and Biome
  lint/format checks (`biome check`).
- `pnpm lint:agent` — run Ruff format/lint checks (`agent/` and `deploy/*.py`)
  and `mypy` strict type-checking.
- `pnpm lint:deploy` — run Terraform (`fmt -check` and `validate`), ShellCheck,
  and Hadolint checks.
- `pnpm fix` — auto-fix formatting and lint issues across UI (`biome check
  --write`), Python (`ruff check --fix` + `ruff format`), and Terraform
  (`terraform fmt`).

Run `pnpm test` (and `pnpm build` for UI changes) before considering work done.

Component-level commands:

UI, from `narratives/ui/` (or via `pnpm -C ui <command>`):

- `pnpm run dev` — start the Vite dev server on port 3000.
- `pnpm run build` — build production assets into `ui/dist/`.
- `pnpm run lint` — type-check (`tsc --noEmit`) and run Biome
  (`biome check`).
- `pnpm run fix` — format and auto-fix lint issues
  (`biome check --write`).
- `pnpm run test` — run unit tests once (`vitest run`).

Agent, from `narratives/agent/` (requires **Python 3.14** and **uv**):

- `uv sync` — create `.venv` and install dependencies from `uv.lock`.
- `uv run narratives-agent-dev` — start the development server on port 5001.
- `uv run pytest` — run the Python unit test suite.
- `uv run ruff format . ../deploy` — format Python files.
- `uv run ruff check . ../deploy` — lint Python files.
- `uv run mypy` — run strict static type-checking.
- `uv run python -m narratives_agent.analytics.golden.regenerate_golden`:
  rewrite the analytics golden fixture, `core_golden.json`, after a
  deliberate change to analytics output, and review its diff (never edit
  the fixture by hand); `--check` exits non-zero when the fixture is stale,
  without writing it.
- `uv lock` — regenerate `uv.lock` after editing `pyproject.toml` (never edit
  `uv.lock` by hand).

## Code style

Repo-wide rules live in [`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md);
frontend rules in [`FRONTEND.md`](FRONTEND.md). What is specific to this app:

- **Enforcement (UI)** — formatted and linted with **Biome** (`biome.json`) and
  type-checked with the TypeScript compiler (`tsc --noEmit`) via `pnpm lint:ui`
  (auto-fixable with `pnpm fix:ui`). Existing files pending cleanup are listed
  as `!<path>` exclusions under `files.includes` in `biome.json`; remove a
  file's exclusion entry in a dedicated, behavior-preserving refactor PR (see
  [`CODING_GUIDELINES.md` §1.2](../CODING_GUIDELINES.md#12-surgical-changes-and-preparatory-refactoring))
  rather than mixing whole-file lint/format churn into a feature PR.
- **Enforcement (Agent)** — formatted and linted with `ruff` at 80 columns and
  type-checked with `mypy --strict`, both configured in `agent/pyproject.toml`
  and run via `pnpm lint:agent` (auto-fixable with `pnpm fix:agent`).
- **Enforcement (Deployment)** — Terraform modules are checked with `terraform
  fmt -check` and `terraform validate`, shell scripts with `shellcheck`, and
  Dockerfiles with `hadolint` via `pnpm lint:deploy`. Existing shell scripts and
  Dockerfiles pending cleanup are listed in `.lintignore`.
- **Python typing** — every module, tests included, passes `mypy --strict`.
  Never add a `[[tool.mypy.overrides]]` block that ignores errors in
  `agent/pyproject.toml`.
- **File naming** — `snake_case` for all source files (`card_response.tsx`,
  `instance_config.ts`, `chat_pipeline.py`) and category-first naming
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

Choose the workflow below based on which component you are changing. The MCP
server is not run as part of this deployment; connect either to a deployed
backend, public Data Commons or a local MCP server as preferred.

- **UI (`narratives/ui/`)** — run `pnpm install`, optionally configure
  `AGENT_URL` in `.env.local` (from `.env.local.example`) to point at a
  deployed instance, and run `pnpm dev:ui` (or `pnpm -C ui run dev`). In
  development, Vite's `server.proxy` (`ui/vite.config.ts`) forwards `/agent/*`
  to `AGENT_URL`; in production, the Python server in `agent/` serves the
  compiled SPA (`server/routes/spa.py`). Restart Vite after editing
  `.env.local`.
- **Agent (`narratives/agent/`)** — run `uv sync`, configure `.env.local` (from
  `.env.local.example`) with `GEMINI_API_KEY`, `DC_API_KEY` (which is optional
  for some MCP servers), and optional `MCP_SERVER_URL`, and run `pnpm dev:agent`
  (or `uv run narratives-agent-dev`).
- **Secrets** — never place API keys or secrets in the client bundle. All
  model and data-plane credentials stay server-side in `agent/`.

## Verify

`pnpm test` for every change; `pnpm build` and a manual check for UI changes.

To run individual layer checks locally (mirrors
[`cloudbuild/pr-validate.yaml`](cloudbuild/pr-validate.yaml)):

1. **Test and lint suites**: `pnpm test` (runs `pnpm test:ui`,
   `pnpm test:agent`, and `pnpm lint`). Run `pnpm fix` to auto-fix formatting
   and lint issues.
2. **Build**: `pnpm build` (compiles React UI and stages `ui/dist/` into
   `agent/static/` and `defaults/` into `agent/defaults/`).
3. **UI style and types**: `pnpm lint:ui` (`tsc --noEmit` and `biome check`).
4. **Agent style and types**: `pnpm lint:agent` (`ruff format --check`,
   `ruff check`, and `mypy`).
5. **Deployment checks**: `pnpm lint:deploy` (`terraform fmt -check`,
   `terraform validate`, `shellcheck`, and `hadolint`).
6. **Schemas** (if `schemas/` or `defaults/` changed):
   validate each example and default config against its JSON Schema in
   `schemas/` with `ajv-cli`.

## Self-maintenance

When a change affects project structure, dependencies, commands, or
architecture, update this file, [`FRONTEND.md`](FRONTEND.md),
[`README.md`](README.md), and the guides in [`docs/`](docs/) to match. Put each
rule in one place: general rules in
[`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md), shared frontend rules in
[`../FRONTEND.md`](../FRONTEND.md), and Narratives-specific conventions here or
in the local [`FRONTEND.md`](FRONTEND.md).

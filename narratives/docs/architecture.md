# Architecture

This document explains how Narratives is structured, how it communicates with
Data Commons, and how chat streaming, multi-turn conversations, and
configuration work under the hood.

- For local development and testing, see [`development.md`](development.md).
- For Cloud Run deployment, see [`deployment.md`](deployment.md).

## Contents

- [System overview](#system-overview)
- [How Narratives connects to Data Commons](#how-narratives-connects-to-data-commons)
- [MCP tool discovery & session recovery](#mcp-tool-discovery--session-recovery)
- [Chat pipeline & SSE streaming](#chat-pipeline--sse-streaming)
- [Stateless multi-turn conversations](#stateless-multi-turn-conversations)
- [Configuration, secrets & UI theming](#configuration-secrets--ui-theming)

## System overview

```text
┌──────────────┐        ┌─────────────────────────────────────────┐
│              │  SSE   │  Narratives Container (FastAPI)         │
│   Browser    ├───────►│  - React web app (routes/spa.py)        │
│  (React SPA) │  HTTP  │  - Agent API (/agent/*)                 │
│              │        └────────────────────┬────────────────────┘
│              │                             │ MCP
│              │                             ▼
│              │                 ┌──────────────────────┐
│              │                 │ Data Commons MCP     │
│              │                 │ (api.datacommons.org │
│              │                 │  /mcp)               │
│              │                 └──────────────────────┘
│              │  HTTP
│              └───────►┌────────────────────┐
                        │ Data Commons Web   │
                        │ (datacommons.org)  │
                        └────────────────────┘
```

In production, a single FastAPI container (`narratives_agent.server.app:app`)
serves both the frontend and backend from one origin:

1. **React web app (`server/routes/spa.py`)** — serves `index.html`, static
   JavaScript/CSS bundles (`/assets/` and `/theme/`), and `/healthz` for
   container health checks.
2. **Agent API (`/agent/*`)** — handles chat streaming (`/agent/chat/stream`)
   and health checks (`/agent/health`).

## How Narratives connects to Data Commons

Narratives talks to Data Commons in two ways — one for the Python agent and one
for browser-rendered charts:

### 1. Agent queries (via MCP)

When a user asks a question, the Python agent uses the Model Context Protocol
(`mcp/client.py`) over HTTP to search Data Commons for statistical variables
and their metadata, and fetches observations through the server's fetch
functions (`workflows/fetch.py`).

### 2. Browser chart requests

When an answer includes a chart, the UI renders Data Commons web components
(such as `<datacommons-line>` or `<datacommons-bar>`). Those components fetch
their own chart data and place names directly from Data Commons
(`datacommons.org` or the same-origin Data Commons website host).

Prose figures come from the digest while charts are drawn by the Data Commons
web components from their own fetch, pinned by `facet_ids`, so the reference
date and the per-capita denominator can differ between prose and chart.

## MCP tool discovery & session recovery

### Automatic tool discovery

The agent requires the six tools served by MCP 1.3.x (`REQUIRED_TOOLS`). It
queries the MCP server for its available tools (`tools/list` in
`mcp/client.py`) and caches the result. `mcp/capabilities.py` checks that list
against `REQUIRED_TOOLS`, logs a warning if any are missing, and summarizes the
tool surface for `/agent/health` (see
[deployment.md](deployment.md#step-4-verify-the-deployment)).

The server does not connect to the MCP server during container startup, so
`/agent/health` responds immediately even if the upstream Data Commons server is
slow or unreachable.

### Automatic session recovery

An MCP session ID (`Mcp-Session-Id`) is only recognized by the specific upstream
server instance that created it. When the Data Commons MCP server runs across
multiple Cloud Run instances without session affinity, a follow-up tool call can
land on a different instance that rejects the session ID. When that happens, the
agent automatically starts a fresh MCP session and retries the tool call.

## Chat pipeline & SSE streaming

### What happens during a chat turn

Each `POST /agent/chat/stream` request first checks whether chat is enabled
(`chat.enabled` in `agent-config.json`, default `true`, overridden by
`ENABLE_CHAT` when set); when chat is disabled, the turn aborts immediately
with a single `terminal` error frame (`reason: "chat_disabled"`,
`is_retryable: false`) carrying `chat.unavailable_message` (overridden by
`UNAVAILABLE_MESSAGE` when set) before making any Gemini or MCP calls.
Otherwise, the request runs through the agent loop in five steps:

1. **Query classification (`classify`):** Before any tool is called, a
   deterministic pre-filter screens out prompt injection, persona overrides,
   secret exfiltration, jailbreak phrases, and injection payloads without a
   model call. When `MODEL_ARMOR_TEMPLATE` is configured, the user query is
   then screened against Google Cloud Model Armor (`model_armor.py`) before
   calling Gemini; a match ends the turn as `refused` with reason
   `safety_blocked`. One structured Gemini call on `gemini.classify_model`
   (`gemini-3.5-flash-lite` by default) then produces one of three outcomes:
   - **Refused:** Ends the turn in a single `terminal` frame
     `{state: "refused", idempotency_key, reason, message}` with no `error` key
     (`reason` is `adversarial`, `off_domain`, or `safety_blocked`). The turn is
     not signed and is excluded from the multi-turn window, and the UI renders
     the message as a notice rather than an error card.
   - **Clarification:** When a place name is ambiguous or required and omitted,
     streams the clarification question as the answer's one text block, signs
     the turn with empty state slots, and emits a signed `complete` terminal
     frame without `data_status`, `sources`, chart block, or `follow_ups`
     frames.
   - **Classified:** Continues into the discovery loop and synthesis with the
     analytical `pattern` (`single_point`, `top_n_ranking`, `distribution`,
     `trend_delta`, `outliers`, `correlation`, `composition`,
     `sequential_stages`, `clustering`, `forecasting`, `exploratory`, or
     `data_availability`) recorded in telemetry and its directive from
     `workflows/pattern_guidance.py` appended to the system instructions of both
     calls. If the classifier call fails, the turn falls through as
     `exploratory` without a directive.
2. **Discovery and processing (`discovery` / `processing`):** Gemini runs the
   discovery loop (`workflows/mcp_loop.py`) with the three MCP discovery tools
   (`search_indicators`, `search_child_indicators`, `get_variable_metadata`),
   the three server-side fetch functions (`fetch_observations`,
   `fetch_child_observations`, `fetch_multi_entity_observations`), and the two
   terminal functions (`submit_specification`, `report_unavailable`). Each
   fetch stores an `ObservationTable` in the turn's cache (`t1`, `t2`, ...) and
   returns a compact `TableSummary` to the model rather than the observation
   rows. When the model calls `submit_specification`, the server validates the
   `AnalysisSpecification` against the cache and runs its steps through the
   deterministic analytics scripts (`workflows/processing.py`) under the
   `processing` status phase; a validation or step refusal is returned to the
   model for up to two retries, and an accepted `AnalysisDigest` ends the loop.
   Before a specification runs, the server requests variable metadata
   (`workflows/metadata_backfill.py`) for the fetched tables the
   specification references whose facet has no metadata yet, best effort and
   at most once per variable and facet in a turn, so citations can provide
   the provider, dataset, date range, and license even when the model did
   not call `get_variable_metadata`. These requests are not model tool calls
   and stream no `tool_call` frame.
   A specification holds at most six steps. `analyze_timeseries` and
   `compute_composition` report every place they cover, so without `places`
   their input may cover at most ten places, and a ranking or relation
   reports at most 25 places per end. A change, growth rate, or period mean
   across a larger cohort is computed by `reduce_series`, which reduces each
   place's series to one figure over a window the places share and produces
   a window cohort (reference date `start..end`) that a later `rank_cohort`,
   `summarize_distribution`, or `relate_cohorts` step reads.
   If the loop ends without an accepted digest or an `UnavailableReport`, a
   default specification is built from the cached tables and the query's
   pattern. If the MCP server cannot be reached, the turn stops and returns an
   error so the model never guesses numbers without data.
3. **Answer synthesis (`synthesis`):** The synthesis phase
   (`workflows/synthesis.py`, `workflows/blocks.py`, `workflows/charts.py`, and
   `workflows/chart_defaults.py`) writes the answer from the digest alone. The
   prompt holds the digest's computed results (with floats rounded to display
   precision), the numbered sources, the missing-data notes, the pattern's
   directive, and a table inventory naming each cached table's variable, unit,
   places, and dates; externally sourced text (variable names, source names, and
   missing-data notes) stays in typed fields until the message is rendered. A
   citation is one source as cited for one variable: each fetched table's
   source carries the table's variable, so two variables drawn from one source
   are two numbered sources, and each numbered source names its variable. Each
   sourced digest step carries a step-level `cite:` marker and, when a
   multi-variable step's variables carry distinct citations, a
   `cite by variable:` breakdown so single-variable figures cite their own
   variable's source. The synthesis contract shows markers only on figures taken
   straight from a source; calculated figures, including cross-variable ones,
   carry none, and the rules that would cite them with the combined sources
   are kept disabled in an HTML comment in `contracts/synthesis.md`. The model
   writes markdown and places each chart where it belongs as a fenced block
   tagged `chart` holding one specification: the chart kind (`line`, `bar`,
   `map`, `ranking`, `scatter`, or `highlight`), the table ids it draws from, a
   title, and the places (an explicit subset, the table's cohort, or a `top_n`
   or `bottom_n` slice), with an optional unit and, on single-date charts, an
   optional date.
   The server splits the stream at paragraph boundaries and at the closing fence
   of each chart block, and emits one `content {block}` frame per completed
   paragraph and per chart that resolves. Resolution is set membership against
   the turn cache: an unknown table, a place or date the table does not hold, a
   unit mismatch across the tables on one axis, or a kind the table shape cannot
   support (a map without a cohort, a scatter without two variables) rejects the
   chart, which is dropped and counted while the prose stands. Each resolved
   chart carries `facet_ids` mapping its variables to the facets that served
   them, matching the Data Commons web components' facet attributes (`facetId`
   on highlight, `facetIds` or `facetMapping` on the other components). A
   derived per-capita table is scaled automatically in the digest (per 1,
   1,000, or 100,000 people so the median non-zero magnitude is at least 1) and
   is charted when referenced by its `s<n>` table id as its numerator with the
   web component's per-person normalization; other derived tables are not
   chartable. At most three charts are accepted per answer. When the digest has
   data and no chart is emitted, the default chart floor appends at most one
   chart projected directly from the primary result (`scatter` for a cohort
   `relate_cohorts` result, which is considered first, or the direct chart of
   `analyze_timeseries`, `rank_cohort`, or `compute_composition`;
   distributions, standalone derivations, non-cohort relations, and
   relations over a window cohort receive none). A ranking of a cohort, or
   any ranking over a window cohort, is charted as a `line` of its first five
   places, with the parent place when a step analyzed the parent's series; a
   single-date cohort ranking falls back to a `ranking` chart when its table
   has one date, or when the ranking supports a relation. A `ranking`,
   `bar`, `map`, or `scatter` of a table that the digest ranks only over a
   window needs an explicit date, because without one it would draw the
   latest values rather than the change the prose describes. The signed
   `model_response` is the text blocks joined by blank lines,
   with the chart blocks stripped, matching the text blocks emitted in
   `content` frames. A stream that stalls for 60 seconds waiting for a chunk
   ends the turn with `synthesis_stream_error`.
4. **Turn signing (`finalize`):** The server builds the turn's `state_slots`
   from the fetched tables the specification used and the displayed charts
   (`workflows/state_slots.py`), and signs the completed turn into the window
   so the browser can include it in follow-up questions.
5. **Follow-up suggestions (`follow_ups`):** Suggested follow-up questions are
   streamed after the main answer finishes.

### Server-Sent Events (SSE)

The server streams progress and answer chunks to the browser as Server-Sent
Events (SSE). Each event has an `event` name, a JSON `data` payload, and (except
for `heartbeat`) a sequential `id` starting at `1`:

| Event | What it contains |
| :--- | :--- |
| `status` | Current step (`classify`, `discovery`, `processing`, or `synthesis`) and status message |
| `thought` | Model reasoning summary from the `discovery` or `synthesis` step |
| `content` | Answer block (`{block}` of type `text` or `chart`), tool call details (`{tool_call}`), citations (`{sources}`), or data status (`{data_status}`) |
| `terminal` | Final turn status (`state: "complete"`, `"refused"`, or `"error"`), plus the signed conversation state on completion, `{reason, message}` (with no `error` key) on refusal, or `{error, reason, is_retryable}` on failure |
| `follow_ups` | `{follow_up_questions}`, sent after `terminal` when available |
| `debug_report` | Gated turn debug report, sent as the final frame when the debug report mode is `on`, or `flag` with `"debug": true` |
| `heartbeat` | `{}`, sent every 15 seconds so proxies do not close idle connections |

How the stream ends:

- **Explicit completion (`terminal`):** Every finished turn sends a single
  `terminal` event with `state: "complete"`, `state: "refused"`, or
  `state: "error"`. A `refused` frame carries `{reason, message}` and no `error`
  key, and is left unsigned. An `error` frame carries `{error, reason,
  is_retryable}`, where `is_retryable` is `false` only when the failure is
  identified as permanent (for example, disabled chat or a request Gemini
  rejects); every other failure is retryable, and the UI shows a "Try again"
  button for it. If the connection drops before a `terminal` event arrives, the
  UI shows that the response was interrupted.
- **Client disconnect:** If the user closes the tab or stops the request, the
  server cancels any in-progress model calls and logs the turn as `canceled`.
- **Duplicate protection (`idempotency_key`):** Each request includes a unique
  `idempotency_key` generated by the UI, which the server echoes back in the
  `terminal` event.
- **Debug reporting (`debug_report`):** When debug reporting is enabled for the
  request, `debug_report` follows `terminal` (and `follow_ups`, when present)
  as the last frame of the stream. It is omitted when chat is disabled or the
  client disconnects. The mode is `DEBUG_REPORT` when that variable is set,
  and otherwise `debug.report` in `agent-config.json`.

## Stateless multi-turn conversations

Narratives does not use a database or server-side memory to store chat sessions.
Instead, **the browser holds the conversation history** and sends recent turns
back to the server with each follow-up question:

```json
{
  "message": "And for Germany?",
  "idempotency_key": "b7e0...",
  "turns": [
    {
      "turn_index": 0,
      "idempotency_key": "3f1c...",
      "user_query": "What is the population of France?",
      "model_response": "<exact streamed answer text>",
      "state_slots": {"scopes": ["..."]},
      "hmac": "<64 hex characters>"
    }
  ],
  "compacted_summary": null
}
```

### How the server verifies conversation history

Because the conversation history comes from the browser, the server verifies
that previous answers were not modified before feeding them back to Gemini:

- When a turn finishes, the server computes an HMAC signature (`hmac`) over that
  turn's question, answer, and position in the conversation using
  `TRANSCRIPT_HMAC_SECRET`.
- When the browser sends a follow-up question, the server re-checks the
  signatures on every turn before starting the stream:

| HTTP Status | When it happens |
| :--- | :--- |
| `413` (`request_too_large`) | Request body is larger than 4 MiB |
| `400` (`transcript_invalid`) | Turn history was modified, reordered, or exceeds size limits (>6 turns, >32,000-character answer, or >8,000-character summary) |
| `422` | Request body is invalid JSON, or `message` (>4,000 characters) / `idempotency_key` is invalid |

If the server returns `400`, the UI clears its stored signatures so the user's
next question starts fresh.

In local development, if neither `TRANSCRIPT_HMAC_SECRET` nor
`TRANSCRIPT_HMAC_SECRET_NAME` is set, the server generates a temporary random
key at startup. In multi-instance deployments (such as GKE or Cloud Run), where
follow-up requests can land on any container instance, all instances share the
same key either by injecting `TRANSCRIPT_HMAC_SECRET` directly or by resolving
`TRANSCRIPT_HMAC_SECRET_NAME` from Secret Manager at startup.

### Keeping conversation history compact

To keep prompts fast and within model token limits, the browser sends at most
the **6 most recent turns** in full:

- **Summarizing older turns (`compacted_summary`):** When a 7th turn finishes,
  the server summarizes the oldest turn into `compacted_summary`, removes that
  turn from the list, and re-signs the remaining 6 turns. The browser replaces
  its stored history with the updated `window` returned in the `terminal` event.
- **Remembering context (`state_slots`):** Each turn records the places,
  variables, and dates used in that turn inside `state_slots`. This helps the
  agent resolve follow-up questions like *"How about Germany?"* or *"What about
  in 2020?"*.
- **Oversized answers:** If an answer is too large to sign (over 32,000
  characters), the server omits `hmac` on that turn and the browser leaves it
  out of future follow-up requests.

## Configuration, secrets & UI theming

### Agent configuration & API keys

At startup, `narratives_agent/config.py` loads configuration into memory from
the first available source:

1. **Cloud Run (`CONFIG_URL`):** Downloads `agent-config.json` and
   `prompts/*.md` (`classify`, `discovery`, `synthesis`, `follow_up`) once at
   startup from the private GCS config bucket. HTML comments (`<!-- ... -->`)
   are stripped from prompt files, and `{{instance.*}}` placeholders are filled
   in from `template_vars` in `agent-config.json`.
2. **Local development (`agent/config.json`):** Generated by `pnpm dev:agent`
   (`dev.py`) by merging `defaults/`, `config/`, and `.env.local`, and
   automatically reloaded whenever the file changes.
3. **Container defaults (`agent/defaults/`):** Copied into the container image
   by `Dockerfile` (and staged by `scripts/stage_static.mjs` for local
   non-container runs). Its `prompts/*.md` files provide the base prompt
   layer on every configuration path, and `agent-config.json` is used when
   neither `CONFIG_URL` nor `agent/config.json` is present.

Whichever source applies, the loaded document is parsed once by
`narratives_agent/config_model.py` into a frozen `AgentConfig`, and the
workflows read typed fields from it (for example `config.prompts.synthesis`)
rather than the document itself; a value of the wrong type is reported at load
time and replaced by its default. Each Gemini call resolves its model,
temperature, and thinking level through
`config.resolve_role_config(GeminiRole.<ROLE>)`, which combines the configured
models and thinking levels with the per-role settings fixed in
`config_model.py`. Where a phase carries a code-owned contract under
`workflows/contracts/`, `workflows/prompt_contracts.py` appends it after the
configured prompt so an instance override cannot drop or contradict the
server's contract.

Every Gemini call renders its system instruction with `render_prompt`, which
fills in `{{CURRENT_DATETIME}}` and the `{{instance.*}}` placeholders. The
`classify` prompt, the discovery contract, and the `synthesis` prompt name the
current date and time, so relative dates such as "this month" or "over the
last decade" resolve against it. `run_turn` pins one timestamp for the whole
turn with `pin_current_datetime` (a context variable, so concurrent turns
keep their own), and every phase of the turn renders that same timestamp. An
instance that overrides the `classify` or `synthesis` prompt keeps the date
only when its own prompt includes `{{CURRENT_DATETIME}}`.

For the Gemini API key (`get_gemini_api_key()`):

- **Cloud Run / GKE:** Reads `GEMINI_API_KEY_SECRET` from Secret Manager and
  caches it in memory for 5 minutes. Any `key=...` query parameters are redacted
  from logs and error messages.
- **Local development:** Reads `gemini.api_key` from the local
  `agent/config.json`.

For the Data Commons API key (`attach_auth()`):

- Uses `DC_API_KEY` directly when set (local dev or direct secret injection).
- When `DC_API_KEY` is unset and `DC_API_KEY_SECRET` is configured, resolves the
  key from Secret Manager once at startup and caches it in memory.
- If neither is set, no credential header is attached.

### UI theme & instance branding

The UI uses CSS custom properties in `ui/src/index.css` for its default styling.
To avoid a flash of unstyled content on page load, custom branding is injected
directly into `ui/index.html` and read synchronously when the app starts:

- **Theme colors:** Custom `--theme-*` CSS variables are injected into
  `<style id="theme-tokens">`.
- **Instance settings:** UI components read the site title, logo, headline,
  suggested questions, navigation links, and status indicators synchronously via
  `getInstanceConfig()` in `ui/src/config/instance_config.ts`. This helper
  reads `<script id="instance-config" type="application/json">`, validates each
  field, and falls back to `DEFAULT_INSTANCE_CONFIG` for any field that is
  missing or invalid.

When the agent server serves `index.html` (`server/routes/spa.py`), it also
stamps the effective chat availability,
`{"enable_chat": <bool>, "unavailable_message": "<str>"}`, into
`<script id="runtime-config" type="application/json">`, escaping `<`, `>`,
`&`, U+2028, and U+2029. The `ETag` hashes the stamped bytes and
`Last-Modified` is omitted, so a browser revalidating the page receives the
current value after a restart that changes it. `getRuntimeConfig()` in
`ui/src/config/runtime_config.ts` reads `#runtime-config` synchronously at
startup. When `enable_chat` is `false`, `App` renders `UnavailableView`
(`ui/src/components/view_unavailable.tsx`) with the unavailable message on the
Data Agent route instead of the chat, keeps `Header` and `MetricsPage`
available, and hides the "New chat" controls. Under `pnpm dev:ui`, the Vite
dev server fetches the shell from the agent at `AGENT_URL` on every page load
and copies its `#runtime-config` (`copyAgentRuntimeConfig` in
`ui/src/config/runtime_config_dev.ts`, which only `vite.config.ts` imports),
parsing and re-escaping the value. The shell is fetched from the `AGENT_URL`
path without following redirects; when the agent cannot be read, the element
stays empty and Vite logs a warning with the reason.

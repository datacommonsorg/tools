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

### HTTP security headers

`SecurityHeadersMiddleware` (`server/security_headers.py`) adds these headers
to every response, including the static files, `/agent/*`, 404 responses, and
CORS preflight responses, unless the response already sets them:

| Header | Value |
| :--- | :--- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Cross-Origin-Opener-Policy` | `same-origin-allow-popups` |

The middleware is plain ASGI rather than Starlette's `BaseHTTPMiddleware`: it
edits only the response start message and forwards each body chunk as it is
sent, so the chat stream is never buffered. It sets no
`Content-Security-Policy`; `.svg` files carry `Content-Security-Policy:
sandbox` from `server/routes/spa.py`. The one response without the headers is
the plain-text 500 that Starlette's `ServerErrorMiddleware` sends for an
unhandled exception, because that middleware wraps every user middleware.

The HTML shell (`/` and `/index.html`, on 200 and 304 responses) also carries
the page's `Content-Security-Policy`, which `build_content_security_policy` in
`server/routes/spa.py` builds once at startup from the chart host settings and
any configured reCAPTCHA site keys (shown below with reCAPTCHA unset):

```text
default-src 'self';
script-src 'self' <origin of DC_WEB_COMPONENT_URL>;
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com data:;
img-src 'self' https: data: blob:;
connect-src 'self' <DC_WEB_COMPONENT_API_ROOT>;
frame-src 'self';
object-src 'none';
base-uri 'none';
form-action 'self';
frame-ancestors 'self'
```

When either `RECAPTCHA_SESSION_SITE_KEY` or `RECAPTCHA_CHECKBOX_SITE_KEY` is
set at startup, `build_content_security_policy` also adds Google's reCAPTCHA
endpoints to `script-src`, `connect-src`, and `frame-src` (see
[deployment.md](deployment.md#protecting-traffic-with-recaptcha-enterprise-optional)).

`script-src` allows no inline or evaluated script: the shell's two inline
`<script>` elements are JSON data blocks, which browsers do not run, and the
loader that adds `datacommons.js` is part of the app's own bundle. The app
stylesheet (`ui/src/index.css`) and `datacommons.js` both load Google Fonts, so
`style-src` allows `fonts.googleapis.com` and `font-src` allows
`fonts.gstatic.com`. The Emotion and styled-components code in
`datacommons.js` inserts `<style>` elements into each chart's shadow root, so
`style-src` keeps `'unsafe-inline'`. The PDF export code draws `data:` and
`blob:` images. `base-uri 'none'` breaks nothing because the app resolves paths
from `location.pathname`, and `form-action 'self'` does not affect the chat
input, which submits through JavaScript. Static files other than the shell and
`/agent/*` responses carry no page policy.

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
(such as `<datacommons-line>` or `<datacommons-bar>`). The browser loads them
from `DC_WEB_COMPONENT_URL` (default
`https://datacommons.org/datacommons.js`), and they fetch their own chart data
and place names directly from `DC_WEB_COMPONENT_API_ROOT` (default
`https://datacommons.org`), passed to each component as its `apiroot`. Both are
agent settings that the server stamps into `#runtime-config` (see
[UI theme & instance branding](#ui-theme--instance-branding)), so they change
without a UI rebuild. The API root is a Data Commons website host, not
`api.datacommons.org`, which requires an API key that the browser cannot
hold.

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
   or `bottom_n` slice), with an optional unit, on single-date charts an
   optional date, and on `line` charts optional `start_date` and `end_date`
   bounds that clamp the drawn series.
   The server splits the stream at paragraph boundaries and at the closing fence
   of each chart block, and emits one `content {block}` frame per completed
   paragraph and per chart that resolves. A Markdown heading line is a
   paragraph of its own, and so is a one-line lead-in ending with a colon
   directly above a list item or table row, even without a blank line
   between them. The Data gaps block that closes an answer (a `**Data gaps**`
   label line, an introducing line, and a list of the measures the answer
   could not cover) is one text block even when the model leaves blank lines
   inside it. The server (`workflows/data_gaps.py`) parses it, and its
   `content {block}` frame also carries `data_gaps`: the introducing line as
   `intro` and the measures as `items`, both in plain text. The app shows
   that list as a "Data gaps" section after the answer's blocks and above
   the citations, and does not render the block's Markdown. A label that no
   list follows stays ordinary text. Resolution is set membership against
   the turn cache: an unknown table, a place or date the table does not hold, a
   unit mismatch across the tables on one axis, a `line` whose date bounds
   leave a charted table without a place holding two dates, or a kind the
   table shape cannot support (a map without a cohort, a scatter without two
   variables) rejects the chart, which is dropped and counted while the prose
   stands. When the digest relates a scatter's two variables
   (`relate_cohorts`), the resolver orders them from the relation, the
   compared `target` first and the grouping `by` second, so the component
   draws the grouping variable on the horizontal axis whatever order the
   model listed the tables in. A single-date chart without a `date` is drawn
   at the reference date of the results over its tables only when those
   tables agree on one date; a relation whose two tables are aligned on
   different dates leaves the date unset, so the component draws each
   variable at its latest date.
   The date bounds are checked with the comparison `<datacommons-line>`
   applies, so a `start_date` of `2005-06` excludes an annual `2005`. Each
   resolved chart carries `facet_ids` mapping its variables to the facets that
   served them, matching the Data Commons web components' facet attributes
   (`facetId` on highlight, `facetIds` or `facetMapping` on the other
   components). A derived per-capita table is scaled automatically in the
   digest (per 1, 1,000, or 100,000 people so the median non-zero magnitude is
   at least 1), or given as a percentage when its step sets a scale of 100 (a
   share of the population, such as people below the poverty line). A per-capita
   table not given as a percentage is charted when referenced by its `s<n>`
   table id as its numerator with the web component's per-person normalization;
   a percentage is not, because that normalization applies no scale and would
   draw per-person fractions beside the percentages, nor is its numerator
   charted in its place by the default chart floor; other derived tables
   are not chartable. At most four charts are accepted per answer. The model
   writes each chart directly after the bullet list or table holding its
   figures, and the app shows that list or table beside the chart in one
   section, headed by its section heading when it has one. A list's section
   sits on its own surface (`--color-surface-section`, white by default),
   with the heading at the top of the list's column; a table's section has
   no surface, since the table carries its own card, and its heading spans
   the full width above the table and chart. The model writes a section
   heading as a Markdown heading line (`## Population by sex`), and the app
   renders one whose label is plain text as an h2 section heading. A line
   that only ends with a colon is text, never a heading.
   Maps, scatter charts, and a chart after prose render full width. When the
   digest has data and no chart is
   emitted, the default chart floor appends at most one chart projected directly
   from the primary result (`scatter` for a cohort `relate_cohorts` result,
   which is considered first, or the direct chart of `analyze_timeseries`,
   `rank_cohort`, or `compute_composition`; distributions, standalone
   derivations, non-cohort relations, and relations over a window cohort receive
   none). When the digest holds a cohort `relate_cohorts` result, the floor is
   that relation's scatter or nothing: it never falls back to a chart of one of
   the two measures, which would show places the answer's group tables do not.
   The default chart's block carries `standalone: true`, so the app shows it
   full width rather than beside the text before it. A ranking of a cohort, or
   any ranking
   over a window cohort, is charted as a `line` of its first five places, with
   the parent place when a step analyzed the parent's series, the parent's table
   holds at least two dates in the drawn span, and the parent's value does not
   exceed every cohort place's value on each date they share (as a total or
   count does, which would flatten their lines), and with the ranked places
   alone otherwise; a single-date cohort ranking falls back to a `ranking` chart
   when its table has one date. The
   default `line` of a window ranking is clamped to the window's start and end
   dates. The default `line` of an `analyze_timeseries` step is clamped to the
   earliest date the step summarized when the step, or the derived table it
   reads, sets `start_date`, and to the latest when either sets `end_date`. A
   `ranking`, `bar`, `map`, or `scatter` of a table that the digest ranks only
   over a window needs an explicit date, because without one it would draw the
   latest values rather than the change the prose describes. When
   the digest has data, the synthesis contract's `synthesis_title` addendum
   has the model open its answer with a `# ` title line, a short label for
   the data the answer presents; the server (`workflows/title.py`) takes that
   line off the stream and sends it as a `{title}` `content` frame before the
   first block. Only a Markdown heading (`#` to `######`) or a line starting
   with a `Title:` label counts as a title line. A turn without data gets the
   `synthesis_no_title` addendum and no title, even when the model writes
   one. The model does not write a closing line or link on such a turn. When
   the search finished, the app shows its own link to the dataset intake form
   under the answer (`SUGGEST_DATASET_URL` in `ui/src/config/copy_chat.ts`).
   The signed `model_response` is the text blocks joined by blank lines,
   with the chart blocks and the title line stripped, matching the text
   blocks emitted in `content` frames. A stream that stalls for 60 seconds
   waiting for a chunk ends the turn with `synthesis_stream_error`.
4. **Turn signing (`finalize`):** The server builds the turn's `state_slots`
   from the fetched tables the specification used and the displayed charts
   (`workflows/state_slots.py`), and signs the completed turn into the window
   so the browser can include it in follow-up questions.
5. **Follow-up suggestions (`follow_ups`):** Suggested follow-up questions are
   streamed after the main answer finishes.
   A follow-up call that does not finish within 10 seconds is abandoned, and
   the stream closes without a `follow_ups` frame.

### Server-Sent Events (SSE)

The server streams progress and answer chunks to the browser as Server-Sent
Events (SSE). Each event has an `event` name, a JSON `data` payload, and (except
for `heartbeat`) a sequential `id` starting at `1`:

| Event | What it contains |
| :--- | :--- |
| `status` | Current step (`classify`, `discovery`, `processing`, or `synthesis`) and status message |
| `thought` | Model reasoning summary from the `discovery` or `synthesis` step |
| `content` | Answer title (`{title}`, before the first block, only when the answer has data), answer block (`{block}` of type `text` or `chart`; the Data gaps text block adds `data_gaps: {intro, items}`; a server-supplied default chart adds `standalone: true`), tool call details (`{tool_call}`), citations (`{sources}`), or data status (`{data_status}`) |
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
  "compacted_summary": null,
  "conversation_id": "<32 hex characters>"
}
```

### How the server verifies conversation history

Because the conversation history comes from the browser, the server verifies
that previous answers were not modified before feeding them back to Gemini:

- When a turn finishes, the server computes an HMAC signature (`hmac`) over that
  turn's question, answer, and position in the conversation, together with
  the window's `compacted_summary` and `conversation_id`, using
  `TRANSCRIPT_HMAC_SECRET`.
- When the browser sends a follow-up question, the server re-checks the
  signatures on every turn before starting the stream:

| HTTP Status | When it happens |
| :--- | :--- |
| `403` | Cloud Armor reCAPTCHA policy requires interactive verification |
| `413` (`request_too_large`) | Request body is larger than 4 MiB |
| `400` (`transcript_invalid`) | Turn history was modified, reordered, or exceeds size limits (>6 turns, >32,000-character answer, or >8,000-character summary), or `conversation_id` does not match the turns |
| `422` | Request body is invalid JSON, or `message` (>4,000 characters) / `idempotency_key` is invalid |

If the server returns `400`, the UI clears its stored signatures so the user's
next question starts fresh. If Cloud Armor returns `403` while
`recaptcha_checkbox_site_key` is configured in `#runtime-config`, the UI evicts
any cached checkbox token, opens `RecaptchaModal` over the paused turn, caches
the solved token in memory for 25 minutes, and retries the identical request
once with `X-Recaptcha-Token`.

In local development, if neither `TRANSCRIPT_HMAC_SECRET` nor
`TRANSCRIPT_HMAC_SECRET_NAME` is set, the server generates a temporary random
key at startup. In multi-instance deployments (such as GKE or Cloud Run), where
follow-up requests can land on any container instance, all instances share the
same key either by injecting `TRANSCRIPT_HMAC_SECRET` directly or by resolving
`TRANSCRIPT_HMAC_SECRET_NAME` from Secret Manager at startup.

### Conversation ID

Each conversation has a `conversation_id` of 32 lowercase hexadecimal
characters, which links its turns without server-side state. The server mints
it from random bytes when a request arrives without `turns`, signs it into
every turn of the conversation, and returns it in each signed `terminal`
event. The browser sends it back beside `turns`, and compaction re-signs the
window under the same ID. The ID is not derived from any user, browser, or
network identifier, and the browser holds it only in memory with the turns,
so reloading the page or starting a new chat starts a new conversation. A
request whose `conversation_id` is changed, malformed, missing beside
`turns`, or sent without `turns` is rejected with `400`
(`transcript_invalid`). Two properties follow from keeping no server-side
state:

- A conversation whose first turn is not signed (it was refused, it failed, or
  its answer was too large to sign) leaves the browser without a window, so
  the next request receives a new `conversation_id`.
- A client that resends an older window it was given keeps that window's
  `conversation_id` and repeats a `turn_index`.

### Keeping conversation history compact

To keep prompts fast and within model token limits, the browser sends at most
the **6 most recent turns** in full:

- **Summarizing older turns (`compacted_summary`):** When a 7th turn finishes,
  the server summarizes the oldest turn into `compacted_summary`, removes that
  turn from the list, and re-signs the remaining 6 turns. The browser replaces
  its stored history with the updated `window` returned in the `terminal` event.
  The summarization prompt quotes the earlier summary inside an
  `<earlier_summary>` block and each evicted turn inside its own
  `<evicted_turn>` block, removes every conversation delimiter (including case,
  whitespace, self-closing, and attribute variants) from the quoted text, and
  tells the model that the blocks hold material to summarize, not instructions
  to follow.
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
fills in only the `{{instance.*}}` placeholders, so no system instruction
contains the current date. The server supplies the date in the request
instead: in the `classify`, discovery, and `synthesis` calls, the user
message that carries the current request opens with a
`Current date: YYYY-MM-DD` line, which `transcript_contents`
(`workflows/transcript.py`) writes as a text part of its own before the
request text. The date is the calendar date in the `TIMEZONE` zone, and
relative dates such as "this month" or "over the last decade" resolve
against it. `run_turn` pins one date for the whole turn with
`pin_current_date` (a context variable, so concurrent turns keep their own),
and all three calls carry that same date. The code-owned classify,
discovery, and synthesis contracts state that this line is the
authoritative current date, so an instance that overrides a prompt keeps
both the date and that rule. The signed turn, the
messages of earlier turns, and the follow-up and compaction requests carry
no date.

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
  missing or invalid. A Key Metrics tile keeps only the attributes that
  `metricsTile` lists in `schemas/theme.schema.json`, and a tile whose `type`
  is not one of its chart types is dropped, so a theme cannot set an arbitrary
  attribute on a chart element.

When the agent server serves `index.html` (`server/routes/spa.py`), it also
injects the runtime settings — the effective chat availability, the chart
hosts, and any configured public reCAPTCHA site keys — into
`<script id="runtime-config" type="application/json">`:

```json
{
  "enable_chat": true,
  "unavailable_title": "<str>",
  "unavailable_message": "<str>",
  "web_component_url": "<str>",
  "web_component_api_root": "<str>",
  "recaptcha_session_site_key": "<str, omitted when unset>",
  "recaptcha_checkbox_site_key": "<str, omitted when unset>"
}
```

`getRuntimeConfig()` in `ui/src/config/runtime_config.ts` reads
`#runtime-config` synchronously at startup; missing or invalid chart hosts
resolve to `""` without affecting chat, so no script or chart data loads from
an unintended origin. When `web_component_url` is non-empty, `ui/src/main.tsx`
appends one `<script>` before the first render
(`ui/src/utils/load_web_components.ts`), and chart components wait for each
custom element with `customElements.whenDefined`. When `enable_chat` is
`false`, `App` renders `UnavailableView`
(`ui/src/components/view_unavailable.tsx`) with `unavailable_title` and
`unavailable_message` on the Data Agent route, marks the background shell
(`Header`, `Sidebar`, and `MenuDrawer`) `inert` while the portaled note is
shown, keeps `MetricsPage` (`#/metrics`) interactive when opened by URL, and
hides the "New chat" controls. Under `pnpm dev:ui`, the Vite dev server copies
`#runtime-config` from the agent at `AGENT_URL` on page load
(`ui/src/config/runtime_config_dev.ts`), leaving the element empty with a
warning when the agent shell cannot be read.

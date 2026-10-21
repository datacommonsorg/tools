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
(`mcp/client.py`) over HTTP to search Data Commons for places, statistical
variables, and observations.

### 2. Browser chart requests

When an answer includes a chart, the UI renders Data Commons web components
(such as `<datacommons-line>` or `<datacommons-bar>`). Those components fetch
their own chart data and place names directly from Data Commons
(`datacommons.org` or the same-origin Data Commons website host).

## MCP tool discovery & session recovery

### Automatic tool discovery

Different versions of the Data Commons MCP server expose slightly different
tools (for example, newer versions add `get_variable_metadata` and source
attribution). Instead of hardcoding a fixed list of tools, the agent asks the
MCP server which tools are available (`tools/list` in `mcp/capabilities.py`) on
the first chat request and caches the result.

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
(`ENABLE_CHAT`, default `true`); when `ENABLE_CHAT=false`, the turn aborts
immediately with a single `terminal` error frame (`reason: "chat_disabled"`)
before making any Gemini or MCP calls. Otherwise, the request runs through the
agent loop in five steps:

1. **Query classification (`classify`):** Before any tool is called, a
   deterministic pre-filter screens out prompt injection, persona overrides,
   secret exfiltration, jailbreak phrases, and injection payloads without a
   model call. One structured Gemini call on `gemini.classify_model`
   (`gemini-3.5-flash-lite` by default) then produces one of three outcomes:
   - **Refused:** Ends the turn in a single `terminal` frame
     `{state: "refused", idempotency_key, reason, message}` with no `error` key
     (`reason` is `adversarial`, `off_domain`, or `safety_blocked`). The turn is
     not signed and is excluded from the multi-turn window, and the UI renders
     the message as a notice rather than an error card.
   - **Clarification:** When a place name is ambiguous or required and omitted,
     streams the clarification question as answer `text`, signs the turn with
     empty state slots, and emits a signed `complete` terminal frame without
     `data_status`, `sources`, `chart_config`, or `follow_ups` frames.
   - **Classified:** Continues into the discovery loop and synthesis with the
     analytical `pattern` (`single_point`, `top_n_ranking`, `distribution`,
     `trend_delta`, `outliers`, `correlation`, `composition`,
     `sequential_stages`, `clustering`, `forecasting`, `exploratory`, or
     `data_availability`) recorded in telemetry and its directive from
     `workflows/pattern_guidance.py` appended to the system instructions of both
     calls. If the classifier call fails, the turn falls through as
     `exploratory` without a directive.
2. **Data gathering (`mcp`):** Gemini calls Data Commons MCP tools to look up
   places, variables, and observations. If the MCP server cannot be reached, the
   turn stops and returns an error so the model never guesses numbers without
   data.
3. **Answer synthesis & chart selection (`synthesis` / `chart_config`):**
   Gemini writes a markdown response with inline citations while checking in
   parallel whether the data can be shown in a chart. A chart is included only
   if validation confirms that matching data exists.
4. **Turn signing (`finalize`):** The server packages the updated conversation
   history and signs the completed turn so the browser can include it in
   follow-up questions.
5. **Follow-up suggestions (`follow_up`):** Suggested follow-up questions are
   streamed after the main answer finishes.

### Server-Sent Events (SSE)

The server streams progress and answer chunks to the browser as Server-Sent
Events (SSE). Each event has an `event` name, a JSON `data` payload, and (except
for `heartbeat`) a sequential `id` starting at `1`:

| Event | What it contains |
| :--- | :--- |
| `status` | Current step (`classify`, `mcp`, `synthesis`, or `chart_config`) and status message |
| `thought` | Model reasoning summary from the `mcp` or `synthesis` step |
| `content` | Answer text (`{text}`), tool call details (`{tool_call}`), citations (`{sources}`), data status (`{data_status}`), or chart config (`{chart_config}`) |
| `terminal` | Final turn status (`state: "complete"`, `"refused"`, or `"error"`), plus the signed conversation state on completion, `{reason, message}` (with no `error` key) on refusal, or `{error, reason}` on failure |
| `follow_ups` | `{follow_up_questions}`, sent after `terminal` when available |
| `heartbeat` | `{}`, sent every 15 seconds so proxies do not close idle connections |

How the stream ends:

- **Explicit completion (`terminal`):** Every finished turn sends a single
  `terminal` event with `state: "complete"`, `state: "refused"`, or
  `state: "error"`. A `refused` frame carries `{reason, message}` and no `error`
  key, and is left unsigned. If the connection drops before a `terminal` event
  arrives, the UI shows that the response was interrupted.
- **Client disconnect:** If the user closes the tab or stops the request, the
  server cancels any in-progress model calls and logs the turn as `canceled`.
- **Duplicate protection (`idempotency_key`):** Each request includes a unique
  `idempotency_key` generated by the UI, which the server echoes back in the
  `terminal` event.

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

In local development, if `TRANSCRIPT_HMAC_SECRET` is not set, the server
generates a temporary random key at startup. On Cloud Run, where follow-up
requests can land on any container instance, all instances share the same
`TRANSCRIPT_HMAC_SECRET` from Secret Manager.

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
   `prompts/*.md` (`classify`, `mcp`, `synthesis`, `follow_up`) once at startup
   from the private GCS config bucket. HTML comments (`<!-- ... -->`) are
   stripped from prompt files, and `{{instance.*}}` placeholders are filled in
   from `template_vars` in `agent-config.json`.
2. **Local development (`agent/config.json`):** Generated by `pnpm dev:agent`
   (`dev.py`) by merging `defaults/`, `config/`, and `.env.local`, and
   automatically reloaded whenever the file changes.
3. **Container defaults (`agent/defaults/`):** Built into the container image by
   `scripts/stage_static.mjs`. Its `prompts/*.md` files provide the base prompt
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
`config_model.py`.

For the Gemini API key (`get_gemini_api_key()`):

- **Cloud Run:** Reads `GEMINI_API_KEY_SECRET` from Secret Manager and caches it
  in memory for 5 minutes. Any `key=...` query parameters are redacted from logs
  and error messages.
- **Local development:** Reads `gemini.api_key` from the local
  `agent/config.json`.

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

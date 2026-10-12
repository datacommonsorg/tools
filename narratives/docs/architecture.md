# Architecture & Design Notes

This document describes the runtime architecture, network seams, streaming
protocol, multi-turn state management, and configuration model of Narratives.

For operational deployment instructions, see [`deployment.md`](deployment.md).
For local development and testing, see [`development.md`](development.md).

---

## Contents

- [System overview](#system-overview)
- [Two seams: MCP vs. HTTP reverse proxy](#two-seams-mcp-vs-http-reverse-proxy)
- [MCP capability discovery & session recovery](#mcp-capability-discovery--session-recovery)
- [Chat pipeline & typed SSE protocol](#chat-pipeline--typed-sse-protocol)
- [Stateless multi-turn context & HMAC signing](#stateless-multi-turn-context--hmac-signing)
- [Configuration, secrets & UI theme loading](#configuration-secrets--ui-theme-loading)
- [Critical invariants tested in CI](#critical-invariants-tested-in-ci)

---

## System overview

```
                     ┌──────────────────────────────────────┐
   browser ─────────►│  APP PLANE                           │
                     │  one container: agent API + SPA      │
                     │                                      │
                     │   MCP client ─ capability probe      │
                     │   /dcproxy   ─ → DATA_PLANE_URL      │
                     │   auth       ─ strategy chosen by    │
                     │                host                  │
                     └──────────────┬───────────────────────┘
                                    │  DATA_PLANE_URL
                                    ▼
                          public datacommons.org
                          nothing to run
```

In production, a single Uvicorn container (`narratives_agent.server.app:app`)
exposes three surfaces on one origin:

1. **Compiled React SPA (`server/routes/spa.py`)** — serves `index.html`,
   content-hashed bundles under `/assets/` and `/theme/` (`immutable` cache
   headers), root-level SVGs (sandboxed via `Content-Security-Policy: sandbox`),
   and `/healthz` for the Cloud Run container startup probe.
2. **Agent API (`/agent/*`)** — serves `/agent/health`, `/agent/chat/stream`,
   and system routes.
3. **Data Commons reverse proxy (`server/routes/dcproxy.py`)** — forwards
   browser chart and place queries to the configured Data Commons data plane.

---

## Two seams: MCP vs. HTTP reverse proxy

### Agent → backend, over MCP (stable, abstracted)

The agent uses the official `mcp` Python SDK (`mcp/client.py`) to send
`initialize`, `notifications/initialized`, `ping`, `tools/list`, and
`tools/call` requests over Streamable HTTP. The session ID is carried in the
`Mcp-Session-Id` header, and the protocol version is negotiated during
`initialize`. This seam works unchanged across Data Commons MCP server
generations.

### Browser → backend, over HTTP (proxied, never translated)

Data Commons REST generations return different payload shapes
(`data[var][entity].series` + `facets` versus `byVariable[v].byEntity`), and the
Data Commons chart web components fetch their own data relative to the page
origin. Narratives therefore enforces: **one origin, one reverse proxy, no shape
translation.** The browser always talks to the app plane, and `/dcproxy` replays
requests to the configured data plane.

When targeting public Data Commons, the agent and browser routes live on two
different hosts:

| Setting | Default | Used by |
| :--- | :--- | :--- |
| `DATA_PLANE_URL` (`PUBLIC_DC_URL`) | `https://api.datacommons.org` | Agent MCP (`/mcp`) and versioned REST routes |
| `DATA_PLANE_WEB_URL` (`PUBLIC_DC_WEB_URL`) | `https://datacommons.org` | Browser chart routes (`/api/observations/series`, `/api/place/name`, `/core/api/...`) |

`/dcproxy` enforces two security boundaries on every proxied request:

- **Host-scoped credential attachment:** `DC_API_KEY` is attached only when the
  target host is a recognized public Data Commons host, never to arbitrary
  third-party hosts.
- **IAP identity header stripping:** When Identity-Aware Proxy (IAP) sits in
  front of Cloud Run, Cloud Run hands the container IAP's `Authorization` token
  (whose audience is *this* service). `/dcproxy` strips incoming IAP/auth
  headers before forwarding so the user's identity token is never leaked
  upstream.

---

## MCP capability discovery & session recovery

### Capability discovery, not declaration

The tool surface is probed from `tools/list` (`mcp/capabilities.py`) rather than
hardcoded. A hardcoded union of tool names would let the model call
`get_variable_metadata` against a 1.2.x server (which answers "Unknown tool" and
burns a reasoning iteration), and on a 1.2.x server source attribution would be
unavailable silently.

The server does not contact MCP at startup, and `/agent/health` never blocks on
the data plane: it reports the resolved `mcp_url` and the cached tool surface
(`mcp.generation` and `mcp.supports_source_attribution`), which starts empty and
populates once a chat turn or background probe lists the tools.

### Session recovery across Cloud Run scaling

MCP sessions are bound to the upstream server process that minted them, and
Cloud Run has no session affinity by default. A session created against upstream
instance 1 may be presented on the next tool call to instance 2, which has never
seen that `Mcp-Session-Id`. The MCP client detects session rejection,
transparently re-initializes a fresh session, and retries the tool call.

---

## Chat pipeline & typed SSE protocol

`POST /agent/chat/stream` streams a turn as typed Server-Sent Events (SSE).
Every frame names its `event:` and carries a JSON `data:` payload, and every
frame except `heartbeat` carries an `id:` counting up from 1:

| Event | Payload |
| :--- | :--- |
| `status` | `{phase, message}` (`mcp`, `synthesis`, or `chart_config`) |
| `thought` | `{thought, phase}` (a reasoning summary from `mcp` or `synthesis`) |
| `content` | one of `{text}`, `{tool_call}`, `{sources}`, `{data_status}`, `{chart_config}` |
| `terminal` | `{state, idempotency_key, error?, reason?}`, plus `{turn_index, hmac, state_slots, compacted_summary, window}` on a signed `complete` |
| `follow_ups` | `{follow_up_questions}`, sent after `terminal` when any are generated |
| `heartbeat` | `{}`, sent every 15 seconds so proxies keep the connection open |

Key stream invariants:

- **Single terminal frame:** A turn finishes only when its single `terminal`
  frame arrives with `state: "complete"` or `state: "error"` (carrying a
  user-safe `error` and a machine-readable `reason` such as `mcp_unavailable`,
  `mcp_timeout`, or `synthesis_empty`). A stream that closes without a
  `terminal` frame was cut off, and the UI renders the turn as interrupted.
- **MCP as a hard dependency:** When no tools can be listed or a tool call fails
  at the transport layer, the turn terminates in `error` rather than answering
  from ungrounded model weights.
- **Disconnect cancellation:** A disconnected client receives no terminal frame;
  the server cancels in-flight work and records the turn as `canceled`.
- **Idempotency:** The request may carry an `idempotency_key` generated per UI
  submission, which the `terminal` frame echoes.

---

## Stateless multi-turn context & HMAC signing

The agent server stores no server-side session state. Instead, the browser holds
the conversation transcript and sends the active turn window with each follow-up
request, and the agent cryptographically signs each completed turn with
`TRANSCRIPT_HMAC_SECRET`:

```json
{
  "message": "And for Germany?",
  "idempotency_key": "b7e0...",
  "turns": [
    {
      "turn_index": 0,
      "idempotency_key": "3f1c...",
      "user_query": "What is the population of France?",
      "model_response": "<the streamed answer text, exactly>",
      "state_slots": {"scopes": [...]},
      "hmac": "<64 hex characters>"
    }
  ],
  "compacted_summary": null
}
```

### Verification and rejection

Each turn's `hmac` chains it to the preceding turn. Before opening the SSE
stream, the agent validates the transcript and rejects invalid requests:

| HTTP Status | Condition |
| :--- | :--- |
| `413` (`request_too_large`) | Request body exceeds 4 MiB |
| `400` (`transcript_invalid`) | Window was altered, reordered, or spliced, or exceeds schema caps (>6 turns, >32,000-char answer, or >8,000-char summary) |
| `422` | Body is not valid JSON, or `message` (>4,000 chars) / `idempotency_key` is invalid |

The UI recovers from a `400` by clearing its stored signatures so the user's
next question starts cleanly without prior context.

When `TRANSCRIPT_HMAC_SECRET` is unset, the agent generates an ephemeral random
key at startup. That suffices for a single local process, where a server restart
simply invalidates earlier browser transcripts. On Cloud Run, where requests
route across multiple container instances, every instance must share one
`TRANSCRIPT_HMAC_SECRET` (the agent logs a warning when `K_SERVICE` is set and
the secret is absent).

### Sliding window compaction and `state_slots`

- **6-turn window & compaction:** The window holds at most 6 turns. When a 7th
  turn completes, the oldest turn is folded into `compacted_summary` via a model
  call (falling back to a deterministic structured summary after 5 seconds) and
  the entire window is re-signed. The client replaces its stored turns with the
  re-signed `window` returned in the `complete` frame.
- **`state_slots`:** Records the places, variables, and dates retrieved during
  each turn so subsequent turns can resolve conversational references such as
  *"them"* or *"that period"*.
- **Unsigned turns:** A `complete` frame without an `hmac` marks a turn that was
  not signed (for example, because its answer exceeded the 32,000-character cap
  or signing failed); the client omits it from future requests. Signing and
  compaction are recorded as the `finalize` phase in OpenTelemetry spans.

---

## Configuration, secrets & UI theme loading

### Agent configuration & Secret Manager

`narratives_agent/config.py` resolves configuration in priority order and holds
it in process memory:

1. **`CONFIG_URL` (Cloud Run):** Fetched once at startup from the private GCS
   config bucket using the instance's metadata service-account token, along with
   `prompts/<slot>.md` (`mcp`, `synthesis`, `follow_up`). HTML authoring
   comments (`<!-- ... -->`) are stripped before prompts reach Gemini.
2. **`agent/config.json` (Local dev):** Staged by `pnpm dev:agent` (`dev.py`)
   from `defaults/` + `config/` + `.env.local` and reloaded when the file's
   modification time changes.
3. **`agent/defaults/` (Container fallback):** Shipped inside the image via
   `scripts/stage_static.mjs`.

The Gemini API key is resolved by `get_gemini_api_key()`:

- In Cloud Run, it reads `GEMINI_API_KEY_SECRET` from Secret Manager (cached in
  memory for 5 minutes with a 10-second timeout lock so concurrent cache misses
  share one read). The secret payload stores the bare API key string.
- In local development, it falls back to `gemini.api_key` in the staged
  `agent/config.json`.

### UI theme tokens & `#instance-config`

The UI ships with the Base Data Commons theme in `ui/src/index.css` using CSS
custom properties with fallback values (`var(--theme-*, <fallback>)`).
Per-instance customization is applied synchronously on initial render without an
asynchronous branding fetch:

- **Theme colors:** Optional `--theme-*` CSS custom property overrides are
  injected into `<style id="theme-tokens">` in `ui/index.html`.
- **Instance metadata & structure:** Components read `instanceName`, `logoUrl`,
  `logoText`, `logoAlt`, `headline`, `tagline`, `suggestions`, `navigation`,
  `metrics`, `thinkingIndicatorUrl`, and `doneIndicatorUrl` synchronously via
  `getInstanceConfig()` in `ui/src/config/instance_config.ts`. This module
  parses and validates `<script id="instance-config" type="application/json">`,
  sanitizing asset URLs and falling back field-by-field to
  `DEFAULT_INSTANCE_CONFIG` when the tag is empty or a field has an unexpected
  shape.

---

## Critical invariants tested in CI

The agent and UI test suites specifically guard six failure modes that would
otherwise fail **silently** in production:

1. **MCP session recovery** when the data plane scales across stateless Cloud
   Run instances.
2. **Both MCP server generations (1.2.x and 1.3.x) parsing accurately** —
   including a 1.3.x empty response (`{"data": {}}`), which must report
   `has_data=false` so the model never hallucinates numbers for missing data.
3. **Auth chosen strictly by target host** — attaching `DC_API_KEY` only for
   recognized public Data Commons hosts.
4. **Prompt placeholder substitution** — leaving unmatched `{{instance.*}}`
   placeholders visible verbatim rather than silently blanking a sentence's
   subject, while ignoring `_comment` keys.
5. **Gemini non-200 reporting and credential redaction** — failing closed with
   `key=...` query parameters redacted from logs and error messages.
6. **Chart suppression when validation gives no verdict** — hiding charts
   whenever the chart validation call returns an empty candidate list,
   malformed JSON, or a missing `data_found` boolean.

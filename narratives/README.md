# Narratives — Conversational Data Commons

A branded, conversational Data Commons explorer that packages a React 19
single-page application (`ui/`) and a Python 3.14 FastAPI + Gemini agent
(`agent/`) into a single container running against public `datacommons.org`.

Narratives answers natural-language statistical questions using Data Commons MCP
tools, renders interactive Data Commons charts, attaches inline source
citations, suggests follow-up questions, exports reports to PDF, and hosts a
configurable Key Metrics dashboard.

---

## How it fits together

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

The app plane serves the compiled React UI, runs the `/agent/*` chat pipeline,
discovers the upstream MCP tool surface at runtime, and reverse-proxies chart
data requests through `/dcproxy`. For deep-dive details on the streaming
protocol, multi-turn HMAC transcripts, and proxy design, see
[`docs/architecture.md`](docs/architecture.md).

---

## Quickstart: Run locally (2 minutes)

Run commands from the `narratives/` directory. You need **Node 24**, **pnpm**,
**Python 3.14**, **[`uv`](https://docs.astral.sh/uv/)**, and a
**[Gemini API key](https://aistudio.google.com)**.

```sh
# 1. Install UI and agent dependencies.
nvm use
corepack enable && pnpm i
(cd agent && uv sync)

# 2. Configure your local environment and add GEMINI_API_KEY.
cp .env.local.example .env.local
$EDITOR .env.local

# 3. Start the agent (port 5001) and Vite UI (port 3000) in two terminals.
pnpm dev:agent
pnpm dev:ui
```

Open `http://localhost:3000` in your browser. If you only want to work on the UI
against an already-deployed Cloud Run instance, set `AGENT_URL` in `.env.local`
and run `pnpm dev:ui` alone. See [`docs/development.md`](docs/development.md)
for full local workflows and testing commands.

---

## Quickstart: Deploy to Google Cloud (~10 minutes)

**One clone of this repository is one deployment.** Everything specific to your
instance lives in `config/` and is layered over `defaults/` at deploy time —
branding and prompts are configuration values, not code branches.

```sh
# 1. Clone. This clone IS the deployment.
git clone <repo-url> acme-dc && cd acme-dc/narratives

# 2. Fill in the four required values in config/instance.env.
$EDITOR config/instance.env

# 3. Check credentials, billing, and org policies before creating anything.
./deploy.sh --preflight

# 4. Store API keys in Secret Manager — once, ever.
DC_API_KEY=... GEMINI_API_KEY=... ./deploy.sh --bootstrap-secrets

# 5. Deploy.
./deploy.sh
```

Then open your deployment according to the `ACCESS_MODE` you chose:

```sh
# private
gcloud run services proxy <instance>-app --region=<your-region> --port=8080

# public or iap — deploy.sh prints the service URL
```

See [`docs/deployment.md`](docs/deployment.md) for prerequisites, customization
(`branding.json`, `agent-config.json`, `prompts/`), access modes, verification,
and troubleshooting.

---

## Documentation

| Audience | Document | Covers |
| :--- | :--- | :--- |
| **Operators & Deployers** | [`docs/deployment.md`](docs/deployment.md) | GCP setup, `config/instance.env`, secrets, branding, prompts, `deploy.sh`, access modes, and troubleshooting |
| **Developers & Maintainers** | [`docs/development.md`](docs/development.md) | Local dev (UI-only and full-stack), workspace scripts, testing, linting, repository layout, and PR checklist |
| **Architects & Engineers** | [`docs/architecture.md`](docs/architecture.md) | MCP vs. `/dcproxy` seams, capability discovery, typed SSE protocol, HMAC-signed transcripts, and theme loading |
| **Coding Agents & Contributors** | [`AGENTS.md`](AGENTS.md) · [`FRONTEND.md`](FRONTEND.md) | App-specific engineering conventions, Tailwind v4 styling rules, and verification commands |

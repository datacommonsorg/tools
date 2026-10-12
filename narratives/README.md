# Narratives

Narratives is a customizable, conversational web application for exploring
[Data Commons](https://datacommons.org/) datasets. It packages a React 19
single-page application (`ui/`) and a Python 3.14 FastAPI + Gemini backend
(`agent/`) into a single container that queries Data Commons over the Model
Context Protocol (MCP).

## Key features

- **Grounded statistical Q&A:** Answers natural-language questions using Data
  Commons MCP tools.
- **Interactive visualizations:** Renders Data Commons charts alongside
  generated responses.
- **Source attribution:** Attaches inline citations and dataset provenance to
  statistical claims.
- **Multi-turn conversations:** Supports follow-up questions and contextual
  suggestions across turns.
- **Key Metrics dashboard:** Displays a configurable dashboard of curated charts
  and indicators.
- **PDF export:** Exports answers and charts as formatted PDF reports.
- **Config-driven customization:** Customizes branding, themes, navigation, and
  system prompts through JSON and Markdown files in `config/` without modifying
  source code.

## Documentation

- **Run, test, or develop locally:** See the
  [Local Development Guide](docs/development.md).
- **Deploy to Google Cloud Run:** See the
  [Deployment & Customization Guide](docs/deployment.md).
- **Customize branding, themes, or prompts:** See
  [Customizing Your Instance](docs/deployment.md#customizing-your-instance).
- **Understand the architecture and protocols:** See the
  [Architecture Reference](docs/architecture.md).
- **Contribute code or configure AI coding agents:** See
  [`AGENTS.md`](AGENTS.md) and [`FRONTEND.md`](FRONTEND.md).

## Quickstart: Run locally

Run all commands from the `narratives/` directory.

### Prerequisites

- **Node.js 24** (via [`nvm`](https://github.com/nvm-sh/nvm)) and **pnpm**
- **Python 3.14** and **[`uv`](https://docs.astral.sh/uv/)**
- A **[Gemini API key](https://aistudio.google.com)**

### Steps

1. Install frontend and backend dependencies:

   ```sh
   nvm use
   corepack enable && pnpm i
   (cd agent && uv sync)
   ```

2. Create `.env.local` from the template and set `GEMINI_API_KEY`:

   ```sh
   cp .env.local.example .env.local
   $EDITOR .env.local
   ```

3. Start the backend server (port 5001) and frontend dev server (port 3000) in
   separate terminals:

   ```sh
   # Terminal 1: Start the Python agent server
   pnpm dev:agent

   # Terminal 2: Start the Vite UI server
   pnpm dev:ui
   ```

4. Open `http://localhost:3000` in your browser.

## Quickstart: Deploy to Google Cloud

Each deployment is configured in `config/` and deployed to Google Cloud Run
using Terraform and Cloud Build via `./deploy.sh`.

### Prerequisites

- A Google Cloud project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth login` and
  `gcloud auth application-default login`)
- `terraform`, `pnpm`, `python3`, and `uv` installed
- A [Data Commons API key](https://apikeys.datacommons.org) and a
  [Gemini API key](https://aistudio.google.com)

### Steps

1. Edit `config/instance.env` and set the required variables (`PROJECT_ID`,
   `REGION`, `INSTANCE`, and `ACCESS_MODE`):

   ```sh
   $EDITOR config/instance.env
   ```

2. Run preflight checks to verify credentials, billing, organization policies,
   and IAM permissions before provisioning resources:

   ```sh
   ./deploy.sh --preflight
   ```

3. Store your API keys in Google Cloud Secret Manager (required once per
   deployment):

   ```sh
   DC_API_KEY="<your-dc-key>" GEMINI_API_KEY="<your-gemini-key>" \
     ./deploy.sh --bootstrap-secrets
   ```

4. Build and deploy the service:

   ```sh
   ./deploy.sh
   ```

5. Access your deployed instance based on the `ACCESS_MODE` configured in
   `config/instance.env`:
   - **`public` or `iap`:** Open the Cloud Run service URL printed at the end of
     `./deploy.sh`.
   - **`private`:** Proxy the service locally with `gcloud`:

     ```sh
     gcloud run services proxy <instance>-app --region=<region> --port=8080
     ```

See the [Deployment & Customization Guide](docs/deployment.md) for custom
branding, prompt configuration, access modes, and troubleshooting.

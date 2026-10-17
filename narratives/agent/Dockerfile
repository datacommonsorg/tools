# Builds the Narratives application image, packaging the Python agent API and
# the compiled React UI in a single container.
#
# Before building this image, stage `ui/dist` into `./static` and `../defaults`
# into `./defaults` using `pnpm build` (which runs `scripts/stage_static.mjs`)
# or `./build.sh`.
#
# Force linux/amd64 architecture — Cloud Run rejects arm64 silently with a
# "failed to find supported architecture" startup error.
# hadolint ignore=DL3029
FROM --platform=linux/amd64 python:3.14-slim

# uv resolves and installs from uv.lock, so the image gets exactly the versions
# committed to the repository. Pinned to a uv release rather than :latest, so
# rebuilding an old commit still uses the uv that produced its lockfile.
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    AGENT_ROOT=/app \
    PATH="/app/.venv/bin:$PATH" \
    AGENT_PORT=5001 \
    MCP_PORT=8082 \
    TIMEZONE=UTC \
    ALLOWED_ORIGIN=*

WORKDIR /app

# System deps: tzdata is needed for ZoneInfo on slim images, and
# ca-certificates for HTTPS. Package versions are left unpinned because Debian
# slim repositories drop superseded versions across point releases.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Run the application as a non-root user while keeping `/app` owned by root.
RUN groupadd -g 10001 appuser \
    && useradd -u 10001 -g appuser -m -s /sbin/nologin appuser

# Dependencies first, without the project itself, so editing application code
# does not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Stage the compiled SPA (`static/`) and fallback configuration (`defaults/`).
COPY static/ ./static/
COPY defaults/ ./defaults/

USER appuser

# 8080 when this container is the Cloud Run ingress (the split deployment);
# AGENT_PORT still applies when it runs as a sidecar behind nginx.
EXPOSE 8080

# Served by Uvicorn in a single process: on 1 vCPU extra worker processes only
# contend. Scale out with Cloud Run instances, not in with workers.
#
# --timeout-graceful-shutdown 120: on SIGTERM, Uvicorn stops accepting
# connections and waits up to 120 s for in-flight requests, such as a chat
# stream, to finish before it closes them. On Cloud Run the drain is bounded
# at about 10 s instead, because Cloud Run sends SIGKILL 10 s after SIGTERM.
#
# Shell form is required here (rather than the JSON array exec form enforced by
# hadolint DL3025) so ${PORT} and ${AGENT_PORT} expand at startup: Cloud Run
# injects PORT when the container is the ingress, and falls back to AGENT_PORT
# when it runs as a sidecar behind nginx. `exec` keeps Uvicorn as PID 1 so it
# receives SIGTERM.
# hadolint ignore=DL3025
CMD exec uvicorn narratives_agent.server.app:app \
      --host 0.0.0.0 \
      --port "${PORT:-${AGENT_PORT:-5001}}" \
      --timeout-graceful-shutdown 120

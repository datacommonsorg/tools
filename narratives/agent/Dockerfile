# App plane for Custom Data Commons: the agent API and the compiled React UI in
# one container. Vendored from upstream additional_features/mcp_proxy_only.py
# (Apache-2.0), adapted for Cloud Run.
#
# The UI build is staged into ./static by build.sh (or by deploy.sh before
# `gcloud builds submit`) because the Docker build context is this directory —
# ui/dist sits outside it and cannot be COPYed directly.
#
# Built linux/amd64 only — Cloud Run rejects arm64 silently with a
# "failed to find supported architecture" startup error.

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

# System deps: tzdata is needed for ZoneInfo on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Run as a dedicated non-root user. /app is owned by that user so the config
# bootstrap can write config.json there at startup without root, and switching
# before `uv sync` avoids a recursive chown across `/app/.venv` in a later layer.
RUN groupadd -g 10001 appuser \
    && useradd -u 10001 -g appuser -m -s /sbin/nologin appuser \
    && chown appuser:appuser /app
USER appuser

# Dependencies first, without the project itself, so editing application code
# does not invalidate this layer.
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=appuser:appuser src/ ./src/
RUN uv sync --frozen --no-dev

# The compiled SPA, staged here by build.sh / deploy.sh. Served by
# src/narratives_agent/server/routes/spa.py.
COPY --chown=appuser:appuser static/ ./static/

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
# Shell form (not exec form) so ${PORT} expands: Cloud Run injects PORT when the
# container is the ingress, and falls back to AGENT_PORT when it runs as a
# sidecar behind nginx. `exec` keeps Uvicorn as PID 1 so it receives SIGTERM.
CMD exec uvicorn narratives_agent.server.app:app \
      --host 0.0.0.0 \
      --port "${PORT:-${AGENT_PORT:-5001}}" \
      --timeout-graceful-shutdown 120

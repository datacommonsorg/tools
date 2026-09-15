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

FROM --platform=linux/amd64 python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROXY_PORT=5001 \
    MCP_PORT=8082 \
    TIMEZONE=UTC \
    ALLOWED_ORIGIN=*

WORKDIR /app

# System deps: tzdata is needed for ZoneInfo on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Run as a dedicated non-root user. /app is owned by that user so the config
# bootstrap can write config.json there at startup without root.
RUN groupadd -g 10001 appuser \
    && useradd -u 10001 -g appuser -m -s /sbin/nologin appuser

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY main.py ./
COPY src/ ./src/

# The compiled SPA, staged here by build.sh / deploy.sh. Served by
# src/server/routes/spa.py.
COPY static/ ./static/

RUN chown -R appuser:appuser /app
USER appuser

# 8080 when this container is the Cloud Run ingress (the split deployment);
# PROXY_PORT still applies when it runs as a sidecar behind nginx.
EXPOSE 8080

# Served by gunicorn, not Flask's development server.
#
# Why the specific flags:
#   --worker-class gthread  chat responses are SSE streams held open for tens of
#                           seconds while Gemini thinks. Sync workers would tie
#                           up a whole process per stream -- worse than the dev
#                           server. Threads let one worker hold many streams.
#   --workers 1             on 1 vCPU extra worker processes only contend. Scale
#                           out with Cloud Run instances, not in with workers.
#   --timeout 0             gunicorn otherwise kills a worker whose request has
#                           "hung" -- which is what a long SSE stream looks like.
#   --graceful-timeout 120  Cloud Run sends SIGTERM before every deploy and
#                           scale-in; this drains in-flight streams instead of
#                           cutting answers off mid-sentence.
#
# Shell form (not exec form) so ${PORT} expands: Cloud Run injects PORT when the
# container is the ingress, and falls back to PROXY_PORT when it runs as a
# sidecar behind nginx. `exec` keeps gunicorn as PID 1 so it receives SIGTERM.
CMD exec gunicorn \
      --bind "0.0.0.0:${PORT:-${PROXY_PORT:-5001}}" \
      --worker-class gthread \
      --workers 1 \
      --threads 16 \
      --timeout 0 \
      --graceful-timeout 120 \
      --access-logfile - \
      main:app

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Multi-stage build for the Narratives application image, compiling the React
# SPA in Stage 1 and packaging it alongside the FastAPI backend in Stage 2.
#
# Build from the `narratives/` directory:
#   docker buildx build --platform linux/amd64 .
# To serve under a URL subpath (such as `/narratives/`), pass VITE_BASE_PATH:
#   docker buildx build --platform linux/amd64 --build-arg VITE_BASE_PATH=/narratives/ .

# Force linux/amd64 architecture so images built on Apple Silicon run on Cloud
# Run and GKE amd64 node pools.
# hadolint ignore=DL3029
FROM --platform=linux/amd64 node:24.22.1-slim AS ui-builder

WORKDIR /build

RUN corepack enable

COPY .npmrc package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY ui/package.json ./ui/
RUN pnpm install --frozen-lockfile

COPY ui/ ./ui/
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN pnpm -C ui build

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
    TIMEZONE=UTC

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
COPY agent/pyproject.toml agent/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY agent/src/ ./src/
RUN uv sync --frozen --no-dev

# Copy the compiled SPA from Stage 1 (`static/`) and fallback configuration (`defaults/`).
COPY --from=ui-builder /build/ui/dist ./static/
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

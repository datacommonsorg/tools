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
FROM --platform=linux/amd64 node:24-slim AS ui-builder

ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}

WORKDIR /build

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY ui/package.json ./ui/
RUN pnpm install --frozen-lockfile

COPY ui/ ./ui/
RUN pnpm -C ui build

# Force linux/amd64 architecture for the Python runtime stage.
# hadolint ignore=DL3029
FROM --platform=linux/amd64 python:3.14-slim

# Pin uv so dependency resolution matches the version that generated uv.lock.
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

# Install tzdata for ZoneInfo on slim images and ca-certificates for HTTPS.
# Package versions are unpinned because Debian slim drops superseded versions.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Run the application as a non-root user while keeping `/app` owned by root.
RUN groupadd -g 10001 appuser \
    && useradd -u 10001 -g appuser -m -s /sbin/nologin appuser

# Install dependencies before copying source so code edits keep this layer cached.
COPY agent/pyproject.toml agent/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY agent/src/ ./src/
RUN uv sync --frozen --no-dev

# Copy the compiled SPA from Stage 1 and fallback configuration from defaults/.
COPY --from=ui-builder /build/ui/dist ./static/
COPY defaults/ ./defaults/

USER appuser

EXPOSE 8080

# Shell form is required so ${PORT} and ${AGENT_PORT} expand at container
# startup while `exec` keeps Uvicorn as PID 1 to receive SIGTERM.
# hadolint ignore=DL3025
CMD exec uvicorn narratives_agent.server.app:app \
      --host 0.0.0.0 \
      --port "${PORT:-${AGENT_PORT:-5001}}" \
      --timeout-graceful-shutdown 120

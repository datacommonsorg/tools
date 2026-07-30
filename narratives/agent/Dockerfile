# Sidecar agent for the Custom Data Commons multi-container Cloud Run service.
# Vendored from upstream additional_features/mcp_proxy_only.py (Apache-2.0),
# adapted for multi-instance Cloud Run.
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

COPY mcp_proxy_only.py ./

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 5001

# Cloud Run health probes hit the agent on PROXY_PORT; the agent is the
# sidecar container, so the ingress container's nginx reverse-proxies
# /agent/* to 127.0.0.1:${PROXY_PORT}.
CMD ["python", "-u", "mcp_proxy_only.py"]

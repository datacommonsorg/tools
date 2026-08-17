# Services image — the ingress container for a Custom Data Commons instance.
#
# An overlay on the upstream Custom Data Commons image. It adds two things and
# changes nothing else:
#   1. The compiled React UI at /workspace/react-ui/.
#   2. An nginx config that serves that build at / and /assets/*, proxies
#      /agent/* to the agent sidecar on 127.0.0.1:${PROXY_PORT}, and leaves
#      /core/api/*, /mcp and everything else routed to the upstream services
#      (Flask :7070, Mixer/Envoy :8081, MCP :8082).
#
# This is one of the two containers in the Cloud Run service; the other is
# built from agent/Dockerfile. When upstream cuts a new tag, only the FROM
# below changes — the overlay itself is upstream-agnostic.
#
# Build context is narratives/, so `docker build -f narratives/Dockerfile` must
# be given narratives/ as its context. build.sh handles that.

# ---- Build stage: compile the React app -------------------------------------
# The build runs here rather than on the host so the image is reproducible from
# a clean clone: npm ci installs exactly the tree in package-lock.json, and no
# pre-built dist/ has to be staged in beforehand.
FROM node:20-alpine AS build

WORKDIR /src

# Copy the manifests first so this layer caches unless dependencies change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Runtime stage: upstream services + our overlay -------------------------
FROM --platform=linux/amd64 gcr.io/datcom-ci/datacommons-services:stable

# The React build. nginx serves index.html at / and the hashed bundles from
# /assets/*; public/ assets (logo.png, loader.png, send.svg) land here too.
COPY --from=build /src/dist /workspace/react-ui/

# Replaces the upstream nginx config in place.
COPY nginx.conf /workspace/nginx.conf

# Inherit the upstream ENTRYPOINT/CMD — it starts nginx, Flask, Mixer, the MCP
# server and the NL server together. Overriding it here would break the image.
#
# On running as root: the agent sidecar (agent/Dockerfile) drops to a dedicated
# non-root user, and this image deliberately does not. It is a thin overlay on
# an upstream image whose entrypoint supervises five processes and owns its own
# filesystem layout; choosing the runtime user is upstream's decision, and
# forcing one here would likely break nginx's pid/temp paths and the Flask and
# NL servers' writable directories. Nothing this overlay adds needs write
# access — the React build and nginx.conf are read-only at runtime. If upstream
# publishes a non-root variant, switch the FROM tag and add USER here.

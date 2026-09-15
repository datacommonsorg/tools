# Data-plane overlay on the upstream Custom Data Commons image.
#
# We do not fork upstream. This image adds exactly one thing: an nginx config
# that routes between the servers sharing this container — Mixer/Envoy :8081
# at /core/api/*, the MCP server :8082 at /mcp, and the upstream Flask website
# :7070 for everything else.
#
# It no longer carries the React UI and no longer proxies /agent/*. Both moved
# to the app-plane service, which is the public front door and reverse-proxies
# the routes above to this one. See DECOUPLING-PLAN.md.
#
# When upstream cuts a new tag, only the FROM tag below changes — the overlay
# is upstream-agnostic.

FROM --platform=linux/amd64 gcr.io/datcom-ci/datacommons-services:stable

# nginx config — overrides the upstream /workspace/nginx.conf in place.
COPY nginx.conf /workspace/nginx.conf

# Inherit upstream's ENTRYPOINT / CMD — nginx + Flask + Mixer + MCP + NL server
# are all started by the upstream entrypoint.

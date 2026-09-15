#!/usr/bin/env bash
# Build and (optionally) push the data-plane overlay image to Artifact Registry.
#
# No UI staging: this image stopped carrying the React build when the app plane
# was split out. The overlay is now just nginx.conf. See the README.
#
# Usage:
#   ./build.sh                     # build only, no push
#   ./build.sh --push              # build and push to AR
#   AR_REGION=us-central1 AR_REPO=dc-images PROJECT=cdc-platform-stg ./build.sh --push

set -euo pipefail

AR_REGION="${AR_REGION:-us-central1}"
AR_REPO="${AR_REPO:-custom-dc}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [ -z "$PROJECT" ] || [ "$PROJECT" = "(unset)" ]; then
    echo "Error: set PROJECT=<gcp-project> or run: gcloud config set project <id>" >&2
    exit 1
fi
IMAGE_NAME="services"
TAG="$(git rev-parse --short=12 HEAD)"

FULL_IMAGE="${AR_REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE_NAME}:${TAG}"

cd "$(dirname "$0")"

# Left over from when this image carried the UI. Removing it keeps a stale
# tree from being silently baked in by a future COPY.
rm -rf ./dist

# Build.
echo "Building ${FULL_IMAGE}"
docker buildx build \
    --platform linux/amd64 \
    -t "${FULL_IMAGE}" \
    -t "${AR_REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE_NAME}:latest" \
    --load \
    .

ARCH="$(docker inspect --format '{{.Architecture}}' "${FULL_IMAGE}")"
if [[ "${ARCH}" != "amd64" ]]; then
    echo "FATAL: image architecture is ${ARCH}, expected amd64" >&2
    exit 1
fi
echo "  arch verified: ${ARCH}"

if [[ "${1:-}" == "--push" ]]; then
    echo "Pushing ${FULL_IMAGE}"
    docker push "${FULL_IMAGE}"
    docker push "${AR_REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE_NAME}:latest"
    echo "Done. Tag for tfvars: ${TAG}"
fi

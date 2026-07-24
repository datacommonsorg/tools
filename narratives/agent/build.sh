#!/usr/bin/env bash
# Build and (optionally) push the agent sidecar image to Artifact Registry.
#
# Usage:
#   ./build.sh                     # build only, no push
#   ./build.sh --push              # build and push to AR
#   AR_REGION=us-central1 AR_REPO=dc-images PROJECT=cdc-platform-stg ./build.sh --push
#
# Tag is the short git SHA so image and infra (Terraform tfvars) stay in sync.

set -euo pipefail

AR_REGION="${AR_REGION:-us-central1}"
AR_REPO="${AR_REPO:-custom-dc}"
PROJECT="${PROJECT:-gdatacomms}"
IMAGE_NAME="agent"
TAG="$(git rev-parse --short=12 HEAD)"

FULL_IMAGE="${AR_REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE_NAME}:${TAG}"

echo "Building ${FULL_IMAGE}"
echo "  PROJECT=${PROJECT} AR_REGION=${AR_REGION} AR_REPO=${AR_REPO}"

docker buildx build \
    --platform linux/amd64 \
    -t "${FULL_IMAGE}" \
    -t "${AR_REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE_NAME}:latest" \
    --load \
    .

# Verify amd64 — Cloud Run rejects arm64 silently
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

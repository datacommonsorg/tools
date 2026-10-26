#!/usr/bin/env bash
# Build and (optionally) push the app-plane image (agent + UI) to Artifact Registry.
#
# Tag is the short git SHA so image and infra (Terraform tfvars) stay in sync.

set -euo pipefail

usage() {
    cat <<'USAGE'
Build and (optionally) push the app-plane image (agent + UI) to Artifact Registry.

Usage: ./build.sh [--push] [--help]

Options:
  --push    Push the built image (both the SHA tag and :latest) to AR.
  --help    Show this help and exit.

Environment overrides (with defaults):
  AR_REGION       Artifact Registry region   (us-central1)
  AR_REPO         Artifact Registry repo     (custom-dc)
  PROJECT         GCP project                (defaults to the active gcloud project)
  VITE_BASE_PATH  SPA base path              (/)
USAGE
}

# Resolve the narratives/ root directory so the multi-stage docker build has
# access to ui/, defaults/, and agent/ regardless of the caller's working directory.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
NARRATIVES_DIR="$(cd "${DIR}/.." >/dev/null 2>&1 && pwd)"

PUSH=false
for arg in "$@"; do
    case "${arg}" in
        --push) PUSH=true ;;
        --help|-h) usage; exit 0 ;;
        *)
            echo "Error: unknown argument '${arg}'" >&2
            usage >&2
            exit 1
            ;;
    esac
done

AR_REGION="${AR_REGION:-us-central1}"
AR_REPO="${AR_REPO:-custom-dc}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [ -z "$PROJECT" ] || [ "$PROJECT" = "(unset)" ]; then
    echo "Error: set PROJECT=<gcp-project> or run: gcloud config set project <id>" >&2
    exit 1
fi
IMAGE_NAME="agent"
TAG="$(git rev-parse --short=12 HEAD)"

IMAGE_BASE="${AR_REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE_NAME}"
FULL_IMAGE="${IMAGE_BASE}:${TAG}"
LATEST_IMAGE="${IMAGE_BASE}:latest"

echo "Building ${FULL_IMAGE}"
echo "  PROJECT=${PROJECT} AR_REGION=${AR_REGION} AR_REPO=${AR_REPO}"

docker buildx build \
    --platform linux/amd64 \
    --build-arg "VITE_BASE_PATH=${VITE_BASE_PATH:-/}" \
    -t "${FULL_IMAGE}" \
    -t "${LATEST_IMAGE}" \
    --load \
    "${NARRATIVES_DIR}"

# Verify amd64 — Cloud Run rejects arm64 silently.
ARCH="$(docker inspect --format '{{.Architecture}}' "${FULL_IMAGE}")"
if [[ "${ARCH}" != "amd64" ]]; then
    echo "FATAL: image architecture is ${ARCH}, expected amd64" >&2
    exit 1
fi
echo "  arch verified: ${ARCH}"

if [[ "${PUSH}" == true ]]; then
    echo "Pushing ${FULL_IMAGE}"
    docker push "${FULL_IMAGE}"
    docker push "${LATEST_IMAGE}"
    echo "Done. Tag for tfvars: ${TAG}"
fi

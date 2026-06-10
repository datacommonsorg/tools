#!/bin/bash

set -eo pipefail

# Change working directory to the script's directory
cd "$(dirname "$0")"

# Get current git commit SHA for image tagging
COMMIT_SHA=$(git rev-parse --short HEAD)

# Build the app locally to verify compilation
echo "Building the app locally..."
if command -v pnpm &> /dev/null; then
  pnpm i
  pnpm build
fi

# Build the container using Cloud Build (using custom service account & regional buckets to bypass default compute service account deletion issues)
echo "Building container with Cloud Build..."
gcloud builds submit . \
  --tag us-central1-docker.pkg.dev/datcom-website-sandbox/cloud-run-source-deploy/dataweaver-dev:${COMMIT_SHA} \
  --service-account projects/datcom-website-sandbox/serviceAccounts/data-weaver-sa-mj@datcom-website-sandbox.iam.gserviceaccount.com \
  --default-buckets-behavior=regional-user-owned-bucket \
  --project datcom-website-sandbox \
  --region us-central1

# Deploy the pre-built container to Cloud Run
echo "Deploying container to Cloud Run..."
gcloud run deploy dataweaver-dev \
  --image us-central1-docker.pkg.dev/datcom-website-sandbox/cloud-run-source-deploy/dataweaver-dev:${COMMIT_SHA} \
  --project datcom-website-sandbox \
  --region us-central1 \
  --no-allow-unauthenticated \
  --iap \
  --service-account data-weaver-sa-mj@datcom-website-sandbox.iam.gserviceaccount.com

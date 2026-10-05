#!/usr/bin/env bash
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
#
# Sourced by deploy.sh, after config/instance.env is loaded.

# Sync config/ to the bucket without building images, running Terraform,
# updating secrets, or ingesting data.
run_config_sync() {
    CONFIG_BUCKET="${CONFIG_BUCKET:-${PROJECT_ID}-${INSTANCE}-config}"
    if ! gcloud storage buckets describe "gs://${CONFIG_BUCKET}" --project="$PROJECT_ID" &>/dev/null; then
        log_error "Config bucket 'gs://${CONFIG_BUCKET}' does not exist. Run a full deploy first."
        exit 1
    fi

    log_info "[Config-Only] Synchronizing config/ assets to GCS config bucket..."
    gcloud storage rsync "$CONFIG_SRC" "gs://${CONFIG_BUCKET}" --recursive --project="$PROJECT_ID" --exclude="instance\.env"
    log_success "Configuration assets synced."

    # The agent reads its configuration once at startup, so a new revision is
    # required for uploaded config changes to take effect.
    if [ "$RESTART" = true ]; then
        log_info "[Config-Only] Forcing a new revision so the agent reloads config..."
        if gcloud run services update "${APP_SERVICE}" \
            --region="$REGION" --project="$PROJECT_ID" \
            --update-env-vars "FORCE_RESTART=$(date +%s)"; then
            log_success "[Config-Only] Done. New revision rolling out with the new config."
        else
            log_error "Restart failed. The bucket has the new config; the service does not."
            exit 1
        fi
    else
        log_warn "[Config-Only] Uploaded to the bucket, but NOT live on the service."
        echo "  The agent reads config once at startup and serves it from memory," >&2
        echo "  so a running revision keeps the old values until it is replaced:" >&2
        echo "    ./deploy.sh --config-only --restart" >&2
    fi
    exit 0
}

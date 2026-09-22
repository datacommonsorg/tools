#!/usr/bin/env bash
# ===========================================================================
# --config-only : push config/ to the bucket, no build, no terraform
# ===========================================================================
#
# Sourced by deploy.sh, which has already loaded config/instance.env, validated
# it, and defined the log_* helpers and colours this uses. Not runnable alone.

# --config-only: fast, deploy-free config/branding update against an existing
# instance. Syncs config/ to the bucket and nudges the agent to drop its
# branding cache, then exits — no images, terraform, secrets, or data.
run_config_sync() {
    CONFIG_BUCKET="${CONFIG_BUCKET:-${PROJECT_ID}-${INSTANCE}-config}"
    if ! gcloud storage buckets describe "gs://${CONFIG_BUCKET}" --project="$PROJECT_ID" &>/dev/null; then
        log_error "Config bucket 'gs://${CONFIG_BUCKET}' does not exist. Run a full deploy first."
        exit 1
    fi

    log_info "[Config-Only] Synchronizing config/ assets to GCS config bucket..."
    gcloud storage rsync "$CONFIG_SRC" "gs://${CONFIG_BUCKET}" --recursive --project="$PROJECT_ID" --exclude="instance\.env"
    log_success "Configuration assets synced."

    # --restart forces a new revision, which is the only way a config change
    # reaches the running service. Branding, agent-config and prompts are read
    # once at startup and served from process memory -- there is no cache TTL
    # and no refresh endpoint, so without this the bucket changes and the
    # service does not.
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

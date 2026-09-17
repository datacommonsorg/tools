#!/usr/bin/env bash
# ===========================================================================
# --destroy : tear this deployment down
# ===========================================================================
#
# Sourced by deploy.sh, which has already loaded config/instance.env, validated
# it, and defined the log_* helpers and colours this uses. Not runnable alone.

#
# Clients get the configuration wrong on a first attempt and need a way back to
# nothing. Without this they delete resources by hand and leave state behind
# that makes the next deploy fail in a confusing way.
run_destroy() {
    STATE_BUCKET="${STATE_BUCKET:-${PROJECT_ID}-tfstate}"
    CONFIG_BUCKET="${CONFIG_BUCKET:-${PROJECT_ID}-${INSTANCE}-config}"
    echo -e "\n${RED}This destroys every resource for '${INSTANCE}' in ${PROJECT_ID}.${NC}"
    echo -e "The config bucket gs://${CONFIG_BUCKET} is left alone; delete it separately if you want it gone.\n"
    printf "Type the deployment name (%s) to confirm: " "$INSTANCE"
    local answer; read -r answer
    [ "$answer" = "$INSTANCE" ] || { log_error "Not confirmed; nothing was destroyed."; return 1; }

    cd deploy/terraform-custom-datacommons/modules
    export TF_DATA_DIR=".terraform-${INSTANCE}"
    terraform init \
        -backend-config="bucket=${STATE_BUCKET}" \
        -backend-config="prefix=custom-datacommons/${INSTANCE}" \
        -reconfigure
    # The same guard the apply path uses: never destroy resources belonging to
    # another deployment.
    if ! terraform show -json 2>/dev/null | python3 ../../../deploy/check-state-owner.py "$INSTANCE"; then
        log_error "Refusing to destroy: the loaded state describes a different deployment."
        return 1
    fi
    terraform destroy -var-file="../${INSTANCE}.tfvars"
    log_success "Destroyed. The config bucket and Secret Manager entries remain."
}

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
#
# Globals:
#   PROJECT_ID, INSTANCE, STATE_BUCKET, CONFIG_BUCKET, STATE_SERVICE_RENAMED

# ===========================================================================
# --destroy : tear this deployment down
# ===========================================================================
#
# Clients get the configuration wrong on a first attempt and need a way back to
# nothing. Without this they delete resources by hand and leave state behind
# that makes the next deploy fail in a confusing way.
run_destroy() {
    echo -e "\n${RED}This destroys every resource for '${INSTANCE}' in ${PROJECT_ID}.${NC}"
    echo -e "The config bucket gs://${CONFIG_BUCKET} is left alone; delete it separately if you want it gone.\n"
    printf "Type the deployment name (%s) to confirm: " "$INSTANCE"
    local answer; read -r answer
    [ "$answer" = "$INSTANCE" ] || { log_error "Not confirmed; nothing was destroyed."; return 1; }

    cd deploy/terraform-custom-datacommons/modules || return 1
    export TF_DATA_DIR=".terraform-${INSTANCE}"
    terraform init \
        -backend-config="bucket=${STATE_BUCKET}" \
        -backend-config="prefix=custom-datacommons/${INSTANCE}" \
        -reconfigure
    # The same guard the apply path uses: never destroy resources belonging to
    # another deployment. A renamed service is this deployment's own, and a
    # teardown removes it either way.
    local state_json
    if ! state_json=$(terraform show -json); then
        log_error "Could not read the Terraform state for '${INSTANCE}'; nothing was destroyed."
        return 1
    fi
    local state_check=0
    python3 ../../../deploy/check_state_owner.py "$INSTANCE" <<<"$state_json" || state_check=$?
    if [[ "$state_check" -ne 0 && "$state_check" -ne "$STATE_SERVICE_RENAMED" ]]; then
        log_error "Refusing to destroy: the loaded state describes a different deployment."
        return 1
    fi
    terraform destroy -var-file="../${INSTANCE}.tfvars"
    log_success "Destroyed. The config bucket and Secret Manager entries remain."
}

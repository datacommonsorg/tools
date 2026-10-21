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
#   PROJECT_ID, INSTANCE, STATE_BUCKET, CONFIG_BUCKET

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
    # another deployment. Status 3 is this deployment's own service under an
    # old name, which a teardown removes either way.
    local STATE_CHECK=0
    # `|| true` so the status comes from the check alone; see deploy.sh.
    (terraform show -json 2>/dev/null || true) \
        | python3 ../../../deploy/check_state_owner.py "$INSTANCE" || STATE_CHECK=$?
    if [[ "$STATE_CHECK" -ne 0 && "$STATE_CHECK" -ne 3 ]]; then
        log_error "Refusing to destroy: the loaded state describes a different deployment."
        return 1
    fi
    terraform destroy -var-file="../${INSTANCE}.tfvars"
    log_success "Destroyed. The config bucket and Secret Manager entries remain."
}

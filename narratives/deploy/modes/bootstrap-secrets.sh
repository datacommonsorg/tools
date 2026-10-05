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

create_secret_if_missing() {
    local secret_id="$1"
    if ! gcloud secrets describe "$secret_id" --project="$PROJECT_ID" &>/dev/null; then
        log_info "Creating secret '$secret_id' in Secret Manager..."
        gcloud secrets create "$secret_id" --replication-policy="automatic" --project="$PROJECT_ID"
    fi
}

add_secret_version_if_changed() {
    local secret_id="$1"
    local secret_val="$2"
    if gcloud secrets versions describe latest --secret="$secret_id" --project="$PROJECT_ID" &>/dev/null; then
        local current_val
        # Fetch current value, suppressing errors if inaccessible
        current_val=$(gcloud secrets versions access latest --secret="$secret_id" --project="$PROJECT_ID" 2>/dev/null || echo "")
        if [ "$current_val" = "$secret_val" ]; then
            log_info "Secret '$secret_id' value matches latest version. Skipping upload."
            return
        fi
    fi
    log_info "Uploading new version for secret '$secret_id'..."
    echo -n "$secret_val" | gcloud secrets versions add "$secret_id" --data-file=- --project="$PROJECT_ID" >/dev/null
}

run_bootstrap_secrets() {
    secret_pairs=("DC_SECRET:DC_API_KEY" "GEMINI_SECRET:GEMINI_API_KEY")
    # MAPS_API_KEY was read only by the removed cdc data plane. Say so
    # rather than drop it in silence and still report "Secrets written".
    if [ -n "${MAPS_API_KEY:-}" ]; then
        log_warn "MAPS_API_KEY was supplied, but no backend reads it. NOTHING was stored for it."
    fi
    for pair in "${secret_pairs[@]}"; do
        secret_var="${pair%%:*}"; value_var="${pair##*:}"
        secret_id="${!secret_var}"; value="${!value_var:-}"
        create_secret_if_missing "$secret_id"
        if [ -z "$value" ]; then
            log_warn "${value_var} not set in the environment; leaving '${secret_id}' as-is."
            continue
        fi

        # Trim surrounding whitespace. A key pasted from a terminal or an
        # email routinely carries a leading space or a trailing newline, and
        # both are invisible in the value and fatal at the API.
        value="$(printf '%s' "$value" | tr -d '[:space:]')"

        # Validate before storing. Getting this wrong is expensive to find:
        # the deploy succeeds, the service starts, and the only symptom is
        # every chat turn failing with "The data service is unavailable"
        # while /agent/health reports zero tools, which looks like a
        # broken deployment rather than a mistyped key, and sends you into
        # the logs for an hour.
        if [ "$value_var" = "DC_API_KEY" ]; then
            dc_probe="${PUBLIC_DC_URL:-https://api.datacommons.org}"
            log_info "Checking DC_API_KEY against ${dc_probe} ..."
            dc_code=$(curl -s --max-time 30 -o /dev/null -w "%{http_code}" \
                -X POST "${dc_probe}/mcp" \
                -H "Content-Type: application/json" \
                -H "Accept: application/json, text/event-stream" \
                -H "X-API-Key: ${value}" \
                -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"deploy","version":"1"}}}' \
                || echo "000")
            if [ "$dc_code" = "401" ] || [ "$dc_code" = "403" ]; then
                log_error "DC_API_KEY was rejected by ${dc_probe} (HTTP ${dc_code}). Nothing was written."
                case "$value" in
                    *%) echo "  The value ends in '%'. zsh prints a reverse-video % at the end of" >&2
                        echo "  output with no trailing newline, and copying from the terminal picks" >&2
                        echo "  it up as a real character. Re-copy the key without it." >&2 ;;
                    *)  echo "  Check the key at https://apikeys.datacommons.org" >&2 ;;
                esac
                exit 1
            elif [ "$dc_code" = "000" ]; then
                log_warn "Could not reach ${dc_probe} to check the key; storing it unverified."
            else
                log_success "DC_API_KEY accepted (HTTP ${dc_code})."
            fi
        fi
        if [ "$value_var" = "GEMINI_API_KEY" ]; then
            # Store the bare API key string in Secret Manager and verify it
            # against the Gemini API before writing a new secret version so
            # invalid credentials fail during bootstrap rather than at
            # runtime.
            case "$value" in
                \[*|\"*)
                    log_error "GEMINI_API_KEY looks like a JSON array or quoted string. Supply the bare API key string. Nothing was written."
                    exit 1 ;;
            esac
            gem_base="https://generativelanguage.googleapis.com/v1beta/models"
            log_info "Checking GEMINI_API_KEY against the Gemini API ..."
            gem_code=$(curl -g -s --max-time 25 -o /dev/null -w "%{http_code}" \
                "${gem_base}?key=${value}&pageSize=1" || echo "000")
            case "$gem_code" in
                200) log_success "GEMINI_API_KEY accepted." ;;
                000) log_warn "Could not reach the Gemini API to check the key; storing it unverified." ;;
                *)   log_error "GEMINI_API_KEY was rejected by the Gemini API (HTTP ${gem_code}). Nothing was written."
                     echo "  Check the key at https://aistudio.google.com" >&2
                     case "$value" in
                         *%) echo "  The value ends in '%' -- that is zsh's end-of-line marker, copied by mistake." >&2 ;;
                     esac
                     exit 1 ;;
            esac
        fi
        add_secret_version_if_changed "$secret_id" "$value"
    done
    log_success "Secrets written to Secret Manager for instance '${INSTANCE}'."
    echo
    log_info "Nothing was written to disk. Deploy with: ./deploy.sh"
    exit 0
}

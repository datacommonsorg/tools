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

# ===========================================================================
# --preflight : check everything, create nothing
# ===========================================================================
#
# The failure this prevents is the worst kind: a deploy that reports success and
# produces a service nobody can open. Most commonly because the organization
# forbids public access, or because IAP has no consent screen to sign people in
# with. Both are invisible until someone tries the URL.
run_preflight() {
    local fail=0 warn=0
    # Never let a gcloud call block on a prompt. An expired token otherwise
    # makes preflight hang forever instead of telling the operator to re-auth,
    # and a check that can hang is worse than no check at all. Every call below
    # also reads from /dev/null for the same reason.
    export CLOUDSDK_CORE_DISABLE_PROMPTS=1
    STATE_BUCKET="${STATE_BUCKET:-${PROJECT_ID}-tfstate}"
    CONFIG_BUCKET="${CONFIG_BUCKET:-${PROJECT_ID}-${INSTANCE}-config}"
    echo -e "\n=== Preflight: ${INSTANCE} (${ACCESS_MODE} access) ===\n"

    _ok()   { echo -e "  ${GREEN}ok${NC}    $1"; }
    _bad()  { echo -e "  ${RED}FAIL${NC}  $1"; fail=1; }
    _warn() { echo -e "  ${YELLOW}warn${NC}  $1"; warn=1; }

    # --- tooling -----------------------------------------------------------
    local node_major uv_py
    if command -v uv &>/dev/null; then
        _ok "$(uv --version)"
        if uv_py=$(uv python find '>=3.14' 2>/dev/null); then
            _ok "$("$uv_py" --version 2>&1) ($uv_py)"
        else
            _bad "python >=3.14 missing — run: uv python install 3.14"
        fi
    else
        _bad "uv missing — install from https://docs.astral.sh/uv/"
    fi
    node_major=$(node -v 2>/dev/null | sed 's/^v//; s/\..*//' || echo 0)
    if [ "${node_major:-0}" -eq 24 ]; then _ok "node ${node_major}"; else _bad "node ${node_major:-missing} — the UI build needs 24"; fi
    if command -v pnpm &>/dev/null; then _ok "pnpm $(pnpm --version)"; else _bad "pnpm missing — run: corepack enable"; fi

    # --- credentials -------------------------------------------------------
    if gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null </dev/null | grep -q .; then
        _ok "gcloud authenticated as $(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null </dev/null | head -1)"
    else
        _bad "not authenticated — run: gcloud auth login"
    fi
    # Terraform reads Application Default Credentials, which are a SEPARATE
    # login from `gcloud auth login`. Missing ADC fails inside terraform, well
    # after the deploy looks like it is working.
    if [ -f "${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/application_default_credentials.json" ]; then
        _ok "application-default credentials present (Terraform uses these)"
    else
        _bad "no ADC — run: gcloud auth application-default login"
    fi

    # --- project -----------------------------------------------------------
    if gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1 </dev/null; then
        _ok "project ${PROJECT_ID} reachable"
        if gcloud beta billing projects describe "$PROJECT_ID" \
             --format='value(billingEnabled)' 2>/dev/null | grep -qi true; then
            _ok "billing enabled"
        else
            _warn "could not confirm billing is enabled (needs the billing API, or permission to read it)"
        fi
    else
        _bad "project ${PROJECT_ID} not found, or no permission to read it"
    fi

    # --- the two checks that actually matter -------------------------------
    case "$ACCESS_MODE" in
      public)
        # Domain Restricted Sharing forbids allUsers in many organizations. The
        # deploy still succeeds; the binding is simply refused, and the result
        # is a URL that returns 403 to everyone.
        local policy
        policy=$(gcloud resource-manager org-policies describe \
                   constraints/iam.allowedPolicyMemberDomains \
                   --effective --project="$PROJECT_ID" 2>/dev/null || true)
        if [ -n "$policy" ] && ! echo "$policy" | grep -qi "allowAll\|allValues: ALLOW"; then
            _bad "this organization restricts who can be granted access, so ACCESS_MODE=public will be refused"
            echo -e "        Everyone would get 403 on a deploy that otherwise reports success." >&2
            echo -e "        Set ACCESS_MODE=\"iap\" in config/instance.env." >&2
        else
            _ok "public access is permitted by org policy"
        fi
        ;;
      iap)
        # IAP cannot sign anyone in without an OAuth consent screen, and
        # creating one is a console action Terraform cannot perform.
        if gcloud iap oauth-brands list --project="$PROJECT_ID" --format='value(name)' 2>/dev/null </dev/null | grep -q .; then
            _ok "OAuth consent screen exists — IAP can sign users in"
        else
            _bad "no OAuth consent screen in this project; IAP has nothing to sign users in with"
            echo -e "        Create it once, here:" >&2
            echo -e "        https://console.cloud.google.com/apis/credentials/consent?project=${PROJECT_ID}" >&2
        fi
        ;;
      private)
        _ok "private — reach it with: gcloud run services proxy ${APP_SERVICE} --port=8080"
        ;;
    esac

    # --- secrets -----------------------------------------------------------
    local missing_secrets=""
    for s in "${INSTANCE}-dc-api-key" "${INSTANCE}-gemini-api-key"; do
        gcloud secrets describe "$s" --project="$PROJECT_ID" >/dev/null 2>&1 </dev/null || missing_secrets="${missing_secrets} ${s}"
    done
    if [ -z "$missing_secrets" ]; then
        _ok "API keys present in Secret Manager"
    else
        _warn "secrets not created yet:${missing_secrets}"
        echo -e "        DC_API_KEY=... GEMINI_API_KEY=... ./deploy.sh --bootstrap-secrets" >&2
    fi

    echo ""
    if [ "$fail" -ne 0 ]; then
        log_error "Preflight failed. Fix the items above before deploying."
        return 1
    fi
    if [ "$warn" -ne 0 ]; then
        log_warn "Preflight passed with warnings."
    else
        log_success "Preflight passed. Run ./deploy.sh to deploy."
    fi
    return 0
}

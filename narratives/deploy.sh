#!/usr/bin/env bash
# ===========================================================================
# CUSTOM DATA COMMONS - UNIFIED ONE-COMMAND DEPLOYER & UPDATE MANAGER
# ===========================================================================
set -euo pipefail

# Parse command line arguments
CODE_ONLY=false
INFRA_ONLY=false
PLAN_ONLY=false
FRONTEND_ONLY=false
AGENT_ONLY=false
CONFIG_ONLY=false
RESTART=false
BOOTSTRAP_SECRETS=false
PREFLIGHT=false
DESTROY=false

# One repository is one deployment. There is no --instance: the configuration
# is always config/instance.env, and a second deployment is a second clone.
args=("$@")
for i in "${!args[@]}"; do
    arg="${args[$i]}"
    case $arg in
        --instance|--instance=*)
            echo "--instance is gone: this repository is one deployment." >&2
            echo "  Its settings are in config/instance.env." >&2
            echo "  For another deployment, clone the repository again." >&2
            exit 1
            ;;
        --preflight)
            # Check everything and create nothing. Auth, ADC, billing, APIs,
            # IAM, the org policy that decides whether public access is even
            # allowed, the OAuth consent screen IAP needs, tool versions, and
            # whether config/instance.env is actually filled in.
            PREFLIGHT=true
            ;;
        --destroy)
            # Tear the deployment down. Clients get this wrong on their first
            # attempt and need a way back to nothing.
            DESTROY=true
            ;;
        --bootstrap-secrets)
            # Write the API keys from this process's environment into Secret
            # Manager, then exit. Run once per instance; no later deploy needs
            # a key.
            BOOTSTRAP_SECRETS=true
            ;;
        --code-only)
            CODE_ONLY=true
            ;;
        --plan)
            # Render everything, then show the Terraform diff and stop. Nothing
            # is applied and no image is built. The point is to read the plan
            # before an apply in a shared project -- particularly to confirm
            # every line says "will be created" and no existing instance's
            # resources appear, which would mean the state prefix did not take.
            PLAN_ONLY=true
            shift
            ;;
        --infra-only)
            INFRA_ONLY=true
            CODE_ONLY=true
            ;;
        --frontend-only)
            FRONTEND_ONLY=true
            CODE_ONLY=true
            ;;
        --agent-only)
            AGENT_ONLY=true
            CODE_ONLY=true
            ;;
        --config-only)
            # Fast path: push config/ (branding.json, agent-config.json,
            # prompts/, assets/) to the existing config bucket and
            # refresh the running service's branding cache. No image builds,
            # no terraform, no data ingestion.
            CONFIG_ONLY=true
            ;;
        --restart)
            # Used with --config-only: force a new Cloud Run revision so the
            # agent reloads agent-config.json and prompts (read only at
            # startup) -- including branding.json, which is NOT fetched live
            # despite what this comment used to say. Without --restart,
            # --config-only only updates the bucket.
            RESTART=true
            ;;
    esac
done

# Retrieve the running image from one of the two services. Each has a single
# container now, so this takes a service name rather than a container index --
# the index form silently returned the wrong image the moment the containers
# were separated.
get_active_image() {
    local service="$1"
    gcloud run services describe "$service" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --format="value(spec.template.spec.containers[0].image)" 2>/dev/null || echo ""
}

# The services image is the CDC data plane. On dcp it is Google's, on none there
# is no data plane at all, and terraform ignores the variable in both cases
# because the resource has count = 0 -- but it still has to be set to something.
reuse_or_placeholder_services_image() {
    if [ "$DATA_BACKEND" != "cdc" ]; then
        echo "unused-for-${DATA_BACKEND}-backend"
        return 0
    fi
    local image
    image=$(get_active_image "$DATA_SERVICE")
    if [ -z "$image" ]; then
        log_error "No active data-plane image on '${DATA_SERVICE}'. Run a full deployment first."
        return 1
    fi
    echo "$image"
}

# Color helper utilities
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0;37m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Early check for required CLI tools
for cmd in gcloud terraform python3; do
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required tool '$cmd' is not installed or not in PATH!"
        exit 1
    fi
done
if ! command -v pnpm &>/dev/null && ! command -v npm &>/dev/null; then
    log_error "Required tool 'pnpm' (or 'npm') is not installed or not in PATH!"
    exit 1
fi

# 1. Load this deployment's configuration
#
# One repository is one deployment, so the location is fixed. config/ holds what
# this deployment overrides; defaults/ holds the baseline it inherits.
INSTANCE_DIR="config"
ENV_FILE="config/instance.env"
if [ ! -f "$ENV_FILE" ]; then
    log_error "No configuration at '${ENV_FILE}'."
    echo "  This repository is one deployment and its settings live there." >&2
    echo "  If the file is missing, restore it from git:" >&2
    echo "    git checkout config/instance.env" >&2
    exit 1
fi

log_info "Loading configuration from $ENV_FILE..."
# `set -a; . file` rather than `export $(... | xargs)`: the old form split on
# whitespace, so any value containing a space was silently truncated and an
# inline comment became three bogus variables.
set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

# Secrets are deliberately NOT required here -- they live in Secret Manager,
# put there once by --bootstrap-secrets. This is what lets an instance.env be
# committed (to a private repo) and this repo be public.
# Nothing here has a default. Each of these decides where the data lives, what
# it costs, or who can reach it, and a default for any of them is a decision
# made on the operator's behalf that they would not see until the bill or the
# latency showed up. REGION in particular was defaulted before and should not be.
#
# Reported all at once rather than one per run: a client filling this in for the
# first time should get the whole list, not six consecutive failures.
REQUIRED_VARS=(PROJECT_ID REGION INSTANCE DATA_BACKEND ACCESS_MODE)
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
    value="${!var:-}"
    case "$value" in
        ""|YOUR_*|your-gcp-project|"<"*|"changeme"|"TODO") MISSING+=("$var") ;;
    esac
done

# Conditionally required, by the choices already made above.
if [ "${DATA_BACKEND:-}" = "dcp" ]; then
    [ -n "${DCP_SERVICE_URL:-}" ]  || MISSING+=("DCP_SERVICE_URL (required when DATA_BACKEND=dcp)")
    [ -n "${DCP_SERVICE_NAME:-}" ] || MISSING+=("DCP_SERVICE_NAME (required when DATA_BACKEND=dcp)")
fi
if [ "${DATA_BACKEND:-}" = "none" ]; then
    [ -n "${PUBLIC_DC_URL:-}" ]     || MISSING+=("PUBLIC_DC_URL (required when DATA_BACKEND=none — try https://api.datacommons.org)")
    [ -n "${PUBLIC_DC_WEB_URL:-}" ] || MISSING+=("PUBLIC_DC_WEB_URL (required when DATA_BACKEND=none — try https://datacommons.org)")
fi
if [ "${DATA_BACKEND:-}" = "cdc" ]; then
    [ -n "${CLOUDSQL_TIER:-}" ]              || MISSING+=("CLOUDSQL_TIER (required when DATA_BACKEND=cdc)")
    [ -n "${CLOUDSQL_AVAILABILITY_TYPE:-}" ] || MISSING+=("CLOUDSQL_AVAILABILITY_TYPE (required when DATA_BACKEND=cdc)")
fi
if [ "${ACCESS_MODE:-}" = "iap" ] || [ "${ACCESS_MODE:-}" = "private" ]; then
    [ -n "${AUTHORIZED_MEMBERS:-}" ] || MISSING+=("AUTHORIZED_MEMBERS (required when ACCESS_MODE=${ACCESS_MODE})")
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    log_error "${ENV_FILE} is incomplete."
    for m in "${MISSING[@]}"; do echo "    $m" >&2; done
    echo "" >&2
    echo "  Fill these in, then run: ./deploy.sh --preflight" >&2
    exit 1
fi

# Ensure DNS compatibility for instance label
if [[ ! "$INSTANCE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]]; then
    log_error "INSTANCE name '$INSTANCE' must be lowercase, alphanumeric, and DNS-safe."
    exit 1
fi

# Service names. Since the app plane was split out of the coupled service there
# are two: the data plane keeps the historical name, the app plane is the public
# one. Must match locals.data_service_name / locals.app_service_name in main.tf.
#
# Defined after instance.env is loaded -- INSTANCE does not exist before that, and
# under `set -u` referencing it earlier aborts the script.
# Both were required above, so they are set. Validate the values rather than
# defaulting them -- a typo should stop here, not produce a deployment that is
# subtly not the one the operator asked for.
case "$ACCESS_MODE" in
    public|iap|private) ;;
    *) log_error "ACCESS_MODE must be one of: public, iap, private (got '${ACCESS_MODE}')"; exit 1 ;;
esac

# CDC-only sizing, required above when the backend is cdc. Unused otherwise, but
# terraform still wants a value for the variable.
CLOUDSQL_TIER="${CLOUDSQL_TIER:-db-g1-small}"
CLOUDSQL_AVAILABILITY_TYPE="${CLOUDSQL_AVAILABILITY_TYPE:-REGIONAL}"

# What gets uploaded is defaults/ with config/ laid over the top.
#
# The alternative -- copying defaults/ into config/ once at setup -- is what the
# previous layout did, and it is why one prompt bug survived in four of five
# instance directories: a fix upstream never reached a copy. With an overlay a
# deployment carries only what it actually overrides, and everything else
# improves when the repository is updated.
#
# instance.env is excluded: it names the project and the people who can reach
# it, and must not land in a bucket that may be read more widely.
CONFIG_SRC=".build/config"
rm -rf "$CONFIG_SRC"
mkdir -p "$(dirname "$CONFIG_SRC")"
cp -R defaults "$CONFIG_SRC"
if [ -d config ]; then
    # `cp -R config/. dest` copies the contents, including dotfiles, without
    # nesting a second config/ inside.
    cp -R config/. "$CONFIG_SRC"/
    rm -f "${CONFIG_SRC}/instance.env"
fi

OVERRIDES=$(cd config && find . -type f ! -name instance.env | sed 's|^\./||' | tr '\n' ' ')
if [ -n "$OVERRIDES" ]; then
    log_info "Config overrides from config/: ${OVERRIDES}"
else
    log_info "No overrides in config/; using defaults/ as shipped."
fi

if [ ! -f "${CONFIG_SRC}/branding.json" ]; then
    log_error "No branding.json in defaults/ or config/."
    exit 1
fi

# Validate branding.json against its schema BEFORE it is synced to the config
# bucket. Presence was checked; shape was not, and the schema sets
# additionalProperties:false precisely so a typo'd key is an error rather than
# a silently ignored one -- a guarantee nothing was enforcing at deploy time.
#
# The failure this prevents is quiet. A file with `primary_color` instead of
# `colors.primary` deploys clean, the agent serves it, /agent/brand echoes the
# instance name so branding looks applied, and only the colour is missing --
# from a key that was never read. CI validates agent-config.json with ajv;
# branding had no equivalent anywhere.
#
# The validator uses jsonschema when it is installed and falls back to a
# stdlib walk of the unknown-key and required-key rules when it is not, so this
# always runs. An earlier version skipped with a warning when jsonschema was
# missing -- which is the case for the system python3 here, so it warned and
# uploaded the broken file anyway. A check that quietly does nothing on the
# machine you are standing at is worse than none; it reads like coverage.
if ! python3 deploy/validate-branding.py "${CONFIG_SRC}/branding.json"; then
    log_error "branding.json does not match schemas/branding.schema.json (see above)."
    echo "  Colour keys live under \"colors\": {\"primary\": \"#RRGGBB\", \"accent\": ...}." >&2
    echo "  Compare against schemas/branding.neutral.example.json." >&2
    exit 1
fi
log_success "branding.json validates against its schema."
DCP_SERVICE_URL="${DCP_SERVICE_URL:-}"
DCP_SERVICE_NAME="${DCP_SERVICE_NAME:-}"

case "$DATA_BACKEND" in
    dcp|cdc|none) ;;
    *) log_error "DATA_BACKEND must be one of: dcp, cdc, none (got '${DATA_BACKEND}')"; exit 1 ;;
esac

# Fail here rather than after a 15-minute apply: an app plane pointed at an
# empty URL answers "no data" to every question with nothing to indicate why.
if [ "$DATA_BACKEND" = "dcp" ] && { [ -z "$DCP_SERVICE_URL" ] || [ -z "$DCP_SERVICE_NAME" ]; }; then
    log_error "DATA_BACKEND=dcp needs DCP_SERVICE_URL and DCP_SERVICE_NAME in ${ENV_FILE}."
    echo "  Get them from the datacommons-cli scaffold:" >&2
    echo "    terraform output datacommons_service_url" >&2
    echo "    terraform output datacommons_service_name" >&2
    exit 1
fi
log_info "Data backend: ${DATA_BACKEND}"

DATA_SERVICE="${INSTANCE}-datacommons"
APP_SERVICE="${INSTANCE}-app"


# ===========================================================================
# --preflight : check everything, create nothing
# ===========================================================================
#
# The failure this prevents is the worst kind: a deploy that reports success and
# produces a service nobody can open. Most commonly because the organisation
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
    echo -e "\n=== Preflight: ${INSTANCE} (${DATA_BACKEND} backend, ${ACCESS_MODE} access) ===\n"

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
    if [ "${node_major:-0}" -ge 20 ]; then _ok "node ${node_major}"; else _bad "node ${node_major:-missing} — the UI build needs 20+"; fi

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
        # Domain Restricted Sharing forbids allUsers in many organisations. The
        # deploy still succeeds; the binding is simply refused, and the result
        # is a URL that returns 403 to everyone.
        local policy
        policy=$(gcloud resource-manager org-policies describe \
                   constraints/iam.allowedPolicyMemberDomains \
                   --effective --project="$PROJECT_ID" 2>/dev/null || true)
        if [ -n "$policy" ] && ! echo "$policy" | grep -qi "allowAll\|allValues: ALLOW"; then
            _bad "this organisation restricts who can be granted access, so ACCESS_MODE=public will be refused"
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
    for s in "${INSTANCE}-dc-api-key" "${INSTANCE}-gemini-api-keys"; do
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
    [ "$warn" -ne 0 ] && log_warn "Preflight passed with warnings." || log_success "Preflight passed. Run ./deploy.sh to deploy."
    return 0
}

# ===========================================================================
# --destroy : tear this deployment down
# ===========================================================================
#
# Clients get the configuration wrong on a first attempt and need a way back to
# nothing. Without this they delete resources by hand and leave state behind
# that makes the next deploy fail in a confusing way.
run_destroy() {
    STATE_BUCKET="${STATE_BUCKET:-${PROJECT_ID}-tfstate}"
    CONFIG_BUCKET="${CONFIG_BUCKET:-${PROJECT_ID}-${INSTANCE}-config}"
    echo -e "\n${RED}This destroys every resource for '${INSTANCE}' in ${PROJECT_ID}.${NC}"
    [ "$DATA_BACKEND" = "cdc" ] && echo -e "${RED}That includes the Cloud SQL instance and its data.${NC}"
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

if [ "$PREFLIGHT" = true ]; then
    run_preflight
    exit $?
fi

if [ "$DESTROY" = true ]; then
    run_destroy
    exit $?
fi

log_info "Configuring active gcloud project to '$PROJECT_ID'..."
gcloud config set project "$PROJECT_ID" --quiet

# --config-only: fast, deploy-free config/branding update against an existing
# instance. Syncs config/ to the bucket and nudges the agent to drop its
# branding cache, then exits — no images, terraform, secrets, or data.
if [ "$CONFIG_ONLY" = true ]; then
    CONFIG_BUCKET="${CONFIG_BUCKET:-${PROJECT_ID}-${INSTANCE}-config}"
    if ! gcloud storage buckets describe "gs://${CONFIG_BUCKET}" --project="$PROJECT_ID" &>/dev/null; then
        log_error "Config bucket 'gs://${CONFIG_BUCKET}' does not exist. Run a full deploy first."
        exit 1
    fi

    log_info "[Config-Only] Synchronizing config/ assets to GCS config bucket..."
    gcloud storage rsync "$CONFIG_SRC" "gs://${CONFIG_BUCKET}" --recursive --project="$PROJECT_ID" --exclude="instance\.env"
    log_success "Configuration assets synced."

    # --restart forces a new revision, which is the ONLY way a config change
    # reaches the running service.
    #
    # This block used to claim otherwise. It said branding.json "is fetched live
    # and does not require this", then GET /agent/brand?refresh=1 and reported
    # "Config changes are live (or will be within the cache TTL)". None of that
    # was true: brand.py has no `refresh` parameter and no TTL -- branding,
    # agent-config and prompts are all read once at startup and served
    # from process memory, exactly as the README documents. The request
    # returned 200 because it is an ordinary GET, and 200 was read as proof.
    #
    # So `--config-only` without `--restart` uploaded to the bucket and changed
    # nothing about the running service, while printing three lines saying it
    # had worked. It cost a real debugging detour: a corrected branding.json
    # sat in the bucket while the service kept serving the old colour.
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
fi

# 2. Enable Required APIs (Skipped in --code-only mode)
if [ "$CODE_ONLY" = false ]; then
    log_info "Enabling required Google Cloud APIs..."
    APIS=(
        run.googleapis.com
        sqladmin.googleapis.com
        secretmanager.googleapis.com
        cloudbuild.googleapis.com
        artifactregistry.googleapis.com
        storage.googleapis.com
        compute.googleapis.com
        apikeys.googleapis.com
        generativelanguage.googleapis.com
    )
    gcloud services enable "${APIS[@]}" --project="$PROJECT_ID"
    log_success "All required APIs enabled successfully."
else
    log_info "[Fast-Track] Skipping Google Cloud API enablement check."
fi

# 3. Bootstrap State Bucket & Artifact Registry (Skipped in --code-only mode)
STATE_BUCKET="${PROJECT_ID}-tfstate"
AR_REPO="custom-dc"
if [ "$CODE_ONLY" = false ]; then
    if ! gcloud storage buckets describe "gs://${STATE_BUCKET}" --project="$PROJECT_ID" &>/dev/null; then
        log_info "Creating Terraform state bucket 'gs://${STATE_BUCKET}'..."
        gcloud storage buckets create "gs://${STATE_BUCKET}" --project="$PROJECT_ID" --location="$REGION" --uniform-bucket-level-access
        gcloud storage buckets update "gs://${STATE_BUCKET}" --project="$PROJECT_ID" --versioning
        log_success "State bucket created."
    else
        log_info "Terraform state bucket 'gs://${STATE_BUCKET}' already exists."
    fi

    if ! gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
        log_info "Creating Artifact Registry repository '$AR_REPO' in '$REGION'..."
        gcloud artifacts repositories create "$AR_REPO" \
            --repository-format=docker \
            --location="$REGION" \
            --description="Docker repository for Custom Data Commons" \
            --project="$PROJECT_ID"
        log_success "Artifact Registry repository created."
    else
        log_info "Artifact Registry repository '$AR_REPO' already exists."
    fi
else
    log_info "[Fast-Track] Skipping GCS state bucket and Artifact Registry checks."
fi

# 4. Secret Manager Setup (Skipped in --code-only mode)
if [ "$CODE_ONLY" = false ]; then
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

    # Database password, CDC only: it is the Cloud SQL user's password, and
    # dcp and none have no database. Creating it regardless meant generating a
    # random password for a database that would never exist, and leaving a
    # secret behind that no later step or teardown accounts for.
    DB_PASS_SECRET="${INSTANCE}-db-pass"
    if [ "$DATA_BACKEND" = "cdc" ]; then
        create_secret_if_missing "$DB_PASS_SECRET"
        if ! gcloud secrets versions describe latest --secret="$DB_PASS_SECRET" --project="$PROJECT_ID" &>/dev/null; then
            log_info "Generating secure random database password..."
            RAND_PASS=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 || true)
            echo -n "$RAND_PASS" | gcloud secrets versions add "$DB_PASS_SECRET" --data-file=- --project="$PROJECT_ID" >/dev/null
        fi
    fi

    DC_SECRET="${INSTANCE}-dc-api-key"
    MAPS_SECRET="${INSTANCE}-maps-api-key"
    GEMINI_SECRET="${INSTANCE}-gemini-api-keys"

    # Values come from THIS PROCESS's environment, never from a file on disk,
    # and only during --bootstrap-secrets. A normal deploy verifies the secrets
    # exist and never handles a plaintext key at all.
    if [ "$BOOTSTRAP_SECRETS" = true ]; then
        secret_pairs=("DC_SECRET:DC_API_KEY" "GEMINI_SECRET:GEMINI_API_KEY")
        # MAPS_API_KEY is read by the CDC data-plane container and by nothing
        # else, so it is not created on the backends that have no such container.
        if [ "$DATA_BACKEND" = "cdc" ]; then
            secret_pairs+=("MAPS_SECRET:MAPS_API_KEY")
        elif [ -n "${MAPS_API_KEY:-}" ]; then
            # Supplying a key this backend does not consume used to be dropped in
            # silence, and the run still ended in "Secrets written". The key looks
            # stored; the backend is switched to cdc later; the deploy then fails
            # on a secret the operator is certain they wrote. Say so instead.
            log_warn "MAPS_API_KEY was supplied but DATA_BACKEND=\"${DATA_BACKEND}\" has no data-plane"
            log_warn "  container to read it. NOTHING was stored for '${MAPS_SECRET}'."
            log_warn "  Set DATA_BACKEND=\"cdc\" in config/instance.env first, then re-run this command."
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
            # chat answering "MCP server not connected" while /agent/health
            # reports zero tools -- which looks like a broken deployment rather
            # than a mistyped key, and sends you into the logs for an hour.
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
                # The agent expects a JSON array of keys, so this value has to
                # be encoded rather than pasted into brackets. Building it as
                # "[\"$value\"]" was wrong twice over:
                #
                #   * a key containing a quote or backslash produced invalid
                #     JSON, and
                #   * feeding back a value that was ALREADY a JSON array --
                #     which is what you get from `gcloud secrets versions
                #     access` on another instance, the obvious way to copy a
                #     key between stacks -- double-wrapped it into
                #     ["["AIza..."]"], which is not parseable at all.
                #
                # Both failed silently. Secret Manager stores any bytes, the
                # deploy reported success, and the break only appeared at
                # runtime as "No Gemini API keys configured in config.json"
                # while the env var and the secret both looked correctly wired.
                #
                # So: pass an existing array through unchanged, split a
                # comma-separated list into a pool, and encode with json.dumps.
                value=$(GEMINI_RAW="$value" python3 -c '
import json, os, sys
raw = os.environ["GEMINI_RAW"].strip()
try:
    parsed = json.loads(raw)
except ValueError:
    parsed = None
if isinstance(parsed, list) and parsed and all(isinstance(k, str) and k for k in parsed):
    keys = parsed                      # already encoded; idempotent
elif isinstance(parsed, str) and parsed:
    keys = [parsed]
else:
    keys = [k.strip() for k in raw.split(",") if k.strip()]
if not keys:
    sys.stderr.write("GEMINI_API_KEY held no usable key\n")
    sys.exit(1)
sys.stdout.write(json.dumps(keys))
') || { log_error "Could not encode GEMINI_API_KEY as a JSON array."; exit 1; }
                # Refuse to write something the agent cannot read back.
                echo -n "$value" | python3 -c '
import json, sys
keys = json.loads(sys.stdin.read())
assert isinstance(keys, list) and all(isinstance(k, str) for k in keys), keys
' || { log_error "Encoded GEMINI value is not a JSON array of strings. Refusing to write."; exit 1; }
                log_info "Gemini key pool: $(echo -n "$value" | python3 -c 'import json,sys; print(len(json.loads(sys.stdin.read())))') key(s)."

                # Same reasoning as DC_API_KEY: a rejected Gemini key produces a
                # deployment that starts, serves the UI, and fails only when
                # someone asks a question -- as "All N API keys failed", which
                # reads as a quota problem rather than a bad key.
                gem_base="https://generativelanguage.googleapis.com/v1beta/models"
                bad_keys=""
                while IFS= read -r k; do
                    [ -n "$k" ] || continue
                    gem_code=$(curl -s --max-time 25 -o /dev/null -w "%{http_code}" \
                        "${gem_base}?key=${k}&pageSize=1" || echo "000")
                    case "$gem_code" in
                        200) ;;
                        000) log_warn "Could not reach the Gemini API to check a key; storing it unverified." ;;
                        *)   bad_keys="${bad_keys} ${k:0:6}...(HTTP ${gem_code})" ;;
                    esac
                done <<EOF
$(echo -n "$value" | python3 -c 'import json,sys; print("\n".join(json.loads(sys.stdin.read())))')
EOF
                if [ -n "$bad_keys" ]; then
                    log_error "These Gemini keys were rejected:${bad_keys}. Nothing was written."
                    echo "  Check them at https://aistudio.google.com" >&2
                    case "$value" in
                        *%\"*|*%\]*) echo "  One ends in '%' -- that is zsh's end-of-line marker, copied by mistake." >&2 ;;
                    esac
                    exit 1
                fi
                log_success "Gemini key(s) accepted."
            fi
            add_secret_version_if_changed "$secret_id" "$value"
        done
        log_success "Secrets written to Secret Manager for instance '${INSTANCE}'."
        echo
        log_info "Nothing was written to disk. Deploy with: ./deploy.sh"
        exit 0
    fi

    # Normal deploy: the keys must already be in Secret Manager.
    required_pairs=("${DC_SECRET}:DC_API_KEY" "${GEMINI_SECRET}:GEMINI_API_KEY")
    if [ "$DATA_BACKEND" = "cdc" ]; then
        required_pairs+=("${MAPS_SECRET}:MAPS_API_KEY")
    fi
    # No else-branch. The Maps secret used to be created empty on every backend
    # because Terraform's data source read its metadata whether or not anything
    # consumed it. That data source is gated to cdc now, so on dcp and none the
    # secret is neither read nor needed.
    missing=()
    missing_vars=()
    for pair in "${required_pairs[@]}"; do
        secret_id="${pair%%:*}"; value_var="${pair##*:}"
        if ! gcloud secrets versions describe latest --secret="$secret_id" --project="$PROJECT_ID" &>/dev/null; then
            missing+=("$secret_id")
            missing_vars+=("${value_var}=...")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        log_error "These secrets have no value in Secret Manager: ${missing[*]}"
        echo "  Write them once (values are read from the environment, never stored on disk):" >&2
        # Naming the fixed DC/Gemini pair here regardless of what was missing sent
        # you to re-enter the two keys that were already stored, while the one
        # actually missing went unmentioned.
        echo "    ${missing_vars[*]} \\" >&2
        echo "      ./deploy.sh --bootstrap-secrets" >&2
        echo "  DATA_BACKEND is \"${DATA_BACKEND}\" right now, and --bootstrap-secrets only writes the" >&2
        echo "  secrets that backend reads. Set it in config/instance.env before running the above." >&2
        exit 1
    fi

    log_success "All secrets present in Secret Manager."
else
    log_info "[Fast-Track] Skipping Secret Manager checks."
fi

# 5. Build and Stage React UI Frontend
if [ "$INFRA_ONLY" = false ] && [ "$AGENT_ONLY" = false ]; then
    log_info "Compiling React UI production bundle and staging assets..."
    if command -v pnpm &>/dev/null; then
        pnpm install --frozen-lockfile
        pnpm build
    else
        log_warn "pnpm not found, falling back to npm..."
        cd ui
        npm install
        npm run build
        cd ..
        rm -rf agent/static
        cp -R ui/dist agent/static
    fi
    log_success "Frontend assets staged into agent/static."
else
    log_info "[Surgical-Build] Skipping React UI compilation."
fi

# 6. Build and Push Container Images via Cloud Build
IMAGE_TAG=$(git rev-parse --short HEAD 2>/dev/null || date +%s)
SERVICES_IMAGE=""
AGENT_IMAGE=""

if [ "$INFRA_ONLY" = true ]; then
    log_info "[Surgical-Build] Skipping all container builds. Retrieving active images from Cloud Run..."
    AGENT_IMAGE=$(get_active_image "$APP_SERVICE")
    if [ -z "$AGENT_IMAGE" ]; then
        log_error "Could not retrieve the active app-plane image from '${APP_SERVICE}'! Please run a full deployment first."
        exit 1
    fi
    # Only the CDC backend has a data service to read an image from. Demanding
    # one on dcp/none made --infra-only and --agent-only abort on stacks that
    # are working perfectly -- on those backends there is no data service to query,
    # so the lookup returned empty and this read it as "run a full deployment
    # first". The build path was already gated on the backend; the reuse path
    # was not.
    SERVICES_IMAGE=$(reuse_or_placeholder_services_image)
elif [ "$FRONTEND_ONLY" = true ] || [ "$AGENT_ONLY" = true ]; then
    # The SPA is baked into the app-plane image now, so a UI change and an
    # agent change rebuild the same thing. --frontend-only is kept as an alias
    # rather than removed, so existing runbooks and muscle memory keep working.
    log_info "[Surgical-Build] App-plane only. Building the agent + UI image..."
    AGENT_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent:${IMAGE_TAG}"
    gcloud builds submit --tag="$AGENT_IMAGE" --project="$PROJECT_ID" agent || { log_error "App-plane container build failed!"; exit 1; }

    SERVICES_IMAGE=$(reuse_or_placeholder_services_image)
else
    log_info "Submitting container builds to Google Cloud Build (Tag: $IMAGE_TAG)..."
    AGENT_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent:${IMAGE_TAG}"
    log_info "Starting background build for the app plane (agent + UI)..."
    gcloud builds submit --tag="$AGENT_IMAGE" --project="$PROJECT_ID" agent &
    AGENT_PID=$!

    # The services overlay is the CDC data plane. On DCP that image is Google's
    # and comes from datacommons-cli; on "none" there is no data plane at all.
    # Building it anyway would waste several minutes producing an image nothing
    # references, and terraform does not declare dc_web_service_image for those
    # backends.
    SERVICES_PID=""
    if [ "$DATA_BACKEND" = "cdc" ]; then
        SERVICES_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/services:${IMAGE_TAG}"
        log_info "Starting background build for the CDC data plane (services overlay)..."
        gcloud builds submit --tag="$SERVICES_IMAGE" --project="$PROJECT_ID" image &
        SERVICES_PID=$!
    else
        # Terraform still requires the variable to be set; it is unused when
        # data_backend is not "cdc" because the resource has count = 0.
        SERVICES_IMAGE="unused-for-${DATA_BACKEND}-backend"
        log_info "[${DATA_BACKEND}] Skipping the services overlay build -- this backend does not use it."
    fi

    log_info "Waiting for container builds to complete..."
    wait $AGENT_PID || { log_error "App-plane container build failed!"; exit 1; }
    [ -n "$SERVICES_PID" ] && { wait $SERVICES_PID || { log_error "Services container build failed!"; exit 1; }; }
fi

log_success "Resolved Container Images:"
echo "  Agent:    $AGENT_IMAGE"
echo "  Services: $SERVICES_IMAGE"

# 7. Create & Seed Configuration Bucket (Skipped in --code-only mode)
CONFIG_BUCKET="${CONFIG_BUCKET:-${PROJECT_ID}-${INSTANCE}-config}"
if [ "$CODE_ONLY" = false ]; then
    if ! gcloud storage buckets describe "gs://${CONFIG_BUCKET}" --project="$PROJECT_ID" &>/dev/null; then
        log_info "Creating GCS configuration bucket 'gs://${CONFIG_BUCKET}'..."
        gcloud storage buckets create "gs://${CONFIG_BUCKET}" --project="$PROJECT_ID" --location="$REGION" --uniform-bucket-level-access
        CORS_FILE=$(mktemp)
        echo '[{"origin": ["*"], "method": ["GET", "OPTIONS"], "responseHeader": ["Content-Type"], "maxAgeSeconds": 3600}]' > "$CORS_FILE"
        gcloud storage buckets update "gs://${CONFIG_BUCKET}" --cors-file="$CORS_FILE" --project="$PROJECT_ID"
        rm -f "$CORS_FILE"
        log_success "Config bucket created."
    else
        log_info "GCS configuration bucket 'gs://${CONFIG_BUCKET}' already exists."
    fi

    log_info "Synchronizing config/ assets to GCS config bucket..."
    gcloud storage rsync "$CONFIG_SRC" "gs://${CONFIG_BUCKET}" --recursive --project="$PROJECT_ID" --exclude="instance\.env"
    log_success "Configuration assets seeded successfully."
else
    log_info "[Fast-Track] Skipping config bucket synchronization."
fi

# 8. Generate tfvars configuration
TFVARS_FILE="deploy/terraform-custom-datacommons/${INSTANCE}.tfvars"
log_info "Generating Terraform variable overrides file: $TFVARS_FILE"

# Values travel through the environment rather than positional argv. The
# positional form shifted once already when an image argument was removed, and
# the output path silently became one of the values -- writing the tfvars to a
# file named after the AR repo, which then failed far from the cause. A named
# environment cannot be reordered.
TPL_SRC="deploy/terraform-custom-datacommons/new-instance.tfvars.sample" \
TPL_OUT="$TFVARS_FILE" \
V_PROJECT_ID="$PROJECT_ID" \
V_REGION="$REGION" \
V_INSTANCE="$INSTANCE" \
V_SERVICES_IMAGE="$SERVICES_IMAGE" \
V_AGENT_IMAGE="$AGENT_IMAGE" \
V_AR_REPO="$AR_REPO" \
V_IMAGE_TAG="$IMAGE_TAG" \
V_AUTHORIZED_MEMBERS="${AUTHORIZED_MEMBERS:-}" \
V_CONFIG_BUCKET="$CONFIG_BUCKET" \
V_DATA_BACKEND="$DATA_BACKEND" \
V_PUBLIC_DC_URL="${PUBLIC_DC_URL:-https://api.datacommons.org}" \
V_PUBLIC_DC_WEB_URL="${PUBLIC_DC_WEB_URL:-https://datacommons.org}" \
V_DCP_SERVICE_URL="$DCP_SERVICE_URL" \
V_DCP_SERVICE_NAME="$DCP_SERVICE_NAME" \
V_ACCESS_MODE="$ACCESS_MODE" \
V_CLOUDSQL_TIER="$CLOUDSQL_TIER" \
V_CLOUDSQL_AVAILABILITY="$CLOUDSQL_AVAILABILITY_TYPE" \
python3 - <<'PY'
import os, re, sys

content = open(os.environ["TPL_SRC"]).read()
replacements = {
    "REPLACE_PROJECT_ID":     os.environ["V_PROJECT_ID"],
    "REPLACE_REGION":         os.environ["V_REGION"],
    "REPLACE_INSTANCE":       os.environ["V_INSTANCE"],
    "REPLACE_SERVICES_IMAGE": os.environ["V_SERVICES_IMAGE"],
    "REPLACE_AGENT_IMAGE":    os.environ["V_AGENT_IMAGE"],
    "REPLACE_AR_REPO":        os.environ["V_AR_REPO"],
    "REPLACE_IMAGE_TAG":      os.environ["V_IMAGE_TAG"],
    # Comma-separated in, HCL list out. Empty is legitimate -- public mode
    # grants allUsers and names nobody -- and must render as [] rather than
    # crash, which is what the bash array it replaced did.
    "REPLACE_AUTHORIZED_MEMBERS": ", ".join(
        '"%s"' % m.strip()
        for m in os.environ["V_AUTHORIZED_MEMBERS"].split(",")
        if m.strip()
    ),
    "REPLACE_CONFIG_BUCKET":  os.environ["V_CONFIG_BUCKET"],
    "REPLACE_DATA_BACKEND":   os.environ["V_DATA_BACKEND"],
    "REPLACE_PUBLIC_DC_URL":     os.environ["V_PUBLIC_DC_URL"],
    "REPLACE_PUBLIC_DC_WEB_URL": os.environ["V_PUBLIC_DC_WEB_URL"],
    "REPLACE_DCP_SERVICE_URL":  os.environ["V_DCP_SERVICE_URL"],
    "REPLACE_DCP_SERVICE_NAME": os.environ["V_DCP_SERVICE_NAME"],
    "REPLACE_ACCESS_MODE":     os.environ["V_ACCESS_MODE"],
    "REPLACE_CLOUDSQL_TIER":         os.environ["V_CLOUDSQL_TIER"],
    "REPLACE_CLOUDSQL_AVAILABILITY": os.environ["V_CLOUDSQL_AVAILABILITY"],
    "REPLACE_OUTPUT_DIR":     "",
    "REPLACE_INPUT_DIR":      "",
}
for k, v in replacements.items():
    content = content.replace(k, v)

# Fail loudly rather than writing a file with an unsubstituted token in it:
# terraform reports that as a syntax or type error a long way from the cause.
leftover = sorted(set(re.findall(r"REPLACE_[A-Z_]+", content)))
if leftover:
    sys.exit(f"tfvars template has unwired tokens: {leftover}")

open(os.environ["TPL_OUT"], "w").write(content)
PY


log_success "tfvars file generated cleanly."

# 9. Run Terraform Pipeline
cd deploy/terraform-custom-datacommons/modules

# Every instance shares this one module directory, and each deploy points it at
# that instance's state with `init -reconfigure`. The backend pointer lives in
# .terraform/ INSIDE that shared directory, so two instances operating at the
# same time race on it: whichever init runs last wins, and the other's next
# apply silently reads and writes the wrong state.
#
# That is not hypothetical. Running `--plan` for one instance while another
# instance's apply was in flight repointed the shared directory mid-run, and
# the second apply wrote its resources into the first's state prefix --
# replacing all 17 tracked resources. Both stacks kept running; only the
# bookkeeping was destroyed, which is the kind of damage nobody notices until a
# later apply proposes to delete a live service.
#
# TF_DATA_DIR moves that per-instance, so the directory is shared but the
# backend pointer is not. Concurrent instance operations stop interfering.
export TF_DATA_DIR=".terraform-${INSTANCE}"

log_info "Initializing Terraform backend (TF_DATA_DIR=${TF_DATA_DIR})..."
terraform init \
    -backend-config="bucket=${STATE_BUCKET}" \
    -backend-config="prefix=custom-datacommons/${INSTANCE}" \
    -reconfigure

# Second line of defence. TF_DATA_DIR should make it impossible to load another
# instance's state, but if it ever happens again the consequence is severe and
# silent: Terraform does not see a mistake, it sees resources whose names no
# longer match the configuration, and replacing those is its job. It will delete
# a live stack without a warning -- which is exactly what happened once here.
#
# So before anything is applied, refuse to proceed if the loaded state names a
# different known instance. Costs one `terraform show` and turns a destroyed
# stack into a failed deploy.
# There is no instances/ directory to enumerate now, but the hazard is
# unchanged: two clones of this repository pointed at one project, or an
# INSTANCE renamed after a deploy. Either loads state describing resources named
# for a different deployment, and applying would rename them -- which Terraform
# does by destroying and recreating.
if ! terraform show -json 2>/dev/null \
    | python3 ../../../deploy/check-state-owner.py "$INSTANCE"; then
    log_error "Refusing to apply: the state loaded describes a different deployment, not '${INSTANCE}'."
    echo "  Applying would rename -- that is, DESTROY AND RECREATE -- those resources." >&2
    echo "  Check the backend prefix (custom-datacommons/${INSTANCE}), and whether" >&2
    echo "  INSTANCE in config/instance.env was changed after a previous deploy." >&2
    exit 1
fi
log_success "State ownership verified for '${INSTANCE}'."

# The staged data-plane apply and the ingest Job are CDC-only. On dcp the data
# plane is Google's and provisioned by datacommons-cli; on none there is no data
# plane at all, so the targets below resolve to count=0 resources and the data
# bucket the ingest step writes to does not exist.
#
# The staged apply exists so Cloud Run is not started against a database that is
# still being created. With no database, there is nothing to stage around.
if [ "$CODE_ONLY" = false ] && [ "$PLAN_ONLY" = false ] && [ "$DATA_BACKEND" = "cdc" ]; then
    log_info "Provisioning data-plane infrastructure resources..."
    terraform apply -auto-approve \
        -var-file="../${INSTANCE}.tfvars" \
        -target=google_sql_database_instance.dc \
        -target=google_sql_database.dc \
        -target=google_sql_user.dc \
        -target=google_storage_bucket.data \
        -target=google_service_account.datacommons \
        -target=google_project_iam_member.secret_accessor \
        -target=google_project_iam_member.cloudsql_client \
        -target=google_project_iam_member.log_writer \
        -target=google_project_iam_member.metric_writer \
        -target=google_project_iam_member.trace_agent \
        -target=google_storage_bucket_iam_member.config_reader \
        -target=google_storage_bucket_iam_member.data_reader \
        -target=google_cloud_run_v2_job.data_ingest

    # Stage data and execute ingest job
    DATA_BUCKET="${INSTANCE}-data-${PROJECT_ID}"
    log_info "Staging sample dataset CSV files to GCS data bucket 'gs://${DATA_BUCKET}/input/'..."
    gcloud storage cp -r ../../../sample-data/* "gs://${DATA_BUCKET}/input/" --project="$PROJECT_ID"

    log_info "Triggering data-plane SQL database ingestion job..."
    gcloud run jobs execute "${INSTANCE}-data-ingest" \
        --region="$REGION" --project="$PROJECT_ID" --wait
elif [ "$CODE_ONLY" = false ]; then
    log_info "[${DATA_BACKEND}] No data plane to provision here -- skipping the staged apply and the ingest job."
else
    log_info "[Fast-Track] Skipping data-plane provisioning and database ingestion."
fi

if [ "$PLAN_ONLY" = true ]; then
    log_info "[--plan] Showing the Terraform plan. Nothing will be applied."
    # Without this check a plan that fails -- an unresolvable data source, a
    # tripped precondition -- still prints "Plan complete", which is exactly
    # the false all-clear this flag exists to prevent.
    if ! terraform plan -var-file="../${INSTANCE}.tfvars"; then
        cd ../../..
        log_error "Plan FAILED for instance '${INSTANCE}'. Do not apply until this is resolved."
        exit 1
    fi
    cd ../../..
    log_success "Plan complete for instance '${INSTANCE}'. Nothing was applied."
    exit 0
fi

# Deploy services (Updates Cloud Run to point to new image tags)
log_info "Provisioning and updating service container configurations..."
terraform apply -auto-approve -var-file="../${INSTANCE}.tfvars"

# Retrieve final service endpoint URL
SERVICE_URL=$(terraform output -raw service_url)
cd ../../..

# 10. Run Verification Smoke Tests
if [ "$CODE_ONLY" = false ]; then
    # Only CDC cold-starts a data plane of its own. On dcp the plane is Google's
    # and already running, and on none it is api.datacommons.org, so both answer
    # the first capability probe. A fresh CDC Mixer took ~60s to serve its first
    # MCP response, which is why the smoke tests have to be given room here
    # rather than reporting a healthy deploy as four failures.
    if [ "$DATA_BACKEND" = "cdc" ]; then SMOKE_WARMUP=180; else SMOKE_WARMUP=60; fi

    # The IAP toggle around the smoke tests made sense when every instance was
    # IAP-fronted. It must not run for ACCESS_MODE=public: the final step
    # switches IAP ON, which puts a sign-in wall in front of a service that is
    # meant to be open and answers every request with a 302 and
    # "Invalid IAP credentials: empty token".
    #
    # Briefly removing the sign-in requirement mid-deploy is also exactly the
    # wrong thing to do on the environments that do use IAP, so this whole
    # dance is worth retiring once smoke.sh can present a token.
    if [ "$ACCESS_MODE" = "public" ]; then
        log_info "Running post-deployment smoke tests (public access; no IAP toggle needed)..."
        SMOKE_WARMUP_SECS="$SMOKE_WARMUP" bash docs/smoke.sh "$SERVICE_URL" || log_warn "Smoke tests encountered failures."
    else
        log_info "Temporarily disabling Identity-Aware Proxy (IAP) for validation..."
        gcloud beta run services update "${APP_SERVICE}" \
            --no-iap --region="$REGION" --project="$PROJECT_ID"

        log_info "Running automated post-deployment smoke tests..."
        SMOKE_WARMUP_SECS="$SMOKE_WARMUP" bash docs/smoke.sh "$SERVICE_URL" || log_warn "Smoke tests encountered failures."

        log_info "Re-enabling Identity-Aware Proxy (IAP) on Cloud Run service..."
        gcloud beta run services update "${APP_SERVICE}" \
            --iap --region="$REGION" --project="$PROJECT_ID"
    fi
else
    log_info "[Fast-Track] Skipping IAP toggles and smoke tests."
fi

echo -e "\n==========================================================================="
log_success "CONGRATULATIONS! CUSTOM DATA COMMONS UPDATED SUCCESSFULLY!"
echo -e "==========================================================================="
echo -e "Instance Display Name:  ${INSTANCE} Data Commons"
echo -e "Service Web Endpoint:   ${GREEN}${SERVICE_URL}${NC}"
case "$ACCESS_MODE" in
    public)  echo -e "Access:                 ${YELLOW}PUBLIC${NC} — anyone with the URL, and every request spends Gemini quota" ;;
    iap)     echo -e "Access:                 IAP — Google sign-in required" ;;
    private) echo -e "Access:                 PRIVATE — no public route; use \`gcloud run services proxy ${APP_SERVICE} --port=8080\`" ;;
esac
if [ -n "${AUTHORIZED_MEMBERS:-}" ]; then
    echo -e "Authorized:"
    # Guarded: on bash 3.2, which macOS ships, expanding an empty array under
    # `set -u` is an unbound-variable error rather than an empty expansion.
    IFS=',' read -ra ADDR <<< "$AUTHORIZED_MEMBERS"
    for member in "${ADDR[@]}"; do
        echo -e "  - ${member}"
    done
fi
if [ "$ACCESS_MODE" = "iap" ]; then
    echo -e ""
    echo -e "${YELLOW}One manual step remains if this project has no OAuth consent screen:${NC}"
    echo -e "  https://console.cloud.google.com/apis/credentials/consent?project=${PROJECT_ID}"
    echo -e "  Until it exists, IAP cannot sign anyone in and the service stays unreachable."
fi
echo -e "===========================================================================\n"

#!/usr/bin/env bash
# ===========================================================================
# Custom Data Commons — deploy and update one instance.
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
            # Check everything, create nothing: auth, ADC, billing, the org
            # policy gating public access, IAP's consent screen, tool versions.
            PREFLIGHT=true
            ;;
        --destroy)
            # Tear the deployment down, back to an empty project.
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
            # Show the Terraform diff and stop. In a shared project, check
            # no other instance's resources appear in it.
            PLAN_ONLY=true
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
            # Fast path: push config/ to the bucket. No builds, no terraform.
            # Needs --restart to reach the running service.
            CONFIG_ONLY=true
            ;;
        --restart)
            # Used with --config-only: force a new revision. The agent reads
            # branding, agent-config and prompts once at startup, so without
            # this the bucket changes and the running service does not.
            RESTART=true
            ;;
    esac
done

# Takes a service name, not a container index, which returns the wrong image
# as soon as a service has more than one container.
get_active_image() {
    local service="$1"
    gcloud run services describe "$service" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --format="value(spec.template.spec.containers[0].image)" 2>/dev/null || echo ""
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

# The four modes that are not the deploy path -- preflight, destroy,
# config-only and bootstrap-secrets -- live in deploy/modes/. Sourcing only
# defines their functions; each still runs from the same loaded instance.env.
DEPLOY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for _mode in preflight destroy config-sync bootstrap-secrets; do
    # shellcheck source=/dev/null
    . "${DEPLOY_ROOT}/deploy/modes/${_mode}.sh"
done
unset _mode

# Early check for required CLI tools
for cmd in gcloud terraform npm python3 curl; do
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required tool '$cmd' is not installed or not in PATH!"
        exit 1
    fi
done

# 1. Load this deployment's configuration. One repo is one deployment, so the
# location is fixed. config/ overrides; defaults/ is the baseline.
ENV_FILE="config/instance.env"
if [ ! -f "$ENV_FILE" ]; then
    log_error "No configuration at '${ENV_FILE}'."
    echo "  This repository is one deployment and its settings live there." >&2
    echo "  If the file is missing, restore it from git:" >&2
    echo "    git checkout config/instance.env" >&2
    exit 1
fi

log_info "Loading configuration from $ENV_FILE..."
# `set -a; . file`, not `export $(... | xargs)`, which splits on whitespace
# and truncates any value containing a space.
set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

# Secrets are NOT required here: they live in Secret Manager, written once by
# --bootstrap-secrets, which is what lets this repository stay public.
#
# Nothing below has a default: each decides where data lives, what it costs or
# who can reach it. Reported all at once, so a first setup gets the whole list.
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

# Validate rather than default, so a typo stops here rather than deploying
# something subtly different from what was asked for.
case "$ACCESS_MODE" in
    public|iap|private) ;;
    *) log_error "ACCESS_MODE must be one of: public, iap, private (got '${ACCESS_MODE}')"; exit 1 ;;
esac

# Upload defaults/ with config/ laid over the top, so a deployment carries only
# what it overrides and everything else improves when this repo is updated.
# instance.env is excluded: it names the project and who can reach it.
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

# Validate branding.json before it reaches the bucket. The schema sets
# additionalProperties:false, so a misspelled key is an error here rather than
# a deploy that looks clean and silently drops the setting.
#
# validate-branding.py falls back to a stdlib walk when jsonschema is missing,
# as it is on the system python3. It must never skip.
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
    dcp|none) ;;
    cdc) log_error "DATA_BACKEND=cdc is no longer supported. The self-hosted Cloud SQL plane, its ingest job and its services image were removed; destroy any instance still on it with the last revision that declared them."; exit 1 ;;
    *) log_error "DATA_BACKEND must be one of: dcp, none (got '${DATA_BACKEND}')"; exit 1 ;;
esac

# Fail here rather than after a 15-minute apply: an app plane pointed at an
# empty URL answers "no data" to everything, with nothing to indicate why.
if [ "$DATA_BACKEND" = "dcp" ] && { [ -z "$DCP_SERVICE_URL" ] || [ -z "$DCP_SERVICE_NAME" ]; }; then
    log_error "DATA_BACKEND=dcp needs DCP_SERVICE_URL and DCP_SERVICE_NAME in ${ENV_FILE}."
    echo "  Get them from the datacommons-cli scaffold:" >&2
    echo "    terraform output datacommons_service_url" >&2
    echo "    terraform output datacommons_service_name" >&2
    exit 1
fi
log_info "Data backend: ${DATA_BACKEND}"

# Must match locals.app_service_name in main.tf. Defined after instance.env
# loads, because INSTANCE does not exist before that and `set -u` would abort.
APP_SERVICE="${INSTANCE}-app"

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

if [ "$CONFIG_ONLY" = true ]; then
    run_config_sync   # syncs config/, optionally restarts, then exits
fi

# 2. Enable Required APIs (Skipped in --code-only mode)
if [ "$CODE_ONLY" = false ]; then
    log_info "Enabling required Google Cloud APIs..."
    APIS=(
        run.googleapis.com
        secretmanager.googleapis.com
        cloudbuild.googleapis.com
        artifactregistry.googleapis.com
        storage.googleapis.com
        compute.googleapis.com
        monitoring.googleapis.com
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
    DC_SECRET="${INSTANCE}-dc-api-key"
    GEMINI_SECRET="${INSTANCE}-gemini-api-keys"

    if [ "$BOOTSTRAP_SECRETS" = true ]; then
        run_bootstrap_secrets   # writes the keys and exits
    fi

    # Normal deploy: the keys must already be in Secret Manager.
    required_pairs=("${DC_SECRET}:DC_API_KEY" "${GEMINI_SECRET}:GEMINI_API_KEY")
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
        # Name the keys actually missing, not the fixed pair.
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
    log_info "Compiling React UI production bundle..."
    cd ui
    npm ci --registry=https://registry.npmjs.org/
    npm run build
    cd ..

    # Staged into the agent build context: the SPA ships in the app-plane image.
    log_info "Staging compiled static assets into the app-plane build context..."
    rm -rf agent/static
    cp -R ui/dist agent/static
    log_success "Frontend assets staged into agent/static."
else
    log_info "[Surgical-Build] Skipping React UI compilation."
fi

# 6. Build and Push Container Images via Cloud Build
IMAGE_TAG=$(git rev-parse --short HEAD 2>/dev/null || date +%s)
AGENT_IMAGE=""

if [ "$INFRA_ONLY" = true ]; then
    log_info "[Surgical-Build] Skipping all container builds. Retrieving active images from Cloud Run..."
    AGENT_IMAGE=$(get_active_image "$APP_SERVICE")
    if [ -z "$AGENT_IMAGE" ]; then
        log_error "Could not retrieve the active app-plane image from '${APP_SERVICE}'! Please run a full deployment first."
        exit 1
    fi
elif [ "$FRONTEND_ONLY" = true ] || [ "$AGENT_ONLY" = true ]; then
    # Both flags build the same image; they differ earlier. --agent-only reuses
    # agent/static, --frontend-only rebuilds the SPA first.
    log_info "[Surgical-Build] App-plane only. Building the agent + UI image..."
    AGENT_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent:${IMAGE_TAG}"
    gcloud builds submit --tag="$AGENT_IMAGE" --project="$PROJECT_ID" agent || { log_error "App-plane container build failed!"; exit 1; }
else
    log_info "Submitting container builds to Google Cloud Build (Tag: $IMAGE_TAG)..."
    AGENT_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent:${IMAGE_TAG}"
    log_info "Starting background build for the app plane (agent + UI)..."
    gcloud builds submit --tag="$AGENT_IMAGE" --project="$PROJECT_ID" agent &
    AGENT_PID=$!

    log_info "Waiting for the container build to complete..."
    wait $AGENT_PID || { log_error "App-plane container build failed!"; exit 1; }
fi

log_success "Resolved Container Image:"
echo "  Agent: $AGENT_IMAGE"

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

# Values travel through the environment, not positional argv, which cannot be
# silently reordered when an argument is added or removed.
TPL_SRC="deploy/terraform-custom-datacommons/new-instance.tfvars.sample" \
TPL_OUT="$TFVARS_FILE" \
V_PROJECT_ID="$PROJECT_ID" \
V_REGION="$REGION" \
V_INSTANCE="$INSTANCE" \
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
python3 - <<'PY'
import os, re, sys

content = open(os.environ["TPL_SRC"]).read()
replacements = {
    "REPLACE_PROJECT_ID":     os.environ["V_PROJECT_ID"],
    "REPLACE_REGION":         os.environ["V_REGION"],
    "REPLACE_INSTANCE":       os.environ["V_INSTANCE"],
    "REPLACE_AGENT_IMAGE":    os.environ["V_AGENT_IMAGE"],
    "REPLACE_AR_REPO":        os.environ["V_AR_REPO"],
    "REPLACE_IMAGE_TAG":      os.environ["V_IMAGE_TAG"],
    # Comma-separated in, HCL list out. Empty is legitimate -- public mode
    # names nobody -- and must render as [].
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

# Every instance shares this module directory and points it at its own state
# with `init -reconfigure`. The backend pointer lives in .terraform/ inside that
# shared directory, so two instances deploying at once race on it and the loser
# applies against the wrong state. TF_DATA_DIR makes the pointer per-instance.
export TF_DATA_DIR=".terraform-${INSTANCE}"

log_info "Initializing Terraform backend (TF_DATA_DIR=${TF_DATA_DIR})..."
terraform init \
    -backend-config="bucket=${STATE_BUCKET}" \
    -backend-config="prefix=custom-datacommons/${INSTANCE}" \
    -reconfigure

# Second line of defence. Terraform cannot tell wrong state from a rename, so
# it would destroy and recreate a live stack without comment. Refuse to apply
# when the state names a different deployment -- two clones sharing a project,
# or an INSTANCE renamed after a deploy, both land here.
if ! terraform show -json 2>/dev/null \
    | python3 ../../../deploy/check-state-owner.py "$INSTANCE"; then
    log_error "Refusing to apply: the state loaded describes a different deployment, not '${INSTANCE}'."
    echo "  Applying would rename -- that is, DESTROY AND RECREATE -- those resources." >&2
    echo "  Check the backend prefix (custom-datacommons/${INSTANCE}), and whether" >&2
    echo "  INSTANCE in config/instance.env was changed after a previous deploy." >&2
    exit 1
fi
log_success "State ownership verified for '${INSTANCE}'."

if [ "$PLAN_ONLY" = true ]; then
    log_info "[--plan] Showing the Terraform plan. Nothing will be applied."
    # Without this a failed plan still prints "Plan complete".
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
    # Both backends answer the first probe promptly: a dcp plane is already
    # running, and "none" is api.datacommons.org.
    SMOKE_WARMUP=60

    # Skipped when ACCESS_MODE=public: the last step switches IAP on, which
    # would wall off a service meant to be open. Retire this whole toggle once
    # smoke.sh can present its own token.
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
    # `set -u` is an error rather than an empty expansion.
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

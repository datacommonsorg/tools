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
            # no terraform.
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

# Retrieve the running image from a Cloud Run service. It has a single
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

# The modes other than a deploy live in deploy/modes/. Sourcing them only
# defines their functions.
DEPLOY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
for mode in preflight destroy config-sync bootstrap-secrets; do
    # shellcheck source=/dev/null
    . "${DEPLOY_ROOT}/deploy/modes/${mode}.sh"
done

# Early check for required CLI tools
for cmd in gcloud terraform pnpm python3; do
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required tool '$cmd' is not installed or not in PATH!"
        exit 1
    fi
done

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

# An instance.env from before the backends were removed may still choose one.
# Deploying it from here would quietly repoint that instance at public data.
if [ -n "${DATA_BACKEND:-}" ] && [ "${DATA_BACKEND}" != "none" ] \
    || [ -n "${DCP_SERVICE_URL:-}" ]; then
    log_error "${ENV_FILE} selects a private data plane (DATA_BACKEND=${DATA_BACKEND:-unset})."
    echo "  Only public Data Commons is supported. Remove DATA_BACKEND and DCP_SERVICE_*," >&2
    echo "  or manage this instance with the last revision that had its backend." >&2
    exit 1
fi

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
REQUIRED_VARS=(PROJECT_ID REGION INSTANCE ACCESS_MODE)
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
    value="${!var:-}"
    case "$value" in
        ""|YOUR_*|your-gcp-project|"<"*|"changeme"|"TODO") MISSING+=("$var") ;;
    esac
done

# Conditionally required, by the choices already made above.
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

# Both were required above, so they are set. Validate the values rather than
# defaulting them -- a typo should stop here, not produce a deployment that is
# subtly not the one the operator asked for.
case "$ACCESS_MODE" in
    public|iap|private) ;;
    *) log_error "ACCESS_MODE must be one of: public, iap, private (got '${ACCESS_MODE}')"; exit 1 ;;
esac

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
# instance name so branding looks applied, and only the color is missing --
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
    echo "  Color keys live under \"colors\": {\"primary\": \"#RRGGBB\", \"accent\": ...}." >&2
    echo "  Compare against schemas/branding.neutral.example.json." >&2
    exit 1
fi
log_success "branding.json validates against its schema."

# Must match locals.app_service_name in main.tf. Defined after instance.env is
# loaded -- INSTANCE does not exist before that, and under `set -u` referencing
# it earlier aborts the script.
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
    run_config_sync
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
    DC_SECRET="${INSTANCE}-dc-api-key"
    GEMINI_SECRET="${INSTANCE}-gemini-api-key"

    # Values come from THIS PROCESS's environment, never from a file on disk,
    # and only during --bootstrap-secrets. A normal deploy verifies the secrets
    # exist and never handles a plaintext key at all.
    if [ "$BOOTSTRAP_SECRETS" = true ]; then
        run_bootstrap_secrets
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
        # Naming the fixed DC/Gemini pair here regardless of what was missing sent
        # you to re-enter the two keys that were already stored, while the one
        # actually missing went unmentioned.
        echo "    ${missing_vars[*]} \\" >&2
        echo "      ./deploy.sh --bootstrap-secrets" >&2
        exit 1
    fi

    log_success "All secrets present in Secret Manager."
else
    log_info "[Fast-Track] Skipping Secret Manager checks."
fi

# 5. Build and Stage React UI Frontend
if [ "$INFRA_ONLY" = false ] && [ "$AGENT_ONLY" = false ]; then
    log_info "Compiling React UI production bundle and staging assets..."
    pnpm install --frozen-lockfile
    pnpm build
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
    # The SPA is baked into the app-plane image now, so a UI change and an
    # agent change rebuild the same thing. --frontend-only is kept as an alias
    # rather than removed, so existing runbooks and muscle memory keep working.
    log_info "[Surgical-Build] App-plane only. Building the agent + UI image..."
    AGENT_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent:${IMAGE_TAG}"
    gcloud builds submit --tag="$AGENT_IMAGE" --project="$PROJECT_ID" agent || { log_error "App-plane container build failed!"; exit 1; }
else
    log_info "Submitting container builds to Google Cloud Build (Tag: $IMAGE_TAG)..."
    AGENT_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent:${IMAGE_TAG}"
    log_info "Starting background build for the app plane (agent + UI)..."
    gcloud builds submit --tag="$AGENT_IMAGE" --project="$PROJECT_ID" agent &
    AGENT_PID=$!

    log_info "Waiting for container builds to complete..."
    wait $AGENT_PID || { log_error "App-plane container build failed!"; exit 1; }
fi

log_success "Resolved Container Images:"
echo "  Agent:    $AGENT_IMAGE"

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
V_AGENT_IMAGE="$AGENT_IMAGE" \
V_AR_REPO="$AR_REPO" \
V_IMAGE_TAG="$IMAGE_TAG" \
V_AUTHORIZED_MEMBERS="${AUTHORIZED_MEMBERS:-}" \
V_CONFIG_BUCKET="$CONFIG_BUCKET" \
V_PUBLIC_DC_URL="${PUBLIC_DC_URL:-https://api.datacommons.org}" \
V_PUBLIC_DC_WEB_URL="${PUBLIC_DC_WEB_URL:-https://datacommons.org}" \
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
    # grants allUsers and names nobody -- and must render as [] rather than
    # crash, which is what the bash array it replaced did.
    "REPLACE_AUTHORIZED_MEMBERS": ", ".join(
        '"%s"' % m.strip()
        for m in os.environ["V_AUTHORIZED_MEMBERS"].split(",")
        if m.strip()
    ),
    "REPLACE_CONFIG_BUCKET":  os.environ["V_CONFIG_BUCKET"],
    "REPLACE_PUBLIC_DC_URL":     os.environ["V_PUBLIC_DC_URL"],
    "REPLACE_PUBLIC_DC_WEB_URL": os.environ["V_PUBLIC_DC_WEB_URL"],
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

# Second line of defense. TF_DATA_DIR should make it impossible to load another
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
    SMOKE_WARMUP=60

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

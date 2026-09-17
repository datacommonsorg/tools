#!/usr/bin/env bash
# ===========================================================================
# --bootstrap-secrets : write the API keys into Secret Manager, then exit
# ===========================================================================
#
# Sourced by deploy.sh, which has already loaded config/instance.env, validated
# it, and defined the log_* helpers and colours this uses. Not runnable alone.


    # Values come from THIS PROCESS's environment, never from a file on disk,
    # and only during --bootstrap-secrets. A normal deploy verifies the secrets
    # exist and never handles a plaintext key at all.
run_bootstrap_secrets() {
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

        secret_pairs=("DC_SECRET:DC_API_KEY" "GEMINI_SECRET:GEMINI_API_KEY")
        if [ -n "${MAPS_API_KEY:-}" ]; then
            # Nothing reads a Maps key any more: it was consumed by the CDC
            # data-plane container, and that backend is gone. Supplying one used
            # to be dropped in silence while the run still reported success, so
            # say plainly that it is not stored rather than letting an operator
            # believe it is.
            log_warn "MAPS_API_KEY was supplied but no backend reads it since the cdc plane was removed."
            log_warn "  NOTHING was stored. Drop it from your command."
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
}

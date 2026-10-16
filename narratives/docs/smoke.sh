#!/usr/bin/env bash
# Post-deploy smoke test for a unified-architecture app plane.
#
# Usage:
#   bash docs/smoke.sh https://<instance>-app-<hash>-<region>.a.run.app
#
# Set BEARER_TOKEN for an IAM/IAP-gated stack:
#   BEARER_TOKEN=$(gcloud auth print-identity-token) bash docs/smoke.sh "$URL"
#
# Final line is "SMOKE: PASS" or "SMOKE: FAIL".

set -uo pipefail

URL="${1:-}"
if [ -z "$URL" ]; then
    echo "Usage: $0 <service-url>" >&2
    exit 2
fi
URL="${URL%/}"

PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl_cmd() {
    if [ -n "${BEARER_TOKEN:-}" ]; then
        curl -H "Authorization: Bearer ${BEARER_TOKEN}" "$@"
    else
        curl "$@"
    fi
}

check() {
    local label="$1"; shift
    local detail
    if detail=$("$@" 2>&1); then
        echo "OK   #${label}${detail:+  -- $detail}"
        PASS=$((PASS+1))
    else
        echo "FAIL #${label}${detail:+  -- $detail}"
        FAIL=$((FAIL+1))
    fi
}

# ---------------------------------------------------------------------------

# 1. The SPA is served.
c1() {
    local code
    code=$(curl_cmd -sS -o "$TMP/home.html" -w '%{http_code}' "$URL/")
    [ "$code" = "200" ] || { echo "homepage HTTP $code"; return 1; }
    grep -q '<title>' "$TMP/home.html" || { echo "no <title>"; return 1; }
    echo "homepage 200"
}
check 1 c1

# 2. The hashed JS bundle is served with a script MIME type. Catches the
#    classic SPA-fallback bug where a missing asset returns index.html as
#    text/html and the browser silently refuses to execute it.
c2() {
    local js code ctype
    js=$(grep -oE '/assets/[^"]+\.js' "$TMP/home.html" | head -1)
    [ -n "$js" ] || { echo "no /assets/*.js referenced in the page"; return 1; }
    read -r code ctype < <(curl_cmd -sSI "$URL$js" \
        | awk 'BEGIN{IGNORECASE=1} /^HTTP/{c=$2} /^content-type:/{t=$2} END{print c, t}')
    [ "$code" = "200" ] || { echo "$js HTTP $code"; return 1; }
    case "$ctype" in
        *javascript*) echo "bundle $ctype" ;;
        *) echo "$js served as $ctype -- SPA fallback is shadowing the asset"; return 1 ;;
    esac
}
check 2 c2

# 3. The capability probe reached the data plane. This is the check that
#    replaces "is the backend up" -- /agent/health reports the tool surface it
#    discovered at startup, so a non-empty tool list proves the app plane
#    completed an MCP handshake with whatever backend it was pointed at.
#
#    The tool COUNT is deliberately not asserted. 1.2.x serves 2 and 1.3.x
#    serves 6, and both are correct; pinning a number here would make the
#    script fail on exactly the backend difference it exists to tolerate.
#    Retried on a deadline, deliberately. /agent/health never blocks on the data
#    plane; when its cache is cold it serves the empty snapshot and kicks off the
#    probe in the background. So the FIRST call after a deploy legitimately
#    reports zero tools and a later one is correct.
#
#    The budget is a deadline rather than a fixed retry count, because a data
#    plane that has to cold-start can take ~60s to answer.
#
#    This check also gates the chat check after it: both need the same data
#    plane, so letting 3 block until it answers keeps check 5 from failing for a
#    reason that has nothing to do with what it tests.
WARMUP_SECS="${SMOKE_WARMUP_SECS:-120}"

c3() {
    local health n gen start elapsed attempt=0
    start=$(date +%s)
    while :; do
        attempt=$((attempt+1))
        health=$(curl_cmd -sS --max-time 30 "$URL/agent/health")
        echo "$health" | jq -e '.status == "ok"' >/dev/null \
            || { echo "health not ok: $(echo "$health" | head -c 200)"; return 1; }
        n=$(echo "$health" | jq -r '.mcp.tool_count // 0')
        gen=$(echo "$health" | jq -r '.mcp.generation // "unknown"')
        if [ "$n" -ge 1 ] 2>/dev/null; then
            elapsed=$(( $(date +%s) - start ))
            if [ "$attempt" -eq 1 ]; then
                echo "$n tools, generation $gen"
            else
                echo "$n tools, generation $gen (ready after ${elapsed}s, $attempt reads)"
            fi
            return 0
        fi
        elapsed=$(( $(date +%s) - start ))
        [ "$elapsed" -ge "$WARMUP_SECS" ] && break
        sleep 5
    done
    echo "capability probe found no tools in ${WARMUP_SECS}s ($attempt reads) -- data plane unreachable or refusing auth"
    return 1
}
check 3 c3

# 4. Verify that the HTML shell includes the #theme-tokens and #instance-config
#    elements.
c4() {
    local slot
    for slot in theme-tokens instance-config; do
        grep -q "id=\"$slot\"" "$TMP/home.html" \
            || { echo "no id=\"$slot\" in the page"; return 1; }
    done
    echo "theme-tokens and instance-config slots present"
}
check 4 c4

# 5. A real chat turn. The only check that exercises the model, so it is last
#    and it is the slowest.
c5() {
    local out
    # Written to a file rather than piped from a variable: `grep -q` exits on
    # its first match, which SIGPIPEs the feeding echo, and under `pipefail`
    # that surfaced as "echo: write error: Broken pipe" and a bogus failure.
    out="$TMP/chat.sse"
    curl_cmd -sS -N --max-time 150 -X POST "$URL/agent/chat/stream" \
        -H 'Content-Type: application/json' \
        -d '{"message":"What is the population of the United States?","turns":[]}' \
        > "$out" 2>/dev/null
    [ -s "$out" ] || { echo "chat stream returned nothing (timeout or cold start)"; return 1; }
    grep -q '"tool_call"' "$out" || { echo "no tool_call content: the model answered without consulting data"; return 1; }
    grep -q '"state": "complete"' "$out" || { echo "no complete terminal event: $(grep -m1 -A1 '^event: terminal' "$out" | tail -1)"; return 1; }
    grep -q '"hmac": "[0-9a-f]\{64\}"' "$out" || { echo "complete terminal event carries no transcript signature"; return 1; }
    echo "chat streamed $(grep -c '^id:' "$out") events"
}
check 5 c5

echo
echo "Pass: $PASS  Fail: $FAIL"
if [ $FAIL -eq 0 ]; then
    echo "SMOKE: PASS"
    exit 0
else
    echo "SMOKE: FAIL"
    exit 1
fi

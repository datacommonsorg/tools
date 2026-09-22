#!/usr/bin/env bash
# Post-deploy smoke test for a unified-architecture app plane.
#
# Usage:
#   bash docs/smoke.sh https://<instance>-app-<hash>-<region>.a.run.app
#
# Set BEARER_TOKEN for an IAM/IAP-gated stack:
#   BEARER_TOKEN=$(gcloud auth print-identity-token) bash docs/smoke.sh "$URL"
#
# Every check here holds on BOTH backends -- dcp and none. That is
# the point: the app plane is supposed to be identical whichever data plane
# serves it, so a check that only passes on one of them is testing the backend
# rather than the architecture.
#
# An older version of this script was written for the long-gone single-container
# stamp and asserted two things that are wrong here:
#
#   * /api/observations/series -- a *website* Flask route. The DCP plane serves
#     REST V2 and api.datacommons.org serves /v1 and /v2; neither has it. It
#     404s on two of three backends while the data path is perfectly healthy.
#   * .brand_config_url from /agent/brand -- deliberately removed, so the
#     browser never learns the config bucket's URL. Asserting it means asserting
#     an information leak.
#
# Both are replaced by checks against the path the agent actually uses: an MCP
# session through /dcproxy, ending in a real tools/call that returns numbers.
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

# An MCP response over Streamable HTTP may arrive as plain JSON or as an SSE
# frame. Reduce both to the JSON payload so jq can read either.
mcp_body() {
    sed -n 's/^data: //p;/^{/p' | tail -1
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
#    The budget is a deadline rather than a fixed retry count because the three
#    backends warm at very different speeds. `none` points at api.datacommons.org,
#    which is always hot, and dcp's plane is provisioned and running before this
#    script ever sees it. Neither should need more than a read or two.
#
#    The deadline is kept anyway. The removed cdc backend cold-started a Mixer of
#    its own and took ~60s to answer -- comfortably past a 3-reads-and-5-seconds
#    ceiling, so a healthy stack reported FAIL on checks 3, 4, 5 and 7 and passed
#    on a manual re-run minutes later. Nothing guarantees a future backend is
#    warm, and a smoke test that cries wolf on a first deploy trains you to
#    ignore it, which is worse than not having one.
#
#    This check also gates the ones after it: 4, 5 and 7 all need the same data
#    plane, so letting 3 block until it answers keeps them from failing for a
#    reason that has nothing to do with what they test.
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

# 4. MCP initialize through the same-origin proxy. Proves /dcproxy forwards,
#    strips the inbound identity headers, and attaches the app plane's own
#    credential -- the browser has none of its own.
c4() {
    local body name
    body=$(curl_cmd -sS --max-time 60 -X POST "$URL/mcp" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -D "$TMP/mcp.headers" \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
        | mcp_body)
    name=$(echo "$body" | jq -r '.result.serverInfo.name // empty')
    [ -n "$name" ] || { echo "no serverInfo: $(echo "$body" | head -c 200)"; return 1; }
    echo "serverInfo $name"
}
check 4 c4

# 5. A real tools/call that returns numbers, over a full MCP session through
#    the proxy. This is the end-to-end data path minus the model: session
#    handshake, notifications/initialized, then get_observations.
#
#    get_observations is used, with variable_dcid + place_dcid, because that is
#    the one call whose name AND required arguments are identical across both
#    generations. Verified against a live 1.2.x DCP server (2 tools) and a live
#    1.3.x server (6 tools): 1.3.x splits the fat tools apart but keeps this
#    signature. The 1.3.x-only names -- entity_dcids, get_multi_entity_
#    observations -- would 400 against DCP.
#
#    The session id is treated as OPTIONAL. Streamable HTTP allows a stateless
#    server, and the Data Commons MCP servers are stateless: they return no
#    Mcp-Session-Id at all and accept tools/call without one. Requiring the
#    header made this check fail against a perfectly healthy backend.
c5() {
    local sid session_hdr body
    curl_cmd -sS --max-time 60 -X POST "$URL/mcp" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -D "$TMP/h5b" -o /dev/null \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
    sid=$(awk 'BEGIN{IGNORECASE=1} /^mcp-session-id:/{print $2}' "$TMP/h5b" | tr -d '\r')
    session_hdr="X-Smoke-Stateless: 1"
    [ -n "$sid" ] && session_hdr="Mcp-Session-Id: $sid"

    curl_cmd -sS --max-time 30 -X POST "$URL/mcp" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -H "$session_hdr" \
        -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null

    body=$(curl_cmd -sS --max-time 90 -X POST "$URL/mcp" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -H "$session_hdr" \
        -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_observations","arguments":{"variable_dcid":"Count_Person","place_dcid":"country/IND"}}}' \
        | mcp_body)
    echo "$body" | grep -qi 'validation error' \
        && { echo "tools/call rejected the arguments: $(echo "$body" | head -c 200)"; return 1; }
    echo "$body" | jq -e '.result' >/dev/null 2>&1 \
        || { echo "tools/call returned no result: $(echo "$body" | head -c 200)"; return 1; }
    # Any digit run of 4+ is a population-scale number; enough to distinguish a
    # real observation from an empty envelope without pinning a value that
    # moves when the source updates.
    echo "$body" | grep -qE '[0-9]{4,}' \
        || { echo "tools/call result carried no observations"; return 1; }
    echo "get_observations returned data"
}
check 5 c5

# 6. Branding is served from the agent's memory, and the config bucket's URL is
#    NOT disclosed to the browser.
c6() {
    local brand name
    brand=$(curl_cmd -sS --max-time 30 "$URL/agent/brand")
    name=$(echo "$brand" | jq -r '.branding.instance_name // empty')
    [ -n "$name" ] || { echo "no branding.instance_name: $(echo "$brand" | head -c 200)"; return 1; }
    if echo "$brand" | jq -e 'to_entries | any(.value | tostring | test("storage.googleapis.com|gs://"))' >/dev/null 2>&1; then
        echo "brand payload discloses the config bucket"; return 1
    fi
    echo "branding \"$name\", bucket not disclosed"
}
check 6 c6

# 7. A real chat turn. The only check that exercises the model, so it is last
#    and it is the slowest.
c7() {
    local out
    # Written to a file rather than piped from a variable: `grep -q` exits on
    # its first match, which SIGPIPEs the feeding echo, and under `pipefail`
    # that surfaced as "echo: write error: Broken pipe" and a bogus failure.
    out="$TMP/chat.sse"
    curl_cmd -sS -N --max-time 150 -X POST "$URL/agent/chat/stream" \
        -H 'Content-Type: application/json' \
        -d '{"message":"What is the population of the United States?","session_id":"smoke-script","history":[]}' \
        > "$out" 2>/dev/null
    [ -s "$out" ] || { echo "chat stream returned nothing (timeout or cold start)"; return 1; }
    grep -q 'session_id' "$out" || { echo "no session_id event"; return 1; }
    grep -q 'mcp_start'  "$out" || { echo "no mcp_start event -- the model answered without consulting data"; return 1; }
    echo "chat streamed $(grep -c 'data:' "$out") events"
}
check 7 c7

echo
echo "Pass: $PASS  Fail: $FAIL"
if [ $FAIL -eq 0 ]; then
    echo "SMOKE: PASS"
    exit 0
else
    echo "SMOKE: FAIL"
    exit 1
fi

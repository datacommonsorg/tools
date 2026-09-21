#!/usr/bin/env python3
"""Prompt URLs are derived from CONFIG_URL as a URL, not as a string.

Run from the agent/ directory with no test framework:
    python3 tests/test_prompt_urls.py

A prompt whose URL comes out wrong 404s, and _fetch_prompt_bodies treats a 404
as "slot absent" and carries on -- so the whole class of failure here is silent:
the agent starts, answers, and only runs every phase with no system instruction.
That makes the derivation worth pinning at each shape CONFIG_URL can take.
"""

import importlib.util
import os
import sys
import types

sys.path.insert(0, os.getcwd())

# Stub the Secret Manager import config.py does at module scope.
_sm = types.ModuleType("google.cloud.secretmanager")
_sm.SecretManagerServiceClient = object
sys.modules.setdefault("google", types.ModuleType("google"))
sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
sys.modules["google.cloud.secretmanager"] = _sm

spec = importlib.util.spec_from_file_location(
    "agentconfig", "src/narratives_agent/config.py"
)
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)

requested = []


class _Response:
    """Enough of requests.Response for _fetch_prompt_bodies."""

    text = "body"

    def raise_for_status(self):
        pass


def _record(url):
    requested.append(url)
    return _Response()


cfg._fetch_gcs_url = _record

# Test: the three shapes CONFIG_URL arrives in.
# Situation: config in a bucket subdirectory, config at the host root, and a
#   config URL carrying a query whose own value contains a slash.
# Expectation: prompts/<slot>.md resolves beside the config every time, with a
#   single slash at the root, and the query -- which addresses the config object
#   alone -- neither carried over nor read as part of the path.
CASES = [
    (
        "https://storage.googleapis.com/bucket/dir/agent-config.json",
        "https://storage.googleapis.com/bucket/dir/prompts/mcp.md",
    ),
    (
        "https://example.com/agent-config.json",
        "https://example.com/prompts/mcp.md",
    ),
    (
        "https://storage.googleapis.com/bucket/agent-config.json?generation=17&x=a/b",
        "https://storage.googleapis.com/bucket/prompts/mcp.md",
    ),
]

fails = []
for config_url, expected in CASES:
    requested.clear()
    cfg._fetch_prompt_bodies(config_url)
    got = requested[0] if requested else None
    # The first slot's URL is the whole derivation; the rest differ only in
    # filename, so that URL plus the request count covers the loop.
    ok = got == expected and len(requested) == len(cfg.PROMPT_SLOTS)
    print(f"  {'ok  ' if ok else 'FAIL'} {config_url}\n         -> {got}")
    if not ok:
        fails.append(config_url)

print(
    f"\n{len(CASES) - len(fails)}/{len(CASES)} checks passed"
    if not fails
    else f"\nFAILURES: {fails}"
)
sys.exit(1 if fails else 0)

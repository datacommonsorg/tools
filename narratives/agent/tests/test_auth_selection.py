#!/usr/bin/env python3
"""Auth is chosen by target host, not by a backend flag.

Run from the agent/ directory with no test framework:
    python3 tests/test_auth_selection.py

Two backends need two different credentials, and sending the wrong one fails in
a way that looks like a data problem rather than an auth problem:

  * public Data Commons wants X-API-Key -- our service account means nothing to
    it, so an ID token yields "no data" on every query.
  * a private Cloud Run data plane wants a Google-signed ID token -- an API key
    yields 403 on every chart.

The last case is the security property the host allowlist exists for: the MCP
endpoint is configuration-driven and that config is fetched from a GCS bucket,
so an edit to it must not be able to hand our API key to an arbitrary host.
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["DC_API_KEY"] = "test-key-123"

spec = importlib.util.spec_from_file_location("gcp_auth", "src/gcp_auth.py")
ga = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ga)
ga.get_id_token = lambda audience: "fake-id-token"  # no metadata server in tests

CASES = [
    ("https://api.datacommons.org/mcp", "X-API-Key", "test-key-123"),
    ("https://datacommons.org/api", "X-API-Key", "test-key-123"),
    ("https://x-dc-datacommons-service-uc.a.run.app/mcp", "Authorization", "Bearer fake-id-token"),
    ("http://localhost:8082/mcp", None, None),
]

fails = []
for url, header, expected in CASES:
    headers = {}
    ga.attach_auth(headers, url)
    ok = headers.get(header) == expected if header else headers == {}
    print(f"  {'ok  ' if ok else 'FAIL'} {url[:52]:54s} -> {headers or '{} (no auth)'}")
    if not ok:
        fails.append(url)

headers = {}
ga.attach_auth(headers, "https://evil.example.com/mcp")
leaked = "X-API-Key" in headers
print(f"  {'ok  ' if not leaked else 'FAIL'} API key NOT sent to an unlisted host")
if leaked:
    fails.append("api key leaked to unlisted host")

print(f"\n{len(CASES) + 1 - len(fails)}/{len(CASES) + 1} checks passed" if not fails else f"\nFAILURES: {fails}")
sys.exit(1 if fails else 0)

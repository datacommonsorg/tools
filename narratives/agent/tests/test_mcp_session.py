#!/usr/bin/env python3
"""Behavioural test for MCP session handling.

Run from the agent/ directory with no test framework:
    python3 tests/test_mcp_session.py

Guards the fix for the module-global session_id, which made N instances
incorrect rather than merely slow. The three behaviours asserted here are the
ones whose absence is silent: a session rejected by a different data-plane
instance must recover, concurrent threads must not share a session, and a
failing tools/list must not blank the tool surface.

Behavioural test for MCP session handling: thread isolation, recovery from a
data-plane instance that does not recognise our session, and tool-cache TTL."""
import importlib.util, os, sys, threading, types
sys.path.insert(0, os.getcwd())
os.environ["MCP_SERVER_URL"] = "https://data.example.run.app/mcp"

# Stub the heavy deps client.py imports so we can load it standalone.
for name, attrs in {
    "src.config": {"load_config": lambda: {}, "AGENT_ROOT": "."},
    "src.gcp_auth": {"attach_auth": lambda h, u: None},
    "src.mcp.schema": {"fix_tool_arguments": lambda n, a: a},
    "src.session_logger": {"SessionLogger": object},
}.items():
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m

spec = importlib.util.spec_from_file_location("mcpclient", "src/mcp/client.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)

calls = []
def fake_request(method, params=None, is_notification=False):
    """Scripted server: rejects the first tools/list, accepts after re-init."""
    calls.append(method)
    if method == "initialize":
        c._set_session_id("sess-" + threading.current_thread().name)
        return {"result": {"ok": True}}
    if method == "notifications/initialized":
        return {"result": "notification sent"}
    if method == "tools/list":
        if fake_request.reject_next:
            fake_request.reject_next = False
            return {"error": {"code": -32000, "message": "Session not found"}}
        return {"result": {"tools": [{"name": "get_observations"}]}}
    return {"result": {}}
fake_request.reject_next = True
c.mcp_request = fake_request

fails = []
def check(label, cond):
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")
    if not cond: fails.append(label)

# 1. Recovery: a rejected session re-initialises and retries once.
tools = c.get_tools(force_refresh=True)
check("recovers from a rejected session", tools == [{"name": "get_observations"}])
check("re-initialised exactly once", calls.count("initialize") == 2)
check("retried tools/list exactly once", calls.count("tools/list") == 2)

# 2. Thread isolation: two threads never share a session id.
seen = {}
def worker():
    c.initialize_mcp()
    seen[threading.current_thread().name] = c.get_session_id()
t1 = threading.Thread(target=worker, name="A"); t2 = threading.Thread(target=worker, name="B")
t1.start(); t2.start(); t1.join(); t2.join()
check("threads hold distinct sessions", seen.get("A") != seen.get("B") and all(seen.values()))

# 3. Tool cache: served from cache, and stale-on-failure beats empty.
before = calls.count("tools/list")
c.get_tools(); c.get_tools()
check("cached within TTL (no extra round trips)", calls.count("tools/list") == before)

def always_fail(method, params=None, is_notification=False):
    calls.append(method)
    return {"error": {"message": "backend down"}}
c.mcp_request = always_fail
check("serves a stale list rather than nothing",
      c.get_tools(force_refresh=True) == [{"name": "get_observations"}])

print(f"\n{4+2-len(fails)}/6 checks passed" if not fails else f"\nFAILURES: {fails}")
sys.exit(1 if fails else 0)

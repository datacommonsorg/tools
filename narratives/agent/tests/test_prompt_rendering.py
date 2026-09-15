#!/usr/bin/env python3
"""Prompt placeholder substitution, and the gate on ?key= overrides.

Run from the agent/ directory with no test framework:
    python3 tests/test_prompt_rendering.py

Two things are pinned here, both of which fail silently if they regress.

{{instance.*}} substitution was documented in agent-config.schema.json long
before anything implemented it, so every instance that set template_vars got a
prompt containing literal braces. An unknown placeholder is deliberately left
in place rather than blanked: a visible {{instance.region}} in an answer is a
much louder failure than a sentence that quietly lost its subject.

query_param_key gates model/thinking overrides and ?demo=true, which switches
to reserved demo API keys. It used to fall back to a literal default, so a
public repo published a working credential; and an empty default would make
"" == "" true for every anonymous caller, which is worse still.
"""
import importlib.util
import os
import secrets
import sys
import types

sys.path.insert(0, os.getcwd())

# Stub the Secret Manager import config.py does at module scope.
_sm = types.ModuleType("google.cloud.secretmanager")
_sm.SecretManagerServiceClient = object
sys.modules.setdefault("google", types.ModuleType("google"))
sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
sys.modules["google.cloud.secretmanager"] = _sm

spec = importlib.util.spec_from_file_location("agentconfig", "src/config.py")
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)

checks = 0
failures = []


def check(label, got, want):
    global checks
    checks += 1
    if got == want:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}\n         got:  {got!r}\n         want: {want!r}")


def with_config(doc):
    cfg.load_config = lambda: doc


# --- {{instance.*}} substitution -------------------------------------------
print("instance template vars")

with_config({"template_vars": {"name": "Example DC", "region": "the world",
                               "states_term": "regions"}})
check("single placeholder",
      cfg.render_prompt("Welcome to {{instance.name}}."),
      "Welcome to Example DC.")
check("repeated placeholder",
      cfg.render_prompt("{{instance.name}} / {{instance.name}}"),
      "Example DC / Example DC")
check("several distinct placeholders",
      cfg.render_prompt("{{instance.name}} covers {{instance.region}} by {{instance.states_term}}"),
      "Example DC covers the world by regions")
check("unknown placeholder is left intact, not blanked",
      cfg.render_prompt("fiscal year {{instance.fiscal_year_start}}"),
      "fiscal year {{instance.fiscal_year_start}}")
check("prompt with no placeholders is untouched",
      cfg.render_prompt("plain text"),
      "plain text")

with_config({"template_vars": {"_comment": "notes for humans", "name": "Example DC"}})
check("_comment keys are not substitutable",
      cfg.render_prompt("{{instance._comment}}|{{instance.name}}"),
      "{{instance._comment}}|Example DC")

with_config({"template_vars": {"fiscal_year_start": "04-01", "count": 7}})
check("non-string scalars are coerced",
      cfg.render_prompt("{{instance.count}} on {{instance.fiscal_year_start}}"),
      "7 on 04-01")

with_config({})
check("absent template_vars leaves placeholders intact",
      cfg.render_prompt("{{instance.name}}"),
      "{{instance.name}}")

with_config({"template_vars": "not-an-object"})
check("malformed template_vars does not raise",
      cfg.render_prompt("{{instance.name}}"),
      "{{instance.name}}")

with_config({"template_vars": {"name": "Example DC"}})
rendered = cfg.render_prompt("{{CURRENT_DATETIME}} at {{instance.name}}")
check("datetime still substituted alongside instance vars",
      "{{CURRENT_DATETIME}}" not in rendered and rendered.endswith("at Example DC"),
      True)


# --- the ?key= override gate ------------------------------------------------
print("query param key gate")


def gate(expected, supplied):
    """The condition guarding overrides in routes/chat.py."""
    return bool(expected) and secrets.compare_digest(supplied, expected)


with_config({})
check("unconfigured key reads as empty", cfg.get_query_param_key(), "")
check("no key configured, none supplied -> refused", gate(cfg.get_query_param_key(), ""), False)
check("no key configured, key guessed  -> refused",
      gate(cfg.get_query_param_key(), "AISummit2026"), False)

with_config({"query_param_key": "  a-long-non-guessable-value  "})
check("configured key is stripped", cfg.get_query_param_key(), "a-long-non-guessable-value")
check("configured key, wrong value -> refused",
      gate(cfg.get_query_param_key(), "nope"), False)
check("configured key, right value -> allowed",
      gate(cfg.get_query_param_key(), "a-long-non-guessable-value"), True)

with_config({"query_param_key": 12345})
check("non-string key reads as empty", cfg.get_query_param_key(), "")


print()
if failures:
    print(f"{len(failures)}/{checks} checks FAILED")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"{checks}/{checks} checks passed")

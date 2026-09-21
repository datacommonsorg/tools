# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Prompt placeholder substitution, the ?key= gate, and prompt URL derivation.

Three things are pinned here, all of which fail silently if they regress.

{{instance.*}} substitution was documented in agent-config.schema.json long
before anything implemented it, so every instance that set template_vars got a
prompt containing literal braces. An unknown placeholder is deliberately left
in place rather than blanked: a visible {{instance.region}} in an answer is a
much louder failure than a sentence that quietly lost its subject.

query_param_key gates model/thinking overrides and ?demo=true, which switches
to reserved demo API keys. It used to fall back to a literal default, so a
public repo published a working credential; and an empty default would make
"" == "" true for every anonymous caller, which is worse still.

Prompt URLs are derived from CONFIG_URL as a URL, not as a string. A prompt
whose URL comes out wrong 404s, and _fetch_prompt_bodies treats a 404 as "slot
absent" and carries on -- so the whole class of failure here is silent: the
agent starts, answers, and only runs every phase with no system instruction.
That makes the derivation worth pinning at each shape CONFIG_URL can take.
"""

import secrets

import pytest

from narratives_agent import config


def _with_config(
    monkeypatch: pytest.MonkeyPatch, doc: dict[str, object]
) -> None:
    """Serve `doc` as the agent config for the duration of one test."""
    monkeypatch.setattr(config, "load_config", lambda: doc)


def _gate(expected: str, supplied: str) -> bool:
    """The condition guarding overrides in routes/chat.py."""
    return bool(expected) and secrets.compare_digest(supplied, expected)


# --- {{instance.*}} substitution -------------------------------------------


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Welcome to {{instance.name}}.", "Welcome to Example DC."),
        ("{{instance.name}} / {{instance.name}}", "Example DC / Example DC"),
        (
            "{{instance.name}} covers {{instance.region}} by "
            "{{instance.states_term}}",
            "Example DC covers the world by regions",
        ),
        ("plain text", "plain text"),
    ],
    ids=[
        "single placeholder",
        "repeated placeholder",
        "several distinct placeholders",
        "prompt with no placeholders is untouched",
    ],
)
def test_instance_placeholders_are_substituted(
    monkeypatch: pytest.MonkeyPatch, prompt: str, expected: str
) -> None:
    # Test: {{instance.<key>}} substitution from template_vars.
    # Situation: an instance configures template_vars and authors a prompt
    #   using one placeholder, the same placeholder twice, several distinct
    #   placeholders, or none at all.
    # Expectation: every configured placeholder is replaced by its value, and
    #   a prompt without placeholders comes back unchanged.
    _with_config(
        monkeypatch,
        {
            "template_vars": {
                "name": "Example DC",
                "region": "the world",
                "states_term": "regions",
            }
        },
    )
    assert config.render_prompt(prompt) == expected


def test_unknown_placeholder_is_left_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: what happens to a placeholder template_vars does not define.
    # Situation: a prompt names {{instance.fiscal_year_start}}, which the
    #   configured template_vars has no entry for.
    # Expectation: it is left in place rather than blanked -- a visible
    #   placeholder in an answer is a much louder failure than a sentence that
    #   quietly lost its subject.
    _with_config(
        monkeypatch,
        {
            "template_vars": {
                "name": "Example DC",
                "region": "the world",
                "states_term": "regions",
            }
        },
    )
    assert (
        config.render_prompt("fiscal year {{instance.fiscal_year_start}}")
        == "fiscal year {{instance.fiscal_year_start}}"
    )


def test_comment_keys_are_not_substitutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: the "_comment" convention used throughout the config files.
    # Situation: template_vars carries a _comment key alongside a real one.
    # Expectation: the _comment placeholder is not substituted, so authoring
    #   notes cannot leak into a prompt; the real key still is.
    _with_config(
        monkeypatch,
        {
            "template_vars": {
                "_comment": "notes for humans",
                "name": "Example DC",
            }
        },
    )
    rendered = config.render_prompt("{{instance._comment}}|{{instance.name}}")
    assert rendered == "{{instance._comment}}|Example DC"


def test_non_string_scalars_are_coerced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: template_vars values that are not strings.
    # Situation: a config sets a numeric template var, which JSON permits.
    # Expectation: it is coerced to its string form rather than skipped.
    _with_config(
        monkeypatch,
        {"template_vars": {"fiscal_year_start": "04-01", "count": 7}},
    )
    rendered = config.render_prompt(
        "{{instance.count}} on {{instance.fiscal_year_start}}"
    )
    assert rendered == "7 on 04-01"


def test_absent_template_vars_leaves_placeholders_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: the default case, where an instance configures nothing.
    # Situation: the config document has no template_vars at all.
    # Expectation: placeholders survive untouched, matching the unknown-key
    #   behavior rather than blanking the prompt.
    _with_config(monkeypatch, {})
    assert config.render_prompt("{{instance.name}}") == "{{instance.name}}"


def test_malformed_template_vars_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: tolerance of a config that does not match the schema.
    # Situation: template_vars is a string where an object is required.
    # Expectation: rendering degrades to leaving placeholders in place instead
    #   of raising, so one bad config field cannot take the agent down.
    _with_config(monkeypatch, {"template_vars": "not-an-object"})
    assert config.render_prompt("{{instance.name}}") == "{{instance.name}}"


def test_datetime_is_substituted_alongside_instance_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: the pre-existing {{CURRENT_DATETIME}} placeholder still works.
    # Situation: a prompt mixes {{CURRENT_DATETIME}} with an instance var.
    # Expectation: both are substituted -- adding instance vars must not have
    #   displaced the datetime substitution that prompts already relied on.
    _with_config(monkeypatch, {"template_vars": {"name": "Example DC"}})
    rendered = config.render_prompt("{{CURRENT_DATETIME}} at {{instance.name}}")
    assert "{{CURRENT_DATETIME}}" not in rendered
    assert rendered.endswith("at Example DC")


# --- the ?key= override gate ------------------------------------------------


def test_unconfigured_key_reads_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: the value get_query_param_key returns when nothing is configured.
    # Situation: the config document sets no query_param_key.
    # Expectation: "" rather than a literal default -- this repo is public, so
    #   any literal here would be a published credential for every instance
    #   that did not override it.
    _with_config(monkeypatch, {})
    assert config.get_query_param_key() == ""


@pytest.mark.parametrize(
    "supplied",
    ["", "AISummit2026"],
    ids=["none supplied", "key guessed"],
)
def test_gate_refuses_when_no_key_is_configured(
    monkeypatch: pytest.MonkeyPatch, supplied: str
) -> None:
    # Test: the gate's behavior on an instance that configured no key.
    # Situation: no query_param_key is configured, and a caller supplies
    #   nothing or a guess.
    # Expectation: refused either way. An empty default would make "" == ""
    #   true for every anonymous caller, which is worse than a published one.
    _with_config(monkeypatch, {})
    assert _gate(config.get_query_param_key(), supplied) is False


def test_configured_key_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test: whitespace handling on the configured key.
    # Situation: the config value carries leading and trailing whitespace, as
    #   a hand-edited JSON document readily can.
    # Expectation: it is stripped, so the key a caller can actually supply is
    #   the one the config author meant to write.
    _with_config(
        monkeypatch, {"query_param_key": "  a-long-non-guessable-value  "}
    )
    assert config.get_query_param_key() == "a-long-non-guessable-value"


def test_gate_refuses_a_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test: the gate rejects a mismatch.
    # Situation: a key is configured and the caller supplies a different one.
    # Expectation: refused.
    _with_config(
        monkeypatch, {"query_param_key": "  a-long-non-guessable-value  "}
    )
    assert _gate(config.get_query_param_key(), "nope") is False


def test_gate_allows_the_configured_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: the gate admits the configured key.
    # Situation: a key is configured and the caller supplies exactly it.
    # Expectation: allowed -- the overrides and demo mode this gates are
    #   unreachable otherwise.
    _with_config(
        monkeypatch, {"query_param_key": "  a-long-non-guessable-value  "}
    )
    assert _gate(config.get_query_param_key(), "a-long-non-guessable-value")


def test_non_string_key_reads_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: a query_param_key of the wrong JSON type.
    # Situation: the config sets a number where a string is required.
    # Expectation: "" -- which the gate refuses for every caller -- rather
    #   than a value compare_digest would raise on.
    _with_config(monkeypatch, {"query_param_key": 12345})
    assert config.get_query_param_key() == ""


# --- prompt URLs derived from CONFIG_URL ------------------------------------


class _StubResponse:
    """Enough of requests.Response for _fetch_prompt_bodies."""

    text = "body"

    def raise_for_status(self) -> None:
        pass


class _RecordingFetch:
    """Records every URL _fetch_prompt_bodies asks for, and fetches nothing."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> _StubResponse:
        self.urls.append(url)
        return _StubResponse()


@pytest.mark.parametrize(
    ("config_url", "expected"),
    [
        (
            "https://storage.googleapis.com/bucket/dir/agent-config.json",
            "https://storage.googleapis.com/bucket/dir/prompts/mcp.md",
        ),
        (
            "https://example.com/agent-config.json",
            "https://example.com/prompts/mcp.md",
        ),
        (
            "https://storage.googleapis.com/bucket/agent-config.json"
            "?generation=17&x=a/b",
            "https://storage.googleapis.com/bucket/prompts/mcp.md",
        ),
    ],
    ids=["bucket subdirectory", "host root", "query containing a slash"],
)
def test_prompt_urls_are_derived_from_the_config_url(
    monkeypatch: pytest.MonkeyPatch, config_url: str, expected: str
) -> None:
    # Test: the three shapes CONFIG_URL arrives in.
    # Situation: config in a bucket subdirectory, config at the host root, and
    #   a config URL carrying a query whose own value contains a slash.
    # Expectation: prompts/<slot>.md resolves beside the config every time,
    #   with a single slash at the root, and the query -- which addresses the
    #   config object alone -- neither carried over nor read as part of the
    #   path.
    fetch = _RecordingFetch()
    monkeypatch.setattr(config, "_fetch_gcs_url", fetch)

    config._fetch_prompt_bodies(config_url)

    # The first slot's URL is the whole derivation; the rest differ only in
    # filename, so that URL plus the request count covers the loop.
    assert fetch.urls[0] == expected
    assert len(fetch.urls) == len(config.PROMPT_SLOTS)

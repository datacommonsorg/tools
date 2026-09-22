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
"""Tests for prompt placeholder substitution and prompt URL derivation.

Covers two configuration behaviors:
1. `{{instance.*}}` placeholder substitution from `template_vars`, leaving
   unconfigured placeholders intact so missing values remain visible in rendered
   prompts.
2. Derivation of `prompts/<slot>.md` URLs relative to `CONFIG_URL`, preserving
   bucket directory prefixes while stripping query parameters.
"""

import pytest

from narratives_agent import config


def _with_config(
    monkeypatch: pytest.MonkeyPatch, doc: dict[str, object]
) -> None:
    """Stub `config.load_config` to return `doc` for the current test."""
    monkeypatch.setattr(config, "load_config", lambda: doc)


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
    # Test: Substitution of {{instance.<key>}} placeholders from template_vars.
    # Situation: The configuration defines template_vars, and the prompt
    #   contains a single placeholder, repeated placeholders, multiple distinct
    #   placeholders, or no placeholders.
    # Expectation: Every configured placeholder is replaced with its configured
    #   value, and prompts without placeholders are returned unchanged.
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
    # Test: Handling of placeholders not defined in template_vars.
    # Situation: A prompt references {{instance.fiscal_year_start}}, which is
    #   not present in the configured template_vars dictionary.
    # Expectation: The unknown placeholder is left intact in the rendered output
    #   rather than replaced with an empty string, making missing configuration
    #   values immediately visible.
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
    # Test: Exclusion of "_comment" metadata keys from prompt substitution.
    # Situation: template_vars contains a "_comment" documentation entry
    #   alongside a valid template variable.
    # Expectation: {{instance._comment}} is not substituted into the prompt,
    #   while the valid {{instance.name}} placeholder is replaced normally.
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
    # Test: Coercion of non-string scalar values in template_vars.
    # Situation: template_vars includes an integer value alongside a string.
    # Expectation: The integer value is converted to its string representation
    #   and substituted into the prompt.
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
    # Test: Prompt rendering when template_vars is omitted from the config.
    # Situation: The configuration dictionary does not contain a template_vars
    #   key.
    # Expectation: All {{instance.*}} placeholders remain untouched in the
    #   rendered prompt.
    _with_config(monkeypatch, {})
    assert config.render_prompt("{{instance.name}}") == "{{instance.name}}"


def test_malformed_template_vars_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Graceful handling when template_vars has an invalid JSON type.
    # Situation: template_vars is configured as a string instead of a
    #   dictionary.
    # Expectation: render_prompt does not raise an exception and leaves
    #   placeholders unchanged.
    _with_config(monkeypatch, {"template_vars": "not-an-object"})
    assert config.render_prompt("{{instance.name}}") == "{{instance.name}}"


def test_datetime_is_substituted_alongside_instance_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Simultaneous substitution of {{CURRENT_DATETIME}} and instance vars.
    # Situation: A prompt contains both {{CURRENT_DATETIME}} and
    #   {{instance.name}}.
    # Expectation: Both placeholders are replaced with their resolved values.
    _with_config(monkeypatch, {"template_vars": {"name": "Example DC"}})
    rendered = config.render_prompt("{{CURRENT_DATETIME}} at {{instance.name}}")
    assert "{{CURRENT_DATETIME}}" not in rendered
    assert rendered.endswith("at Example DC")


# --- prompt URLs derived from CONFIG_URL ------------------------------------


class _StubResponse:
    """Minimal requests.Response stub for _fetch_prompt_bodies."""

    text = "body"

    def raise_for_status(self) -> None:
        pass


class _RecordingFetch:
    """Callable stub that records requested URLs without network I/O."""

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
    # Test: Derivation of prompt file URLs from CONFIG_URL.
    # Situation: CONFIG_URL points to a bucket subdirectory, a host root, or
    #   includes query parameters whose values contain slashes.
    # Expectation: _fetch_prompt_bodies resolves prompts/<slot>.md sibling to
    #   the config file path in all three cases and strips query parameters
    #   before constructing the prompt URLs.
    fetch = _RecordingFetch()
    monkeypatch.setattr(config, "_fetch_gcs_url", fetch)

    config._fetch_prompt_bodies(config_url)

    # All slots share the same base directory URL and differ only in filename.
    assert fetch.urls[0] == expected
    assert len(fetch.urls) == len(config.PROMPT_SLOTS)


# --- Gemini API key resolution ----------------------------------------------


@pytest.mark.parametrize(
    ("gemini_section", "expected"),
    [
        ({"api_key": "  test-valid-gemini-key  "}, "test-valid-gemini-key"),
        ({"api_key": "REPLACE_ME_WITH_KEY"}, ""),
        ({"api_key": "DEPRECATED_KEY"}, ""),
        ({"api_key": None}, ""),
        ({"api_key": ""}, ""),
        (None, ""),
    ],
    ids=[
        "trimmed valid key",
        "replace_me placeholder",
        "deprecated placeholder",
        "null api_key",
        "empty api_key",
        "null gemini section",
    ],
)
def test_get_gemini_api_key_resolves_and_validates_config_fallback(
    monkeypatch: pytest.MonkeyPatch,
    gemini_section: dict[str, object] | None,
    expected: str,
) -> None:
    # Test: Local config fallback in get_gemini_api_key.
    # Situation: GEMINI_API_KEY_SECRET is unset and config.json contains a
    #   valid key, placeholder string, empty string, or null value.
    # Expectation: Valid keys are stripped and returned; placeholders, empty
    #   strings, and nulls return "".
    monkeypatch.delenv("GEMINI_API_KEY_SECRET", raising=False)
    monkeypatch.setattr(
        config, "load_config", lambda: {"gemini": gemini_section}
    )

    assert config.get_gemini_api_key() == expected


def test_get_gemini_api_key_prefers_secret_manager_and_falls_back_on_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Secret Manager priority and config fallback in get_gemini_api_key.
    # Situation: GEMINI_API_KEY_SECRET is set; first Secret Manager returns a
    #   key, then it returns "".
    # Expectation: Secret Manager value wins when non-empty; config.json
    #   fallback is used when Secret Manager returns "".
    monkeypatch.setenv("GEMINI_API_KEY_SECRET", "gemini-key-secret")
    monkeypatch.setattr(
        config, "load_config", lambda: {"gemini": {"api_key": "fallback-key"}}
    )

    monkeypatch.setattr(
        config, "_fetch_key_from_secret_manager", lambda name: "secret-key"
    )
    assert config.get_gemini_api_key() == "secret-key"

    monkeypatch.setattr(
        config, "_fetch_key_from_secret_manager", lambda name: ""
    )
    assert config.get_gemini_api_key() == "fallback-key"


@pytest.mark.parametrize(
    ("raw_payload", "expected"),
    [
        (b"  test-bare-gemini-key\n", "test-bare-gemini-key"),
        (b'["test-array-gemini-key"]', ""),
        (b'"test-quoted-gemini-key"', ""),
        (b"   \n", ""),
    ],
    ids=[
        "bare key",
        "legacy json array",
        "quoted json string",
        "whitespace only",
    ],
)
def test_fetch_key_from_secret_manager_validates_secret_payload(
    monkeypatch: pytest.MonkeyPatch,
    raw_payload: bytes,
    expected: str,
) -> None:
    # Test: Payload validation in _fetch_key_from_secret_manager.
    # Situation: Secret Manager returns a bare key, a legacy JSON array, a
    #   JSON-quoted string, or whitespace.
    # Expectation: Only the bare key is returned and cached; JSON-encoded and
    #   empty payloads are rejected with "".
    class _StubPayload:
        data = raw_payload

    class _StubVersionResponse:
        payload = _StubPayload()

    class _StubSecretClient:
        def access_secret_version(
            self, request: dict[str, str]
        ) -> _StubVersionResponse:
            return _StubVersionResponse()

    class _StubSecretModule:
        SecretManagerServiceClient = _StubSecretClient

    monkeypatch.setattr(config, "_SECRET_MANAGER_AVAILABLE", True)
    monkeypatch.setattr(
        config, "secretmanager", _StubSecretModule, raising=False
    )
    monkeypatch.setattr(config, "_SECRET_MANAGER_CACHE", {})

    secret_path = "projects/test-proj/secrets/gemini-key/versions/latest"
    assert config._fetch_key_from_secret_manager(secret_path) == expected
    if expected:
        assert config._SECRET_MANAGER_CACHE[secret_path][1] == expected
    else:
        assert secret_path not in config._SECRET_MANAGER_CACHE

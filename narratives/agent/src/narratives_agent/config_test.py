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
"""Tests for config loading, prompt rendering, and keys.

Covers six configuration behaviors in `config`:
1. `{{instance.*}}` placeholder substitution from `template_vars`, leaving
   unconfigured placeholders intact so missing values remain visible in rendered
   prompts, including when no configuration is loaded.
2. Derivation of `prompts/<slot>.md` URLs relative to `CONFIG_URL`, preserving
   bucket directory prefixes while stripping query parameters, and stripping
   HTML authoring comments from loaded prompt files.
3. `bootstrap_config_from_url` holding the fetched configuration in memory as
   an `AgentConfig`, where `load_config` reads it ahead of any file, layering
   the fetched prompts over the default prompts in `defaults/prompts/`, and
   holding `None` when the fetch fails or the response is not a JSON object.
4. `load_config` falling back to `config.json` under `agent_root`, re-read when
   it changes, and then to `agent-config.json` under `defaults_dir`, with the
   default `prompts/` as the base layer of every path, returning `None` when
   neither holds a JSON object, and reporting a value of the wrong type once
   while loading the rest of the document.
5. Resolution of `get_gemini_api_key` and `_fetch_key_from_secret_manager`,
   preferring Secret Manager over `config.json`, rejecting placeholder,
   empty, or JSON-wrapped secret payloads, and reusing a key another thread
   loaded while the caller waited.
6. Fallback to `UTC` in `get_current_datetime` when `TIMEZONE` cannot be
   resolved.
"""

import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path

import pytest
import requests

from narratives_agent import config
from narratives_agent.config_model import (
    PROMPT_SLOTS,
    AgentConfig,
    GeminiConfig,
    McpConfig,
    Prompts,
    ThinkingLevels,
)


@pytest.fixture(autouse=True)
def reset_config_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resets in-memory config caches before each test."""
    monkeypatch.setattr(config, "_bootstrapped", False)
    monkeypatch.setattr(config, "_bootstrapped_config", None)
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(config, "_config_mtime", 0.0)
    monkeypatch.setattr(config, "_config_path", None)
    monkeypatch.setattr(config, "_defaults_config", None)
    monkeypatch.setattr(config, "_defaults_dir", None)


def _with_config(
    monkeypatch: pytest.MonkeyPatch, loaded: AgentConfig | None
) -> None:
    """Stub `config.load_config` to return `loaded` for the current test."""
    monkeypatch.setattr(config, "load_config", lambda: loaded)


# --- {{instance.*}} substitution -------------------------------------------

_TEMPLATE_VARS = {
    "name": "Example DC",
    "region": "the world",
    "states_term": "regions",
}


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
    _with_config(monkeypatch, AgentConfig(template_vars=_TEMPLATE_VARS))
    assert config.render_prompt(prompt) == expected


def test_unknown_placeholder_is_left_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Handling of placeholders not defined in template_vars.
    # Situation: A prompt references {{instance.fiscal_year_start}}, which is
    #   not present in the configured template_vars.
    # Expectation: The unknown placeholder is left intact in the rendered output
    #   rather than replaced with an empty string, making missing configuration
    #   values immediately visible.
    _with_config(monkeypatch, AgentConfig(template_vars=_TEMPLATE_VARS))
    assert (
        config.render_prompt("fiscal year {{instance.fiscal_year_start}}")
        == "fiscal year {{instance.fiscal_year_start}}"
    )


@pytest.mark.parametrize(
    "loaded",
    [AgentConfig(), None],
    ids=["no template_vars", "no configuration loaded"],
)
def test_absent_template_vars_leaves_placeholders_intact(
    monkeypatch: pytest.MonkeyPatch, loaded: AgentConfig | None
) -> None:
    # Test: Prompt rendering without template variables.
    # Situation: The loaded configuration has no template_vars, or no
    #   configuration is loaded at all.
    # Expectation: All {{instance.*}} placeholders remain untouched in the
    #   rendered prompt and nothing is raised.
    _with_config(monkeypatch, loaded)
    assert config.render_prompt("{{instance.name}}") == "{{instance.name}}"


def test_datetime_is_substituted_alongside_instance_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Simultaneous substitution of {{CURRENT_DATETIME}} and instance vars.
    # Situation: A prompt contains both {{CURRENT_DATETIME}} and
    #   {{instance.name}}.
    # Expectation: Both placeholders are replaced with their resolved values.
    _with_config(monkeypatch, AgentConfig(template_vars={"name": "Example DC"}))
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
            "https://storage.googleapis.com/bucket/dir/prompts/classify.md",
        ),
        (
            "https://example.com/agent-config.json",
            "https://example.com/prompts/classify.md",
        ),
        (
            "https://storage.googleapis.com/bucket/agent-config.json"
            "?generation=17&x=a/b",
            "https://storage.googleapis.com/bucket/prompts/classify.md",
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
    assert len(fetch.urls) == len(PROMPT_SLOTS)


@pytest.mark.parametrize(
    ("url", "expects_auth"),
    [
        ("https://storage.googleapis.com/bucket/agent-config.json", True),
        ("https://bucket.storage.googleapis.com/agent-config.json", True),
        ("http://storage.googleapis.com/bucket/agent-config.json", False),
        (
            "https://example.com/config.json?redirect=storage.googleapis.com",
            False,
        ),
        (
            "https://storage.googleapis.com.example.com/agent-config.json",
            False,
        ),
    ],
    ids=[
        "https gcs root host",
        "https gcs subdomain",
        "http gcs rejected",
        "gcs in query string rejected",
        "spoofed suffix host rejected",
    ],
)
def test_fetch_gcs_url_attaches_metadata_token_only_for_https_gcs_hosts(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    expects_auth: bool,
) -> None:
    # Test: Hostname and scheme validation in `_fetch_gcs_url`.
    # Situation: `_fetch_gcs_url` is called with HTTPS GCS URLs, an HTTP GCS
    #   URL, a non-GCS URL containing `storage.googleapis.com` in its query
    #   string, and a spoofed hostname ending in `.example.com`.
    # Expectation: The metadata server is queried and `Authorization: Bearer` is
    #   attached only for HTTPS URLs whose hostname is `storage.googleapis.com`
    #   or a `.storage.googleapis.com` subdomain.
    calls: list[tuple[str, dict[str, str]]] = []

    class _FakeHttpResponse:
        status_code = 200
        encoding = "utf-8"

        def json(self) -> dict[str, str]:
            return {"access_token": "metadata-token"}

    def _fake_get(
        request_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 0,
    ) -> _FakeHttpResponse:
        calls.append((request_url, dict(headers or {})))
        return _FakeHttpResponse()

    monkeypatch.setattr("narratives_agent.config.requests.get", _fake_get)
    config._fetch_gcs_url(url)

    if expects_auth:
        assert len(calls) == 2
        assert calls[1] == (url, {"Authorization": "Bearer metadata-token"})
    else:
        assert calls == [(url, {})]


# --- Gemini API key resolution ----------------------------------------------


@pytest.mark.parametrize(
    ("loaded", "expected"),
    [
        (
            AgentConfig(gemini=GeminiConfig(api_key="test-valid-gemini-key")),
            "test-valid-gemini-key",
        ),
        (AgentConfig(gemini=GeminiConfig(api_key="REPLACE_ME_WITH_KEY")), ""),
        (AgentConfig(gemini=GeminiConfig(api_key="DEPRECATED_KEY")), ""),
        (AgentConfig(), ""),
        (None, ""),
    ],
    ids=[
        "valid key",
        "replace_me placeholder",
        "deprecated placeholder",
        "no api_key",
        "no configuration loaded",
    ],
)
def test_get_gemini_api_key_resolves_and_validates_config_fallback(
    monkeypatch: pytest.MonkeyPatch,
    loaded: AgentConfig | None,
    expected: str,
) -> None:
    # Test: Local config fallback in get_gemini_api_key.
    # Situation: GEMINI_API_KEY_SECRET is unset and the loaded configuration
    #   carries a valid key, a placeholder string, or no key, or no
    #   configuration is loaded.
    # Expectation: A valid key is returned; placeholders, a missing key, and
    #   a missing configuration return "".
    monkeypatch.delenv("GEMINI_API_KEY_SECRET", raising=False)
    monkeypatch.setattr(config, "load_config", lambda: loaded)

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
        config,
        "load_config",
        lambda: AgentConfig(gemini=GeminiConfig(api_key="fallback-key")),
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
    #   empty payloads are rejected with "". The read is bounded by
    #   `_SECRET_MANAGER_TIMEOUT_SECONDS`.
    timeouts: list[float] = []

    class _StubPayload:
        data = raw_payload

    class _StubVersionResponse:
        payload = _StubPayload()

    class _StubSecretClient:
        def access_secret_version(
            self, request: dict[str, str], timeout: float
        ) -> _StubVersionResponse:
            timeouts.append(timeout)
            return _StubVersionResponse()

    class _StubSecretModule:
        SecretManagerServiceClient = _StubSecretClient

    monkeypatch.setattr(config, "_SECRET_MANAGER_AVAILABLE", True)
    monkeypatch.setattr(
        config, "secretmanager", _StubSecretModule, raising=False
    )
    monkeypatch.setattr(config, "_secret_manager_cache", {})

    secret_path = "projects/test-proj/secrets/gemini-key/versions/latest"
    assert config._fetch_key_from_secret_manager(secret_path) == expected
    assert timeouts == [config._SECRET_MANAGER_TIMEOUT_SECONDS]
    if expected:
        assert config._secret_manager_cache[secret_path][1] == expected
    else:
        assert secret_path not in config._secret_manager_cache


# --- prompt bodies ----------------------------------------------------------


class _BodyFetch:
    """Callable stub that returns a fixed response body for every slot."""

    def __init__(self, body: str) -> None:
        self.body = body

    def __call__(self, url: str) -> _StubResponse:
        response = _StubResponse()
        response.text = self.body
        return response


def test_html_comments_are_stripped_from_prompt_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Stripping of HTML authoring comments in `_fetch_prompt_bodies`.
    # Situation: A fetched `.md` prompt file contains an `<!-- ... -->` comment
    #   between two lines of instruction text.
    # Expectation: `_fetch_prompt_bodies` removes the HTML comment before
    #   storing the prompt text for the slot.
    monkeypatch.setattr(
        config,
        "_fetch_gcs_url",
        _BodyFetch("Answer plainly.\n<!-- keep in sync with X -->\nCite."),
    )
    prompts = config._fetch_prompt_bodies("https://example.com/config.json")
    assert prompts["discovery"] == "Answer plainly.\n\nCite."


# --- config loading ---------------------------------------------------------

_CONFIG_URL = "https://storage.googleapis.com/bucket/dir/agent-config.json"
_PROMPTS_URL = "https://storage.googleapis.com/bucket/dir/prompts"


class _NotFoundResponse(_StubResponse):
    """Response for an object that is absent from the bucket."""

    def raise_for_status(self) -> None:
        raise requests.HTTPError("404 Client Error: Not Found")


class _UrlFetch:
    """Answers each configured URL and raises `ConnectionError` otherwise.

    A URL whose body is `None` answers with a 404 response.
    """

    def __init__(self, bodies: Mapping[str, str | None]) -> None:
        self.bodies = bodies

    def __call__(self, url: str) -> _StubResponse:
        if url not in self.bodies:
            raise ConnectionError(url)
        body = self.bodies[url]
        if body is None:
            return _NotFoundResponse()
        response = _StubResponse()
        response.text = body
        return response


@pytest.fixture
def agent_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configures empty `AGENT_ROOT` and `DEFAULTS_DIR` with no `CONFIG_URL`."""
    root = tmp_path / "agent"
    root.mkdir()
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    monkeypatch.setenv("AGENT_ROOT", str(root))
    monkeypatch.setenv("DEFAULTS_DIR", str(defaults))
    monkeypatch.delenv("CONFIG_URL", raising=False)
    return root


@pytest.fixture
def defaults_dir(agent_root: Path) -> Path:
    return agent_root.parent / "defaults"


def _write_defaults(
    defaults_dir: Path, document: dict[str, object], prompts: dict[str, str]
) -> None:
    (defaults_dir / "agent-config.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    prompts_dir = defaults_dir / "prompts"
    prompts_dir.mkdir()
    for slot, body in prompts.items():
        (prompts_dir / f"{slot}.md").write_text(body, encoding="utf-8")


_DEFAULT_PROMPTS = {slot: f"Default {slot}." for slot in PROMPT_SLOTS}


def test_bootstrap_holds_the_fetched_config_in_memory(
    monkeypatch: pytest.MonkeyPatch, agent_root: Path
) -> None:
    # Test: In-memory caching of `CONFIG_URL` in `bootstrap_config_from_url`.
    # Situation: `CONFIG_URL` serves a document with an inline `synthesis`
    #   prompt, `prompts/discovery.md` and `prompts/synthesis.md` are served in
    #   the same directory, `prompts/follow_up.md` is absent, `defaults_dir`
    #   holds no prompts, and `agent_root` contains a local `config.json`.
    # Expectation: `load_config` returns the fetched configuration with the file
    #   prompt in `discovery`, the inline prompt in `synthesis`, and no
    #   `follow_up`. Each call returns the same instance, and
    #   `agent_root/config.json` is not modified.
    monkeypatch.setenv("CONFIG_URL", _CONFIG_URL)
    monkeypatch.setattr(
        config,
        "_fetch_gcs_url",
        _UrlFetch(
            {
                _CONFIG_URL: json.dumps(
                    {
                        "template_vars": {"name": "Fetched"},
                        "prompts": {"synthesis": "Inline synthesis."},
                    }
                ),
                f"{_PROMPTS_URL}/discovery.md": (
                    "Fetched discovery.\n<!-- note -->"
                ),
                f"{_PROMPTS_URL}/synthesis.md": "File synthesis.",
            }
        ),
    )
    disk_config = '{"template_vars": {"name": "Disk"}}'
    (agent_root / "config.json").write_text(disk_config, encoding="utf-8")

    config.bootstrap_config_from_url()
    loaded = config.load_config()

    assert loaded == AgentConfig(
        template_vars={"name": "Fetched"},
        prompts=Prompts(
            discovery="Fetched discovery.", synthesis="Inline synthesis."
        ),
    )
    assert config.load_config() is loaded
    assert (agent_root / "config.json").read_text("utf-8") == disk_config


@pytest.mark.parametrize(
    "classify_body",
    [None, "<!-- not written yet -->"],
    ids=["fetch returns 404", "empty after comment stripping"],
)
def test_bootstrap_layers_fetched_prompts_over_the_default_prompts(
    monkeypatch: pytest.MonkeyPatch,
    defaults_dir: Path,
    caplog: pytest.LogCaptureFixture,
    classify_body: str | None,
) -> None:
    # Test: Prompt precedence in `bootstrap_config_from_url` when a configured
    #   prompt is unusable.
    # Situation: `defaults_dir` holds all four default prompts. `CONFIG_URL`
    #   serves a document with an inline `synthesis` prompt;
    #   `prompts/discovery.md` and `prompts/synthesis.md` are served,
    #   `prompts/classify.md` answers 404 or contains only an HTML comment, and
    #   `prompts/follow_up.md` is unreachable.
    # Expectation: `classify` and `follow_up` carry the default bodies,
    #   `discovery` carries the fetched body, and `synthesis` carries the inline
    #   body. The unusable fetches are logged as warnings and no error is
    #   logged.
    monkeypatch.setenv("CONFIG_URL", _CONFIG_URL)
    _write_defaults(defaults_dir, {}, _DEFAULT_PROMPTS)
    monkeypatch.setattr(
        config,
        "_fetch_gcs_url",
        _UrlFetch(
            {
                _CONFIG_URL: json.dumps(
                    {"prompts": {"synthesis": "Inline synthesis."}}
                ),
                f"{_PROMPTS_URL}/classify.md": classify_body,
                f"{_PROMPTS_URL}/discovery.md": "Fetched discovery.",
                f"{_PROMPTS_URL}/synthesis.md": "Fetched synthesis.",
            }
        ),
    )

    with caplog.at_level("WARNING"):
        config.bootstrap_config_from_url()

    assert config.load_config() == AgentConfig(
        prompts=Prompts(
            classify="Default classify.",
            discovery="Fetched discovery.",
            synthesis="Inline synthesis.",
            follow_up="Default follow_up.",
        )
    )
    warning_messages = [
        r.getMessage() for r in caplog.records if r.levelname == "WARNING"
    ]
    assert any("'classify'" in message for message in warning_messages)
    assert any("'follow_up'" in message for message in warning_messages)
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_load_config_layers_config_json_over_the_default_prompts(
    agent_root: Path,
    defaults_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Default prompts on the `agent_root/config.json` path.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` has no
    #   `prompts` key, and `defaults_dir` holds all four default prompts.
    # Expectation: `load_config` returns the file's own settings with every
    #   prompt slot carrying the default body, and no error is logged.
    (agent_root / "config.json").write_text(
        '{"template_vars": {"name": "Disk"}}', "utf-8"
    )
    _write_defaults(defaults_dir, {}, _DEFAULT_PROMPTS)

    with caplog.at_level("WARNING"):
        loaded = config.load_config()

    assert loaded == AgentConfig(
        template_vars={"name": "Disk"}, prompts=Prompts(**_DEFAULT_PROMPTS)
    )
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_load_config_warns_about_an_unknown_inline_prompt_slot(
    agent_root: Path,
    defaults_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Inline `prompts` keys outside `PROMPT_SLOTS` in `_layer_prompts`.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` carries an
    #   inline prompt under the misspelled key `classfy`, and `defaults_dir`
    #   holds all four default prompts.
    # Expectation: The misspelled key is dropped and a warning names it along
    #   with the valid slots; `classify` carries the default body, and no error
    #   is logged.
    (agent_root / "config.json").write_text(
        json.dumps({"prompts": {"classfy": "Typo."}}), "utf-8"
    )
    _write_defaults(defaults_dir, {}, _DEFAULT_PROMPTS)

    with caplog.at_level("WARNING"):
        loaded = config.load_config()

    assert loaded == AgentConfig(prompts=Prompts(**_DEFAULT_PROMPTS))
    warning_messages = [
        r.getMessage() for r in caplog.records if r.levelname == "WARNING"
    ]
    assert any(
        "'classfy'" in message and "'classify'" in message
        for message in warning_messages
    )
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


@pytest.mark.parametrize(
    ("prompts_value", "expected_key"),
    [
        ("not-an-object", "'prompts'"),
        ({"classify": 123}, "'prompts.classify'"),
        ({"classify": "   "}, "'prompts.classify'"),
    ],
    ids=["section not an object", "slot not a string", "slot blank"],
)
def test_load_config_warns_about_an_unusable_inline_prompt(
    agent_root: Path,
    defaults_dir: Path,
    caplog: pytest.LogCaptureFixture,
    prompts_value: object,
    expected_key: str,
) -> None:
    # Test: Unusable inline `prompts` values in `_layer_prompts`.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` has a
    #   non-object `prompts` section or a `classify` entry that is not a
    #   non-empty string, and `defaults_dir` holds all four default prompts.
    # Expectation: Every slot carries the default body, one warning names the
    #   unusable key, and no error is logged.
    (agent_root / "config.json").write_text(
        json.dumps({"prompts": prompts_value}), "utf-8"
    )
    _write_defaults(defaults_dir, {}, _DEFAULT_PROMPTS)

    with caplog.at_level("WARNING"):
        loaded = config.load_config()

    assert loaded == AgentConfig(prompts=Prompts(**_DEFAULT_PROMPTS))
    warning_messages = [
        r.getMessage() for r in caplog.records if r.levelname == "WARNING"
    ]
    assert [expected_key in message for message in warning_messages] == [True]
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


@pytest.mark.parametrize(
    "bodies",
    [{}, {_CONFIG_URL: "{not json"}, {_CONFIG_URL: "[1, 2]"}],
    ids=["unreachable", "malformed", "not an object"],
)
def test_bootstrap_holds_no_config_for_an_unusable_response(
    monkeypatch: pytest.MonkeyPatch,
    agent_root: Path,
    defaults_dir: Path,
    bodies: dict[str, str],
) -> None:
    # Test: `bootstrap_config_from_url` when `CONFIG_URL` does not return a JSON
    #   object.
    # Situation: Fetching `CONFIG_URL` raises an error, returns invalid JSON, or
    #   returns a JSON array, while valid configurations exist in `agent_root`
    #   and `defaults_dir`.
    # Expectation: `load_config` returns `None` rather than falling back to
    #   local files, and `agent_root/config.json` is not modified.
    monkeypatch.setenv("CONFIG_URL", _CONFIG_URL)
    monkeypatch.setattr(config, "_fetch_gcs_url", _UrlFetch(bodies))
    disk_config = '{"template_vars": {"name": "Disk"}}'
    (agent_root / "config.json").write_text(disk_config, encoding="utf-8")
    _write_defaults(defaults_dir, {"template_vars": {"name": "Shipped"}}, {})

    config.bootstrap_config_from_url()

    assert config.load_config() is None
    assert (agent_root / "config.json").read_text("utf-8") == disk_config


def test_load_config_reads_config_json_before_the_defaults(
    agent_root: Path, defaults_dir: Path
) -> None:
    # Test: Precedence of `agent_root/config.json` over `defaults_dir`.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` exists, and
    #   `defaults_dir` contains a different configuration.
    # Expectation: `load_config` returns the configuration parsed from
    #   `agent_root/config.json`, and the same instance while the file is
    #   unchanged.
    config_path = agent_root / "config.json"
    config_path.write_text('{"template_vars": {"name": "Disk"}}', "utf-8")
    _write_defaults(defaults_dir, {"template_vars": {"name": "Shipped"}}, {})

    loaded = config.load_config()

    assert loaded == AgentConfig(template_vars={"name": "Disk"})
    assert config.load_config() is loaded


def test_bootstrap_without_config_url_releases_the_other_sources(
    monkeypatch: pytest.MonkeyPatch, agent_root: Path
) -> None:
    # Test: `bootstrap_config_from_url` when `CONFIG_URL` is unset.
    # Situation: An earlier bootstrap with `CONFIG_URL` set failed, so
    #   `load_config` returns `None`; the variable is then unset and
    #   `bootstrap_config_from_url` runs again, with `agent_root/config.json`
    #   present.
    # Expectation: The second bootstrap clears the `CONFIG_URL` state, and
    #   `load_config` reads `agent_root/config.json`.
    monkeypatch.setattr(config, "_bootstrapped", True)
    monkeypatch.setattr(config, "_bootstrapped_config", None)
    (agent_root / "config.json").write_text(
        '{"template_vars": {"name": "Disk"}}', "utf-8"
    )
    assert config.load_config() is None

    config.bootstrap_config_from_url()

    assert config.load_config() == AgentConfig(template_vars={"name": "Disk"})


def test_load_config_rereads_config_json_when_it_changes(
    agent_root: Path,
) -> None:
    # Test: Reloading `agent_root/config.json` when its modification time
    #   changes.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` is loaded once,
    #   and the file is then updated with a newer modification time.
    # Expectation: `load_config` returns the updated configuration.
    config_path = agent_root / "config.json"
    config_path.write_text('{"template_vars": {"name": "First"}}', "utf-8")
    assert config.load_config() == AgentConfig(template_vars={"name": "First"})

    config_path.write_text('{"template_vars": {"name": "Second"}}', "utf-8")
    later = config_path.stat().st_mtime + 10
    os.utime(config_path, (later, later))

    assert config.load_config() == AgentConfig(template_vars={"name": "Second"})


@pytest.mark.parametrize(
    "raw_bytes",
    [b"{not json", b"[1, 2]", b"\xff"],
    ids=["malformed", "not an object", "not UTF-8"],
)
def test_load_config_is_none_when_config_json_is_unreadable(
    agent_root: Path,
    defaults_dir: Path,
    raw_bytes: bytes,
) -> None:
    # Test: `load_config` when `agent_root/config.json` becomes invalid or is
    #   not a JSON object.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` is first loaded
    #   with a valid configuration and then overwritten with malformed JSON, a
    #   JSON array, or invalid UTF-8 bytes, while `defaults_dir` holds a valid
    #   configuration.
    # Expectation: `load_config` clears `_config_cache` and returns `None`
    #   rather than raising an exception or falling back to `defaults_dir`.
    config_path = agent_root / "config.json"
    config_path.write_text('{"template_vars": {"name": "Initial"}}', "utf-8")
    assert config.load_config() == AgentConfig(
        template_vars={"name": "Initial"}
    )

    config_path.write_bytes(raw_bytes)
    later = config_path.stat().st_mtime + 10
    os.utime(config_path, (later, later))
    _write_defaults(defaults_dir, {"template_vars": {"name": "Shipped"}}, {})

    assert config.load_config() is None
    assert config._config_cache is None


def test_load_config_falls_back_to_the_defaults_dir(
    agent_root: Path, defaults_dir: Path
) -> None:
    # Test: Fallback to `defaults_dir` when `CONFIG_URL` and `config.json` are
    #   absent.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` does not exist,
    #   and `defaults_dir` contains `agent-config.json` and `prompts/*.md`.
    # Expectation: `load_config` returns the merged configuration from
    #   `defaults_dir`, stripping HTML comments from prompt files and keeping
    #   inline prompt overrides, and returns the same instance on the next
    #   call.
    _write_defaults(
        defaults_dir,
        {
            "template_vars": {"name": "Shipped"},
            "prompts": {"synthesis": "Inline synthesis."},
        },
        {
            "discovery": "Shipped discovery.\n<!-- keep in sync -->\nCite.",
            "synthesis": "File synthesis.",
            "follow_up": "<!-- not written yet -->",
        },
    )

    loaded = config.load_config()

    assert loaded == AgentConfig(
        template_vars={"name": "Shipped"},
        prompts=Prompts(
            discovery="Shipped discovery.\n\nCite.",
            synthesis="Inline synthesis.",
        ),
    )
    assert config.load_config() is loaded


@pytest.mark.parametrize(
    "discovery_bytes",
    [b"\xff", b"<!-- not written yet -->"],
    ids=["not UTF-8", "empty after comment stripping"],
)
def test_load_config_reports_an_unusable_default_prompt_as_an_error(
    agent_root: Path,
    defaults_dir: Path,
    caplog: pytest.LogCaptureFixture,
    discovery_bytes: bytes,
) -> None:
    # Test: `load_config` when a default prompt file yields no body and no
    #   configured prompt covers that slot.
    # Situation: `defaults_dir/agent-config.json` and the default `classify`,
    #   `synthesis`, and `follow_up` prompts are valid, while
    #   `prompts/discovery.md` contains invalid UTF-8 bytes or only an HTML
    #   comment.
    # Expectation: `load_config` returns the parsed `agent-config.json` with
    #   the three valid slots and an empty `discovery` slot, logs a warning
    #   naming `discovery.md`, and logs one error naming exactly `['discovery']`
    #   and the default prompts directory.
    valid_prompts = {
        slot: body
        for slot, body in _DEFAULT_PROMPTS.items()
        if slot != "discovery"
    }
    _write_defaults(
        defaults_dir, {"template_vars": {"name": "Shipped"}}, valid_prompts
    )
    (defaults_dir / "prompts" / "discovery.md").write_bytes(discovery_bytes)

    with caplog.at_level("WARNING"):
        loaded = config.load_config()

    assert loaded == AgentConfig(
        template_vars={"name": "Shipped"}, prompts=Prompts(**valid_prompts)
    )
    assert "discovery.md" in caplog.text
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "'discovery'" in errors[0]
    assert not any(f"'{slot}'" in errors[0] for slot in valid_prompts)
    assert str(defaults_dir / "prompts") in errors[0]


@pytest.mark.parametrize(
    "config_bytes",
    [None, b"{not json", b"[1, 2]", b"\xff"],
    ids=["missing", "malformed", "not an object", "not UTF-8"],
)
def test_load_config_is_none_when_the_defaults_are_unreadable(
    agent_root: Path,
    defaults_dir: Path,
    caplog: pytest.LogCaptureFixture,
    config_bytes: bytes | None,
) -> None:
    # Test: `load_config` when `defaults_dir` does not contain a readable
    #   configuration.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` is absent,
    #   `defaults_dir/prompts/discovery.md` is valid, and
    #   `defaults_dir/agent-config.json` is missing, invalid JSON, not a JSON
    #   object, or not valid UTF-8.
    # Expectation: `load_config` returns `None`, without the default prompts,
    #   logs a warning or error referencing `defaults_dir` once, and does not
    #   read the directory again on the next call.
    if config_bytes is not None:
        (defaults_dir / "agent-config.json").write_bytes(config_bytes)
    (defaults_dir / "prompts").mkdir()
    (defaults_dir / "prompts" / "discovery.md").write_bytes(
        b"Shipped discovery."
    )

    with caplog.at_level("WARNING"):
        loaded = config.load_config()
        again = config.load_config()

    assert loaded is None
    assert again is None
    assert [str(defaults_dir) in r.getMessage() for r in caplog.records] == [
        True
    ]


def test_load_config_reports_a_value_of_the_wrong_type_once(
    agent_root: Path,
    defaults_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: `load_config` when the document holds values of the wrong type.
    # Situation: `CONFIG_URL` is unset, `agent_root/config.json` sets
    #   `thinking` to the string `"high"` and `mcp.enabled` to the string
    #   `"yes"` beside a valid `gemini.discovery_model`, and `defaults_dir`
    #   holds all four default prompts.
    # Expectation: `load_config` returns a configuration rather than `None`,
    #   with the configured model, the default thinking levels, and `enabled`
    #   left `True`; one warning names `thinking`, one names `mcp.enabled`,
    #   and no error is logged.
    (agent_root / "config.json").write_text(
        json.dumps(
            {
                "gemini": {"discovery_model": "gemini-test"},
                "thinking": "high",
                "mcp": {"enabled": "yes"},
            }
        ),
        "utf-8",
    )
    _write_defaults(defaults_dir, {}, _DEFAULT_PROMPTS)

    with caplog.at_level("WARNING"):
        loaded = config.load_config()

    assert loaded == AgentConfig(
        gemini=GeminiConfig(discovery_model="gemini-test"),
        mcp=McpConfig(enabled=True),
        thinking=ThinkingLevels(),
        prompts=Prompts(**_DEFAULT_PROMPTS),
    )
    warning_messages = [
        r.getMessage() for r in caplog.records if r.levelname == "WARNING"
    ]
    assert sum("'thinking'" in message for message in warning_messages) == 1
    assert sum("'mcp.enabled'" in message for message in warning_messages) == 1
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


# --- prompt datetime rendering ----------------------------------------------


def test_unresolvable_timezone_falls_back_to_utc(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Fallback to `UTC` in `get_current_datetime` on an invalid timezone.
    # Situation: The `TIMEZONE` environment variable is set to an unknown IANA
    #   timezone identifier (`"Mars/Olympus_Mons"`).
    # Expectation: `get_current_datetime` logs a warning and returns a timestamp
    #   formatted in `UTC` without raising an exception.
    monkeypatch.setenv("TIMEZONE", "Mars/Olympus_Mons")
    with caplog.at_level("WARNING"):
        result = config.get_current_datetime()
    assert result.endswith("UTC")
    assert "Mars/Olympus_Mons" in caplog.text


class _SignalingSecretCache(dict[str, tuple[float, str]]):
    """Secret cache that sets an event when a lookup returns no entry."""

    def __init__(self) -> None:
        super().__init__()
        self.missed = threading.Event()

    def get(  # type: ignore[override]
        self, key: str, default: tuple[float, str] | None = None
    ) -> tuple[float, str] | None:
        value = super().get(key, default)
        if value is None:
            self.missed.set()
        return value


def test_a_waiting_thread_reuses_the_key_loaded_while_it_waited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Concurrent cache misses share one Secret Manager request.
    # Situation: The test holds `_secret_manager_lock` as if another thread
    #   were loading the key. A worker thread misses the empty cache and waits
    #   on the lock; the test then stores a key, as the loading thread would,
    #   and releases the lock.
    # Expectation: The worker returns the stored key without creating a
    #   Secret Manager client itself.
    clients: list[object] = []

    class _StubSecretModule:
        @staticmethod
        def SecretManagerServiceClient() -> object:  # noqa: N802
            clients.append(object())
            raise AssertionError("Secret Manager must not be called")

    secret_path = "projects/test-proj/secrets/gemini-key/versions/latest"
    cache = _SignalingSecretCache()
    monkeypatch.setattr(config, "_SECRET_MANAGER_AVAILABLE", True)
    monkeypatch.setattr(
        config, "secretmanager", _StubSecretModule, raising=False
    )
    monkeypatch.setattr(config, "_secret_manager_cache", cache)
    result: list[str] = []

    with config._secret_manager_lock:
        worker = threading.Thread(
            target=lambda: result.append(
                config._fetch_key_from_secret_manager(secret_path)
            )
        )
        worker.start()
        assert cache.missed.wait(timeout=5)
        cache[secret_path] = (float("inf"), "loaded-key")
    worker.join(timeout=5)

    assert result == ["loaded-key"]
    assert clients == []

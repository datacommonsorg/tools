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
"""Tests for how `Settings` reads the environment.

Verifies that `Settings`:
1. Strips surrounding whitespace from values of every field type.
2. Treats a variable that is empty or only whitespace as unset.
3. Strips trailing slashes from the API prefix, so "/" selects the root prefix.
4. Derives the default `static_root` from `agent_root`, and rejects a
   `static_root` that equals or contains `agent_root`.
5. Reads `defaults_dir` from the environment, and otherwise resolves it to
   the copy staged under `agent_root` or to the repository copy beside it.
6. Defaults `google_genai_use_vertexai` to `False`, and parses an explicit
   value after stripping and lowercasing it.
7. Leaves `enable_chat` `None` and `unavailable_title` and
   `unavailable_message` empty when their variables are unset, and parses an
   explicit value.
8. Rejects a port that is not a number.
9. Reads `transcript_hmac_secret` without revealing it in `repr()` output, and
   rejects a value shorter than `MIN_SECRET_BYTES`.
10. Leaves `debug_report` `None` when its variable is unset, normalizes
    "off", "on", and "flag" case-insensitively, and rejects unrecognized
    modes.
11. Defaults `build_sha` to None, treating blank values as unset and
    stripping surrounding whitespace.
12. Defaults the chart host settings to public Data Commons, accepts http(s)
    overrides, trims a trailing slash from the API root, and rejects a value
    that is not an http(s) URL on an ASCII hostname, an API root that is not
    an origin, and a value with a character that cannot enter a header.
13. Defaults `recaptcha_session_site_key` and `recaptcha_checkbox_site_key` to
    empty strings, treating blank values as unset and stripping surrounding
    whitespace.
14. Defaults `daily_token_budget_per_instance` to `None`, parses positive
    integers with surrounding whitespace stripped, and rejects zero, negative,
    or non-integer values.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from narratives_agent.settings import (
    DAILY_TOKEN_BUDGET_PER_INSTANCE_ENV,
    DC_API_KEY_SECRET_ENV,
    DC_WEB_COMPONENT_API_ROOT_ENV,
    DC_WEB_COMPONENT_URL_ENV,
    DEBUG_REPORT_ENV,
    DEFAULT_WEB_COMPONENT_API_ROOT,
    DEFAULT_WEB_COMPONENT_URL,
    ENABLE_CHAT_ENV,
    MIN_SECRET_BYTES,
    RECAPTCHA_CHECKBOX_SITE_KEY_ENV,
    RECAPTCHA_SESSION_SITE_KEY_ENV,
    TRANSCRIPT_HMAC_SECRET_ENV,
    TRANSCRIPT_HMAC_SECRET_NAME_ENV,
    UNAVAILABLE_MESSAGE_ENV,
    UNAVAILABLE_TITLE_ENV,
    Settings,
    get_url_origin,
    validate_hmac_secret,
)

# Matches the shape of a Google API key while using explicit
# test/dummy/example/fake tokens to avoid secret-scanner false alarms.
_KEY_SHAPED = "AIza_test_dummy_example_fake_key_0000"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsets every variable `Settings` reads.

    Each test then starts from the defaults, whatever the developer's shell
    exports.
    """
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


def _read_settings(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> Settings:
    """Returns the settings read after exporting every variable in `env`."""
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings()


@pytest.mark.parametrize(
    ("name", "raw", "expected"),
    [
        pytest.param("DC_API_KEY", f" {_KEY_SHAPED}\n", _KEY_SHAPED, id="str"),
        pytest.param("TIMEZONE", "\tAsia/Tokyo ", "Asia/Tokyo", id="tab"),
        pytest.param(
            "GOOGLE_CLOUD_LOCATION",
            " europe-west4\n",
            "europe-west4",
            id="location",
        ),
        pytest.param(
            "MODEL_ARMOR_TEMPLATE",
            " projects/p/locations/us-central1/templates/t\n",
            "projects/p/locations/us-central1/templates/t",
            id="model-armor-template",
        ),
        pytest.param("AGENT_PORT", " 6001 ", 6001, id="int"),
        pytest.param(
            "STATIC_ROOT", " /srv/ui/dist ", Path("/srv/ui/dist"), id="path"
        ),
    ],
)
def test_values_are_stripped_of_whitespace(
    monkeypatch: pytest.MonkeyPatch, name: str, raw: str, expected: object
) -> None:
    # Test: Whitespace handling for string, integer, and path fields.
    # Situation: A variable is exported with surrounding spaces, a tab, or a
    #   newline.
    # Expectation: The field holds the value without the surrounding
    #   whitespace, parsed as the field's type.
    settings = _read_settings(monkeypatch, {name: raw})
    assert getattr(settings, name.lower()) == expected


@pytest.mark.parametrize(
    "raw", [pytest.param("", id="empty"), pytest.param(" \t ", id="blank")]
)
@pytest.mark.parametrize("field", list(Settings.model_fields))
def test_blank_variable_counts_as_unset(
    monkeypatch: pytest.MonkeyPatch, field: str, raw: str
) -> None:
    # Test: Handling of a variable that is empty or only whitespace.
    # Situation: The variable a field reads is exported as the empty string or
    #   as spaces around a tab.
    # Expectation: The field holds the same value as when the variable is
    #   unset.
    unset = getattr(Settings(), field)
    settings = _read_settings(monkeypatch, {field.upper(): raw})
    assert getattr(settings, field) == unset


@pytest.mark.parametrize(
    ("name", "raw", "expected"),
    [
        pytest.param("AGENT_API_PREFIX", "/agent/", "/agent", id="prefix"),
        pytest.param(
            "AGENT_API_PREFIX",
            "/agent//",
            "/agent",
            id="repeated-slashes",
        ),
        pytest.param("AGENT_API_PREFIX", "/", "", id="root-prefix"),
        pytest.param(
            "BASE_PATH", "/narratives/", "/narratives", id="base-path"
        ),
        pytest.param(
            "BASE_PATH",
            "narratives/",
            "/narratives",
            id="base-path-missing-leading-slash",
        ),
        pytest.param("BASE_PATH", "/", "", id="root-base-path"),
        pytest.param(
            "BASE_PATH",
            "//narratives//",
            "/narratives",
            id="base-path-repeated-slashes",
        ),
        pytest.param(
            "BASE_PATH",
            "/labs/discover/",
            "/labs/discover",
            id="nested-base-path",
        ),
    ],
)
def test_trailing_slashes_are_stripped(
    monkeypatch: pytest.MonkeyPatch, name: str, raw: str, expected: str
) -> None:
    # Test: Normalization of URL path prefixes (`AGENT_API_PREFIX`,
    #   `BASE_PATH`).
    # Situation: A variable ends in one or more slashes, omits the leading
    #   slash, or is "/" alone.
    # Expectation: The field holds the value with a leading slash and without
    #   trailing slashes, and "/" yields the empty prefix for the root.
    settings = _read_settings(monkeypatch, {name: raw})
    assert getattr(settings, name.lower()) == expected


def test_static_root_follows_agent_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Test: Default of `static_root` when `AGENT_ROOT` is overridden.
    # Situation: `AGENT_ROOT` names another directory and `STATIC_ROOT` is
    #   unset.
    # Expectation: `static_root` sits at the same place under the new
    #   `agent_root` as the default `static_root` does under the default
    #   `agent_root`.
    default = Settings()
    settings = _read_settings(monkeypatch, {"AGENT_ROOT": str(tmp_path)})
    assert settings.agent_root == tmp_path
    assert settings.static_root == tmp_path / default.static_root.relative_to(
        default.agent_root
    )


@pytest.mark.parametrize(
    ("static_root", "is_rejected"),
    [
        pytest.param(None, False, id="default"),
        pytest.param(".", True, id="agent-root"),
        pytest.param("..", True, id="parent-of-agent-root"),
    ],
)
def test_static_root_must_not_contain_agent_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    static_root: str | None,
    is_rejected: bool,
) -> None:
    # Test: Containment check between `static_root` and `agent_root`.
    # Situation: `AGENT_ROOT` names a directory under `tmp_path`, and
    #   `STATIC_ROOT` is unset, names `AGENT_ROOT` itself, or names its parent.
    # Expectation: The default is accepted. `AGENT_ROOT` itself and its parent
    #   are rejected with a `ValidationError` naming `STATIC_ROOT`, because
    #   serving either would publish config.json.
    agent_root = tmp_path / "agent"
    env = {"AGENT_ROOT": str(agent_root)}
    if static_root is not None:
        env["STATIC_ROOT"] = str(agent_root / static_root)
    if is_rejected:
        with pytest.raises(ValidationError, match="STATIC_ROOT"):
            _read_settings(monkeypatch, env)
    else:
        settings = _read_settings(monkeypatch, env)
        assert settings.static_root == agent_root / "static"


def test_defaults_dir_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Test: Explicit `DEFAULTS_DIR` environment variable override.
    # Situation: `DEFAULTS_DIR` is set to an explicit path while `agent_root`
    #   also contains a `defaults/` subdirectory.
    # Expectation: `defaults_dir` resolves to the explicit `DEFAULTS_DIR` path.
    agent_root = tmp_path / "agent"
    (agent_root / "defaults").mkdir(parents=True)
    explicit = tmp_path / "elsewhere"
    settings = _read_settings(
        monkeypatch,
        {"AGENT_ROOT": str(agent_root), "DEFAULTS_DIR": str(explicit)},
    )
    assert settings.defaults_dir == explicit


def test_defaults_dir_prefers_the_copy_staged_under_agent_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Test: Default `defaults_dir` when `agent_root/defaults` exists.
    # Situation: `DEFAULTS_DIR` is unset and `agent_root/defaults` exists.
    # Expectation: `defaults_dir` resolves to `agent_root/defaults`.
    agent_root = tmp_path / "agent"
    (agent_root / "defaults").mkdir(parents=True)
    settings = _read_settings(monkeypatch, {"AGENT_ROOT": str(agent_root)})
    assert settings.defaults_dir == agent_root / "defaults"


def test_defaults_dir_falls_back_to_the_repository_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Test: Default `defaults_dir` when `agent_root/defaults` does not exist.
    # Situation: `DEFAULTS_DIR` is unset and `agent_root/defaults` is absent.
    # Expectation: `defaults_dir` resolves to `../defaults` relative to
    #   `agent_root`.
    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    settings = _read_settings(monkeypatch, {"AGENT_ROOT": str(agent_root)})
    assert settings.defaults_dir == tmp_path / "defaults"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, False, id="unset"),
        pytest.param(" TRUE ", True, id="padded-true"),
        pytest.param("yes", True, id="yes"),
        pytest.param("1", True, id="one"),
        pytest.param(" 0 ", False, id="padded-zero"),
        pytest.param("false", False, id="false"),
        pytest.param("on", False, id="unrecognized"),
    ],
)
def test_google_genai_use_vertexai_parses_truthy_values(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: bool
) -> None:
    # Test: Default and parsing of `GOOGLE_GENAI_USE_VERTEXAI`.
    # Situation: `GOOGLE_GENAI_USE_VERTEXAI` is unset, or set to a truthy or
    #   non-truthy string, with or without surrounding whitespace.
    # Expectation: When unset or set to any value other than "1", "true", or
    #   "yes" (in any case), Vertex AI mode is disabled; those three values
    #   enable it.
    env = {} if raw is None else {"GOOGLE_GENAI_USE_VERTEXAI": raw}
    settings = _read_settings(monkeypatch, env)
    assert settings.google_genai_use_vertexai is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, None, id="unset"),
        pytest.param("", None, id="empty"),
        pytest.param(" \t ", None, id="blank"),
        pytest.param(" TRUE ", True, id="padded-true"),
        pytest.param("yes", True, id="yes"),
        pytest.param("1", True, id="one"),
        pytest.param(" 0 ", False, id="padded-zero"),
        pytest.param("false", False, id="false"),
        pytest.param("no", False, id="no"),
    ],
)
def test_enable_chat_is_none_when_unset_and_parses_env_values(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: bool | None
) -> None:
    # Test: Default and parsing of `ENABLE_CHAT`.
    # Situation: `ENABLE_CHAT` is unset, empty, or blank, or set to a truthy
    #   or non-truthy string, with or without surrounding whitespace.
    # Expectation: Unset, empty, and blank give `None`, which leaves
    #   `chat.enabled` in effect; "1", "true", or "yes" (in any case) give
    #   `True`; any other value gives `False`.
    env = {} if raw is None else {ENABLE_CHAT_ENV: raw}
    settings = _read_settings(monkeypatch, env)
    assert settings.enable_chat is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, "", id="unset"),
        pytest.param(" \t ", "", id="blank"),
        pytest.param(
            " Scheduled maintenance \n", "Scheduled maintenance", id="padded"
        ),
    ],
)
def test_unavailable_title_is_read_and_stripped(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: str
) -> None:
    # Test: Default and parsing of `UNAVAILABLE_TITLE`.
    # Situation: `UNAVAILABLE_TITLE` is unset, blank, or a title padded with
    #   whitespace.
    # Expectation: Unset and blank give `""`, which leaves
    #   `chat.unavailable_title` in effect; a title is stripped of its
    #   surrounding whitespace.
    env = {} if raw is None else {UNAVAILABLE_TITLE_ENV: raw}
    settings = _read_settings(monkeypatch, env)
    assert settings.unavailable_title == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, "", id="unset"),
        pytest.param(" \t ", "", id="blank"),
        pytest.param(" Back at noon. \n", "Back at noon.", id="padded"),
    ],
)
def test_unavailable_message_is_read_and_stripped(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: str
) -> None:
    # Test: Default and parsing of `UNAVAILABLE_MESSAGE`.
    # Situation: `UNAVAILABLE_MESSAGE` is unset, blank, or a message padded
    #   with whitespace.
    # Expectation: Unset and blank give `""`, which leaves
    #   `chat.unavailable_message` in effect; a message is stripped of its
    #   surrounding whitespace.
    env = {} if raw is None else {UNAVAILABLE_MESSAGE_ENV: raw}
    settings = _read_settings(monkeypatch, env)
    assert settings.unavailable_message == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, None, id="unset"),
        pytest.param("off", "off", id="off"),
        pytest.param(" OFF ", "off", id="padded-off"),
        pytest.param("on", "on", id="on"),
        pytest.param(" ON\n", "on", id="padded-on"),
        pytest.param("flag", "flag", id="flag"),
        pytest.param("\tFLAG ", "flag", id="padded-flag"),
    ],
)
def test_debug_report_is_none_when_unset_and_parses_modes(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: str | None
) -> None:
    # Test: Default and mode parsing for `DEBUG_REPORT`.
    # Situation: `DEBUG_REPORT` is unset, or set to "off", "on", or "flag"
    #   in varying cases with surrounding whitespace.
    # Expectation: Unset gives `None`, which leaves `debug.report` in
    #   effect; valid strings are parsed case-insensitively with whitespace
    #   stripped.
    env = {} if raw is None else {DEBUG_REPORT_ENV: raw}
    settings = _read_settings(monkeypatch, env)
    assert settings.debug_report == expected


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("true", id="boolean-true"),
        pytest.param("1", id="numeric-one"),
        pytest.param("verbose", id="verbose"),
        pytest.param("invalid", id="invalid"),
    ],
)
def test_invalid_debug_report_is_rejected(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    # Test: Validation of invalid `DEBUG_REPORT` modes.
    # Situation: `DEBUG_REPORT` is exported with an unrecognized value.
    # Expectation: Reading the settings raises `ValidationError` naming the
    #   field.
    monkeypatch.setenv(DEBUG_REPORT_ENV, raw)
    with pytest.raises(ValidationError, match="debug_report"):
        Settings()


@pytest.mark.parametrize("name", ["AGENT_PORT", "MCP_PORT"])
def test_non_numeric_port_is_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    # Test: Validation of a port that is not a number.
    # Situation: A port variable is exported as a non-numeric string.
    # Expectation: Reading the settings raises `ValidationError` naming the
    #   field rather than starting with an unusable port.
    monkeypatch.setenv(name, "abc")
    with pytest.raises(ValidationError, match=name.lower()):
        Settings()


def test_transcript_hmac_secret_is_read_and_masked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `TRANSCRIPT_HMAC_SECRET` is read from the environment and masked in
    #   string and `repr()` output.
    # Situation: The variable is first unset and then exported with a valid
    #   secret value.
    # Expectation: When unset, the secret is empty; when set, the secret holds
    #   the value, and neither the field's string form nor `repr(settings)`
    #   reveals it.
    assert Settings().transcript_hmac_secret.get_secret_value() == ""

    settings = _read_settings(
        monkeypatch, {TRANSCRIPT_HMAC_SECRET_ENV: _KEY_SHAPED}
    )

    assert settings.transcript_hmac_secret.get_secret_value() == _KEY_SHAPED
    assert _KEY_SHAPED not in str(settings.transcript_hmac_secret)
    assert _KEY_SHAPED not in repr(settings)


def test_a_short_transcript_hmac_secret_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `TRANSCRIPT_HMAC_SECRET` values shorter than 32 bytes are rejected.
    # Situation: The variable is exported with 31 bytes.
    # Expectation: Reading the settings raises `ValidationError` naming the
    #   variable.
    with pytest.raises(ValidationError, match=TRANSCRIPT_HMAC_SECRET_ENV):
        _read_settings(monkeypatch, {TRANSCRIPT_HMAC_SECRET_ENV: "s" * 31})


def test_secret_names_are_read_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Secret Manager reference variables are read from the environment.
    # Situation: `DC_API_KEY_SECRET` and `TRANSCRIPT_HMAC_SECRET_NAME` are
    #   exported in the environment.
    # Expectation: `settings.dc_api_key_secret` and
    #   `settings.transcript_hmac_secret_name` hold the configured names.
    settings = _read_settings(
        monkeypatch,
        {
            DC_API_KEY_SECRET_ENV: "projects/p/secrets/dc-key/versions/latest",
            TRANSCRIPT_HMAC_SECRET_NAME_ENV: "narratives-hmac-secret",
        },
    )
    assert (
        settings.dc_api_key_secret
        == "projects/p/secrets/dc-key/versions/latest"
    )
    assert settings.transcript_hmac_secret_name == "narratives-hmac-secret"


def test_validate_hmac_secret_enforces_length() -> None:
    # Test: Length validation via `validate_hmac_secret`.
    # Situation: A secret meeting `MIN_SECRET_BYTES` and a secret shorter than
    #   `MIN_SECRET_BYTES` are validated.
    # Expectation: The valid secret is returned unchanged; the short secret
    #   raises `ValueError` naming the configured source and `MIN_SECRET_BYTES`.
    valid = "s" * MIN_SECRET_BYTES
    assert validate_hmac_secret(valid, "TEST_HMAC_SECRET") == valid

    with pytest.raises(ValueError, match="TEST_HMAC_SECRET"):
        validate_hmac_secret("s" * (MIN_SECRET_BYTES - 1), "TEST_HMAC_SECRET")


def test_build_sha_defaults_to_none_and_strips_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Default and whitespace stripping for `BUILD_SHA`.
    # Situation: `BUILD_SHA` is unset, blank, or set with surrounding
    #   whitespace.
    # Expectation: Unset and blank count as None; a non-blank string is
    #   stripped.
    assert Settings().build_sha is None
    settings_blank = _read_settings(monkeypatch, {"BUILD_SHA": "   \n\t "})
    assert settings_blank.build_sha is None
    settings_set = _read_settings(monkeypatch, {"BUILD_SHA": " 3b34f1c\n"})
    assert settings_set.build_sha == "3b34f1c"


@pytest.mark.parametrize(
    ("env_name", "field_name"),
    [
        pytest.param(
            RECAPTCHA_SESSION_SITE_KEY_ENV,
            "recaptcha_session_site_key",
            id="session",
        ),
        pytest.param(
            RECAPTCHA_CHECKBOX_SITE_KEY_ENV,
            "recaptcha_checkbox_site_key",
            id="checkbox",
        ),
    ],
)
def test_recaptcha_site_keys_default_to_empty_and_strip_whitespace(
    monkeypatch: pytest.MonkeyPatch, env_name: str, field_name: str
) -> None:
    # Test: Default and whitespace stripping for reCAPTCHA site key settings.
    # Situation: `RECAPTCHA_SESSION_SITE_KEY` or `RECAPTCHA_CHECKBOX_SITE_KEY`
    #   is unset, blank, or exported with surrounding whitespace.
    # Expectation: Unset and blank resolve to `""`; a non-empty key has its
    #   surrounding whitespace stripped.
    assert getattr(Settings(), field_name) == ""
    blank_settings = _read_settings(monkeypatch, {env_name: " \t\n "})
    assert getattr(blank_settings, field_name) == ""
    configured = _read_settings(monkeypatch, {env_name: "  6Lc_site_key_01 \n"})
    assert getattr(configured, field_name) == "6Lc_site_key_01"


def test_chart_hosts_default_to_public_data_commons() -> None:
    # Test: Defaults of `DC_WEB_COMPONENT_URL` and
    #   `DC_WEB_COMPONENT_API_ROOT`.
    # Situation: Neither variable is set.
    # Expectation: The components load from datacommons.org and fetch their
    #   data from the website host.
    settings = Settings()

    assert settings.dc_web_component_url == DEFAULT_WEB_COMPONENT_URL
    assert DEFAULT_WEB_COMPONENT_URL == "https://datacommons.org/datacommons.js"
    assert settings.dc_web_component_api_root == DEFAULT_WEB_COMPONENT_API_ROOT
    assert DEFAULT_WEB_COMPONENT_API_ROOT == "https://datacommons.org"


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(
            "https://autopush.datacommons.org/datacommons.js", id="autopush"
        ),
        pytest.param("http://localhost:8080/datacommons.js", id="localhost"),
        pytest.param(
            "https://cdn.example.com/dc/datacommons.js?v=2", id="query"
        ),
    ],
)
def test_web_component_url_accepts_http_urls(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    # Test: Accepted `DC_WEB_COMPONENT_URL` overrides.
    # Situation: The variable is an https URL on another host, an http URL
    #   on localhost with a port, or a URL with a query.
    # Expectation: The field holds the value unchanged.
    settings = _read_settings(monkeypatch, {DC_WEB_COMPONENT_URL_ENV: raw})

    assert settings.dc_web_component_url == raw


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "https://autopush.datacommons.org",
            "https://autopush.datacommons.org",
            id="autopush",
        ),
        pytest.param(
            "http://localhost:8080", "http://localhost:8080", id="localhost"
        ),
        pytest.param(
            "https://data.example.org/",
            "https://data.example.org",
            id="trailing-slash",
        ),
        pytest.param(
            "HTTPS://Data.Example.org:8443",
            "https://data.example.org:8443",
            id="uppercase",
        ),
        pytest.param(
            "https://datacommons.org:443",
            "https://datacommons.org",
            id="default-https-port",
        ),
        pytest.param(
            "http://localhost:80",
            "http://localhost",
            id="default-http-port",
        ),
        pytest.param(
            "http://localhost:443",
            "http://localhost:443",
            id="non-default-port-443-on-http",
        ),
    ],
)
def test_web_component_api_root_accepts_http_origins(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str
) -> None:
    # Test: Accepted `DC_WEB_COMPONENT_API_ROOT` overrides.
    # Situation: The variable is an https origin, an http origin on
    #   localhost with a port, an origin with a trailing slash, an origin in
    #   upper case with a non-default port, or an origin naming its scheme's
    #   default port.
    # Expectation: The field holds the normalized origin in lower case, with
    #   any non-default port kept, any default port omitted, and no trailing
    #   slash.
    settings = _read_settings(monkeypatch, {DC_WEB_COMPONENT_API_ROOT_ENV: raw})

    assert settings.dc_web_component_api_root == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param(
            "https://datacommons.org:443/datacommons.js",
            "https://datacommons.org",
            id="https-default-port",
        ),
        pytest.param(
            "http://localhost:80/datacommons.js",
            "http://localhost",
            id="http-default-port",
        ),
        pytest.param(
            "https://cdn.example.com:8443/dc/datacommons.js?v=2",
            "https://cdn.example.com:8443",
            id="https-custom-port",
        ),
        pytest.param(
            "https://localhost:80/datacommons.js",
            "https://localhost:80",
            id="https-port-80",
        ),
    ],
)
def test_get_url_origin_normalizes_scheme_default_ports(
    url: str, expected: str
) -> None:
    # Test: Origin normalization in `get_url_origin`.
    # Situation: Script URLs carry a scheme's default port (`:443` on https,
    #   `:80` on http) or a non-default port alongside a path and query.
    # Expectation: Default scheme ports and URL paths/queries are stripped,
    #   while non-default ports are retained.
    assert get_url_origin(url) == expected


# Values that neither chart host setting accepts.
_INVALID_CHART_HOST_VALUES = [
    pytest.param("datacommons.org/datacommons.js", id="relative"),
    pytest.param("//datacommons.org/datacommons.js", id="scheme-relative"),
    pytest.param("javascript:alert(1)", id="javascript"),
    pytest.param("ftp://datacommons.org/datacommons.js", id="ftp"),
    pytest.param("https://", id="no-host"),
    pytest.param("https://@", id="userinfo-without-host"),
    pytest.param("https://user@datacommons.org", id="userinfo"),
    pytest.param("https://datacommons.org:99999", id="port-out-of-range"),
    pytest.param("https://[::1", id="malformed-ipv6"),
    pytest.param(
        "https://datacommons.org; script-src *", id="semicolon-and-space"
    ),
    pytest.param("https://datacommons.org;script-src", id="semicolon"),
    pytest.param("https://datacommons.org,https://evil.example", id="comma"),
    pytest.param(
        "https://datacommons.org/data;commons.js", id="path-semicolon"
    ),
    pytest.param("https://datacommons.org/data,commons.js", id="path-comma"),
    pytest.param("https://datacommons.org'", id="single-quote"),
    pytest.param('https://datacommons.org"', id="double-quote"),
    pytest.param("https://data\tcommons.org", id="tab"),
    pytest.param("https://datacommons.org\x7f", id="delete"),
    pytest.param("https://*/datacommons.js", id="wildcard-host"),
    pytest.param("https://*.example.org", id="wildcard-subdomain"),
    pytest.param("https://\u4f8b\u3048.jp/datacommons.js", id="non-ascii-host"),
    pytest.param("https://datacommons.org:", id="empty-port"),
    pytest.param("https://exa%41mple.org", id="percent-encoded-host"),
    pytest.param("https://[::1]:8080", id="ipv6-literal"),
]


@pytest.mark.parametrize("raw", _INVALID_CHART_HOST_VALUES)
@pytest.mark.parametrize(
    "variable", [DC_WEB_COMPONENT_URL_ENV, DC_WEB_COMPONENT_API_ROOT_ENV]
)
def test_chart_host_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch, variable: str, raw: str
) -> None:
    # Test: Rejection of invalid chart host settings.
    # Situation: `DC_WEB_COMPONENT_URL` or `DC_WEB_COMPONENT_API_ROOT` is not
    #   an absolute http(s) URL with a hostname, has a wildcard,
    #   percent-encoded, non-ASCII, or IPv6 host, carries user information or
    #   an empty or invalid port, or holds a semicolon, comma, quote,
    #   whitespace, or control character.
    # Expectation: Reading the settings raises `ValidationError` naming the
    #   variable, so the server does not start.
    with pytest.raises(ValidationError, match=variable):
        _read_settings(monkeypatch, {variable: raw})


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("https://datacommons.org/api", id="path"),
        pytest.param("https://datacommons.org//", id="double-slash"),
        pytest.param("https://datacommons.org?x=1", id="query"),
        pytest.param("https://datacommons.org/?", id="empty-query"),
        pytest.param("https://datacommons.org#top", id="fragment"),
    ],
)
def test_web_component_api_root_rejects_more_than_an_origin(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    # Test: Rejection of an API root that is more than an origin.
    # Situation: The variable carries a path, a query (even an empty one),
    #   or a fragment.
    # Expectation: Reading the settings raises `ValidationError` naming the
    #   variable, because the components build `<apiroot>/api/...` and a
    #   policy source with a path matches only that path.
    with pytest.raises(ValidationError, match=DC_WEB_COMPONENT_API_ROOT_ENV):
        _read_settings(monkeypatch, {DC_WEB_COMPONENT_API_ROOT_ENV: raw})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, None, id="unset"),
        pytest.param("", None, id="empty"),
        pytest.param(" \t ", None, id="blank"),
        pytest.param("1", 1, id="one"),
        pytest.param(" 50000 \n", 50000, id="padded-int"),
    ],
)
def test_daily_token_budget_is_none_when_unset_and_parses_positive_int(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: int | None
) -> None:
    # Test: Default and parsing of `DAILY_TOKEN_BUDGET_PER_INSTANCE`.
    # Situation: `DAILY_TOKEN_BUDGET_PER_INSTANCE` is unset, blank, or set to a
    #   positive integer with optional surrounding whitespace.
    # Expectation: Unset and blank yield `None` (enforcement disabled); valid
    #   positive integers are stripped and parsed as `int`.
    env = {} if raw is None else {DAILY_TOKEN_BUDGET_PER_INSTANCE_ENV: raw}
    settings = _read_settings(monkeypatch, env)
    assert settings.daily_token_budget_per_instance == expected


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("0", id="zero"),
        pytest.param("-5", id="negative"),
        pytest.param("abc", id="non-numeric"),
        pytest.param("10.5", id="decimal"),
        pytest.param("1e6", id="scientific"),
        pytest.param("true", id="boolean"),
    ],
)
def test_invalid_daily_token_budget_is_rejected(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    # Test: Validation of invalid `DAILY_TOKEN_BUDGET_PER_INSTANCE` values.
    # Situation: `DAILY_TOKEN_BUDGET_PER_INSTANCE` is set to zero, a negative
    #   integer, or a non-integer string.
    # Expectation: Reading settings raises `ValidationError` naming the field
    #   so a misconfigured pod fails fast at startup.
    monkeypatch.setenv(DAILY_TOKEN_BUDGET_PER_INSTANCE_ENV, raw)
    with pytest.raises(
        ValidationError, match="daily_token_budget_per_instance"
    ):
        Settings()

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
3. Strips trailing slashes from the API prefix and the base URLs, so "/"
   selects the root prefix.
4. Falls back to `data_plane_url` for `data_plane_web_url`.
5. Derives the default `static_root` from `agent_root`, and rejects a
   `static_root` that equals or contains `agent_root`.
6. Reads `defaults_dir` from the environment, and otherwise resolves it to
   the copy staged under `agent_root` or to the repository copy beside it.
7. Defaults `google_genai_use_vertexai` to `False`, and parses an explicit
   value after stripping and lowercasing it.
8. Rejects a port that is not a number.
9. Reads `transcript_hmac_secret` without revealing it in `repr()` output, and
   rejects a value shorter than `MIN_SECRET_BYTES`.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from narratives_agent.settings import Settings

# Matches the shape of a Google API key while using explicit
# test/dummy/example/fake tokens to avoid secret-scanner false alarms.
_KEY_SHAPED = "AIza_test_dummy_example_fake_key_0000"

_DATA_PLANE = "https://data-plane-uc.a.run.app"


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
        pytest.param("AGENT_API_PREFIX", "/", "", id="root-prefix"),
        pytest.param(
            "DATA_PLANE_URL", f"{_DATA_PLANE}/", _DATA_PLANE, id="url"
        ),
        pytest.param(
            "DATA_PLANE_WEB_URL",
            "https://datacommons.org//",
            "https://datacommons.org",
            id="repeated-slashes",
        ),
    ],
)
def test_trailing_slashes_are_stripped(
    monkeypatch: pytest.MonkeyPatch, name: str, raw: str, expected: str
) -> None:
    # Test: Trailing-slash handling for the API prefix and the base URLs.
    # Situation: A variable ends in one or more slashes, has whitespace after
    #   the slash, or is "/" alone.
    # Expectation: The field holds the value without trailing slashes, so "/"
    #   yields the empty prefix that mounts the API at the root.
    settings = _read_settings(monkeypatch, {name: raw})
    assert getattr(settings, name.lower()) == expected


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        pytest.param(
            {"DATA_PLANE_URL": f"{_DATA_PLANE}/"}, _DATA_PLANE, id="unset"
        ),
        pytest.param(
            {"DATA_PLANE_URL": f"{_DATA_PLANE}/", "DATA_PLANE_WEB_URL": ""},
            _DATA_PLANE,
            id="empty",
        ),
        pytest.param(
            {"DATA_PLANE_URL": f"{_DATA_PLANE}/", "DATA_PLANE_WEB_URL": "/"},
            _DATA_PLANE,
            id="slash-only",
        ),
        pytest.param(
            {
                "DATA_PLANE_URL": "https://api.datacommons.org",
                "DATA_PLANE_WEB_URL": "https://datacommons.org",
            },
            "https://datacommons.org",
            id="split-hosts",
        ),
    ],
)
def test_data_plane_web_url_falls_back_to_data_plane_url(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected: str
) -> None:
    # Test: Resolution of `data_plane_web_url`.
    # Situation: `DATA_PLANE_URL` is set, and `DATA_PLANE_WEB_URL` is unset,
    #   empty, only a slash, or names a host of its own.
    # Expectation: The web URL is the normalized `data_plane_url` unless
    #   `DATA_PLANE_WEB_URL` names a host of its own.
    settings = _read_settings(monkeypatch, env)
    assert settings.data_plane_web_url == expected


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
        monkeypatch, {"TRANSCRIPT_HMAC_SECRET": _KEY_SHAPED}
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
    with pytest.raises(ValidationError, match="TRANSCRIPT_HMAC_SECRET"):
        _read_settings(monkeypatch, {"TRANSCRIPT_HMAC_SECRET": "s" * 31})

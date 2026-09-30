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
6. Defaults `session_log_to_file` by `K_SERVICE`, and parses an explicit value
   after stripping and lowercasing it.
7. Rejects a port that is not a number.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from narratives_agent.settings import Settings

# Matches the shape of a Google API key while using explicit
# test/dummy/example/fake tokens to avoid secret-scanner false alarms.
_KEY_SHAPED = "AIza_test_dummy_example_fake_key_0000"

_CLOUD_RUN_SERVICE = "narratives-agent"
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
        pytest.param(
            "BRAND_CONFIG_URL",
            " https://storage.googleapis.com/test-brand-bucket/ ",
            "https://storage.googleapis.com/test-brand-bucket",
            id="padded",
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


@pytest.mark.parametrize(
    ("k_service", "expected"),
    [
        pytest.param("", True, id="off-cloud-run"),
        pytest.param(_CLOUD_RUN_SERVICE, False, id="on-cloud-run"),
    ],
)
def test_session_log_to_file_default_depends_on_k_service(
    monkeypatch: pytest.MonkeyPatch, k_service: str, expected: bool
) -> None:
    # Test: Default of `session_log_to_file`.
    # Situation: `SESSION_LOG_TO_FILE` is unset, and `K_SERVICE` is empty, as
    #   off Cloud Run, or names a service, as on Cloud Run.
    # Expectation: Session logs go to files off Cloud Run only.
    settings = _read_settings(monkeypatch, {"K_SERVICE": k_service})
    assert settings.session_log_to_file is expected


@pytest.mark.parametrize(
    ("k_service", "raw", "expected"),
    [
        pytest.param(_CLOUD_RUN_SERVICE, " TRUE ", True, id="padded-true"),
        pytest.param(_CLOUD_RUN_SERVICE, "yes", True, id="yes"),
        pytest.param(_CLOUD_RUN_SERVICE, "1", True, id="one"),
        pytest.param("", " 0 ", False, id="padded-zero"),
        pytest.param("", "false", False, id="false"),
        pytest.param("", "on", False, id="unrecognized"),
    ],
)
def test_session_log_to_file_explicit_value_overrides_default(
    monkeypatch: pytest.MonkeyPatch, k_service: str, raw: str, expected: bool
) -> None:
    # Test: Parsing of an explicit `SESSION_LOG_TO_FILE`.
    # Situation: `SESSION_LOG_TO_FILE` is set, padded or not, where the default
    #   is the opposite value: on Cloud Run for values that turn file logging
    #   on, and off Cloud Run for the rest.
    # Expectation: "1", "true", and "yes", in any case, turn file logging on;
    #   any other value turns it off.
    settings = _read_settings(
        monkeypatch, {"K_SERVICE": k_service, "SESSION_LOG_TO_FILE": raw}
    )
    assert settings.session_log_to_file is expected


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

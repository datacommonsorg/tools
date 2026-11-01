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
"""Tests for host-based credential selection in `gcp_auth`.

Verifies that `attach_auth` selects credentials based on the target URL:
- Allowlisted public Data Commons hosts receive the `X-API-Key` header.
- Plain HTTP localhost URLs (sidecar deployments) receive no auth headers.
- Unlisted external HTTPS hosts receive no credential, preventing a modified
  remote configuration from leaking the API key to an arbitrary host.
- Setting `DATA_PLANE_AUTH=off` disables credential attachment entirely.
"""

import pytest

from narratives_agent import gcp_auth
from narratives_agent.settings import (
    DC_API_KEY_ENV,
    DC_API_KEY_SECRET_ENV,
)

_API_KEY = "test-key-123"


@pytest.fixture(autouse=True)
def credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure test credentials and clear `DATA_PLANE_AUTH`.

    When `DATA_PLANE_AUTH=off` is set in the environment, `attach_auth` exits
    early without attaching any headers. Clearing `DATA_PLANE_AUTH` ensures
    the credential-selection logic is exercised regardless of the caller's
    shell environment.
    """
    monkeypatch.delenv("DATA_PLANE_AUTH", raising=False)
    monkeypatch.setenv(DC_API_KEY_ENV, _API_KEY)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.datacommons.org/mcp",
        "https://autopush.api.datacommons.org/mcp",
        "https://dev.api.datacommons.org/mcp",
        "https://staging.api.datacommons.org/mcp",
        "https://datacommons.org/api",
    ],
)
def test_public_data_commons_gets_the_api_key(url: str) -> None:
    # Test: Credential selection for public Data Commons endpoints.
    # Situation: The target URL points to an allowlisted public Data Commons
    #   host (`api.datacommons.org`, `autopush.api.datacommons.org`,
    #   `staging.api.datacommons.org`, or `datacommons.org`).
    # Expectation: `attach_auth` sets the `X-API-Key` header to `DC_API_KEY`
    #   and does not attach an `Authorization` Bearer token.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, url)
    assert headers == {"X-API-Key": _API_KEY}


def test_local_http_target_gets_no_credential() -> None:
    # Test: Credential selection for a local HTTP sidecar endpoint.
    # Situation: The target URL uses plain HTTP on localhost.
    # Expectation: `attach_auth` leaves the headers dictionary empty.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "http://localhost:8082/mcp")
    assert headers == {}


def test_api_key_is_not_sent_to_an_unlisted_host() -> None:
    # Test: Enforcement of the host allowlist for `DC_API_KEY`.
    # Situation: The target URL is an external HTTPS host that is not in the
    #   public Data Commons allowlist.
    # Expectation: No credential is added to the request headers, ensuring
    #   `DC_API_KEY` cannot be sent to an untrusted host.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "https://evil.example.com/mcp")
    assert headers == {}


def test_data_plane_auth_off_attaches_no_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Explicit opt-out via `DATA_PLANE_AUTH=off`.
    # Situation: `DATA_PLANE_AUTH` is set to `"off"` in the environment and
    #   `attach_auth` is called for an HTTPS endpoint.
    # Expectation: `attach_auth` exits early and leaves `headers` empty.
    monkeypatch.setenv("DATA_PLANE_AUTH", "off")
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "https://api.datacommons.org/mcp")
    assert headers == {}


def test_dc_api_key_takes_precedence_over_secret_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `DC_API_KEY` precedence over `DC_API_KEY_SECRET`.
    # Situation: Both `DC_API_KEY` and `DC_API_KEY_SECRET` are set.
    # Expectation: `attach_auth` attaches `DC_API_KEY` without calling Secret
    #   Manager.
    secret_called = False

    def _fake_fetch(secret_name: str, env_var: str) -> str:
        nonlocal secret_called
        secret_called = True
        return "sm-key"

    monkeypatch.setattr(gcp_auth, "fetch_secret_with_ttl", _fake_fetch)
    monkeypatch.setenv(DC_API_KEY_ENV, "env-key")
    monkeypatch.setenv(DC_API_KEY_SECRET_ENV, "my-secret")
    gcp_auth.reset_dc_api_key()

    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "https://api.datacommons.org/mcp")
    assert headers == {"X-API-Key": "env-key"}
    assert not secret_called


def test_dc_api_key_secret_is_loaded_from_secret_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Loading `DC_API_KEY_SECRET` when `DC_API_KEY` is unset.
    # Situation: `DC_API_KEY` is unset and `DC_API_KEY_SECRET` is set.
    # Expectation: `attach_auth` calls `fetch_secret_from_secret_manager` and
    #   caches the returned key for subsequent calls.
    fetch_calls: list[tuple[str, str]] = []

    def _fake_fetch(secret_name: str, env_var: str) -> str:
        fetch_calls.append((secret_name, env_var))
        return "secret-loaded-key"

    monkeypatch.setattr(gcp_auth, "fetch_secret_with_ttl", _fake_fetch)
    monkeypatch.delenv(DC_API_KEY_ENV, raising=False)
    monkeypatch.setenv(DC_API_KEY_SECRET_ENV, "mixer-api-key")
    gcp_auth.reset_dc_api_key()

    headers1: dict[str, str] = {}
    gcp_auth.attach_auth(headers1, "https://api.datacommons.org/mcp")
    assert headers1 == {"X-API-Key": "secret-loaded-key"}
    assert fetch_calls == [("mixer-api-key", DC_API_KEY_SECRET_ENV)]

    # Second call should use cache without fetching again
    headers2: dict[str, str] = {}
    gcp_auth.attach_auth(headers2, "https://api.datacommons.org/mcp")
    assert headers2 == {"X-API-Key": "secret-loaded-key"}
    assert len(fetch_calls) == 1


def test_dc_api_key_secret_failure_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Fail-fast error handling when `DC_API_KEY_SECRET` fails to load.
    # Situation: `DC_API_KEY` is unset, `DC_API_KEY_SECRET` is set, but Secret
    #   Manager returns an empty string or fails.
    # Expectation: `init_dc_api_key()` raises `RuntimeError` naming
    #   `DC_API_KEY_SECRET`.
    monkeypatch.setattr(gcp_auth, "fetch_secret_with_ttl", lambda name, var: "")
    monkeypatch.delenv(DC_API_KEY_ENV, raising=False)
    monkeypatch.setenv(DC_API_KEY_SECRET_ENV, "mixer-api-key")
    gcp_auth.reset_dc_api_key()

    with pytest.raises(RuntimeError, match=DC_API_KEY_SECRET_ENV):
        gcp_auth.init_dc_api_key()


def test_no_api_key_configured_attaches_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: When neither DC_API_KEY nor DC_API_KEY_SECRET is configured.
    # Situation: Both variables are unset in the environment.
    # Expectation: attach_auth leaves headers empty and logs a warning.
    monkeypatch.delenv(DC_API_KEY_ENV, raising=False)
    monkeypatch.delenv(DC_API_KEY_SECRET_ENV, raising=False)
    gcp_auth.reset_dc_api_key()

    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "https://api.datacommons.org/mcp")
    assert headers == {}

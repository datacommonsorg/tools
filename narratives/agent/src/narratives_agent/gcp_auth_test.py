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
    monkeypatch.setenv("DC_API_KEY", _API_KEY)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.datacommons.org/mcp",
        "https://datacommons.org/api",
    ],
)
def test_public_data_commons_gets_the_api_key(url: str) -> None:
    # Test: Credential selection for public Data Commons endpoints.
    # Situation: The target URL points to an allowlisted public Data Commons
    #   host (`api.datacommons.org` or `datacommons.org`).
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

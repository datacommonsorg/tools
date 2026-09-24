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
"""Tests for host-based credential selection and ID token caching in `gcp_auth`.

Verifies two behaviors in `gcp_auth`:
1. `attach_auth` selects credentials based on the target URL:
   - Allowlisted public Data Commons hosts receive the `X-API-Key` header.
   - Private HTTPS Cloud Run hosts receive a Google-signed Bearer ID token.
   - Plain HTTP localhost URLs (sidecar deployments) receive no auth headers.
   - Unlisted external HTTPS hosts do not receive `DC_API_KEY`, preventing a
     modified remote configuration from leaking the API key to an arbitrary
     host.
   - Setting `DATA_PLANE_AUTH=off` disables credential attachment entirely.
2. `get_id_token` caches minted ID tokens across requests while refusing to
   cache empty responses or failed metadata server requests.
"""

import pytest
import requests

from narratives_agent import gcp_auth

_API_KEY = "test-key-123"
_ID_TOKEN = "fake-id-token"


def _fake_id_token(audience: str) -> str:
    """Stub for `gcp_auth.get_id_token` to avoid metadata server requests."""
    return _ID_TOKEN


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


@pytest.fixture
def stub_id_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub `gcp_auth.get_id_token` for `attach_auth` tests that mint tokens."""
    monkeypatch.setattr(gcp_auth, "get_id_token", _fake_id_token)


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


def test_private_cloud_run_gets_an_id_token(stub_id_token: None) -> None:
    # Test: Credential selection for a private Cloud Run data plane.
    # Situation: The target URL is an HTTPS Cloud Run service outside the
    #   public Data Commons host allowlist.
    # Expectation: `attach_auth` sets the `Authorization` header to a Bearer ID
    #   token and does not attach `X-API-Key`.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(
        headers, "https://x-dc-datacommons-service-uc.a.run.app/mcp"
    )
    assert headers == {"Authorization": f"Bearer {_ID_TOKEN}"}


def test_local_http_target_gets_no_credential() -> None:
    # Test: Credential selection for a local HTTP sidecar endpoint.
    # Situation: The target URL uses plain HTTP on localhost.
    # Expectation: `attach_auth` leaves the headers dictionary empty.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "http://localhost:8082/mcp")
    assert headers == {}


def test_api_key_is_not_sent_to_an_unlisted_host(
    stub_id_token: None,
) -> None:
    # Test: Enforcement of the host allowlist for `DC_API_KEY`.
    # Situation: The target URL is an external HTTPS host that is not in the
    #   public Data Commons allowlist.
    # Expectation: `X-API-Key` is not added to the request headers, ensuring
    #   `DC_API_KEY` cannot be sent to an untrusted host.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "https://evil.example.com/mcp")
    assert "X-API-Key" not in headers


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


_AUDIENCE = "https://data-plane-uc.a.run.app"


class _StubResponse:
    """Minimal `requests.Response` stub for metadata server responses."""

    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _CountingMetadataServer:
    """Callable stub for `requests.get` that counts metadata server calls."""

    def __init__(self, body: str) -> None:
        self.body = body
        self.calls = 0

    def __call__(self, *args: object, **kwargs: object) -> _StubResponse:
        self.calls += 1
        return _StubResponse(self.body)


@pytest.fixture
def id_token_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate `_TOKEN_CACHE` for each token-caching test."""
    monkeypatch.setattr(gcp_auth, "_TOKEN_CACHE", {})


def test_minted_id_token_is_cached(
    monkeypatch: pytest.MonkeyPatch, id_token_cache: None
) -> None:
    # Test: Caching of a valid ID token returned by the metadata server.
    # Situation: The metadata server returns a non-empty token string, and
    #   `get_id_token` is called twice for the same audience.
    # Expectation: Both calls return the minted token while issuing only one
    #   HTTP request to the metadata server.
    server = _CountingMetadataServer("minted-token")
    monkeypatch.setattr(requests, "get", server)

    assert gcp_auth.get_id_token(_AUDIENCE) == "minted-token"
    assert gcp_auth.get_id_token(_AUDIENCE) == "minted-token"
    assert server.calls == 1


def test_empty_id_token_is_not_cached(
    monkeypatch: pytest.MonkeyPatch, id_token_cache: None
) -> None:
    # Test: Rejection of an empty HTTP 200 body from the metadata server.
    # Situation: The metadata server responds with HTTP 200 and an empty body.
    # Expectation: `get_id_token` returns `""` without writing to
    #   `_TOKEN_CACHE`, so subsequent requests retry the metadata server.
    server = _CountingMetadataServer("")
    monkeypatch.setattr(requests, "get", server)

    assert gcp_auth.get_id_token(_AUDIENCE) == ""
    assert gcp_auth.get_id_token(_AUDIENCE) == ""
    assert server.calls == 2
    assert gcp_auth._TOKEN_CACHE == {}


def test_failed_id_token_fetch_is_not_cached(
    monkeypatch: pytest.MonkeyPatch, id_token_cache: None
) -> None:
    # Test: Handling of network errors when contacting the metadata server.
    # Situation: `requests.get` raises an `OSError` because the metadata server
    #   is unreachable.
    # Expectation: `get_id_token` returns `""` and leaves `_TOKEN_CACHE` empty.
    def _unreachable(*args: object, **kwargs: object) -> _StubResponse:
        raise OSError("no metadata server here")

    monkeypatch.setattr(requests, "get", _unreachable)

    assert gcp_auth.get_id_token(_AUDIENCE) == ""
    assert gcp_auth._TOKEN_CACHE == {}

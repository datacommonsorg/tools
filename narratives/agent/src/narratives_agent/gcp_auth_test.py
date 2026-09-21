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
"""Auth is chosen by target host, not by a backend flag.

Covers `attach_auth`: which credential each kind of target gets, and the host
allowlist that keeps DC_API_KEY off every other host.

Two backends need two different credentials, and sending the wrong one fails in
a way that looks like a data problem rather than an auth problem:

  * public Data Commons wants X-API-Key -- our service account means nothing to
    it, so an ID token yields "no data" on every query.
  * a private Cloud Run data plane wants a Google-signed ID token -- an API key
    yields 403 on every chart.

The last case is the security property the host allowlist exists for: the MCP
endpoint is configuration-driven and that config is fetched from a GCS bucket,
so an edit to it must not be able to hand our API key to an arbitrary host.
"""

import pytest

from narratives_agent import gcp_auth

_API_KEY = "test-key-123"
_ID_TOKEN = "fake-id-token"


def _fake_id_token(audience: str) -> str:
    """Stands in for the metadata server, which is unreachable in tests."""
    return _ID_TOKEN


@pytest.fixture(autouse=True)
def credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two credentials attach_auth chooses between.

    DATA_PLANE_AUTH is cleared as well: it switches attach_auth off wholesale,
    so a developer with it exported would otherwise watch every case below pass
    for the wrong reason.
    """
    monkeypatch.delenv("DATA_PLANE_AUTH", raising=False)
    monkeypatch.setenv("DC_API_KEY", _API_KEY)
    monkeypatch.setattr(gcp_auth, "get_id_token", _fake_id_token)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.datacommons.org/mcp",
        "https://datacommons.org/api",
    ],
)
def test_public_data_commons_gets_the_api_key(url: str) -> None:
    # Test: the credential chosen for public Data Commons.
    # Situation: the target host is one of the allowlisted public DC hosts.
    # Expectation: X-API-Key carries DC_API_KEY and nothing else is attached --
    #   our service account means nothing to public DC, so an ID token would
    #   yield "no data" on every query.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, url)
    assert headers == {"X-API-Key": _API_KEY}


def test_private_cloud_run_gets_an_id_token() -> None:
    # Test: the credential chosen for a private data plane.
    # Situation: the target is an IAM-gated Cloud Run service.
    # Expectation: a Google-signed ID token is sent as a bearer token, and no
    #   API key -- an API key yields 403 on every chart.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(
        headers, "https://x-dc-datacommons-service-uc.a.run.app/mcp"
    )
    assert headers == {"Authorization": f"Bearer {_ID_TOKEN}"}


def test_local_http_target_gets_no_credential() -> None:
    # Test: the co-located sidecar deployment is left alone.
    # Situation: the target is a plain-http localhost URL.
    # Expectation: no header at all, so a sidecar data plane is unaffected.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "http://localhost:8082/mcp")
    assert headers == {}


def test_api_key_is_not_sent_to_an_unlisted_host() -> None:
    # Test: the host allowlist, which is a security property rather than a
    #   convenience.
    # Situation: config -- fetched from a GCS bucket, so editable without a
    #   code change -- points the agent at an arbitrary https host.
    # Expectation: DC_API_KEY is not attached, so a config edit cannot turn
    #   into a credential leak.
    headers: dict[str, str] = {}
    gcp_auth.attach_auth(headers, "https://evil.example.com/mcp")
    assert "X-API-Key" not in headers

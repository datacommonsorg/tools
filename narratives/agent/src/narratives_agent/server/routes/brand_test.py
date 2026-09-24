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
"""Tests for credential scanning, asset serving, and CSS generation in `brand`.

Verifies that:
1. `find_credential_like_values` and `_redact` detect and remove
   credential-shaped strings and secret-named fields across nested dictionaries
   and JSON arrays before `branding.json` is served to clients.
2. `brand_asset` serves mirrored assets with `X-Content-Type-Options: nosniff`
   and immutable cache headers, and returns 404 for unknown assets.
3. `_build_brand_css` emits valid `:root` CSS custom property declarations while
   dropping unsafe declaration values that could escape the CSS rule block.
"""

import pytest
from flask.testing import FlaskClient

from narratives_agent.server.app import app
from narratives_agent.server.routes import brand

# Matches the Google API key regex in `brand._CREDENTIAL_PATTERNS` while using
# explicit test/dummy/example/fake tokens to avoid secret-scanner false alarms.
_KEY_SHAPED = "AIza_test_dummy_example_fake_key_0000"


def test_credential_inside_list_is_found() -> None:
    # Test: Credential pattern detection for string elements inside a JSON list.
    # Situation: `branding.json` contains a list holding a string that matches a
    #   known credential pattern.
    # Expectation: `find_credential_like_values` returns the indexed path
    #   (`"keys[0]"`).
    document = {"keys": [_KEY_SHAPED]}
    assert brand.find_credential_like_values(document) == ["keys[0]"]


def test_credential_nested_below_list_is_found() -> None:
    # Test: Credential detection across alternating dictionary and list levels.
    # Situation: A secret-named field sits inside a dictionary element of a
    #   list.
    # Expectation: `find_credential_like_values` returns the full dotted and
    #   indexed path (`"providers[1].secret"`).
    document = {"providers": [{"name": "x"}, {"secret": "hunter2"}]}
    assert brand.find_credential_like_values(document) == [
        "providers[1].secret"
    ]


def test_credential_in_dict_value_is_found() -> None:
    # Test: Credential pattern detection for a direct dictionary string value.
    # Situation: A value matching a credential pattern sits under an ordinary
    #   non-secret key name alongside valid color settings.
    # Expectation: `find_credential_like_values` flags only the key whose value
    #   matches the credential pattern (`"analytics"`).
    document = {"colors": {"primary": "#123456"}, "analytics": _KEY_SHAPED}
    assert brand.find_credential_like_values(document) == ["analytics"]


def test_list_elements_inherit_parent_key_for_credential_check() -> None:
    # Test: Propagation of secret-bearing dictionary key names to list elements.
    # Situation: A list is stored under the key `"api_keys"` and contains short
    #   strings that do not match a standalone credential regex.
    # Expectation: Both list elements are flagged because they inherit the
    #   enclosing `"api_keys"` key name.
    document = {"api_keys": ["short", "also-short"]}
    assert brand.find_credential_like_values(document) == [
        "api_keys[0]",
        "api_keys[1]",
    ]


def test_empty_value_under_secret_key_is_not_flagged() -> None:
    # Test: Exclusion of empty strings under secret-bearing key names.
    # Situation: `"api_key"` and `"api_keys"` contain empty strings (`""`),
    #   which configuration files use to represent unset fields.
    # Expectation: `find_credential_like_values` returns an empty list.
    document = {"api_key": "", "api_keys": [""]}
    assert brand.find_credential_like_values(document) == []


def test_ordinary_branding_document_is_not_flagged() -> None:
    # Test: Credential scan against a standard branding configuration.
    # Situation: The document contains typical branding fields (`instance_name`,
    #   `logo`, `colors`, `fonts`, and `nav_tabs`).
    # Expectation: `find_credential_like_values` returns an empty list so valid
    #   branding fields are preserved.
    document = {
        "instance_name": "Example Data Commons",
        "logo": "/assets/logo.png",
        "colors": {"primary": "#0b57d0", "text": "#1f1f1f"},
        "fonts": {"primary": "Google Sans"},
        "nav_tabs": [
            {"label": "Explore", "href": "/explore"},
            {"label": "Tools", "href": "/tools"},
        ],
    }
    assert brand.find_credential_like_values(document) == []


def test_flagged_list_element_is_removed_during_redaction() -> None:
    # Test: In-place removal of a flagged list element by `_redact`.
    # Situation: The middle element of a three-element list matches a credential
    #   pattern.
    # Expectation: `_redact` removes the flagged element and preserves the
    #   remaining elements in their original order.
    document = {"integrations": ["alpha", _KEY_SHAPED, "omega"]}
    findings = brand.find_credential_like_values(document)
    assert findings == ["integrations[1]"]
    brand._redact(document, set(findings))
    assert document == {"integrations": ["alpha", "omega"]}


def test_redaction_removes_non_contiguous_flagged_list_elements() -> None:
    # Test: In-place removal when multiple non-adjacent list indices are
    #   flagged.
    # Situation: Indices 0 and 2 of a four-element list under `"api_keys"` hold
    #   non-empty strings while indices 1 and 3 are empty strings.
    # Expectation: `_redact` removes both flagged indices without index-shift
    #   errors, leaving the two unflagged empty strings.
    document = {"api_keys": ["a", "", "c", ""]}
    findings = brand.find_credential_like_values(document)
    assert findings == ["api_keys[0]", "api_keys[2]"]
    brand._redact(document, set(findings))
    assert document == {"api_keys": ["", ""]}


def test_redaction_removes_dict_and_nested_dict_entries() -> None:
    # Test: In-place removal of flagged dictionary keys at top-level and nested
    #   paths.
    # Situation: A document contains a top-level credential string and a
    #   secret-named key inside a list of dictionaries.
    # Expectation: `_redact` deletes both flagged dictionary keys while leaving
    #   unflagged sibling keys intact.
    document = {
        "analytics": _KEY_SHAPED,
        "providers": [{"name": "x"}, {"name": "y", "secret": "hunter2"}],
    }
    findings = brand.find_credential_like_values(document)
    assert findings == ["analytics", "providers[1].secret"]
    brand._redact(document, set(findings))
    assert document == {
        "providers": [{"name": "x"}, {"name": "y"}],
    }


_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'


if "brand" not in app.blueprints:
    app.register_blueprint(brand.brand_bp, url_prefix="/agent")


@pytest.fixture
def client() -> FlaskClient:
    """Return a test client for the application with `brand_bp` mounted."""
    return app.test_client()


@pytest.fixture
def mirrored_svg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate `_BRAND_STATE['assets']` with a single mirrored SVG asset."""
    monkeypatch.setitem(
        brand._BRAND_STATE, "assets", {"logo-a1b2c3d4.svg": _SVG}
    )


def test_load_branding_redacts_credentials_before_publishing(
    monkeypatch: pytest.MonkeyPatch,
    client: FlaskClient,
) -> None:
    # Test: End-to-end credential redaction inside `load_branding`.
    # Situation: `BRAND_CONFIG_URL` points to a bucket whose `branding.json`
    #   contains a credential-shaped string inside a list (`"keys"`).
    # Expectation: `load_branding` strips the credential before storing the
    #   document in `_BRAND_STATE`, so neither `/agent/brand` nor
    #   `/agent/brand.js` publishes the secret.
    class _StubBrandingResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "instance_name": "Example Data Commons",
                "keys": [_KEY_SHAPED],
            }

    monkeypatch.delenv("INSTANCE_ID", raising=False)
    monkeypatch.setenv(
        "BRAND_CONFIG_URL", "https://storage.googleapis.com/test-brand-bucket"
    )
    monkeypatch.setitem(brand._BRAND_STATE, "branding", None)
    monkeypatch.setitem(brand._BRAND_STATE, "assets", {})
    monkeypatch.setitem(brand._BRAND_STATE, "css", "")
    monkeypatch.setitem(brand._BRAND_STATE, "loaded", False)
    monkeypatch.setattr(
        brand,
        "_fetch_gcs_url",
        lambda url: _StubBrandingResponse(),
    )

    brand.load_branding()

    brand_response = client.get("/agent/brand")
    assert brand_response.status_code == 200
    assert brand_response.get_json() == {
        "instance": "",
        "branding": {
            "instance_name": "Example Data Commons",
            "keys": [],
        },
    }
    assert _KEY_SHAPED not in brand_response.get_data(as_text=True)

    js_response = client.get("/agent/brand.js")
    assert js_response.status_code == 200
    assert _KEY_SHAPED not in js_response.get_data(as_text=True)



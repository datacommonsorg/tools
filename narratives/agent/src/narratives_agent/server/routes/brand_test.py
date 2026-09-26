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
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    document: dict[str, brand.JsonValue] = {"keys": [_KEY_SHAPED]}
    assert brand.find_credential_like_values(document) == ["keys[0]"]


def test_credential_nested_below_list_is_found() -> None:
    # Test: Credential detection across alternating dictionary and list levels.
    # Situation: A secret-named field sits inside a dictionary element of a
    #   list.
    # Expectation: `find_credential_like_values` returns the full dotted and
    #   indexed path (`"providers[1].secret"`).
    document: dict[str, brand.JsonValue] = {
        "providers": [{"name": "x"}, {"secret": "hunter2"}]
    }
    assert brand.find_credential_like_values(document) == [
        "providers[1].secret"
    ]


def test_credential_in_dict_value_is_found() -> None:
    # Test: Credential pattern detection for a direct dictionary string value.
    # Situation: A value matching a credential pattern sits under an ordinary
    #   non-secret key name alongside valid color settings.
    # Expectation: `find_credential_like_values` flags only the key whose value
    #   matches the credential pattern (`"analytics"`).
    document: dict[str, brand.JsonValue] = {
        "colors": {"primary": "#123456"},
        "analytics": _KEY_SHAPED,
    }
    assert brand.find_credential_like_values(document) == ["analytics"]


def test_list_elements_inherit_parent_key_for_credential_check() -> None:
    # Test: Propagation of secret-bearing dictionary key names to list elements.
    # Situation: A list is stored under the key `"api_keys"` and contains short
    #   strings that do not match a standalone credential regex.
    # Expectation: Both list elements are flagged because they inherit the
    #   enclosing `"api_keys"` key name.
    document: dict[str, brand.JsonValue] = {"api_keys": ["short", "also-short"]}
    assert brand.find_credential_like_values(document) == [
        "api_keys[0]",
        "api_keys[1]",
    ]


def test_empty_value_under_secret_key_is_not_flagged() -> None:
    # Test: Exclusion of empty strings under secret-bearing key names.
    # Situation: `"api_key"` and `"api_keys"` contain empty strings (`""`),
    #   which configuration files use to represent unset fields.
    # Expectation: `find_credential_like_values` returns an empty list.
    document: dict[str, brand.JsonValue] = {"api_key": "", "api_keys": [""]}
    assert brand.find_credential_like_values(document) == []


def test_ordinary_branding_document_is_not_flagged() -> None:
    # Test: Credential scan against a standard branding configuration.
    # Situation: The document contains typical branding fields (`instance_name`,
    #   `logo`, `colors`, `fonts`, and `nav_tabs`).
    # Expectation: `find_credential_like_values` returns an empty list so valid
    #   branding fields are preserved.
    document: dict[str, brand.JsonValue] = {
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
    document: dict[str, brand.JsonValue] = {
        "integrations": ["alpha", _KEY_SHAPED, "omega"]
    }
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
    document: dict[str, brand.JsonValue] = {"api_keys": ["a", "", "c", ""]}
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
    document: dict[str, brand.JsonValue] = {
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


@pytest.fixture
def client() -> TestClient:
    """Returns a test client for an app that serves only `brand.router`.

    Building the app reads no settings, so a test that sets environment
    variables after requesting this fixture still sees them.
    """
    app = FastAPI()
    app.include_router(brand.router, prefix="/agent")
    return TestClient(app)


@pytest.fixture
def mirrored_svg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate `_BRAND_STATE['assets']` with a single mirrored SVG asset."""
    monkeypatch.setitem(
        brand._BRAND_STATE, "assets", {"logo-a1b2c3d4.svg": _SVG}
    )


def test_load_branding_redacts_credentials_before_publishing(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
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
    assert brand_response.json() == {
        "instance": "",
        "branding": {
            "instance_name": "Example Data Commons",
            "keys": [],
        },
    }
    assert _KEY_SHAPED not in brand_response.text

    js_response = client.get("/agent/brand.js")
    assert js_response.status_code == 200
    assert _KEY_SHAPED not in js_response.text


@pytest.mark.usefixtures("mirrored_svg")
def test_mirrored_asset_is_served_with_nosniff_header(
    client: TestClient,
) -> None:
    # Test: Content-Type and `X-Content-Type-Options` header on
    #   `GET /agent/brand/assets/<name>`.
    # Situation: A mirrored SVG logo is requested over HTTP from
    #   `/agent/brand/assets/logo-a1b2c3d4.svg`.
    # Expectation: The response has HTTP status 200, `image/svg+xml` in
    #   `Content-Type`, `X-Content-Type-Options: nosniff`, and the SVG body.
    response = client.get("/agent/brand/assets/logo-a1b2c3d4.svg")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("image/svg+xml")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.content == _SVG


@pytest.mark.usefixtures("mirrored_svg")
def test_mirrored_asset_is_served_with_immutable_cache_control(
    client: TestClient,
) -> None:
    # Test: `Cache-Control` header on content-addressed brand assets.
    # Situation: A mirrored SVG asset whose filename includes a content hash is
    #   requested over HTTP from `/agent/brand/assets/logo-a1b2c3d4.svg`.
    # Expectation: The response sets `Cache-Control` to
    #   `"public, max-age=31536000, immutable"`.
    response = client.get("/agent/brand/assets/logo-a1b2c3d4.svg")
    assert (
        response.headers["Cache-Control"]
        == "public, max-age=31536000, immutable"
    )


@pytest.mark.usefixtures("mirrored_svg")
def test_unknown_brand_asset_returns_404(client: TestClient) -> None:
    # Test: HTTP lookup of a nonexistent asset name on
    #   `/agent/brand/assets/<name>`.
    # Situation: A client requests `/agent/brand/assets/logo-00000000.svg`,
    #   which is not present in `_BRAND_STATE["assets"]`.
    # Expectation: The endpoint returns HTTP 404.
    response = client.get("/agent/brand/assets/logo-00000000.svg")
    assert response.status_code == 404


def test_build_brand_css_emits_configured_custom_properties() -> None:
    # Test: Generation of `:root` CSS custom properties in `_build_brand_css`.
    # Situation: A branding document configures `colors.primary`, `radius.card`,
    #   and `fonts.primary`.
    # Expectation: `_build_brand_css` returns a `:root` block declaring
    #   `--brand-primary`, `--brand-radius-card`, and `--brand-font`.
    css = brand._build_brand_css(
        {
            "colors": {"primary": "#0b57d0"},
            "radius": {"card": "12px"},
            "fonts": {"primary": "Google Sans"},
        }
    )
    assert css == (
        ":root {\n"
        "  --brand-primary: #0b57d0;\n"
        "  --brand-radius-card: 12px;\n"
        "  --brand-font: Google Sans;\n"
        "}\n"
    )


def test_build_brand_css_drops_unsafe_declaration_values() -> None:
    # Test: Rejection of CSS values containing declaration-breaking characters.
    # Situation: `colors.primary` contains a semicolon and braces (`red; } body
    #   { display: none`) alongside a valid `colors.accent` hex value.
    # Expectation: `_build_brand_css` drops the unsafe `primary` declaration and
    #   emits only the valid `--brand-accent` declaration.
    css = brand._build_brand_css(
        {
            "colors": {
                "primary": "red; } body { display: none",
                "accent": "#ff0000",
            }
        }
    )
    assert css == ":root {\n  --brand-accent: #ff0000;\n}\n"


def test_build_brand_css_returns_empty_string_when_unconfigured() -> None:
    # Test: `_build_brand_css` output when no CSS-mapped tokens are present.
    # Situation: `_build_brand_css` is called with `None` or a document that
    #   sets only non-CSS metadata (`instance_name`).
    # Expectation: `_build_brand_css` returns `""` so default stylesheet tokens
    #   remain untouched.
    assert brand._build_brand_css(None) == ""
    assert brand._build_brand_css({"instance_name": "Example"}) == ""

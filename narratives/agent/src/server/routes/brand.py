#!/usr/bin/env python3
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

"""Serves per-instance branding from memory.

Config lives in GCS, but is read exactly once, at startup, by
:func:`load_branding`. Every request is then answered from process memory --
neither the branding document nor its images are re-read from the bucket, and
no bucket URL is handed to the browser. Changing branding therefore requires a
new revision, which is what ``deploy.sh --config-only`` already forces after it
syncs the bucket.
"""

import hashlib
import json
import logging
import os
import posixpath
import re

from flask import Blueprint, Response, jsonify

from src.config import _fetch_gcs_url

logger = logging.getLogger(__name__)

brand_bp = Blueprint("brand", __name__)

# Branding fields naming an image that must be mirrored into memory so the
# browser never fetches it from the bucket. `logo_url` is the legacy alias.
_ASSET_FIELDS = ("logo", "logo_url", "favicon")

# Browser-visible prefix the SPA reaches this blueprint through. The services
# container's nginx strips it before proxying, so it is configuration rather
# than something the routes themselves see.
# Must match the prefix the API blueprints are registered under
# (routes/__init__.py). This module rewrites asset URLs into the served
# document, so if the two disagree the browser requests a logo from a path
# nothing serves -- a broken image with no error anywhere.
_PUBLIC_PREFIX = os.environ.get("AGENT_API_PREFIX", "/agent").rstrip("/")

_ASSET_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}

# Credential shapes rejected by :func:`find_credential_like_values`. Deliberately
# broad: a false positive costs one log line and a dropped key, a false negative
# publishes a secret to every browser that loads the page.
_CREDENTIAL_PATTERNS = (
    re.compile(r"^AIza[0-9A-Za-z_-]{20,}$"),          # Google API key
    re.compile(r"^gh[pousr]_[0-9A-Za-z]{20,}$"),      # GitHub token
    re.compile(r"^sk-[0-9A-Za-z_-]{20,}$"),           # OpenAI-style key
    re.compile(r"^ya29\.[0-9A-Za-z_-]{20,}$"),        # Google OAuth token
    re.compile(r"^-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

# Keys whose *name* implies a secret, whatever the value looks like.
_CREDENTIAL_KEY_HINTS = ("api_key", "apikey", "secret", "password", "private_key", "token")

# Populated once by load_branding(); read-only thereafter.
_BRAND_STATE: dict = {
    "branding": None,
    "assets": {},
    "css": "",
    "loaded": False,
}

# branding.json path -> the CSS custom property index.css reads. Mirrors
# applyCssVars() in ui/src/hooks/use_branding.ts; the two must stay in step, or
# the pre-paint stylesheet and the runtime fetch would disagree.
_CSS_VARIABLES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("colors", "primary"), "--brand-primary"),
    (("colors", "accent"), "--brand-accent"),
    (("colors", "text"), "--brand-text"),
    (("colors", "text_muted"), "--brand-text-muted"),
    (("colors", "surface"), "--brand-surface"),
    (("colors", "background"), "--brand-background"),
    (("colors", "gradient_start"), "--brand-gradient-start"),
    (("colors", "gradient_end"), "--brand-gradient-end"),
    (("colors", "surface_narrative"), "--brand-surface-narrative"),
    (("colors", "skeleton_bar"), "--brand-skeleton-bar"),
    (("colors", "border"), "--brand-border"),
    (("colors", "user_message"), "--brand-user-msg"),
    (("colors", "container"), "--brand-container"),
    (("colors", "on_container"), "--brand-on-container"),
    (("colors", "nav_active"), "--brand-nav-active"),
    (("radius", "card"), "--brand-radius-card"),
    (("radius", "input"), "--brand-radius-input"),
    (("radius", "chip"), "--brand-radius-chip"),
    (("logo_height",), "--brand-logo-height"),
    (("fonts", "primary"), "--brand-font"),
    (("fonts", "body"), "--brand-font-body"),
)

# A declaration value may only contain these. Anything else — braces,
# semicolons, angle brackets, newlines — could terminate the declaration and
# inject arbitrary CSS, so such values are dropped rather than emitted.
_SAFE_CSS_VALUE = re.compile(r"^[A-Za-z0-9 #,.()%_-]+$")


def _looks_like_credential(key: str, value: str) -> bool:
    """Reports whether a config entry appears to carry a credential.

    Args:
        key: The config key, matched against known secret-bearing names.
        value: The config value, matched against known credential formats.

    Returns:
        True when either the key name or the value shape suggests a secret.
    """
    if any(hint in key.lower() for hint in _CREDENTIAL_KEY_HINTS):
        # An empty string is how the configs mark "unset"; it leaks nothing.
        return bool(value)
    return any(pattern.match(value) for pattern in _CREDENTIAL_PATTERNS)


def find_credential_like_values(node, path: str = "") -> list[str]:
    """Walks a config document and reports paths that look like credentials.

    Args:
        node: The config fragment to inspect: dict, list or scalar.
        path: Dotted path of `node` within the document, used for reporting.

    Returns:
        Dotted paths of every entry that appears to hold a secret.
    """
    findings: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else key
            if isinstance(value, str) and _looks_like_credential(key, value):
                findings.append(child)
            else:
                findings.extend(find_credential_like_values(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            findings.extend(find_credential_like_values(value, f"{path}[{index}]"))
    return findings


def _redact(node, paths: set[str], path: str = "") -> None:
    """Removes the entries at `paths` from `node`, in place."""
    if isinstance(node, dict):
        for key in list(node):
            child = f"{path}.{key}" if path else key
            if child in paths:
                del node[key]
            else:
                _redact(node[key], paths, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _redact(value, paths, f"{path}[{index}]")


def _fetch_branding_document(base_url: str) -> dict | None:
    """Reads branding.json from the config bucket.

    Returns:
        The parsed document, or None when it is absent, unreadable or not valid
        JSON. Never raises: a missing config must not stop the server starting.
    """
    try:
        response = _fetch_gcs_url(f"{base_url}/branding.json")
    except Exception as error:
        logger.error(f"branding.json could not be fetched: {error}")
        return None

    if response.status_code != 200:
        logger.warning(f"branding.json fetch returned HTTP {response.status_code}")
        return None

    try:
        document = response.json()
    except ValueError as error:
        logger.error(f"branding.json is not valid JSON, ignoring it: {error}")
        return None

    if not isinstance(document, dict):
        logger.error("branding.json is not a JSON object, ignoring it")
        return None
    return document


def _fetch_asset(base_url: str, relative_path: str) -> bytes | None:
    """Reads one branding image from the config bucket.

    Returns:
        The image bytes, or None when the asset is absent or unreadable.
    """
    try:
        response = _fetch_gcs_url(f"{base_url}/{relative_path.lstrip('/')}")
    except Exception as error:
        logger.error(f"Brand asset '{relative_path}' could not be fetched: {error}")
        return None
    if response.status_code != 200:
        logger.warning(
            f"Brand asset '{relative_path}' fetch returned HTTP {response.status_code}"
        )
        return None
    return response.content


def _mirror_assets(document: dict, base_url: str) -> dict[str, bytes]:
    """Pulls every referenced image into memory and rewrites its path.

    Each asset field naming a bucket-relative path is fetched once and rewritten
    to this blueprint's own asset route, so a browser rendering the branding
    never issues a request to GCS. Absolute URLs and data: URIs are left alone --
    they are already not our bucket.

    Args:
        document: The branding document, modified in place.
        base_url: Config bucket base URL the relative paths resolve against.

    Returns:
        Asset bytes keyed by the file name used in the rewritten path.
    """
    assets: dict[str, bytes] = {}
    # Bucket-relative source path -> the hashed name it was mirrored under, so
    # two fields naming one file (`logo` and its legacy `logo_url` alias) cost a
    # single fetch.
    mirrored: dict[str, str] = {}
    for field in _ASSET_FIELDS:
        value = document.get(field)
        if not isinstance(value, str) or not value:
            continue
        if value.startswith(("http://", "https://", "//", "data:")):
            continue

        source = value.lstrip("/")
        name = mirrored.get(source)
        if name is None:
            base_name = posixpath.basename(source)
            if not base_name:
                continue
            content = _fetch_asset(base_url, value)
            if content is None:
                # Drop the field so the UI falls back to its bundled logo rather
                # than rendering a broken image.
                document.pop(field, None)
                continue
            # Content-addressed: replacing a logo moves it to a new URL, so a
            # browser still holding the previous revision's copy cannot serve
            # it stale and flash the old mark before the new one arrives.
            stem, extension = posixpath.splitext(base_name)
            digest = hashlib.sha256(content).hexdigest()[:8]
            name = f"{stem}-{digest}{extension}"
            assets[name] = content
            mirrored[source] = name
        document[field] = f"{_PUBLIC_PREFIX}/brand/assets/{name}"
    return assets


def _build_brand_css(document: dict | None) -> str:
    """Renders the branding document as a :root stylesheet.

    The result is what index.html loads before first paint, so the browser has
    the instance's colours in hand for the very first frame instead of painting
    index.css's fallbacks and being recoloured once React has fetched
    /agent/brand.

    Values that are not plain CSS literals are dropped: a branding.json is
    operator-supplied data, and a value carrying a brace or semicolon could
    otherwise close the declaration and inject arbitrary rules into every page.

    Args:
        document: The branding document, or None when none is configured.

    Returns:
        A `:root { ... }` block, or an empty string when nothing is set — in
        which case index.css's own fallbacks stand, exactly as before.
    """
    if not document:
        return ""

    declarations: list[str] = []
    for path, css_variable in _CSS_VARIABLES:
        node = document
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if not isinstance(node, str) or not node.strip():
            continue
        value = node.strip()
        if not _SAFE_CSS_VALUE.match(value):
            logger.warning(
                f"branding value for {css_variable} is not a plain CSS literal; "
                "dropping it from brand.css"
            )
            continue
        declarations.append(f"  {css_variable}: {value};")

    if not declarations:
        return ""
    return ":root {\n" + "\n".join(declarations) + "\n}\n"


def load_branding() -> None:
    """Reads branding and its images from GCS into memory. Call once, at startup.

    Any failure is logged and swallowed: the server must start even when the
    config bucket is missing, unreachable or holds a corrupt document, in which
    case the UI falls back to its shipped design tokens.
    """
    base_url = os.environ.get("BRAND_CONFIG_URL", "").rstrip("/")
    if not base_url:
        logger.info("BRAND_CONFIG_URL is unset; serving the UI's default branding")
        _BRAND_STATE["loaded"] = True
        return

    document = _fetch_branding_document(base_url)
    if document is None:
        _BRAND_STATE["loaded"] = True
        return

    findings = find_credential_like_values(document)
    if findings:
        # Principle: never store API keys in configs -- use Secret Manager. Drop
        # them rather than refusing to boot, and make the breach loud.
        logger.error(
            "branding.json contains credential-like values at "
            f"{', '.join(sorted(findings))}; dropping them. Move secrets to "
            "Secret Manager."
        )
        _redact(document, set(findings))

    assets = _mirror_assets(document, base_url)

    _BRAND_STATE["branding"] = document
    _BRAND_STATE["assets"] = assets
    _BRAND_STATE["css"] = _build_brand_css(document)
    _BRAND_STATE["loaded"] = True
    logger.info(
        f"Loaded branding.json, {len(assets)} brand asset(s) and a "
        f"{len(_BRAND_STATE['css'])}-byte pre-paint stylesheet into memory at "
        "startup"
    )


def _brand_payload() -> dict:
    """Builds the payload that /brand and /brand.js both publish.

    One helper so the two cannot drift: they carry the same in-memory state and
    differ only in how the browser consumes it -- a fetch after mount, or a
    global assigned before first paint.

    Returns:
        The instance id and the branding document held since startup.
    """
    return {
        "instance": os.environ.get("INSTANCE_ID", ""),
        "branding": _BRAND_STATE["branding"],
    }


@brand_bp.route("/brand", methods=["GET"])
def brand_alias() -> Response:
    """Returns the branding document held in memory since startup.

    The config bucket URL is deliberately absent from the payload: the browser
    has no reason to know it, and must never read the bucket itself.
    """
    if not _BRAND_STATE["loaded"]:
        # Defensive: a request arriving before load_branding() would otherwise
        # look like "this instance has no branding".
        logger.warning("/brand served before startup load completed")

    response = jsonify(_brand_payload())
    response.headers["Cache-Control"] = "no-store"
    return response


@brand_bp.route("/brand/assets/<path:name>", methods=["GET"])
def brand_asset(name: str) -> Response:
    """Serves one branding image from memory.

    Args:
        name: File name of the asset, as rewritten into the branding document.
    """
    content = _BRAND_STATE["assets"].get(posixpath.basename(name))
    if content is None:
        return Response("Not found", status=404, mimetype="text/plain")

    extension = posixpath.splitext(name)[1].lower()
    response = Response(
        content,
        mimetype=_ASSET_CONTENT_TYPES.get(extension, "application/octet-stream"),
    )
    # Genuinely immutable: _mirror_assets names each asset after a digest of
    # its bytes, so the content behind a given name can never change and the
    # browser never needs to revalidate.
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@brand_bp.route("/brand.css", methods=["GET"])
def brand_css() -> Response:
    """Serves the pre-paint stylesheet held in memory since startup.

    index.html links this in <head>, and a stylesheet there blocks first paint,
    so the instance's colours are applied before anything is drawn.

    Deliberately uncached, matching /brand. It was previously cacheable on the
    reasoning that branding cannot change without a new revision -- true of the
    server, but not of a browser that already holds a copy: for the life of that
    copy it would pre-paint the *previous* revision's colours and then be
    corrected by the uncached document, which is the flicker this file exists to
    prevent. The body is a few hundred bytes of memory, so caching buys little.
    """
    response = Response(_BRAND_STATE["css"], mimetype="text/css")
    response.headers["Cache-Control"] = "no-store"
    return response


@brand_bp.route("/brand.js", methods=["GET"])
def brand_js() -> Response:
    """Publishes the branding document as a global, before the SPA evaluates.

    index.html loads this as a blocking classic script in <head>, so
    `window.__BRAND__` is set before the bundle runs and useBranding() can seed
    its very first render from it.

    Without it, only the *colours* arrive before first paint (via brand.css) and
    every other branded value -- headline, tagline, wordmark, logo, nav tabs,
    suggestion chips -- necessarily renders as the UI's shipped neutral defaults
    until the /brand fetch resolves, then visibly flips to the instance's own.

    Answered from the same memory as /brand, so this reads nothing from the
    config bucket at request time, and can only publish a document that
    load_branding() has already stripped credential-like values from.
    """
    document = _brand_payload()["branding"]
    # ensure_ascii keeps the body 7-bit; escaping "<" additionally makes it
    # inert if a future change ever inlines this into the HTML rather than
    # linking it.
    literal = json.dumps(document, separators=(",", ":"))
    literal = literal.replace("<", "\\u003c")
    # The favicon and the tab title are set here rather than left to React.
    # index.html's <link rel="icon"> and <title> both precede this script, so
    # the elements already exist and rewriting them now happens before first
    # paint. Applying them from a mount effect instead lets the browser commit
    # the bundled fallback -- mark and the literal string "Custom DC" -- to the
    # tab and then visibly replace it: the same flash brand.js exists to
    # remove, in the two pieces of chrome React cannot render.
    #
    # The title comes from instance_name, which branding.schema.json already
    # documents as "Shown in the header/title". Nothing had ever implemented
    # the title half, so every instance shipped the index.html default.
    patch = (
        "(function(b){if(!b)return;"
        "if(b.favicon){var l=document.querySelector('link[rel=icon]');"
        "if(l)l.href=b.favicon;}"
        "if(b.instance_name)document.title=b.instance_name;"
        "})(window.__BRAND__);"
    )
    response = Response(
        f"window.__BRAND__={literal};{patch}",
        mimetype="text/javascript",
    )
    # Same no-store as /brand and brand.css: a cached copy would seed the
    # previous revision's branding into the first render.
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

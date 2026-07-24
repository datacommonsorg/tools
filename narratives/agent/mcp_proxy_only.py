#!/usr/bin/env python3
# Copyright 2024 Google LLC
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
"""
MCP Proxy Server (Proxy-Only Mode)

This script provides a REST API with CORS for browser-based frontends
to communicate with an already running Data Commons MCP server.

Prerequisites:
    Start the MCP server first:
    python3 -m uv tool run datacommons-mcp serve http --port 3000

Usage:
    python mcp_proxy_only.py
"""

import copy
import json
import logging
import queue
import random
import re
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Generator, Optional
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Secret Manager client for runtime key loading (optional import).
try:
    from google.cloud import secretmanager
    _SECRET_MANAGER_AVAILABLE = True
except ImportError:
    _SECRET_MANAGER_AVAILABLE = False
    logger.warning(
        "google-cloud-secret-manager not installed; "
        "GEMINI_API_KEYS_SECRET will be ignored"
    )


# Configuration
MCP_PORT = int(os.environ.get("MCP_PORT", 3000))
PROXY_PORT = int(os.environ.get("PROXY_PORT", 5001))
MCP_URL = f"http://localhost:{MCP_PORT}/mcp"

# Backend config cache
_config_cache = None
_config_mtime = 0


def _fetch_gcs_url(url: str) -> requests.Response:
    """Fetch from GCS.

    When running in GCP, attach the metadata service-account token so private
    config buckets are readable; falls back to an unauthenticated GET (public
    buckets / local dev) if the metadata server is unavailable.
    """
    headers = {}
    if "storage.googleapis.com" in url:
        try:
            token_url = (
                "http://metadata.google.internal/computeMetadata/v1/"
                "instance/service-accounts/default/token"
            )
            r = requests.get(
                token_url, headers={"Metadata-Flavor": "Google"}, timeout=2
            )
            if r.status_code == 200:
                token = r.json().get("access_token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    logger.info(
                        "Using GCP metadata service account token for GCS fetch"
                    )
        except Exception as e:
            logger.debug(
                "Metadata token fetch skipped/failed (normal if local): %s", e
            )
    return requests.get(url, headers=headers, timeout=15)


def _bootstrap_config_from_url() -> None:
    """If CONFIG_URL is set, fetch the file once at startup and save
    it as config.json so the existing load_config() path finds it. This makes
    the agent compatible with the bucket-driven config model (BRAND_CONFIG_URL +
    CONFIG_URL) without rewriting the upstream loader.
    """
    url = os.environ.get("CONFIG_URL", "").strip()
    if not url:
        return
    config_path = Path(__file__).parent / "config.json"
    try:
        r = _fetch_gcs_url(url)
        r.raise_for_status()
        config_path.write_text(r.text)
        logger.info("CONFIG_URL fetched %d bytes from %s", len(r.text), url)
    except Exception as e:
        logger.error("CONFIG_URL fetch failed (%s): %s", url, e)


_bootstrap_config_from_url()


def load_config() -> dict:
    """Load configuration from config.json file."""
    global _config_cache, _config_mtime

    config_path = Path(__file__).parent / 'config.json'

    if not config_path.exists():
        logger.warning(f"Config file not found at {config_path}")
        return {}

    # Check if file was modified
    current_mtime = config_path.stat().st_mtime
    if _config_cache is not None and current_mtime == _config_mtime:
        return _config_cache

    try:
        with open(config_path, 'r') as f:
            _config_cache = json.load(f)
            _config_mtime = current_mtime
            logger.info("Config loaded/reloaded from config.json")
            return _config_cache
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def get_current_datetime_ist() -> str:
    """Get current date/time formatted for the configured TIMEZONE.

    The TIMEZONE env var controls the
    zone (e.g. "Asia/Kolkata", "America/Los_Angeles"); the function name and the
    "{{CURRENT_DATETIME}}" placeholder are preserved so prompt templates don't
    need to change. The label suffix ("IST", "PT", ...) is derived from the zone
    abbreviation at runtime.
    """
    tz_name = os.environ.get("TIMEZONE", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"Unknown TIMEZONE={tz_name!r}; falling back to UTC")
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    return now.strftime("%A, %B %d, %Y at %I:%M %p ") + now.strftime("%Z")


def inject_datetime(prompt: str) -> str:
    """Replace {{CURRENT_DATETIME}} placeholder with the configured-timezone datetime."""
    return prompt.replace('{{CURRENT_DATETIME}}', get_current_datetime_ist())


_SECRET_MANAGER_CACHE: dict[str, tuple[float, list[str]]] = {}
_SECRET_MANAGER_TTL_SECONDS = 300


def _fetch_keys_from_secret_manager(secret_name: str) -> list[str]:
    """Load a JSON-encoded key array from Secret Manager.

    secret_name is either "projects/<proj>/secrets/<name>/versions/<v>" (full
    resource name) or just "<name>" (resolved against GOOGLE_CLOUD_PROJECT, latest
    version). Cached for 5 minutes to avoid hammering Secret Manager on each call.
    """
    if not _SECRET_MANAGER_AVAILABLE:
        return []
    cached = _SECRET_MANAGER_CACHE.get(secret_name)
    now = time.time()
    if cached and now - cached[0] < _SECRET_MANAGER_TTL_SECONDS:
        return cached[1]
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not secret_name.startswith("projects/"):
        if not project:
            logger.error("GOOGLE_CLOUD_PROJECT not set; cannot resolve short secret name %r", secret_name)
            return []
        full_name = f"projects/{project}/secrets/{secret_name}/versions/latest"
    else:
        full_name = secret_name
    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": full_name})
        payload = response.payload.data.decode("utf-8")
        keys = json.loads(payload)
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            logger.error("Secret %s did not contain a JSON array of strings", full_name)
            return []
        _SECRET_MANAGER_CACHE[secret_name] = (now, keys)
        logger.info("Loaded %d keys from Secret Manager (%s)", len(keys), full_name)
        return keys
    except Exception as e:
        logger.error("Failed to load secret %s: %s", full_name, e)
        return []


def get_api_keys(demo_mode: bool = False) -> list:
    """Load API keys from Secret Manager (preferred) or config (fallback).

    In `prod` mode the agent reads `GEMINI_API_KEYS_SECRET` (and
    optionally `GEMINI_DEMO_API_KEYS_SECRET`) and resolves the value via Secret
    Manager. The on-disk config.json `gemini.api_keys` array is honoured only as
    a dev fallback. The legacy scalar `gemini.api_key` is rejected outright.

    Args:
        demo_mode: If True, returns demo_api_keys for internal demo usage.
                   Demo keys are reserved for events/demos and won't be
                   affected by regular traffic rate limits.
                   If demo_mode=True but no demo keys configured, returns
                   empty list (will cause API call to fail - NO fallback).
    """
    if demo_mode:
        demo_secret = os.environ.get("GEMINI_DEMO_API_KEYS_SECRET", "")
        if demo_secret:
            keys = _fetch_keys_from_secret_manager(demo_secret)
            if keys:
                logger.info(f"Using demo API keys pool from Secret Manager ({len(keys)} keys)")
                return keys
        config = load_config()
        demo_keys = config.get("gemini", {}).get("demo_api_keys", [])
        if demo_keys:
            logger.info(f"Using demo API keys pool from config ({len(demo_keys)} keys)")
        else:
            logger.error("Demo mode requested but no demo_api_keys configured - will fail (no fallback to regular keys)")
        return demo_keys

    secret = os.environ.get("GEMINI_API_KEYS_SECRET", "")
    if secret:
        keys = _fetch_keys_from_secret_manager(secret)
        if keys:
            return keys
        logger.warning("GEMINI_API_KEYS_SECRET set but returned no keys; falling back to config")

    config = load_config()
    gemini_config = config.get("gemini", {})
    keys = gemini_config.get("api_keys", [])
    if not keys:
        single_key = gemini_config.get("api_key", "")
        if single_key and not single_key.startswith("DEPRECATED"):
            logger.warning("Using deprecated scalar gemini.api_key; migrate to api_keys[] or Secret Manager")
            keys = [single_key]
    return keys


def get_query_param_key() -> str:
    """Get the secret key for query param overrides from config."""
    config = load_config()
    return config.get("query_param_key", "AISummit2026")  # Default fallback


def apply_query_overrides(config: dict, query_params: dict) -> dict:
    """Apply query parameter overrides to config.

    Returns a new config dict with overrides applied (does not modify original).
    """
    if not query_params:
        return config

    # Deep copy to avoid modifying cached config
    effective = copy.deepcopy(config)

    # Model override
    if query_params.get("model"):
        effective["gemini"]["mcp_model"] = query_params["model"]
        effective["gemini"]["kb_model"] = query_params["model"]

    # Knowledge base toggle
    if query_params.get("kb_enabled"):
        enabled = query_params["kb_enabled"].lower() == "true"
        effective["knowledge_base"]["enabled"] = enabled

    # MCP thinking budget override
    if query_params.get("mcp_thinking"):
        effective["thinking"]["mcp_level"] = query_params["mcp_thinking"]

    # Synthesis thinking budget override
    if query_params.get("synthesis_thinking"):
        effective["thinking"]["synthesis_level"] = query_params["synthesis_thinking"]

    return effective


# ============================================================
# SESSION LOGGER - Comprehensive logging for debugging & audit
# ============================================================

class SessionLogger:
    """Comprehensive session-based logging for debugging and audit."""

    def __init__(self, session_id: str = None):
        """Initialize or resume a session logger.

        Args:
            session_id: Optional existing session ID for follow-up messages.
                        If None, generates a new session ID.
        """
        self.session_id = session_id or self._generate_session_id()
        self.logs_dir = Path(__file__).parent / 'logs'
        self.logs_dir.mkdir(exist_ok=True)
        self.log_file = self.logs_dir / f"{self.session_id}.log"
        self.entries = []
        # Temporary cost instrumentation: accumulate Gemini token usage across
        # every model call in a single /chat/stream request (MCP tool loop, KB,
        # synthesis, chart config). Emitted to the UI as a `usage` SSE event and
        # gated behind ?debug=tokens on the client. `output` includes thinking
        # tokens (thoughtsTokenCount) since Gemini bills those as output.
        # Guarded by a lock because MCP/KB/chart calls run in parallel threads.
        self.token_usage = {"input": 0, "output": 0, "total": 0}
        self._usage_lock = threading.Lock()
        self._write_header()

    def add_usage(self, usage_metadata: Optional[dict]) -> None:
        """Accumulate one Gemini call's usageMetadata into the request total.

        Args:
            usage_metadata: The `usageMetadata` block from a Gemini response
                (streaming or not). No-op if falsy or missing counts.
        """
        if not usage_metadata:
            return
        prompt = usage_metadata.get("promptTokenCount", 0) or 0
        candidates = usage_metadata.get("candidatesTokenCount", 0) or 0
        thoughts = usage_metadata.get("thoughtsTokenCount", 0) or 0
        total = usage_metadata.get("totalTokenCount", 0) or 0
        with self._usage_lock:
            self.token_usage["input"] += prompt
            self.token_usage["output"] += candidates + thoughts
            # Fall back to input+output when the API omits a total.
            self.token_usage["total"] += total or (prompt + candidates + thoughts)

    def _generate_session_id(self) -> str:
        """Generate a short readable session ID.

        Format: YYMMDD-HHMMSS-XXXX (e.g., 260128-143052-a7f3)
        """
        timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
        short_uuid = uuid.uuid4().hex[:4]
        return f"{timestamp}-{short_uuid}"

    def _write_header(self):
        """Write session header to log file (only if new file)."""
        if self.log_file.exists():
            # Resuming existing session - add continuation marker
            with open(self.log_file, 'a') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"CONTINUATION @ {datetime.now().isoformat()}\n")
                f.write(f"{'='*80}\n")
        else:
            # New session - write header
            with open(self.log_file, 'w') as f:
                f.write(f"{'='*80}\n")
                f.write(f"SESSION LOG: {self.session_id}\n")
                f.write(f"Started: {datetime.now().isoformat()}\n")
                f.write(f"{'='*80}\n\n")

    def log(self, event_type: str, data: dict):
        """Log an event with full request/response details."""
        timestamp = datetime.now().isoformat()
        entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "data": data
        }
        self.entries.append(entry)

        # Write to file immediately
        with open(self.log_file, 'a') as f:
            f.write(f"\n--- {event_type} @ {timestamp} ---\n")
            f.write(json.dumps(data, indent=2, default=str))
            f.write("\n")

    def log_user_message(self, message: str, history_count: int = 0):
        """Log the user's input message."""
        self.log("USER_MESSAGE", {
            "message": message,
            "history_messages": history_count
        })

    def log_gemini_request(self, model: str, endpoint: str, payload_info: dict):
        """Log outgoing Gemini API request."""
        self.log("GEMINI_REQUEST", {
            "model": model,
            "endpoint": endpoint,
            "payload": payload_info
        })

    def log_gemini_response(self, model: str, response: dict, duration_ms: float):
        """Log incoming Gemini API response."""
        self.log("GEMINI_RESPONSE", {
            "model": model,
            "duration_ms": round(duration_ms, 2),
            "response": self._truncate_response(response)
        })

    def log_mcp_tool_call(self, tool_name: str, arguments: dict):
        """Log MCP tool call request."""
        self.log("MCP_TOOL_REQUEST", {
            "tool_name": tool_name,
            "arguments": arguments
        })

    def log_mcp_tool_result(self, tool_name: str, result: Any, duration_ms: float, status: str = "success"):
        """Log MCP tool call result."""
        result_str = json.dumps(result, default=str) if isinstance(result, dict) else str(result)
        self.log("MCP_TOOL_RESPONSE", {
            "tool_name": tool_name,
            "duration_ms": round(duration_ms, 2),
            "status": status,
            "result": result_str  # No truncation - full result for debugging
        })

    def log_kb_query(self, message: str, result: str, duration_ms: float):
        """Log Knowledge Base query."""
        self.log("KB_QUERY", {
            "query": message,
            "duration_ms": round(duration_ms, 2),
            "result_length": len(result),
            "result": result  # No truncation - full result for debugging
        })

    def log_synthesis_start(self, context_parts: list):
        """Log synthesis phase start."""
        self.log("SYNTHESIS_START", {
            "context_sources": context_parts
        })

    def log_final_response(self, text: str, chart_config: dict = None, total_duration_ms: float = None):
        """Log the final response sent to user."""
        self.log("FINAL_RESPONSE", {
            "text_length": len(text),
            "text_preview": text[:500] + "..." if len(text) > 500 else text,
            "chart_config": chart_config,
            "total_duration_ms": round(total_duration_ms, 2) if total_duration_ms else None
        })

    def log_error(self, error_type: str, error_message: str, context: dict = None):
        """Log an error."""
        self.log("ERROR", {
            "error_type": error_type,
            "error_message": str(error_message),
            "context": context or {}
        })

    def _truncate_response(self, response: dict) -> dict:
        """Return full response for logging (no truncation)."""
        return response


# Flask app
app = Flask(__name__)
# Scoped CORS. ALLOWED_ORIGIN defaults to "*" so dev still works
# without configuration; production sets this to the Cloud Run service URL
# (comma-separated for multiple origins).
CORS(app, origins=os.environ.get("ALLOWED_ORIGIN", "*").split(","))


# Route aliases the React UI expects. The upstream routes (/api/chat/stream,
# /api/config) stay live
# for backward compatibility; these aliases are what the SPA at /agent/* hits
# via the services container's nginx prefix-strip.
# Short-TTL cache for branding.json so we don't hit GCS (and the
# metadata token endpoint) on every page load. Bounds staleness to _BRAND_TTL
# seconds; /brand?refresh=1 forces an immediate refetch after a config sync
# (e.g. `deploy.sh --config-only`).
_BRAND_CACHE: dict = {"ts": 0.0, "payload": None}
_BRAND_TTL_SECONDS = int(os.environ.get("BRAND_CACHE_TTL", "60"))


def _build_brand_payload() -> dict:
    """Assemble the /brand payload: the config bucket URL plus, when available,
    the branding.json contents fetched from the (possibly private) bucket."""
    brand_config_url = os.environ.get("BRAND_CONFIG_URL", "").rstrip("/")
    branding_data = None
    if brand_config_url:
        try:
            r = _fetch_gcs_url(f"{brand_config_url}/branding.json")
            if r.status_code == 200:
                branding_data = r.json()
                logger.info("Successfully fetched branding.json from config bucket")
            else:
                logger.warning(f"Failed to fetch branding.json: HTTP {r.status_code}")
        except Exception as e:
            logger.error(f"Error fetching branding.json from bucket: {e}")

    return {
        "brand_config_url": brand_config_url,
        "instance": os.environ.get("INSTANCE_ID", ""),
        "branding": branding_data,
    }


@app.route("/brand", methods=["GET"])
def brand_alias():
    """Return the per-instance branding bucket URL and branding.json contents.

    Cached in-process for _BRAND_TTL_SECONDS; pass ?refresh=1 to force a fresh
    fetch (e.g. right after uploading a new branding.json to the bucket)."""
    force = request.args.get("refresh") == "1"
    now = time.time()
    cached = _BRAND_CACHE["payload"]
    if not force and cached is not None and now - _BRAND_CACHE["ts"] < _BRAND_TTL_SECONDS:
        payload = cached
    else:
        payload = _build_brand_payload()
        _BRAND_CACHE["payload"] = payload
        _BRAND_CACHE["ts"] = now

    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    return resp

# Global state
session_id = None
tools_cache = None


def mcp_request(method: str, params: dict = None, is_notification: bool = False) -> dict:
    """Send a JSON-RPC request or notification to the MCP server.

    Args:
        method: The JSON-RPC method name
        params: Optional parameters
        is_notification: If True, sends as notification (no id, no response expected)
    """
    global session_id  # Needed to SET the global session_id from response headers

    payload = {
        "jsonrpc": "2.0",
        "method": method
    }

    # Notifications don't have an id
    if not is_notification:
        payload["id"] = int(time.time() * 1000)

    if params:
        payload["params"] = params

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    if session_id:
        headers["Mcp-Session-Id"] = session_id

    try:
        # For notifications, we send but don't expect a response
        if is_notification:
            requests.post(
                MCP_URL,
                json=payload,
                headers=headers,
                timeout=5
            )
            return {"result": "notification sent"}

        response = requests.post(
            MCP_URL,
            json=payload,
            headers=headers,
            timeout=300,
            stream=True
        )

        # Log response details for debugging
        logger.info(f"MCP Response - Status: {response.status_code}, Headers: {dict(response.headers)}")

        # Get session ID from response (try multiple header variations)
        session_header = (
            response.headers.get("Mcp-Session-Id") or
            response.headers.get("mcp-session-id") or
            response.headers.get("MCP-Session-ID")
        )
        if session_header:
            session_id = session_header
            logger.info(f"Got MCP session ID from headers: {session_id}")
        else:
            logger.warning(f"No session ID in response headers. Available headers: {list(response.headers.keys())}")

        content_type = response.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # Parse SSE response
            result = None
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        try:
                            data = json.loads(line_str[6:])
                            if "result" in data:
                                result = data["result"]
                            elif "error" in data:
                                return {"error": data["error"]}
                        except json.JSONDecodeError:
                            continue
            return {"result": result} if result else {"error": "No result"}
        else:
            return response.json()

    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to MCP server at {MCP_URL}. Make sure it's running!"}
    except Exception as e:
        return {"error": str(e)}


def initialize_mcp() -> bool:
    """Initialize the MCP session."""
    global session_id

    logger.info("Initializing MCP session...")

    result = mcp_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {"roots": {"listChanged": True}},
        "clientInfo": {"name": "dc-mcp-proxy", "version": "1.0.0"}
    })

    if "error" in result:
        logger.error(f"Failed to initialize MCP: {result['error']}")
        return False

    logger.info(f"MCP session initialized: {session_id}")

    # Send initialized notification (no id, no response expected)
    mcp_request("notifications/initialized", {}, is_notification=True)
    return True


def get_tools() -> list:
    """Get available tools from MCP server."""
    global tools_cache

    if tools_cache:
        return tools_cache

    result = mcp_request("tools/list", {})

    if "result" in result and result["result"] and "tools" in result["result"]:
        tools_cache = result["result"]["tools"]
        return tools_cache

    return []


def transform_schema_for_gemini(schema: dict) -> dict:
    """Transform MCP inputSchema to Gemini-compatible format.

    Gemini function calling only supports a subset of OpenAPI 3.0.3 schema.
    This removes unsupported constructs like 'anyOf' for nullable types.

    Args:
        schema: The MCP inputSchema dictionary

    Returns:
        dict: Gemini-compatible schema
    """
    if not isinstance(schema, dict):
        return schema

    result = {}

    # Handle anyOf (union types) - common for nullable fields in MCP schemas
    # e.g., {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null}
    if "anyOf" in schema:
        # Find the non-null type and use that
        for option in schema["anyOf"]:
            if option.get("type") != "null":
                result = transform_schema_for_gemini(option)
                break
        # Preserve default if present at the anyOf level
        if "default" in schema:
            result["default"] = schema["default"]
        # Preserve description if present at the anyOf level
        if "description" in schema:
            result["description"] = schema["description"]
        return result

    # Copy supported fields
    for key in ["type", "description", "default", "enum"]:
        if key in schema:
            result[key] = schema[key]

    # Handle object properties recursively
    if "properties" in schema:
        result["properties"] = {
            k: transform_schema_for_gemini(v)
            for k, v in schema["properties"].items()
        }

    # Handle required array
    if "required" in schema:
        result["required"] = schema["required"]

    # Handle array items recursively
    if "items" in schema:
        result["items"] = transform_schema_for_gemini(schema["items"])

    return result


def fix_tool_arguments(name: str, arguments: dict) -> dict:
    """Fix common parameter mistakes made by LLMs."""
    args = arguments.copy()

    if name == "get_observations":
        # Fix 1: If date_range_start/end provided but date != 'range', fix it
        has_range_params = args.get("date_range_start") or args.get("date_range_end")
        if has_range_params and args.get("date") != "range":
            logger.info("Fixing: Setting date='range' because date_range params provided")
            args["date"] = "range"

        # Fix 2: Ensure date has a default if not provided
        if "date" not in args:
            args["date"] = "latest"

        # Fix 3: Remove null/None values that might cause issues
        args = {k: v for k, v in args.items() if v is not None}

    if name == "search_indicators":
        # Ensure places is a list
        if "places" in args and isinstance(args["places"], str):
            args["places"] = [args["places"]]

    return args


def call_tool(name: str, arguments: dict, session_logger: Optional[SessionLogger] = None) -> Any:
    """Call a tool on the MCP server with optional logging."""
    # Fix common parameter mistakes
    fixed_args = fix_tool_arguments(name, arguments)
    if fixed_args != arguments:
        logger.info(f"Fixed arguments: {arguments} -> {fixed_args}")

    # Log tool call request
    if session_logger:
        session_logger.log_mcp_tool_call(name, fixed_args)

    start_time = time.time()

    result = mcp_request("tools/call", {
        "name": name,
        "arguments": fixed_args
    })

    duration_ms = (time.time() - start_time) * 1000

    if "result" in result:
        # Log successful result
        if session_logger:
            session_logger.log_mcp_tool_result(name, result["result"], duration_ms, "success")
        return result["result"]

    # Log error result
    error_result = {"error": result.get("error", "Unknown error")}
    if session_logger:
        session_logger.log_mcp_tool_result(name, error_result, duration_ms, "error")
    return error_result


def check_data_availability(tool_calls_list: list) -> dict:
    """Check if MCP tool calls returned useful data.

    Returns:
        dict with keys:
        - has_data: bool
        - no_variables_found: bool (search_indicators returned empty)
        - no_observations_found: bool (get_observations returned empty)
        - message: str (user-friendly message if no data)
    """
    no_variables = False
    has_any_observations = False  # Track if ANY observation has data
    all_observations_empty = True  # Track if ALL observations are empty
    search_called = False
    observations_called = False

    for tc in tool_calls_list:
        result_str = tc.get('result', '')
        result_str_lower = result_str.lower()
        tool_name = tc.get('name', '')

        if tool_name == 'search_indicators':
            search_called = True
            # Check if no variables found
            if 'no indicators found' in result_str_lower or \
               '"variables": []' in result_str_lower or \
               'no matching' in result_str_lower or \
               'could not find' in result_str_lower or \
               ('"indicators":' in result_str_lower and '[]' in result_str_lower):
                no_variables = True

        elif tool_name == 'get_observations':
            observations_called = True

            # Check if THIS observation has actual data (time_series with values)
            # Look for patterns like: "time_series": [["2024", 14984.0]] (has data)
            # vs: "time_series": [] (empty)

            # Check for non-empty time_series with actual values
            has_data_pattern = re.search(r'"time_series":\s*\[\s*\[', result_str)
            if has_data_pattern:
                has_any_observations = True
                all_observations_empty = False

            # Also check for valid source_id (not "unknown")
            valid_source = re.search(r'"source_id":\s*"(?!unknown)[^"]+', result_str_lower)
            if valid_source and has_data_pattern:
                has_any_observations = True
                all_observations_empty = False

            # Check if this specific observation is empty
            is_empty = ('no data' in result_str_lower or
                       '"observations": []' in result_str_lower or
                       '"time_series": []' in result_str_lower or
                       '"time_series":[]' in result_str_lower or
                       'no observations' in result_str_lower)

            if not is_empty:
                all_observations_empty = False

    # Determine if we have usable data
    # We have data if: we found variables AND at least one observation has data
    if search_called and no_variables:
        has_data = False
    elif observations_called and all_observations_empty and not has_any_observations:
        has_data = False
    else:
        has_data = has_any_observations or (observations_called and not all_observations_empty)

    # Build user-friendly message
    message = None
    if not has_data:
        if no_variables:
            message = "We didn't find any matching data variables for your query."
        elif observations_called and all_observations_empty:
            message = "We found the data variable but there are no observations available."
        else:
            message = "We didn't find data for your query."

    return {
        'has_data': has_data,
        'no_variables_found': no_variables,
        'no_observations_found': all_observations_empty,
        'search_called': search_called,
        'observations_called': observations_called,
        'message': message
    }


def extract_provenance_from_mcp_results(tool_calls_list: list) -> list:
    """Extract provenance URLs from MCP tool call results.

    Parses the source_metadata from get_observations results to extract
    import_name and provenance_url for proper source attribution.

    Args:
        tool_calls_list: List of tool call dicts with 'name', 'arguments', 'result'

    Returns:
        list of dicts: [{"name": "Import Name", "url": "https://..."}]
    """
    sources = []
    seen_urls = set()

    for tc in tool_calls_list:
        if tc.get('name') != 'get_observations':
            continue

        result_str = tc.get('result', '')
        try:
            # The result is nested JSON - parse outer layer first
            if isinstance(result_str, str):
                outer = json.loads(result_str)
                if 'content' in outer and outer['content']:
                    # Parse inner text JSON
                    inner_text = outer['content'][0].get('text', '{}')
                    result_data = json.loads(inner_text)
                else:
                    result_data = outer
            else:
                result_data = result_str

            # Extract from source_metadata
            if 'source_metadata' in result_data:
                metadata = result_data['source_metadata']
                url = metadata.get('provenance_url', '')
                name = metadata.get('import_name', '')

                if url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append({
                        "name": name or "Data Source",
                        "url": url
                    })

        except (json.JSONDecodeError, KeyError, TypeError, IndexError):
            continue

    return sources


# Flask Routes

@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({"status": "ok", "mcp_url": MCP_URL})


@app.route("/api/tools", methods=["GET"])
def list_tools():
    """List available tools."""
    global session_id

    if not session_id:
        if not initialize_mcp():
            return jsonify({"success": False, "error": "Cannot connect to MCP server. Make sure it's running on port 3000!"}), 503

    tools = get_tools()
    if not tools:
        return jsonify({"success": False, "error": "No tools available"}), 503

    # Convert to Gemini format (transform schema to remove unsupported constructs)
    gemini_tools = [{
        "name": t.get("name", ""),
        "description": t.get("description", ""),
        "parameters": transform_schema_for_gemini(
            t.get("inputSchema", {"type": "object", "properties": {}})
        )
    } for t in tools]

    return jsonify({"success": True, "tools": gemini_tools, "raw_tools": tools})


@app.route("/api/call", methods=["POST"])
def tool_call():
    """Execute a tool call."""
    global session_id

    if not session_id:
        if not initialize_mcp():
            return jsonify({"success": False, "error": "Cannot connect to MCP server"}), 503

    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"success": False, "error": "Tool name required"}), 400

    logger.info(f"Calling tool: {data['name']}")
    result = call_tool(data["name"], data.get("arguments", {}))
    return jsonify({"success": True, "result": result})


@app.route("/", methods=["GET"])
def index():
    return f"""
    <html>
    <head><title>MCP Proxy</title></head>
    <body>
    <h1>Data Commons MCP Proxy Server (Proxy-Only Mode)</h1>
    <p>MCP Server: {MCP_URL}</p>
    <p>Proxy Server: http://localhost:{PROXY_PORT}</p>
    <ul>
        <li><a href="/health">/health</a> - Health check</li>
        <li><a href="/api/tools">/api/tools</a> - List tools</li>
        <li>POST /api/call - Execute tool</li>
        <li><a href="/api/config">/api/config</a> - Get backend config (no API key)</li>
        <li>POST /api/chat/stream - Full chat with streaming</li>
        <li><a href="/logs?key=">/logs</a> - Query Analytics Dashboard (requires ?key=SECRET)</li>
    </ul>
    <h3>Prerequisite</h3>
    <p>Make sure the MCP server is running:</p>
    <code>python3 -m uv tool run datacommons-mcp serve http --port {MCP_PORT}</code>
    </body>
    </html>
    """


# ============================================================
# NEW BACKEND API ENDPOINTS FOR GEMINI CALLS
# ============================================================

@app.route("/api/config", methods=["GET"])
def get_config_endpoint():
    """Return sanitized config (without API key) for frontend."""
    config = load_config()
    if not config:
        return jsonify({"success": False, "error": "Config not loaded"}), 500

    # Return config without sensitive data
    safe_config = {
        "proxy_url": config.get("proxy_url", f"http://localhost:{PROXY_PORT}"),
        "gemini": {
            "api_base": config.get("gemini", {}).get("api_base", ""),
            "mcp_model": config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview"),
            "kb_model": config.get("gemini", {}).get("kb_model", "gemini-3-flash-preview"),
        },
        "mcp": config.get("mcp", {}),
        "knowledge_base": config.get("knowledge_base", {}),
        "thinking": config.get("thinking", {}),
        "has_api_key": bool(config.get("gemini", {}).get("api_key")),
    }
    return jsonify({"success": True, "config": safe_config})


def build_thinking_config(thinking_value: str, include_thoughts: bool = False) -> dict:
    """Build thinking configuration for Gemini 3 models.

    Args:
        thinking_value: Thinking level ('minimal', 'low', 'medium', 'high')
        include_thoughts: If True, includes thought summaries in the response

    Returns:
        dict: thinkingConfig for Gemini generationConfig
    """
    # Gemini 3 Flash valid levels
    valid_levels = ["minimal", "low", "medium", "high"]
    level = thinking_value.lower() if thinking_value.lower() in valid_levels else "low"

    config = {
        "thinkingConfig": {
            "thinkingLevel": level  # Gemini 3 format (string)
        }
    }

    if include_thoughts:
        config["thinkingConfig"]["includeThoughts"] = True

    return config


def gemini_request(
    messages: list,
    system_instruction: str,
    model: str,
    tools: list = None,
    temperature: float = 0.3,
    thinking_level: str = None,
    response_schema: dict = None,
    stream: bool = False,
    session_logger: Optional[SessionLogger] = None,
    include_thoughts: bool = False,
    demo_mode: bool = False
) -> Generator | dict:
    """Make a request to the Gemini API with key rotation and retry.

    Args:
        messages: Conversation history in Gemini format
        system_instruction: System prompt
        model: Model name (e.g., 'gemini-3-flash-preview')
        tools: Optional list of function declarations
        temperature: Sampling temperature
        thinking_level: Optional thinking budget level
        response_schema: Optional JSON schema for structured output
        stream: If True, returns a generator for SSE streaming
        session_logger: Optional SessionLogger for comprehensive logging
        include_thoughts: If True (and stream=True), yields dicts with 'type' and 'content'
                         for both thoughts and text. If False, yields plain text strings.
        demo_mode: If True, uses demo API keys reserved for internal demos.

    Returns:
        If stream=False: dict with response
        If stream=True and include_thoughts=False: Generator yielding text chunks (str)
        If stream=True and include_thoughts=True: Generator yielding dicts {'type': 'thought'|'text', 'content': str}
    """
    config = load_config()
    api_base = config.get("gemini", {}).get("api_base", "https://generativelanguage.googleapis.com/v1beta/models")

    # Get all available keys (demo or regular based on mode)
    all_keys = get_api_keys(demo_mode=demo_mode)
    if not all_keys:
        return {"error": "No Gemini API keys configured in config.json"}

    # Shuffle keys for random order
    keys_to_try = all_keys.copy()
    random.shuffle(keys_to_try)

    # Build the payload (same for all attempts)
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": temperature,
        }
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": inject_datetime(system_instruction)}]
        }

    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    if thinking_level:
        # Enable includeThoughts in API if caller wants thought streaming
        payload["generationConfig"].update(
            build_thinking_config(thinking_level, include_thoughts=(stream and include_thoughts))
        )

    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema

    endpoint = "streamGenerateContent" if stream else "generateContent"

    # Log request (once, before attempting)
    if session_logger:
        session_logger.log_gemini_request(model, endpoint, {
            "messages_count": len(messages),
            "has_tools": bool(tools),
            "tool_count": len(tools) if tools else 0,
            "temperature": temperature,
            "thinking_level": thinking_level,
            "has_response_schema": bool(response_schema),
            "stream": stream,
            "total_keys_available": len(all_keys)
        })

    last_error = None
    attempt_count = 0

    for api_key in keys_to_try:
        attempt_count += 1

        # Build URL with current key
        url = f"{api_base}/{model}:{endpoint}"
        if stream:
            url += f"?key={api_key}&alt=sse"
        else:
            url += f"?key={api_key}"

        # Log retry attempt (if not first attempt)
        if attempt_count > 1 and session_logger:
            session_logger.log("GEMINI_KEY_ROTATION", {
                "attempt": attempt_count,
                "total_keys": len(all_keys),
                "reason": str(last_error)
            })

        start_time = time.time()

        try:
            if stream:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    stream=True,
                    timeout=300
                )
                # Check for rate limit before streaming
                if response.status_code == 429:
                    last_error = "Rate limited (429)"
                    logger.warning(f"API key rate limited, switching to next key...")
                    continue  # Immediately try next key
                if response.status_code in [500, 503]:
                    last_error = f"Server error ({response.status_code})"
                    logger.warning(f"Server error {response.status_code}, switching to next key...")
                    continue  # Try next key
                return _stream_gemini_response(response, session_logger, return_dicts=include_thoughts)
            else:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=300
                )

                # Check for rate limit - immediately switch key
                if response.status_code == 429:
                    last_error = "Rate limited (429)"
                    logger.warning(f"API key rate limited, switching to next key...")
                    continue  # Immediately try next key

                # Check for other retryable errors (500, 503)
                if response.status_code in [500, 503]:
                    last_error = f"Server error ({response.status_code})"
                    logger.warning(f"Server error {response.status_code}, switching to next key...")
                    continue  # Try next key

                result = response.json()

                # Log response
                if session_logger:
                    duration_ms = (time.time() - start_time) * 1000
                    session_logger.log_gemini_response(model, result, duration_ms)
                    session_logger.add_usage(result.get("usageMetadata"))

                return result

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            logger.warning(f"Request timeout, trying next key...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"Gemini API error: {e}")
            if session_logger:
                session_logger.log_error("GEMINI_API_ERROR", str(e), {"attempt": attempt_count, "model": model})
            continue

    # All keys exhausted
    error_msg = f"All {len(all_keys)} API keys failed. Last error: {last_error}"
    logger.error(error_msg)
    if session_logger:
        session_logger.log_error("GEMINI_ALL_KEYS_EXHAUSTED", error_msg, {"total_keys": len(all_keys)})
    return {"error": error_msg}


def _stream_gemini_response(response, session_logger: Optional[SessionLogger] = None, return_dicts: bool = False) -> Generator:
    """Parse streaming response from Gemini API.

    Args:
        response: The requests response object with streaming enabled
        session_logger: Optional SessionLogger for logging
        return_dicts: If True, yields dicts with 'type' and 'content' keys
                      for both thoughts and text. If False, yields plain text strings.

    Yields:
        If return_dicts=True: {'type': 'thought'|'text', 'content': str}
        If return_dicts=False: str (text only, for backward compatibility)
    """
    start_time = time.time()
    total_text = ""
    total_thoughts = ""
    usage_metadata = None

    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                try:
                    data = json.loads(line_str[6:])
                    # Token counts arrive on the final SSE chunk (cumulative for
                    # this call); keep the latest seen.
                    if 'usageMetadata' in data:
                        usage_metadata = data['usageMetadata']
                    if 'candidates' in data and data['candidates']:
                        candidate = data['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            for part in candidate['content']['parts']:
                                if 'text' in part:
                                    # Check if this is a thought summary or regular text
                                    is_thought = part.get('thought', False)
                                    if is_thought:
                                        total_thoughts += part['text']
                                        if return_dicts:
                                            yield {'type': 'thought', 'content': part['text']}
                                        # Skip thoughts in legacy mode (return_dicts=False)
                                    else:
                                        total_text += part['text']
                                        if return_dicts:
                                            yield {'type': 'text', 'content': part['text']}
                                        else:
                                            yield part['text']
                except json.JSONDecodeError:
                    continue

    # Accumulate this call's token usage into the request total.
    if session_logger:
        session_logger.add_usage(usage_metadata)

    # Log streaming completion
    if session_logger:
        duration_ms = (time.time() - start_time) * 1000
        session_logger.log("GEMINI_STREAM_COMPLETE", {
            "duration_ms": round(duration_ms, 2),
            "total_text_length": len(total_text),
            "total_thoughts_length": len(total_thoughts)
        })


def gemini_request_with_thought_streaming(
    messages: list,
    system_instruction: str,
    model: str,
    tools: list = None,
    temperature: float = 0.3,
    thinking_level: str = None,
    response_schema: dict = None,
    session_logger: Optional[SessionLogger] = None,
    thought_callback: callable = None,
    demo_mode: bool = False
) -> dict:
    """Make a streaming Gemini request, calling thought_callback for thoughts but returning complete response.

    This enables thought streaming for reduced TTFT while still getting the
    complete response needed for tool call processing.

    Args:
        messages: Conversation history in Gemini format
        system_instruction: System prompt
        model: Model name (e.g., 'gemini-3-flash-preview')
        tools: Optional list of function declarations
        temperature: Sampling temperature
        thinking_level: Optional thinking budget level
        response_schema: Optional JSON schema for structured output
        session_logger: Optional SessionLogger for comprehensive logging
        thought_callback: Optional callback function called with each thought chunk.
                         Signature: callback(thought_text: str) -> None
        demo_mode: If True, uses demo API keys reserved for internal demos.

    Returns:
        dict: Complete response (same format as non-streaming gemini_request)
    """
    config = load_config()
    api_base = config.get("gemini", {}).get("api_base", "https://generativelanguage.googleapis.com/v1beta/models")

    # Get all available keys (demo or regular based on mode)
    all_keys = get_api_keys(demo_mode=demo_mode)
    if not all_keys:
        return {"error": "No Gemini API keys configured in config.json"}

    # Shuffle keys for random order
    keys_to_try = all_keys.copy()
    random.shuffle(keys_to_try)

    # Build payload
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": temperature,
        }
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": inject_datetime(system_instruction)}]
        }

    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    if thinking_level:
        # Enable includeThoughts for streaming thought summaries
        payload["generationConfig"].update(
            build_thinking_config(thinking_level, include_thoughts=True)
        )

    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema

    # Log request
    if session_logger:
        session_logger.log_gemini_request(model, "streamGenerateContent", {
            "messages_count": len(messages),
            "has_tools": bool(tools),
            "tool_count": len(tools) if tools else 0,
            "temperature": temperature,
            "thinking_level": thinking_level,
            "include_thoughts": True,
            "total_keys_available": len(all_keys)
        })

    last_error = None
    attempt_count = 0

    for api_key in keys_to_try:
        attempt_count += 1

        # Build URL for streaming
        url = f"{api_base}/{model}:streamGenerateContent?key={api_key}&alt=sse"

        # Log retry attempt (if not first attempt)
        if attempt_count > 1 and session_logger:
            session_logger.log("GEMINI_KEY_ROTATION", {
                "attempt": attempt_count,
                "total_keys": len(all_keys),
                "reason": str(last_error)
            })

        start_time = time.time()

        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                stream=True,
                timeout=300
            )

            # Check for rate limit before streaming
            if response.status_code == 429:
                last_error = "Rate limited (429)"
                logger.warning(f"API key rate limited, switching to next key...")
                continue
            if response.status_code in [500, 503]:
                last_error = f"Server error ({response.status_code})"
                logger.warning(f"Server error {response.status_code}, switching to next key...")
                continue

            # Collect response while streaming thoughts
            collected_text = ""
            collected_function_calls = []
            collected_thoughts = ""
            collected_usage = None

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            if 'usageMetadata' in data:
                                collected_usage = data['usageMetadata']
                            if 'candidates' in data and data['candidates']:
                                candidate = data['candidates'][0]
                                if 'content' in candidate and 'parts' in candidate['content']:
                                    for part in candidate['content']['parts']:
                                        if 'functionCall' in part:
                                            collected_function_calls.append(part)
                                        elif 'text' in part:
                                            is_thought = part.get('thought', False)
                                            if is_thought:
                                                collected_thoughts += part['text']
                                                if thought_callback:
                                                    thought_callback(part['text'])
                                            else:
                                                collected_text += part['text']
                        except json.JSONDecodeError:
                            continue

            # Accumulate this call's token usage into the request total.
            if session_logger:
                session_logger.add_usage(collected_usage)

            # Build response in same format as non-streaming
            result_parts = []
            for fc in collected_function_calls:
                result_parts.append(fc)
            if collected_text:
                result_parts.append({"text": collected_text})

            result = {
                "candidates": [{
                    "content": {
                        "parts": result_parts,
                        "role": "model"
                    }
                }]
            }

            # Log response
            if session_logger:
                duration_ms = (time.time() - start_time) * 1000
                session_logger.log_gemini_response(model, result, duration_ms)
                if collected_thoughts:
                    session_logger.log("THOUGHTS_STREAMED", {
                        "thoughts_length": len(collected_thoughts)
                    })

            return result

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            logger.warning(f"Request timeout, trying next key...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"Gemini API error: {e}")
            if session_logger:
                session_logger.log_error("GEMINI_API_ERROR", str(e), {"attempt": attempt_count, "model": model})
            continue

    # All keys exhausted
    error_msg = f"All {len(all_keys)} API keys failed. Last error: {last_error}"
    logger.error(error_msg)
    if session_logger:
        session_logger.log_error("GEMINI_ALL_KEYS_EXHAUSTED", error_msg, {"total_keys": len(all_keys)})
    return {"error": error_msg}


def execute_mcp_tool_loop(
    user_message: str,
    history: list,
    max_iterations: int = 5,
    session_logger: Optional[SessionLogger] = None,
    effective_config: dict = None,
    thought_callback: callable = None,
    demo_mode: bool = False
) -> tuple:
    """Execute the MCP tool calling loop with optional thought streaming.

    Args:
        user_message: The user's query
        history: Conversation history
        max_iterations: Maximum tool calling iterations
        session_logger: Optional SessionLogger for comprehensive logging
        effective_config: Optional config dict with query param overrides applied
        thought_callback: Optional callback for streaming thought chunks.
                         Signature: callback(thought_text: str) -> None
        demo_mode: If True, uses demo API keys reserved for internal demos.

    Returns:
        tuple: (tool_results_text, tool_calls_list, final_response_text)
    """
    config = effective_config if effective_config else load_config()
    mcp_prompt = config.get("prompts", {}).get("mcp", "")
    mcp_model = config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")
    thinking_level = config.get("thinking", {}).get("mcp_level", "low")

    # Get MCP tools
    tools = get_tools()
    if not tools:
        if session_logger:
            session_logger.log_error("MCP_TOOLS_UNAVAILABLE", "No MCP tools available")
        return "", [], "MCP tools not available"

    # Convert tools to Gemini format (transform schema to remove unsupported constructs)
    gemini_tools = [{
        "name": t.get("name", ""),
        "description": t.get("description", ""),
        "parameters": transform_schema_for_gemini(
            t.get("inputSchema", {"type": "object", "properties": {}})
        )
    } for t in tools]

    # Build conversation - NO history for MCP calls (fresh search every time)
    # History is only used in synthesis phase for context
    contents = []
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    tool_calls_list = []
    all_tool_results = []

    for iteration in range(max_iterations):
        logger.info(f"MCP Tool Loop - Iteration {iteration + 1}/{max_iterations}")

        if session_logger:
            session_logger.log("MCP_LOOP_ITERATION", {"iteration": iteration + 1, "max": max_iterations})

        response = gemini_request_with_thought_streaming(
            messages=contents,
            system_instruction=mcp_prompt,
            model=mcp_model,
            tools=gemini_tools,
            temperature=1.0,
            thinking_level=thinking_level,
            session_logger=session_logger,
            thought_callback=thought_callback,
            demo_mode=demo_mode
        )

        if "error" in response:
            if session_logger:
                session_logger.log_error("MCP_LOOP_ERROR", response['error'])
            return "", tool_calls_list, f"Error: {response['error']}"

        # Check for function calls
        candidates = response.get("candidates", [])
        if not candidates:
            if session_logger:
                session_logger.log_error("MCP_NO_CANDIDATES", "No response from model")
            return "", tool_calls_list, "No response from model"

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        function_calls = []
        text_response = ""

        for part in parts:
            if "functionCall" in part:
                function_calls.append(part["functionCall"])
            elif "text" in part:
                text_response += part["text"]

        # If no function calls, we're done
        if not function_calls:
            tool_results_text = "\n\n".join(all_tool_results)
            if session_logger:
                session_logger.log("MCP_LOOP_COMPLETE", {
                    "iterations_used": iteration + 1,
                    "tools_called": len(tool_calls_list),
                    "has_text_response": bool(text_response)
                })
            return tool_results_text, tool_calls_list, text_response

        # Execute function calls
        contents.append({"role": "model", "parts": parts})
        function_responses = []

        for fc in function_calls:
            tool_name = fc.get("name", "")
            tool_args = fc.get("args", {})

            logger.info(f"Executing MCP tool: {tool_name}")
            result = call_tool(tool_name, tool_args, session_logger=session_logger)

            # Convert result to string
            if isinstance(result, dict):
                if "content" in result and isinstance(result["content"], list):
                    result_text = "\n".join([
                        c.get("text", json.dumps(c)) for c in result["content"]
                    ])
                else:
                    result_text = json.dumps(result)
            else:
                result_text = str(result)

            tool_call_info = {
                "name": tool_name,
                "arguments": tool_args,
                "result": result_text,  # No truncation - full result for source extraction
                "status": "error" if "error" in result_text.lower() else "success"
            }
            tool_calls_list.append(tool_call_info)
            all_tool_results.append(f"Tool: {tool_name}\nResult: {result_text}")

            function_responses.append({
                "functionResponse": {
                    "name": tool_name,
                    "response": {"result": result_text}
                }
            })

        contents.append({"role": "user", "parts": function_responses})

    # Max iterations reached
    tool_results_text = "\n\n".join(all_tool_results)
    if session_logger:
        session_logger.log("MCP_LOOP_MAX_ITERATIONS", {"tools_called": len(tool_calls_list)})
    return tool_results_text, tool_calls_list, "Max tool iterations reached"


def get_api_key_filestore_mapping(demo_mode: bool = False) -> dict:
    """Build mapping of API key -> filestore from config.

    Each API key in gemini.api_keys maps to the filestore at the same index
    in gemini.filestores array.

    Args:
        demo_mode: If True, uses demo_api_keys and demo_filestores for mapping.

    Returns:
        dict mapping api_key -> filestore_id
    """
    config = load_config()
    gemini_config = config.get("gemini", {})

    if demo_mode:
        api_keys = gemini_config.get("demo_api_keys", [])
        filestores = gemini_config.get("demo_filestores", [])
        if api_keys:
            logger.info(f"Using demo filestore mapping ({len(api_keys)} keys)")
    else:
        api_keys = gemini_config.get("api_keys", [])
        filestores = gemini_config.get("filestores", [])

    # Build the mapping - each key maps to filestore at same index
    mapping = {}
    for i, key in enumerate(api_keys):
        if i < len(filestores):
            mapping[key] = filestores[i]
        else:
            # Fallback to legacy store_id if no filestore configured for this key
            legacy_store = config.get("knowledge_base", {}).get("store_id", "")
            mapping[key] = legacy_store

    return mapping


def execute_kb_query(user_message: str, session_logger: Optional[SessionLogger] = None, thought_callback: callable = None, demo_mode: bool = False, effective_config: dict = None) -> dict:
    """Execute Knowledge Base query using file search with key rotation and thought streaming.

    Each API key automatically uses its paired filestore from the config mapping.

    Args:
        user_message: The user's query
        session_logger: Optional SessionLogger for logging
        thought_callback: Optional callback for streaming thought chunks.
                         Signature: callback(thought_text: str) -> None
        demo_mode: If True, uses demo API keys and filestores reserved for internal demos.
        effective_config: Optional config dict with query param overrides applied.

    Returns:
        dict with keys:
        - response: str (the response text)
        - sources: list of dicts with 'title' and 'uri'
    """
    config = effective_config if effective_config else load_config()
    kb_config = config.get("knowledge_base", {})

    if not kb_config.get("enabled", False):
        return {"response": "", "sources": []}

    kb_prompt = config.get("prompts", {}).get("kb", "")
    kb_model = config.get("gemini", {}).get("kb_model", "gemini-3-flash-preview")

    # Get API key -> filestore mapping (demo or regular based on mode)
    key_filestore_map = get_api_key_filestore_mapping(demo_mode=demo_mode)

    if not key_filestore_map:
        logger.warning("No API key to filestore mapping configured")
        return {"response": "", "sources": []}

    # Get all available keys (demo or regular based on mode)
    all_keys = get_api_keys(demo_mode=demo_mode)
    if not all_keys:
        return {"response": "", "sources": []}

    api_base = config.get("gemini", {}).get("api_base", "https://generativelanguage.googleapis.com/v1beta/models")

    # Shuffle keys for random order
    keys_to_try = all_keys.copy()
    random.shuffle(keys_to_try)

    last_error = None
    attempt_count = 0

    for api_key in keys_to_try:
        # Get the filestore for this specific API key
        store_id = key_filestore_map.get(api_key, "")
        if not store_id:
            logger.warning(f"No filestore configured for API key, skipping...")
            continue

        logger.info(f"KB query using filestore: {store_id[:50]}...")

        # Build payload with this key's filestore and thinking config
        thinking_level = config.get("thinking", {}).get("kb_level", "low")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "systemInstruction": {"parts": [{"text": inject_datetime(kb_prompt)}]},
            "generationConfig": {
                "temperature": 0.3,
            },
            "tools": [{
                "fileSearch": {
                    "dynamicFileSearchConfig": {
                        "mode": "MODE_DYNAMIC",
                        "dynamicThreshold": 0.3
                    }
                }
            }],
            "toolConfig": {
                "fileSearch": {
                    "vectorStore": {"storeResourceId": store_id}
                }
            }
        }

        # Add thinking config with includeThoughts for streaming
        if thinking_level:
            payload["generationConfig"].update(
                build_thinking_config(thinking_level, include_thoughts=True)
            )

        attempt_count += 1
        start_time = time.time()

        # Log retry attempt (if not first attempt)
        if attempt_count > 1 and session_logger:
            session_logger.log("KB_KEY_ROTATION", {
                "attempt": attempt_count,
                "total_keys": len(all_keys),
                "reason": str(last_error)
            })

        try:
            # Use streaming endpoint to get thoughts in real-time
            url = f"{api_base}/{kb_model}:streamGenerateContent?key={api_key}&alt=sse"
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                stream=True,
                timeout=300
            )

            # Check for rate limit - immediately switch key
            if response.status_code == 429:
                last_error = "Rate limited (429)"
                logger.warning(f"KB API key rate limited, switching to next key...")
                continue

            # Check for other retryable errors
            if response.status_code in [500, 503]:
                last_error = f"Server error ({response.status_code})"
                logger.warning(f"KB server error {response.status_code}, switching to next key...")
                continue

            # Collect response while streaming thoughts
            result_text = ""
            sources = []
            collected_thoughts = ""
            grounding_metadata = {}
            kb_usage = None

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            if 'usageMetadata' in data:
                                kb_usage = data['usageMetadata']
                            if 'candidates' in data and data['candidates']:
                                candidate = data['candidates'][0]

                                # Extract grounding metadata when available
                                if 'groundingMetadata' in candidate:
                                    grounding_metadata = candidate['groundingMetadata']

                                if 'content' in candidate and 'parts' in candidate['content']:
                                    for part in candidate['content']['parts']:
                                        if 'text' in part:
                                            is_thought = part.get('thought', False)
                                            if is_thought:
                                                collected_thoughts += part['text']
                                                if thought_callback:
                                                    thought_callback(part['text'])
                                            else:
                                                result_text += part['text']
                        except json.JSONDecodeError:
                            continue

            # Accumulate this call's token usage into the request total.
            if session_logger:
                session_logger.add_usage(kb_usage)

            # Extract source citations from grounding metadata
            grounding_chunks = grounding_metadata.get("groundingChunks", [])
            seen_titles = set()
            for chunk in grounding_chunks:
                retrieved_context = chunk.get("retrievedContext", {})
                if retrieved_context:
                    title = retrieved_context.get("title", "Unknown")
                    uri = retrieved_context.get("uri", "")
                    # Deduplicate by title
                    if title not in seen_titles:
                        seen_titles.add(title)
                        sources.append({
                            "title": title,
                            "uri": uri
                        })

            # Log KB query
            if session_logger:
                duration_ms = (time.time() - start_time) * 1000
                session_logger.log_kb_query(user_message, result_text, duration_ms)
                if sources:
                    session_logger.log("KB_SOURCES", {"sources": sources})
                if collected_thoughts:
                    session_logger.log("KB_THOUGHTS_STREAMED", {"thoughts_length": len(collected_thoughts)})

            return {"response": result_text, "sources": sources}

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            logger.warning(f"KB request timeout, trying next key...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"KB query error: {e}")
            if session_logger:
                session_logger.log_error("KB_QUERY_ERROR", str(e), {"query": user_message, "attempt": attempt_count})
            continue

    # All keys exhausted
    logger.error(f"KB query failed: All {len(all_keys)} API keys exhausted. Last error: {last_error}")
    if session_logger:
        session_logger.log_error("KB_ALL_KEYS_EXHAUSTED", f"All keys failed: {last_error}", {"total_keys": len(all_keys)})
    return {"response": "", "sources": []}


# Chart config schema for Gemini structured output (hardcoded - not user configurable)
# Supports multiple charts for variables with different units/scales
CHART_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "should_render": {
            "type": "boolean",
            "description": "True if at least one chart should be rendered"
        },
        "charts": {
            "type": "array",
            "description": "Array of chart configurations (max 3). Group compatible variables together.",
            "items": {
                "type": "object",
                "properties": {
                    "viz_type": {
                        "type": "string",
                        "enum": ["line", "bar", "ranking", "pie", "highlight", "gauge", "scatter", "slider"]
                    },
                    "title": {"type": "string", "description": "Descriptive chart title"},
                    "variable_dcids": {"type": "array", "items": {"type": "string"}},
                    "place_dcids": {"type": "array", "items": {"type": "string"}},
                    "parent_place": {"type": "string"},
                    "child_place_type": {"type": "string"},
                    "date": {
                        "type": "string",
                        "description": "Single comparison date in YYYY, YYYY-MM, or YYYY-MM-DD"
                    }
                }
            }
        }
    },
    "required": ["should_render"]
}


def get_chart_config(mcp_results: str, user_message: str) -> dict:
    """Get chart configuration using structured output.

    Supports multiple charts for variables with different units/scales.
    """
    config = load_config()
    mcp_model = config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")

    prompt = f"""Based on the data query and results, determine chart configurations.

User Query: {user_message}

Data Results:
{mcp_results if mcp_results else 'No data results'}

Instructions:
1. Extract variable DCIDs and place DCIDs from the results
2. Analyze variable units from source_metadata and data scales from the values
3. Group variables that can be meaningfully compared on the same Y-axis:
   - Same unit type (e.g., both INR, both counts, both percentages)
   - Similar magnitude (within ~100x of each other)
4. Create SEPARATE charts for incompatible variable groups:
   - Different unit types should be separate (e.g., "Count" vs "INR" vs "Percentage")
   - Vastly different scales should be separate (e.g., millions vs trillions)
5. MAXIMUM 3 charts - if more groups exist, prioritize most relevant to the query
6. Choose appropriate viz_type for each chart (line for time series, bar for comparison)
7. Give each chart a descriptive title related to data it is showing but do NOT include year/date in the title.
8. For ALL bar charts, ALWAYS include a date field:
   - date can be in formats YYYY, YYYY-MM, or YYYY-MM-DD (e.g., "2021", "2022", "2021-01", "2022-01-01")
   - prefer explicit date from user query or tool result context
   - if no reliable explicit date is available, omit date

Set should_render to false if no meaningful data for visualization."""

    response = gemini_request(
        messages=[{"role": "user", "parts": [{"text": prompt}]}],
        system_instruction="You are a data visualization expert. Extract chart configurations from data results, grouping compatible variables together and separating incompatible ones into multiple charts.",
        model=mcp_model,
        temperature=0.2,
        thinking_level="minimal",  # Fastest for simple extraction
        response_schema=CHART_CONFIG_SCHEMA,
        stream=False
    )

    try:
        if "candidates" in response:
            text = response["candidates"][0]["content"]["parts"][0].get("text", "{}")
            chart_config = json.loads(text)
            logger.info(f"📊 Chart config result: {json.dumps(chart_config, indent=2)}")
            return chart_config
    except Exception as e:
        logger.error(f"Chart config parse error: {e}")

    return {"should_render": False}


# Schema for validating if synthesis response contains actual data
DATA_VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "data_found": {
            "type": "boolean",
            "description": "True if the response contains actual data/statistics that answer the query. False if data is unavailable, not found, or the response says data doesn't exist."
        }
    },
    "required": ["data_found"]
}


def validate_data_response(synthesis_text: str, user_message: str) -> bool:
    """Quick validation: did synthesis actually answer with data?

    Called after synthesis completes to determine if charts should be shown.
    Uses fast model with no thinking for minimal latency.
    """
    config = load_config()
    model = config.get("gemini", {}).get("mcp_model", "gemini-2.0-flash")

    prompt = f"""User asked: {user_message}

Response given:
{synthesis_text[:2000]}

Did this response contain actual data/statistics that answer the user's question?
Return false if the response says data is "not available", "not found", "doesn't exist", or similar."""

    response = gemini_request(
        messages=[{"role": "user", "parts": [{"text": prompt}]}],
        system_instruction="You validate if a response contains actual data.",
        model=model,
        temperature=0,
        thinking_level="none",  # Fastest - no thinking needed
        response_schema=DATA_VALIDATION_SCHEMA,
        stream=False
    )

    try:
        if "candidates" in response:
            text = response["candidates"][0]["content"]["parts"][0].get("text", "{}")
            result = json.loads(text)
            return result.get("data_found", True)
    except Exception as e:
        logger.error(f"Data validation parse error: {e}")

    return True  # Default to showing charts on error


# Schema for structured follow-up question generation.
FOLLOW_UP_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Self-contained follow-up questions, one per related topic."
        }
    },
    "required": ["questions"]
}

# Default system prompt for follow-up generation. Ported from the
# datacommons.org explore feature (server/lib/nl/explore/gemini_prompts.py,
# FOLLOW_UP_QUESTIONS_PROMPT) and adapted for the Custom DC agent. Overridable
# via config["prompts"]["follow_up"] (or config/prompts/follow_up.md).
DEFAULT_FOLLOW_UP_PROMPT = """You are a dynamic, trusted, and factual UI copywriter for a public-data explorer.

Write related follow-up questions that the user might find interesting to BROADEN their research — relatable angles to explore around the original question, NOT continuations of it.

The follow-up questions are based on a list of RELATED TOPICS (statistical variables for the same place) provided in the user message.

CRUCIAL RULES:
- If no related topics are given, return an empty list.
- Generate at most one question per topic. Return at most 3 questions total.
- Each question MUST be fully SELF-CONTAINED: it must name its own subject explicitly and read sensibly on its own, with no prior context.
- NEVER use referential words like "this", "that", "these", "those", "it", or "the above". Do not reference "the previous question/answer".
- Make the questions timeless: do NOT ask for a specific year or range of years.
- Each question must be simple and focus on a single variable.
- Avoid questions about places that meet a certain condition.
- Make the questions extremely varied; use diverse phrasing. For inspiration draw from these angles: Ranking, Maps, Comparison, Correlation, Increase/Decrease over time.
- Only suggest questions that can plausibly be answered from public statistical data for the same place.
- Ensure correct grammar and casing."""


def generate_follow_up_questions(user_message: str, topics: list) -> list:
    """Generate self-contained follow-up questions grounded in the resolved topics.

    Mirrors datacommons.org's related.generate_follow_up_questions: returns []
    when there are no topics (no static fallback), uses a structured Gemini call,
    and filters out any question that leaks a context-dependent pronoun.
    """
    topics = [t.strip() for t in (topics or []) if isinstance(t, str) and t.strip()]
    if not topics or not user_message:
        return []

    config = load_config()
    model = config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")
    system_prompt = config.get("prompts", {}).get("follow_up") or DEFAULT_FOLLOW_UP_PROMPT

    prompt = f"""The user's original research question is: {user_message}

RELATED TOPICS START: {"; ".join(topics)}. RELATED TOPICS END.

Generate the self-contained follow-up questions now."""

    try:
        response = gemini_request(
            messages=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction=system_prompt,
            model=model,
            temperature=0.8,  # higher for varied phrasing
            thinking_level="minimal",
            response_schema=FOLLOW_UP_SCHEMA,
            stream=False
        )
        questions = []
        if "candidates" in response:
            text = response["candidates"][0]["content"]["parts"][0].get("text", "{}")
            questions = (json.loads(text) or {}).get("questions", []) or []
    except Exception as e:
        logger.error(f"Follow-up generation error: {e}")
        return []

    # Safety net: drop empties, context-dependent pronouns, and duplicates; cap 3.
    cleaned, seen = [], set()
    for q in questions:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if not q or re.search(r"\b(this|that|these|those)\b", q, re.IGNORECASE):
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(q)
        if len(cleaned) >= 3:
            break
    return cleaned


@app.route("/api/chat/stream", methods=["POST"])
@app.route("/chat/stream", methods=["POST"])  # alias for the SPA served under /agent/*
def chat_stream():
    """Full chat workflow with SSE streaming.

    Phases:
    1. MCP Tools - Execute data queries (send tool call details)
    2. KB Query - Search knowledge base (if enabled)
    3. Synthesis - Stream final response with chart config

    Request body:
    {
        "message": "user query",
        "history": [...optional conversation history...],
        "session_id": "optional session ID for follow-up messages"
    }

    Query params (optional, requires valid key):
    - key: Secret key for config overrides (must match query_param_key in config)
    - model: Override mcp_model and kb_model
    - kb: "true" or "false" to toggle knowledge base
    - mcp_thinking: Override MCP thinking level
    - synthesis_thinking: Override synthesis thinking level

    Response: Server-Sent Events stream
    """
    global session_id  # MCP session ID

    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Message required"}), 400

    user_message = data["message"]
    history = data.get("history", [])
    existing_session_id = data.get("session_id")  # From follow-up messages

    # Parse query parameters for config overrides
    query_params = {}
    secret_key = request.args.get("key", "")
    expected_key = get_query_param_key()
    demo_mode = False

    if secret_key == expected_key:
        # Valid key - extract override params
        query_params = {
            "model": request.args.get("model"),  # e.g., "gemini-2.0-flash"
            "kb_enabled": request.args.get("kb"),  # "true" or "false"
            "mcp_thinking": request.args.get("mcp_thinking"),  # "low", "medium", "high", or budget number
            "synthesis_thinking": request.args.get("synthesis_thinking"),  # same options
        }
        # Remove None values
        query_params = {k: v for k, v in query_params.items() if v is not None}
        if query_params:
            logger.info(f"Query params override applied: {query_params}")

        # Check for demo mode - uses reserved API keys for internal demos
        if request.args.get("demo", "").lower() == "true":
            demo_mode = True
            logger.info("Demo mode ENABLED - using reserved demo API keys")
    elif secret_key:
        # Invalid key provided - log warning but continue with defaults
        logger.warning(f"Invalid query param key provided, ignoring overrides")

    # Create or resume session logger
    session_logger = SessionLogger(session_id=existing_session_id)

    def generate():
        nonlocal session_logger
        request_start_time = time.time()
        full_text = ""

        # Chart config runs in parallel with KB + synthesis
        chart_result_holder = {'config': {"should_render": False}}
        chart_thread = [None]  # Use list to avoid nonlocal issues

        # Send session ID first so frontend can display it
        yield f"data: {json.dumps({'session_id': session_logger.session_id})}\n\n"

        # Log query params if present
        if query_params:
            session_logger.log("QUERY_PARAMS_OVERRIDE", query_params)

        # Log demo mode if enabled
        if demo_mode:
            session_logger.log("DEMO_MODE_ENABLED", {"using_demo_keys": True})

        # Log user message
        session_logger.log_user_message(user_message, len(history))

        config = load_config()
        if not config:
            session_logger.log_error("CONFIG_ERROR", "Backend config not loaded")
            yield f"data: {json.dumps({'error': 'Backend config not loaded'})}\n\n"
            return

        # Apply query param overrides to config
        effective_config = apply_query_overrides(config, query_params)

        # Ensure MCP is initialized (fix for tool calls not showing)
        mcp_ready = False
        if not session_id:
            logger.info("MCP session not initialized, attempting to connect...")
            session_logger.log("MCP_INIT_ATTEMPT", {"reason": "session_id was None"})
            if initialize_mcp():
                session_logger.log("MCP_INIT_SUCCESS", {"mcp_session_id": session_id})
                mcp_ready = True
            else:
                # Even if init returns False, try to get tools anyway
                # Some MCP servers work without session IDs
                session_logger.log("MCP_INIT_RETURNED_FALSE", {"trying_tools_anyway": True})
        else:
            mcp_ready = True

        # Double-check: if we have tools, MCP is working regardless of session_id
        tools = get_tools()
        if tools:
            mcp_ready = True
            session_logger.log("MCP_TOOLS_AVAILABLE", {"tool_count": len(tools), "tools": [t.get("name") for t in tools]})
        else:
            session_logger.log("MCP_NO_TOOLS", {"session_id": session_id})

        # Create thought queue for streaming thoughts from background threads
        thought_queue = queue.Queue()

        def thought_callback(thought_text: str, phase: str):
            """Callback to put thoughts into queue for streaming."""
            thought_queue.put({'thought': thought_text, 'phase': phase})

        # Phase 1: MCP Tools
        mcp_enabled = effective_config.get("mcp", {}).get("enabled", True)
        mcp_results = ""
        tool_calls_list = []

        if mcp_enabled and mcp_ready:
            yield f"data: {json.dumps({'status': 'mcp_start', 'message': 'Querying data tools...'})}\n\n"

            # Run MCP in thread to enable thought streaming
            mcp_result_holder = {'results': '', 'tool_calls': [], 'text': ''}

            def run_mcp():
                try:
                    mcp_result_holder['results'], mcp_result_holder['tool_calls'], mcp_result_holder['text'] = execute_mcp_tool_loop(
                        user_message, history, session_logger=session_logger,
                        effective_config=effective_config,
                        thought_callback=lambda t: thought_callback(t, 'mcp'),
                        demo_mode=demo_mode
                    )
                except Exception as e:
                    logger.error(f"MCP thread error: {e}")
                    mcp_result_holder['text'] = f"Error: {e}"

            mcp_thread = threading.Thread(target=run_mcp)
            mcp_thread.start()

            # Stream thoughts while MCP runs
            while mcp_thread.is_alive() or not thought_queue.empty():
                try:
                    thought_data = thought_queue.get(timeout=0.1)
                    yield f"data: {json.dumps(thought_data)}\n\n"
                except queue.Empty:
                    continue

            mcp_thread.join()

            # Signal MCP thinking complete
            yield f"data: {json.dumps({'thinking_complete': 'mcp'})}\n\n"

            # Get results from thread
            mcp_results = mcp_result_holder['results']
            tool_calls_list = mcp_result_holder['tool_calls']

            # Send each tool call for left sidebar
            for tc in tool_calls_list:
                yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'arguments': tc['arguments'], 'result': tc['result'], 'status': tc['status']})}\n\n"

            yield f"data: {json.dumps({'status': 'mcp_complete', 'tool_count': len(tool_calls_list)})}\n\n"

            # Check data availability and send status to frontend
            data_status = check_data_availability(tool_calls_list)
            yield f"data: {json.dumps({'data_status': data_status})}\n\n"

            # Extract and send provenance sources from MCP results
            mcp_sources = extract_provenance_from_mcp_results(tool_calls_list)
            if mcp_sources:
                yield f"data: {json.dumps({'mcp_sources': mcp_sources})}\n\n"

            # Start chart config in background (runs parallel with KB + synthesis)
            if mcp_results:
                def run_chart_config():
                    chart_result_holder['config'] = get_chart_config(mcp_results, user_message)
                chart_thread[0] = threading.Thread(target=run_chart_config)
                chart_thread[0].start()

        elif mcp_enabled and not mcp_ready:
            session_logger.log("MCP_SKIPPED", {"reason": "MCP not connected or no tools available"})
            yield f"data: {json.dumps({'status': 'mcp_skipped', 'message': 'MCP server not connected'})}\n\n"

        # Phase 2: KB Query (if enabled)
        kb_response = ""
        kb_sources = []
        kb_enabled = effective_config.get("knowledge_base", {}).get("enabled", False)

        if kb_enabled:
            yield f"data: {json.dumps({'status': 'kb_start', 'message': 'Searching knowledge base...'})}\n\n"

            # Run KB in thread to enable thought streaming
            kb_result_holder = {'response': '', 'sources': []}

            def run_kb():
                try:
                    kb_result = execute_kb_query(
                        user_message, session_logger=session_logger,
                        thought_callback=lambda t: thought_callback(t, 'kb'),
                        demo_mode=demo_mode,
                        effective_config=effective_config
                    )
                    kb_result_holder['response'] = kb_result.get("response", "")
                    kb_result_holder['sources'] = kb_result.get("sources", [])
                except Exception as e:
                    logger.error(f"KB thread error: {e}")

            kb_thread = threading.Thread(target=run_kb)
            kb_thread.start()

            # Stream thoughts while KB runs
            while kb_thread.is_alive() or not thought_queue.empty():
                try:
                    thought_data = thought_queue.get(timeout=0.1)
                    yield f"data: {json.dumps(thought_data)}\n\n"
                except queue.Empty:
                    continue

            kb_thread.join()

            # Signal KB thinking complete
            yield f"data: {json.dumps({'thinking_complete': 'kb'})}\n\n"

            # Get results from thread
            kb_response = kb_result_holder['response']
            kb_sources = kb_result_holder['sources']

            # Send KB sources to frontend for inline citations
            if kb_sources:
                yield f"data: {json.dumps({'kb_sources': kb_sources})}\n\n"
            yield f"data: {json.dumps({'status': 'kb_complete'})}\n\n"

        # Phase 3: Synthesis with streaming
        yield f"data: {json.dumps({'status': 'synthesis_start', 'message': 'Generating response...'})}\n\n"

        synthesis_prompt = effective_config.get("prompts", {}).get("synthesis", "")
        synthesis_model = effective_config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")
        thinking_level = effective_config.get("thinking", {}).get("synthesis_level", "low")

        # Build synthesis context with source labels for citations
        context_parts = []
        if mcp_results:
            # Format extracted sources as markdown links for synthesis
            mcp_sources = extract_provenance_from_mcp_results(tool_calls_list)
            if mcp_sources:
                source_links = ", ".join([f"[{s['name']}]({s['url']})" for s in mcp_sources])
            else:
                source_links = "Data Commons"
            context_parts.append(f"**DATA RESULTS [Sources: {source_links}]:**\n{mcp_results}")
        if kb_response:
            # Include document names from kb_sources for proper citation
            kb_source_names = ", ".join([s['title'] for s in kb_sources]) if kb_sources else "Knowledge Base"
            context_parts.append(f"**POLICY INFORMATION [Sources: {kb_source_names}]:**\n{kb_response}")

        # Log synthesis start
        session_logger.log_synthesis_start(["MCP" if mcp_results else None, "KB" if kb_response else None])

        synthesis_message = f"""User Query: {user_message}

{chr(10).join(context_parts) if context_parts else 'No additional context available.'}

Please provide a comprehensive response combining all available information."""

        # Stream the synthesis response with thought streaming
        try:
            # Build messages with conversation history for context
            synthesis_messages = []

            # Add conversation history first (already in Gemini format from frontend)
            for msg in history:
                synthesis_messages.append(msg)

            # Add current query with MCP/KB context as final user message
            synthesis_messages.append({"role": "user", "parts": [{"text": synthesis_message}]})

            stream_gen = gemini_request(
                messages=synthesis_messages,
                system_instruction=synthesis_prompt,
                model=synthesis_model,
                temperature=0.3,
                thinking_level=thinking_level,
                stream=True,
                session_logger=session_logger,
                include_thoughts=True,  # Enable thought streaming
                demo_mode=demo_mode
            )

            if isinstance(stream_gen, dict) and "error" in stream_gen:
                session_logger.log_error("SYNTHESIS_ERROR", stream_gen['error'])
                yield f"data: {json.dumps({'error': stream_gen['error']})}\n\n"
                return

            for chunk in stream_gen:
                # Handle dict format with 'type' and 'content' keys
                if isinstance(chunk, dict):
                    if chunk.get('type') == 'thought':
                        yield f"data: {json.dumps({'thought': chunk['content'], 'phase': 'synthesis'})}\n\n"
                    elif chunk.get('type') == 'text':
                        full_text += chunk['content']
                        yield f"data: {json.dumps({'text': chunk['content']})}\n\n"
                else:
                    # Backward compatibility: plain text string
                    full_text += chunk
                    yield f"data: {json.dumps({'text': chunk})}\n\n"

            # Signal synthesis thinking complete
            yield f"data: {json.dumps({'thinking_complete': 'synthesis'})}\n\n"

        except Exception as e:
            logger.error(f"Synthesis streaming error: {e}")
            session_logger.log_error("SYNTHESIS_STREAM_ERROR", str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # Quick validation: should we show charts based on synthesis response?
        show_charts = True
        if full_text and chart_thread[0]:
            show_charts = validate_data_response(full_text, user_message)
            if not show_charts:
                session_logger.log("CHART_VALIDATION", {"data_found": False, "action": "hide_charts"})

        # Wait for chart config thread (started after MCP, runs parallel with KB + synthesis)
        if chart_thread[0]:
            chart_thread[0].join(timeout=5)
        chart_config = chart_result_holder['config']

        # Add hide_charts flag if validation determined no data was found
        if not show_charts:
            chart_config['hide_charts'] = True

        # Log final response
        total_duration_ms = (time.time() - request_start_time) * 1000
        session_logger.log_final_response(full_text, chart_config, total_duration_ms)

        # Temporary cost instrumentation: report accumulated Gemini token usage
        # for this query (MCP + KB + synthesis + chart config). Emitted before
        # `done`; the UI shows it only when opened with ?debug=tokens. Follow-up
        # question generation happens after this and is intentionally excluded.
        session_logger.log("TOKEN_USAGE", session_logger.token_usage)
        yield f"data: {json.dumps({'usage': session_logger.token_usage})}\n\n"

        # Send final event with timing info
        yield f"data: {json.dumps({'chart_config': chart_config, 'done': True, 'duration_ms': round(total_duration_ms, 0)})}\n\n"

        # Follow-up questions — grounded in the resolved chart topics. Emitted
        # AFTER `done` so the answer/charts render immediately; the UI shows
        # them when they arrive. Returns nothing when no topics resolved.
        try:
            topics = []
            for c in (chart_config.get('charts') or []):
                title = c.get('title')
                if title:
                    topics.append(title)
            if not topics and chart_config.get('title'):  # legacy single-chart shape
                topics.append(chart_config['title'])
            follow_ups = generate_follow_up_questions(user_message, topics)
            if follow_ups:
                yield f"data: {json.dumps({'follow_up_questions': follow_ups})}\n\n"
        except Exception as e:
            logger.error(f"Follow-up emit error: {e}")

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


# ============================================================
# LOGS ANALYTICS DASHBOARD
# ============================================================

def parse_log_file(log_path: Path) -> dict:
    """Parse a single log file and extract metrics for analytics.

    Returns:
        dict with session_id, query, timestamp, status, duration_ms,
        tool_calls, errors, model, thinking_level, kb_enabled
    """
    result = {
        "session_id": log_path.stem,
        "query": None,
        "timestamp": None,
        "status": "unknown",
        "duration_ms": None,
        "tool_calls": [],
        "stat_vars": [],  # List of unique stat vars fetched
        "errors": [],
        "model": None,
        "thinking_level": None,
        "kb_enabled": False,
        "text_length": 0
    }

    def process_event(event_name: str, data_lines: list):
        """Process a single event's data."""
        if not event_name or not data_lines:
            return
        try:
            data_str = '\n'.join(data_lines)
            data = json.loads(data_str)

            if event_name == 'USER_MESSAGE':
                result['query'] = data.get('message', '')
            elif event_name == 'GEMINI_REQUEST':
                if not result['model']:
                    result['model'] = data.get('model', '')
                if not result['thinking_level']:
                    payload = data.get('payload', {})
                    result['thinking_level'] = payload.get('thinking_level', '')
            elif event_name == 'MCP_TOOL_REQUEST':
                tool_name = data.get('tool_name', '')
                arguments = data.get('arguments', {})
                result['tool_calls'].append({
                    'name': tool_name,
                    'arguments': arguments
                })
                # Extract stat var from get_observations calls
                if tool_name == 'get_observations':
                    var_dcid = arguments.get('variable_dcid', '')
                    if var_dcid and var_dcid not in result['stat_vars']:
                        result['stat_vars'].append(var_dcid)
            elif event_name == 'MCP_TOOL_RESPONSE':
                if result['tool_calls']:
                    result['tool_calls'][-1]['status'] = data.get('status', 'unknown')
                    result['tool_calls'][-1]['duration_ms'] = data.get('duration_ms', 0)
            elif event_name == 'ERROR':
                result['errors'].append({
                    'type': data.get('error_type', ''),
                    'message': data.get('error_message', '')
                })
            elif event_name == 'KB_QUERY':
                result['kb_enabled'] = True
            elif event_name == 'QUERY_PARAMS_OVERRIDE':
                if data.get('kb_enabled') == 'true':
                    result['kb_enabled'] = True
            elif event_name == 'FINAL_RESPONSE':
                result['duration_ms'] = data.get('total_duration_ms')
                result['text_length'] = data.get('text_length', 0)
        except json.JSONDecodeError:
            pass

    try:
        with open(log_path, 'r') as f:
            content = f.read()

        # Parse each event block
        current_event = None
        current_data = []

        for line in content.split('\n'):
            # Check for event header
            if line.startswith('--- ') and ' @ ' in line:
                # Process previous event BEFORE starting new one
                process_event(current_event, current_data)

                # Extract event type from header
                parts = line.split(' @ ')
                current_event = parts[0].replace('--- ', '').strip()
                if len(parts) > 1:
                    timestamp_str = parts[1].replace(' ---', '').strip()
                    if not result['timestamp']:
                        result['timestamp'] = timestamp_str
                current_data = []
            elif line.startswith('{') or (current_data and not line.startswith('=')):
                current_data.append(line)

        # IMPORTANT: Process the LAST event (usually FINAL_RESPONSE)
        process_event(current_event, current_data)

        # Determine success/failure status
        if result['errors']:
            result['status'] = 'failed'
        elif result['text_length'] and result['text_length'] > 0:
            result['status'] = 'success'
        elif result['duration_ms'] and result['duration_ms'] > 0:
            result['status'] = 'success'
        else:
            result['status'] = 'unknown'

    except Exception as e:
        logger.error(f"Error parsing log file {log_path}: {e}")
        result['status'] = 'parse_error'

    return result


def calculate_percentiles(values: list) -> dict:
    """Calculate response time percentiles."""
    if not values:
        return {"p50": 0, "p75": 0, "p90": 0, "p95": 0, "p99": 0}

    sorted_values = sorted(values)
    n = len(sorted_values)

    def percentile(p):
        k = (n - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < n else f
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f]) if c != f else sorted_values[f]

    return {
        "p50": round(percentile(50), 0),
        "p75": round(percentile(75), 0),
        "p90": round(percentile(90), 0),
        "p95": round(percentile(95), 0),
        "p99": round(percentile(99), 0)
    }


def get_all_logs_analytics() -> dict:
    """Aggregate analytics from all log files in the logs folder."""
    logs_dir = Path(__file__).parent / 'logs'

    if not logs_dir.exists():
        return {"error": "Logs directory not found"}

    log_files = sorted(logs_dir.glob('*.log'), reverse=True)

    # Parse all logs
    parsed_logs = []
    for log_file in log_files:
        parsed = parse_log_file(log_file)
        if parsed['query']:  # Only include logs with actual queries
            parsed_logs.append(parsed)

    # Calculate aggregated stats
    total = len(parsed_logs)
    successful = sum(1 for p in parsed_logs if p['status'] == 'success')
    failed = sum(1 for p in parsed_logs if p['status'] == 'failed')
    unknown = sum(1 for p in parsed_logs if p['status'] in ('unknown', 'parse_error'))

    # Response times
    durations = [p['duration_ms'] for p in parsed_logs if p['duration_ms'] is not None]
    avg_duration = sum(durations) / len(durations) if durations else 0
    percentiles = calculate_percentiles(durations)

    # By date
    by_date = {}
    for p in parsed_logs:
        if p['timestamp']:
            date = p['timestamp'][:10]  # Extract YYYY-MM-DD
            if date not in by_date:
                by_date[date] = {"queries": 0, "successful": 0, "failed": 0}
            by_date[date]["queries"] += 1
            if p['status'] == 'success':
                by_date[date]["successful"] += 1
            elif p['status'] == 'failed':
                by_date[date]["failed"] += 1

    # MCP tools summary
    tool_counts = {}
    total_tool_calls = 0
    for p in parsed_logs:
        for tc in p['tool_calls']:
            name = tc.get('name', 'unknown')
            tool_counts[name] = tool_counts.get(name, 0) + 1
            total_tool_calls += 1

    # Model stats
    model_counts = {}
    for p in parsed_logs:
        model = p['model'] or 'unknown'
        model_counts[model] = model_counts.get(model, 0) + 1

    # Config stats
    kb_enabled_count = sum(1 for p in parsed_logs if p['kb_enabled'])
    thinking_levels = {}
    for p in parsed_logs:
        level = p['thinking_level'] or 'unknown'
        thinking_levels[level] = thinking_levels.get(level, 0) + 1

    # Error summary
    error_types = {}
    for p in parsed_logs:
        for e in p['errors']:
            etype = e.get('type', 'unknown')
            error_types[etype] = error_types.get(etype, 0) + 1

    # Recent queries (last 50)
    recent_queries = []
    for p in parsed_logs[:50]:
        # Map 'unknown' status to 'stopped' for display
        status = 'stopped' if p['status'] == 'unknown' else p['status']
        recent_queries.append({
            "session_id": p['session_id'],
            "query": p['query'][:100] + "..." if p['query'] and len(p['query']) > 100 else p['query'],
            "full_query": p['query'],
            "timestamp": p['timestamp'],
            "status": status,
            "duration_ms": p['duration_ms'],
            "tool_count": len(p['tool_calls']),
            "tool_calls": p['tool_calls'],
            "stat_vars": p.get('stat_vars', []),
            "model": p['model'],
            "kb_enabled": p['kb_enabled']
        })

    return {
        "total_queries": total,
        "successful": successful,
        "failed": failed,
        "stopped": unknown,  # Renamed from 'unknown' to 'stopped'
        "success_rate": round(successful / total * 100, 1) if total > 0 else 0,
        "response_times": {
            "avg_ms": round(avg_duration, 0),
            **percentiles
        },
        "by_date": dict(sorted(by_date.items())),
        "mcp_summary": {
            "total_calls": total_tool_calls,
            "by_tool": tool_counts,
            "avg_per_query": round(total_tool_calls / total, 1) if total > 0 else 0
        },
        "error_summary": error_types,
        "recent_queries": recent_queries,
        "generated_at": datetime.now().isoformat()
    }


def main():
    """Main entry point."""
    print("=" * 60)
    print("Data Commons MCP Proxy Server (Proxy-Only Mode)")
    print("=" * 60)
    print(f"\nExpecting MCP server at: http://localhost:{MCP_PORT}")
    print("\nMake sure you started the MCP server first:")
    print(f"  python3 -m uv tool run datacommons-mcp serve http --port {MCP_PORT}")

    # Try to connect to MCP server
    print("\nChecking MCP server connection...")
    if initialize_mcp():
        tools = get_tools()
        print(f"\nConnected! Found {len(tools)} tools:")
        for t in tools:
            print(f"  - {t.get('name')}")
    else:
        print("\nWARNING: Could not connect to MCP server")
        print("The proxy will start anyway - MCP server can be started later")

    # Start proxy
    print(f"\nStarting proxy on port {PROXY_PORT}...")
    print(f"Frontend should connect to: http://localhost:{PROXY_PORT}")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    app.run(host="0.0.0.0", port=PROXY_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()

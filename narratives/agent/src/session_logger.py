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

import json
import threading
import uuid
from datetime import datetime
from typing import Any, Optional

from src.config import AGENT_ROOT


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
        self.logs_dir = AGENT_ROOT / 'logs'
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

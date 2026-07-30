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
import logging
from datetime import datetime
from pathlib import Path

from src.config import AGENT_ROOT

logger = logging.getLogger(__name__)


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
    logs_dir = AGENT_ROOT / 'logs'

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

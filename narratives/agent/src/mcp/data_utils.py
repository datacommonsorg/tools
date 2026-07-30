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
import re


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

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

import json
from urllib.parse import urlparse

# Server 1.3.0 split the two fat tools into six. Both generations are recognised
# here so this keeps working against an in-container 1.2.1 endpoint and the
# public 1.3.0 one alike.
_SEARCH_TOOLS = ("search_indicators", "search_child_indicators")
_OBSERVATION_TOOLS = (
    "get_observations",
    "get_child_observations",
    "get_multi_entity_observations",
)


def _parse_tool_result(result) -> dict:
    """Unwraps an MCP tool result into the payload the server actually returned.

    Results arrive as the JSON-encoded MCP envelope whose `content[0].text` is
    itself JSON. Returns None when the result is not parseable at all -- an
    error string, or a shape this does not recognise -- which callers treat the
    same as "no data", since an unreadable result is not evidence of any.
    """
    if isinstance(result, dict):
        payload = result
    elif isinstance(result, str):
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            return None
    else:
        return None

    if not isinstance(payload, dict):
        return None

    content = payload.get("content")
    if isinstance(content, list) and content:
        try:
            payload = json.loads(content[0].get("text", ""))
        except (json.JSONDecodeError, AttributeError):
            return None

    return payload if isinstance(payload, dict) else None


def _has_observation_rows(payload: dict) -> bool:
    """True when an observations payload carries at least one dated value.

    Checked structurally rather than by searching the text, because the two
    server generations disagree on both spelling and shape. 1.3.0 returns a
    columnar `data.rows` table and signals "nothing found" as `{"data": {}}`;
    1.2.1 returned `place_observations[].time_series` and signalled empty as
    `"time_series": []`. A text search for the 1.2.1 markers finds neither
    marker in a 1.3.0 empty response and so reports data that is not there.
    """
    if not payload:
        return False
    data = payload.get("data")
    if isinstance(data, dict) and data.get("rows"):
        return True
    for entry in payload.get("place_observations") or []:
        if isinstance(entry, dict) and entry.get("time_series"):
            return True
    return False


def _has_search_candidates(payload: dict) -> bool:
    """True when a search payload names at least one topic or variable.

    1.3.0 answers either with `variables` / `topics` lists or, when the match is
    fuzzy, with columnar `variableCandidates` / `topicCandidates` tables. 1.2.1
    only ever used the lists.
    """
    if not payload:
        return False
    if payload.get("variables") or payload.get("topics"):
        return True
    for key in ("variableCandidates", "topicCandidates"):
        table = payload.get(key)
        if isinstance(table, dict) and table.get("rows"):
            return True
    return False


def check_data_availability(tool_calls_list: list) -> dict:
    """Check if MCP tool calls returned useful data.

    Returns:
        dict with keys:
        - has_data: bool
        - no_variables_found: bool (a search returned nothing)
        - no_observations_found: bool (observations were fetched but were empty)
        - message: str (user-friendly message if no data)
    """
    no_variables = False
    has_any_observations = False
    search_called = False
    observations_called = False

    for tc in tool_calls_list:
        tool_name = tc.get('name', '')
        payload = _parse_tool_result(tc.get('result', ''))

        if tool_name in _SEARCH_TOOLS:
            search_called = True
            if not _has_search_candidates(payload):
                no_variables = True
        elif tool_name in _OBSERVATION_TOOLS:
            observations_called = True
            if _has_observation_rows(payload):
                has_any_observations = True

    # Numbers are the only thing that counts as data: a search that found
    # candidate variables still has nothing to report until observations land.
    has_data = has_any_observations
    no_observations = observations_called and not has_any_observations

    message = None
    if not has_data:
        if no_variables:
            message = "We didn't find any matching data variables for your query."
        elif no_observations:
            message = "We found the data variable but there are no observations available."
        else:
            message = "We didn't find data for your query."

    return {
        'has_data': has_data,
        'no_variables_found': no_variables,
        'no_observations_found': no_observations,
        'search_called': search_called,
        'observations_called': observations_called,
        'message': message
    }


def annotate_truncation(status: dict, truncated: bool) -> dict:
    """Records on `status` that the tool loop stopped before it was finished.

    Mutates and returns `status`. check_data_availability only sees the tool
    calls that happened, so when none of them fetched observations it concludes
    the data does not exist. If the loop ran out of iterations that is the wrong
    story -- we stopped looking -- and telling a user the data is missing when
    it may not be is worse than saying nothing.
    """
    status["truncated"] = truncated
    if truncated and not status.get("has_data"):
        status["message"] = (
            "We ran out of research steps before finding data for your "
            "query. Try asking something narrower."
        )
    return status


def _first_present(mapping: dict, *keys: str) -> str:
    """Returns the first non-empty value among `keys`, or an empty string.

    The MCP server returns camelCase, while earlier revisions of this code and
    some fixtures use snake_case. Accepting both keeps old captures readable
    without pinning the parser to one spelling.
    """
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _facet_index_from_variable_metadata(result_data: dict) -> dict:
    """Maps facet id -> {name, url, license} from a get_variable_metadata result.

    Returned as an index rather than a list because this tool describes
    *candidates*: every source a variable could be answered from. Which one
    answered is decided later, by the observation call, which names it by facet
    id. Indexing is what lets the candidates enrich the source that served
    without becoming sources in their own right -- listing them was why an
    answer resting on one dataset credited every dataset the agent had looked
    at on the way there.

    The name prefers `isPartOf` over `source`: `source` is the publishing
    organisation ("World Bank"), while `isPartOf` is the dataset the numbers
    actually came from ("World Development Indicators"). The dataset is the
    provenance a reader needs.

    Args:
        result_data: The parsed tool result.

    Returns:
        dict: {facet_id: {"name": ..., "url": ..., "license": ...}}
    """
    provenances = result_data.get("provenances")
    variables = result_data.get("variables")
    if not isinstance(provenances, dict) or not isinstance(variables, dict):
        return {}

    index = {}
    for variable in variables.values():
        if not isinstance(variable, dict):
            continue
        facets = variable.get("facets")
        if not isinstance(facets, list):
            continue

        for facet in facets:
            if not isinstance(facet, dict):
                continue
            facet_id = facet.get("id")
            if facet_id is None:
                continue
            facet_id = str(facet_id)
            # The same facet is offered for several variables in one call; the
            # first description of it is as good as the last.
            if not facet_id or facet_id in index:
                continue

            provenance = provenances.get(str(facet.get("provenanceId")))
            if not isinstance(provenance, dict):
                continue
            properties = provenance.get("properties")
            if not isinstance(properties, dict):
                continue

            url = _first_present(properties, "url", "descriptionUrl")
            if not url:
                continue

            entry = {
                "name": _first_present(properties, "isPartOf", "source", "domain")
                or url,
                "url": url,
            }
            license_type = _first_present(properties, "licenseType")
            if license_type:
                entry["license"] = license_type
            index[facet_id] = entry

    return index


def extract_provenance_from_mcp_results(tool_calls_list: list) -> list:
    """Returns the sources that actually supplied the answer's numbers.

    This list is the citation numbering: position 1 is `[1]`, both in the
    synthesis prompt and in the Sources block the reader sees. So it has to
    contain what the answer rests on and nothing else -- an extra row shifts
    every number after it, and a missing row leaves a figure unattributable.

    Membership is decided by the observation calls, not by the metadata call.
    An observation result reports `sourceMetadata.sourceId`: the facet the
    server actually served, whether the agent pinned it with `source_override`
    or the server picked it. `get_variable_metadata` only lists *candidates* --
    every source a variable could have been answered from -- so it is read into
    an index and used to put a name and licence on the facet that served. It
    can no longer add a source of its own: doing that is what made an answer
    drawn entirely from one dataset credit four, because the agent had asked
    what was available before choosing.

    Order is first-served-first, and stable: the numbering must not move
    between the prompt and the render.

    Deduplication is by URL rather than facet id, so two facets of the same
    dataset read as one source to a reader instead of two identical rows.

    The server emits camelCase; snake_case spellings are accepted as fallbacks.
    Getting this wrong is silent -- a mismatched key just yields no sources --
    so both spellings are tried rather than assumed.

    Args:
        tool_calls_list: List of tool call dicts with 'name', 'arguments', 'result'

    Returns:
        list of dicts: [{"name": "Source Name", "url": "https://...",
                         "license": "..." (when reported)}]
    """
    # Pass 1: index every candidate facet the metadata calls described.
    facet_index = {}
    for tc in tool_calls_list:
        if tc.get('name') != 'get_variable_metadata':
            continue
        try:
            result_data = _parse_tool_result(tc.get('result', ''))
            if not result_data:
                continue
            for facet_id, entry in _facet_index_from_variable_metadata(
                result_data
            ).items():
                facet_index.setdefault(facet_id, entry)
        except (json.JSONDecodeError, KeyError, TypeError, IndexError):
            continue

    # Pass 2: the observation calls decide which of them are sources at all.
    sources = []
    seen_urls = set()
    for tc in tool_calls_list:
        if tc.get('name') not in _OBSERVATION_TOOLS:
            continue

        try:
            result_data = _parse_tool_result(tc.get('result', ''))
            if not result_data:
                continue

            metadata = result_data.get('sourceMetadata') or result_data.get(
                'source_metadata'
            )
            if not isinstance(metadata, dict):
                continue

            facet_id = _first_present(metadata, 'sourceId', 'source_id')
            # Server 1.2.1 wrote the literal "unknown" for a result that
            # carried no data rather than omitting the block, so it is not an
            # id and must not be looked up as one.
            if facet_id == 'unknown':
                facet_id = ''

            entry = facet_index.get(facet_id) if facet_id else None
            if entry is not None:
                # Copied so a later mutation cannot reach back into the index
                # and rename a source that a previous call already listed.
                entry = dict(entry)
            else:
                # No metadata call described this facet -- either none was made
                # or it served something the candidates did not cover. The
                # observation result still knows where the numbers came from,
                # it just has no dataset name to offer.
                url = _first_present(metadata, 'provenanceUrl', 'provenance_url')
                if not url:
                    continue
                name = _first_present(
                    metadata,
                    'importName',
                    'import_name',
                    'sourceName',
                    'source_name',
                )
                if not name:
                    host = urlparse(url).netloc
                    name = host[4:] if host.startswith('www.') else host
                entry = {"name": name or "Data Source", "url": url}

            if entry["url"] in seen_urls:
                continue
            seen_urls.add(entry["url"])
            sources.append(entry)

        except (json.JSONDecodeError, KeyError, TypeError, IndexError):
            continue

    return sources

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
"""Tests for availability checks and provenance extraction in `data_utils`.

Verifies two groups of behaviors in `data_utils`:
1. `check_data_availability` and `annotate_truncation` distinguish populated
   observation responses, empty observation responses, empty search results,
   malformed payloads, and truncated tool loops across MCP 1.2.x and 1.3.x+
   payload shapes.
2. `extract_provenance_from_mcp_results` builds ordered, URL-deduplicated
   source citations strictly from observation tool calls, enriching them with
   dataset names and licenses from `get_variable_metadata` when available.
"""

import json
from typing import Any

import pytest

from narratives_agent.mcp import data_utils

# ---- payload fixtures, one per server generation -------------------------
V121_WITH_DATA = {
    "place_observations": [
        {
            "place": "country/BEL",
            "time_series": [["2020", 54577.6], ["2021", 59100.1]],
        }
    ]
}
V121_EMPTY = {
    "place_observations": [{"place": "country/BEL", "time_series": []}]
}
V130_WITH_DATA = {
    "data": {
        "rows": [{"entity": "country/BEL", "date": "2021", "value": 59100.1}]
    }
}
V130_EMPTY: dict[str, Any] = {"data": {}}


def tool_call(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap an observation payload in an MCP tool-call result envelope."""
    return {
        "name": name,
        "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }


@pytest.mark.parametrize(
    "payload",
    [V121_WITH_DATA, V130_WITH_DATA],
    ids=["1.2.x populated", "1.3.x populated"],
)
def test_populated_observations_report_data(payload: dict[str, Any]) -> None:
    # Test: Data availability check when observations are present.
    # Situation: `get_observations` returns non-empty observation data in
    #   either the MCP 1.2.x (`place_observations[].time_series`) or MCP 1.3.x
    #   (`data.rows`) format.
    # Expectation: `check_data_availability` returns `has_data: True` for both
    #   formats.
    status = data_utils.check_data_availability(
        [tool_call("get_observations", payload)]
    )
    assert status["has_data"] is True


@pytest.mark.parametrize(
    "payload",
    [V121_EMPTY, V130_EMPTY],
    ids=["1.2.x empty", "1.3.x empty"],
)
def test_empty_observations_report_no_data(payload: dict[str, Any]) -> None:
    # Test: Data availability check when observation results are empty.
    # Situation: `get_observations` returns an empty MCP 1.2.x response
    #   (`"time_series": []`) or an empty MCP 1.3.x response (`{"data": {}}`).
    # Expectation: `check_data_availability` returns `has_data: False` in both
    #   cases.
    status = data_utils.check_data_availability(
        [tool_call("get_observations", payload)]
    )
    assert status["has_data"] is False


def test_unparseable_observation_result_reports_no_data() -> None:
    # Test: Handling of non-JSON tool error strings in
    #   `check_data_availability`.
    # Situation: `get_observations` returns a plain-text error string instead of
    #   a JSON-encoded MCP envelope.
    # Expectation: `check_data_availability` treats the unparseable result as
    #   having no observation rows (`has_data: False`,
    #   `no_observations_found: True`).
    status = data_utils.check_data_availability(
        [{"name": "get_observations", "result": "Error: upstream timed out"}]
    )
    assert status["has_data"] is False
    assert status["no_observations_found"] is True


def test_search_matching_no_variables_reports_missing_variables() -> None:
    # Test: Status message when indicator search returns no matching variables.
    # Situation: `search_indicators` returns empty `variables` and `topics`
    #   lists, and no observation tool is called.
    # Expectation: `no_variables_found` is `True`, `no_observations_found` is
    #   `False`, and the status message reports that no matching data variables
    #   were found.
    status = data_utils.check_data_availability(
        [tool_call("search_indicators", {"variables": [], "topics": []})]
    )
    assert status["no_variables_found"] is True
    assert status["no_observations_found"] is False
    assert status["message"] == (
        "We didn't find any matching data variables for your query."
    )


@pytest.mark.parametrize(
    "payload",
    [V121_EMPTY, V130_EMPTY],
    ids=["1.2.x empty", "1.3.x empty"],
)
def test_matched_variable_with_empty_observations_reports_no_data(
    payload: dict[str, Any],
) -> None:
    # Test: Status message when variables are found but hold no observations.
    # Situation: `search_indicators` returns a candidate variable, and
    #   `get_observations` subsequently returns an empty MCP 1.2.x or MCP 1.3.x
    #   payload.
    # Expectation: `has_data` is `False`, `no_variables_found` is `False`,
    #   `no_observations_found` is `True`, and the status message reports that
    #   the variable exists but has no observations available.
    status = data_utils.check_data_availability(
        [
            tool_call("search_indicators", {"variables": ["Count_Person"]}),
            tool_call("get_observations", payload),
        ]
    )
    assert status["has_data"] is False
    assert status["no_variables_found"] is False
    assert status["no_observations_found"] is True
    assert status["message"] == (
        "We found the data variable but there are no observations available."
    )


def test_fuzzy_search_candidates_count_as_variable_match() -> None:
    # Test: Recognition of MCP 1.3.x columnar `variableCandidates` search hits.
    # Situation: `search_indicators` returns a non-empty `variableCandidates`
    #   table (`rows`) without a top-level `variables` list.
    # Expectation: `search_called` is `True` and `no_variables_found` is
    #   `False`.
    status = data_utils.check_data_availability(
        [
            tool_call(
                "search_indicators",
                {"variableCandidates": {"rows": [{"dcid": "Count_Person"}]}},
            )
        ]
    )
    assert status["search_called"] is True
    assert status["no_variables_found"] is False
    assert status["has_data"] is False


def test_annotate_truncation_sets_step_limit_message_when_no_data() -> None:
    # Test: Truncation message when the MCP tool loop stops before finding data.
    # Situation: The tool loop reaches its iteration cap without fetching any
    #   observations (`has_data` is `False`).
    # Expectation: `annotate_truncation` sets `truncated: True` and replaces the
    #   missing-data message with an explanation that the research step limit
    #   was reached.
    status = data_utils.check_data_availability([])
    data_utils.annotate_truncation(status, True)
    assert status["truncated"] is True
    assert status["message"] == (
        "We ran out of research steps before finding data for your query. "
        "Try asking something narrower."
    )


def test_annotate_truncation_preserves_none_message_when_data_found() -> None:
    # Test: Truncation annotation when valid observation data was already found.
    # Situation: The tool loop reaches its iteration cap after at least one
    #   observation call has returned data (`has_data` is `True`).
    # Expectation: `annotate_truncation` sets `truncated: True` and leaves
    #   `message` as `None`.
    status = data_utils.check_data_availability(
        [tool_call("get_observations", V130_WITH_DATA)]
    )
    data_utils.annotate_truncation(status, True)
    assert status["truncated"] is True
    assert status["message"] is None


# ---- provenance extraction ------------------------------------------------

_CENSUS_METADATA = {
    "variables": {
        "Count_Person": {"facets": [{"id": "facet1", "provenanceId": "prov1"}]}
    },
    "provenances": {
        "prov1": {
            "properties": {
                "isPartOf": "American Community Survey",
                "source": "Census Bureau",
                "url": "https://www.census.gov/",
                "licenseType": "CC-BY-4.0",
            }
        }
    },
}


def _observation(facet_id: str, **metadata: str) -> dict[str, Any]:
    """Build an observation payload attributed to `facet_id`."""
    return {
        "data": {"rows": [{"date": "2021", "value": 1.0}]},
        "sourceMetadata": {"sourceId": facet_id, **metadata},
    }


def test_observation_call_enriches_provenance_from_metadata_index() -> None:
    # Test: Source attribution when an observation facet matches
    #   `get_variable_metadata`.
    # Situation: `get_variable_metadata` describes `facet1` (with `isPartOf`,
    #   `source`, `url`, and `licenseType`), and `get_observations` reports
    #   `sourceId: "facet1"`.
    # Expectation: `extract_provenance_from_mcp_results` returns a single source
    #   entry using the dataset name (`isPartOf`), URL, and license from the
    #   metadata index.
    calls = [
        tool_call("get_variable_metadata", _CENSUS_METADATA),
        tool_call("get_observations", _observation("facet1")),
    ]
    assert data_utils.extract_provenance_from_mcp_results(calls) == [
        {
            "name": "American Community Survey",
            "url": "https://www.census.gov/",
            "license": "CC-BY-4.0",
        }
    ]


def test_unreferenced_metadata_candidate_is_not_included_as_source() -> None:
    # Test: Exclusion of metadata candidates that never served observations.
    # Situation: `get_variable_metadata` returns facet descriptions, but no
    #   observation call references those facets.
    # Expectation: `extract_provenance_from_mcp_results` returns an empty list.
    calls = [tool_call("get_variable_metadata", _CENSUS_METADATA)]
    assert data_utils.extract_provenance_from_mcp_results(calls) == []


def test_observation_absent_from_metadata_uses_inline_source_fields() -> None:
    # Test: Fallback provenance construction when no metadata entry matches.
    # Situation: `get_variable_metadata` describes only `facet1`, and
    #   `get_observations` returns a different `sourceId` along with
    #   `provenanceUrl` and `importName`.
    # Expectation: `extract_provenance_from_mcp_results` constructs the source
    #   entry from `importName` and `provenanceUrl`.
    calls = [
        tool_call("get_variable_metadata", _CENSUS_METADATA),
        tool_call(
            "get_observations",
            _observation(
                "facet_not_in_metadata",
                provenanceUrl="https://www.bls.gov/",
                importName="BLS_LAUS",
            ),
        ),
    ]
    assert data_utils.extract_provenance_from_mcp_results(calls) == [
        {"name": "BLS_LAUS", "url": "https://www.bls.gov/"}
    ]


def test_unnamed_observation_source_falls_back_to_domain() -> None:
    # Test: Domain-name fallback when an observation source carries only a URL.
    # Situation: `get_observations` provides `provenanceUrl` without
    #   `importName` or `sourceName`, and the metadata index does not describe
    #   the facet.
    # Expectation: `extract_provenance_from_mcp_results` uses the URL's hostname
    #   with any leading `www.` removed as the source name.
    calls = [
        tool_call("get_variable_metadata", _CENSUS_METADATA),
        tool_call(
            "get_observations",
            _observation(
                "facet_not_in_metadata",
                provenanceUrl="https://www.example.org/x",
            ),
        ),
    ]
    assert data_utils.extract_provenance_from_mcp_results(calls) == [
        {"name": "example.org", "url": "https://www.example.org/x"}
    ]


def test_literal_unknown_source_id_is_ignored() -> None:
    # Test: Handling of the MCP 1.2.x `"unknown"` sentinel `sourceId`.
    # Situation: `get_observations` returns `sourceMetadata: {"sourceId":
    #   "unknown"}` with no `provenanceUrl`.
    # Expectation: `"unknown"` is not looked up in the facet index and no source
    #   entry is emitted.
    calls = [
        tool_call("get_variable_metadata", _CENSUS_METADATA),
        tool_call("get_observations", _observation("unknown")),
    ]
    assert data_utils.extract_provenance_from_mcp_results(calls) == []


def test_sources_are_deduplicated_by_url() -> None:
    # Test: URL-based deduplication of provenance sources.
    # Situation: Two `get_observations` calls reference distinct facets (`"a"`
    #   and `"b"`) that resolve to the same `provenanceUrl`.
    # Expectation: `extract_provenance_from_mcp_results` emits a single source
    #   entry for that URL.
    calls = [
        tool_call(
            "get_observations",
            _observation("a", provenanceUrl="https://www.bls.gov/"),
        ),
        tool_call(
            "get_observations",
            _observation("b", provenanceUrl="https://www.bls.gov/"),
        ),
    ]
    assert len(data_utils.extract_provenance_from_mcp_results(calls)) == 1


def test_sources_preserve_first_seen_observation_order() -> None:
    # Test: Ordering of extracted provenance sources across observation calls.
    # Situation: Two `get_observations` calls return observations from two
    #   distinct provenance URLs in sequence.
    # Expectation: `extract_provenance_from_mcp_results` returns the sources in
    #   the exact order in which the observation calls appeared.
    calls = [
        tool_call(
            "get_observations",
            _observation("a", provenanceUrl="https://www.bls.gov/"),
        ),
        tool_call(
            "get_observations",
            _observation("b", provenanceUrl="https://www.census.gov/"),
        ),
    ]
    sources = data_utils.extract_provenance_from_mcp_results(calls)
    assert [source["url"] for source in sources] == [
        "https://www.bls.gov/",
        "https://www.census.gov/",
    ]

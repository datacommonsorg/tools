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
"""Tests for `backfill_variable_metadata`."""

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import replace

import pytest

from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.capabilities import Capabilities
from narratives_agent.workflows import metadata_backfill
from narratives_agent.workflows.metadata_backfill import (
    backfill_variable_metadata,
)
from narratives_agent.workflows.processing import execute_specification
from narratives_agent.workflows.specification import AnalysisSpecification
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache

_WDI_URL = "https://datatopics.worldbank.org/world-development-indicators/"
_FACET = "f1"
_CAPABILITIES = Capabilities(tool_names=frozenset({"get_variable_metadata"}))
_INLINE_SOURCE = Source(name="datatopics.worldbank.org", url=_WDI_URL)

type _Answer = Callable[[JsonObject], JsonObject]


def _build_table(
    table_id: str,
    variable_dcid: str,
    places: Sequence[str] = ("country/FRA",),
    *,
    facet_id: str | None = _FACET,
) -> CachedTable:
    """Builds a fetched table citing the inline source, two years per place."""
    source = Source(
        name=_INLINE_SOURCE.name,
        url=_INLINE_SOURCE.url,
        variable_dcid=variable_dcid,
        variable_name=variable_dcid,
    )
    return CachedTable(
        table_id=table_id,
        table=ObservationTable(
            variable_dcid=variable_dcid,
            variable_name=variable_dcid,
            unit=None,
            scaling_factor=None,
            provenance=Provenance(sources=(source,)),
            rows=tuple(
                ObservationRow(place, place, year, 1.0)
                for place in sorted(places)
                for year in ("2022", "2023")
            ),
            requested_places=tuple(places),
            place_names={place: place for place in places},
            facet_id=facet_id,
            source=source,
        ),
    )


def _build_cache(*tables: CachedTable) -> TurnCache:
    """Returns a cache holding `tables` as fetched tables, in order."""
    cache = TurnCache()
    for table in tables:
        cache.store_fetched(table)
    return cache


def _build_specification(*table_ids: str) -> AnalysisSpecification:
    """Returns a specification whose one composition reads `table_ids`."""
    return AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "compute_composition",
                    "components": list(table_ids),
                }
            ]
        }
    )


def _build_metadata_payload(*variable_dcids: str) -> JsonObject:
    """Builds metadata describing `_FACET` of each variable from WDI."""
    return {
        "provenances": {
            "dc/base/WDI": {
                "properties": {
                    "isPartOf": "World Development Indicators",
                    "licenseType": "CC BY 4.0",
                    "source": "World Bank",
                    "url": _WDI_URL,
                }
            }
        },
        "variables": {
            dcid: {
                "facets": [
                    {
                        "id": _FACET,
                        "provenanceId": "dc/base/WDI",
                        "dateRange": {"start": "2000", "end": "2024"},
                    }
                ]
            }
            for dcid in variable_dcids
        },
    }


def _wrap_payload(payload: JsonObject) -> JsonObject:
    """Wraps a payload in the MCP envelope `async_call_tool` returns."""
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def _answer_with_metadata(arguments: JsonObject) -> JsonObject:
    """Answers a metadata call by describing every requested variable."""
    variables = arguments["variable_dcids"]
    assert isinstance(variables, list)
    return _wrap_payload(
        _build_metadata_payload(*(str(dcid) for dcid in variables))
    )


def _install_tool(
    monkeypatch: pytest.MonkeyPatch, answer: _Answer = _answer_with_metadata
) -> list[tuple[str, JsonObject]]:
    """Replaces `async_call_tool` and returns the list of calls it receives."""
    calls: list[tuple[str, JsonObject]] = []

    async def call_tool(name: str, arguments: JsonObject) -> JsonObject:
        calls.append((name, arguments))
        return answer(arguments)

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    return calls


def _list_requested_variables(
    calls: Sequence[tuple[str, JsonObject]],
) -> list[JsonValue]:
    """Returns the `variable_dcids` argument of each call, in order."""
    return [arguments["variable_dcids"] for _, arguments in calls]


@pytest.mark.asyncio
async def test_a_table_without_metadata_is_cited_with_the_backfilled_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The backfill of a referenced table that has no metadata.
    # Situation: `t1` cites the inline source of its facet, and the server
    #   describes that facet as World Development Indicators by the World
    #   Bank, covering 2000 to 2024.
    # Expectation: One `get_variable_metadata` call asks about the table's
    #   variable and place, and the digest of the specification, run
    #   afterward, cites the provider, the dataset, and the date range for
    #   the table's variable.
    calls = _install_tool(monkeypatch)
    cache = _build_cache(_build_table("t1", "Count_Person"))
    specification = AnalysisSpecification.model_validate(
        {
            "steps": [
                {"step_id": "s1", "script": "analyze_timeseries", "table": "t1"}
            ]
        }
    )

    await backfill_variable_metadata(specification, cache, _CAPABILITIES)
    digest = await execute_specification(specification, cache)

    assert calls == [
        (
            "get_variable_metadata",
            {
                "variable_dcids": ["Count_Person"],
                "entity_dcids": ["country/FRA"],
            },
        )
    ]
    assert isinstance(digest, AnalysisDigest)
    (source,) = digest.sources
    assert source.provider == "World Bank"
    assert source.dataset == "World Development Indicators"
    assert source.date_range == "2000 \u2013 2024"
    assert source.variable_dcid == "Count_Person"


@pytest.mark.asyncio
async def test_only_referenced_tables_that_lack_metadata_are_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The selection of tables to request.
    # Situation: The specification reads `t1`, whose variable and facet are
    #   already described, `t3`, which has no rows, `t4`, which has no facet
    #   id, and `t5`, which needs metadata; `t2` needs metadata but is not
    #   read.
    # Expectation: One call asks about `t5`'s variable alone.
    calls = _install_tool(monkeypatch)
    empty = _build_table("t3", "Empty")
    cache = _build_cache(
        _build_table("t1", "Described"),
        _build_table("t2", "Unread"),
        replace(empty, table=replace(empty.table, rows=())),
        _build_table("t4", "Unfaceted", facet_id=None),
        _build_table("t5", "Needed"),
    )
    cache.record_variable_metadata(_build_metadata_payload("Described"))

    await backfill_variable_metadata(
        _build_specification("t1", "t3", "t4", "t5"), cache, _CAPABILITIES
    )

    assert _list_requested_variables(calls) == [["Needed"]]


@pytest.mark.asyncio
async def test_a_facet_described_only_for_another_variable_is_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The exact `(variable, facet)` check.
    # Situation: The cache holds metadata for facet `f1` of `Other`, and
    #   `t1` holds `Needed` served from the same facet id.
    # Expectation: `Needed` is requested, because another variable's entry
    #   for the facet has no date range for `Needed`.
    calls = _install_tool(monkeypatch)
    cache = _build_cache(_build_table("t1", "Needed"))
    cache.record_variable_metadata(_build_metadata_payload("Other"))

    await backfill_variable_metadata(
        _build_specification("t1"), cache, _CAPABILITIES
    )

    assert _list_requested_variables(calls) == [["Needed"]]


@pytest.mark.asyncio
async def test_a_cohort_is_sampled_to_its_first_ten_places(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The entity limit of `get_variable_metadata`.
    # Situation: `t1` covers twelve states.
    # Expectation: The call names the first ten states in row order.
    calls = _install_tool(monkeypatch)
    places = [f"geoId/{number:02d}" for number in range(12, 0, -1)]
    cache = _build_cache(_build_table("t1", "Count_Person", places))

    await backfill_variable_metadata(
        _build_specification("t1"), cache, _CAPABILITIES
    )

    ((_, arguments),) = calls
    assert arguments["entity_dcids"] == sorted(places)[:10]


@pytest.mark.asyncio
async def test_variables_sampled_over_the_same_places_share_bounded_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The variable limit of `get_variable_metadata`.
    # Situation: Eleven tables of different variables cover France.
    # Expectation: Two calls ask about the first ten variables and then the
    #   eleventh, each naming France.
    calls = _install_tool(monkeypatch)
    variables = [f"Variable_{index:02d}" for index in range(1, 12)]
    table_ids = [f"t{index}" for index in range(1, 12)]
    cache = _build_cache(
        *(
            _build_table(table_id, variable)
            for table_id, variable in zip(table_ids, variables, strict=True)
        )
    )

    await backfill_variable_metadata(
        _build_specification(*table_ids), cache, _CAPABILITIES
    )

    assert _list_requested_variables(calls) == [variables[:10], variables[10:]]
    assert [arguments["entity_dcids"] for _, arguments in calls] == [
        ["country/FRA"],
        ["country/FRA"],
    ]


@pytest.mark.asyncio
async def test_variables_sampled_over_different_places_are_requested_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The grouping of tables by sampled places.
    # Situation: `t1` covers France and `t2` covers Germany.
    # Expectation: Each table's variable is requested in its own call with
    #   its own place.
    calls = _install_tool(monkeypatch)
    cache = _build_cache(
        _build_table("t1", "Gdp", ("country/FRA",)),
        _build_table("t2", "Population", ("country/DEU",)),
    )

    await backfill_variable_metadata(
        _build_specification("t1", "t2"), cache, _CAPABILITIES
    )

    assert sorted(
        [arguments["variable_dcids"], arguments["entity_dcids"]]
        for _, arguments in calls
    ) == [
        [["Gdp"], ["country/FRA"]],
        [["Population"], ["country/DEU"]],
    ]


@pytest.mark.asyncio
async def test_a_server_without_the_metadata_tool_is_not_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The capability gate.
    # Situation: The MCP server does not list `get_variable_metadata`.
    # Expectation: No call is made and the table keeps the inline source.
    calls = _install_tool(monkeypatch)
    cache = _build_cache(_build_table("t1", "Count_Person"))

    await backfill_variable_metadata(
        _build_specification("t1"),
        cache,
        Capabilities(tool_names=frozenset({"search_indicators"})),
    )

    assert calls == []
    entry = cache.get("t1")
    assert entry is not None
    assert entry.table.source is not None
    assert entry.table.source.name == _INLINE_SOURCE.name


def _raise_tool_error(arguments: JsonObject) -> JsonObject:
    """Fails a call at the tool layer."""
    raise mcp_client.McpToolError("get_variable_metadata", "bad request")


def _raise_transport_error(arguments: JsonObject) -> JsonObject:
    """Fails a call below the tool layer."""
    raise mcp_client.McpTransportError()


@pytest.mark.parametrize(
    ("answer", "error_name"),
    [
        pytest.param(_raise_tool_error, "McpToolError", id="tool-error"),
        pytest.param(
            _raise_transport_error, "McpTransportError", id="transport-error"
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_failed_call_keeps_the_inline_source_and_logs_a_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    answer: _Answer,
    error_name: str,
) -> None:
    # Test: A failed backfill call.
    # Situation: The metadata call raises `McpToolError` or
    #   `McpTransportError`.
    # Expectation: The backfill returns normally, the table keeps the inline
    #   source, and one warning names the variable and the error class.
    _install_tool(monkeypatch, answer)
    cache = _build_cache(_build_table("t1", "Count_Person"))

    with caplog.at_level(logging.WARNING, logger=metadata_backfill.logger.name):
        await backfill_variable_metadata(
            _build_specification("t1"), cache, _CAPABILITIES
        )

    entry = cache.get("t1")
    assert entry is not None
    assert entry.table.source is not None
    assert entry.table.source.provider is None
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert "Count_Person" in record.getMessage()
    assert error_name in record.getMessage()


@pytest.mark.asyncio
async def test_a_slow_call_times_out_and_keeps_the_inline_source(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Test: The shared backfill timeout.
    # Situation: The budget is shortened to 10 ms and the metadata call
    #   never returns.
    # Expectation: The backfill returns normally, the hung call is
    #   canceled, the table keeps the inline source, and a warning names
    #   the variable and `TimeoutError`.
    canceled = asyncio.Event()

    async def hang(name: str, arguments: JsonObject) -> JsonObject:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            canceled.set()
            raise
        raise AssertionError("unreachable")

    monkeypatch.setattr(mcp_client, "async_call_tool", hang)
    monkeypatch.setattr(metadata_backfill, "_BACKFILL_TIMEOUT_SECONDS", 0.01)
    cache = _build_cache(_build_table("t1", "Count_Person"))

    with caplog.at_level(logging.WARNING, logger=metadata_backfill.logger.name):
        await backfill_variable_metadata(
            _build_specification("t1"), cache, _CAPABILITIES
        )

    assert canceled.is_set()
    entry = cache.get("t1")
    assert entry is not None
    assert entry.table.source is not None
    assert entry.table.source.provider is None
    (record,) = caplog.records
    assert "Count_Person" in record.getMessage()
    assert "TimeoutError" in record.getMessage()


@pytest.mark.asyncio
async def test_a_failed_call_does_not_discard_a_sibling_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Independence of concurrent backfill calls.
    # Situation: `t1` covers France and `t2` covers Germany under another
    #   facet, so each is requested in its own call; the call about Germany
    #   fails with `McpTransportError` before the call about France answers.
    # Expectation: `t1` cites the backfilled World Bank source and `t2`
    #   keeps the inline source.
    germany_failed = asyncio.Event()

    async def call_tool(name: str, arguments: JsonObject) -> JsonObject:
        if arguments["entity_dcids"] == ["country/DEU"]:
            germany_failed.set()
            raise mcp_client.McpTransportError()
        async with asyncio.timeout(1):
            await germany_failed.wait()
        return _answer_with_metadata(arguments)

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    cache = _build_cache(
        _build_table("t1", "Gdp", ("country/FRA",)),
        _build_table("t2", "Population", ("country/DEU",), facet_id="f2"),
    )

    await backfill_variable_metadata(
        _build_specification("t1", "t2"), cache, _CAPABILITIES
    )

    france, germany = cache.get("t1"), cache.get("t2")
    assert france is not None and france.table.source is not None
    assert germany is not None and germany.table.source is not None
    assert france.table.source.provider == "World Bank"
    assert germany.table.source.provider is None


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(_answer_with_metadata, id="succeeded"),
        pytest.param(_raise_tool_error, id="failed"),
    ],
)
@pytest.mark.asyncio
async def test_a_pair_is_requested_at_most_once_per_turn(
    monkeypatch: pytest.MonkeyPatch, answer: _Answer
) -> None:
    # Test: A pair is not requested again in a turn, whether its first
    #   request succeeded or failed.
    # Situation: The backfill runs twice over one cache for the same table;
    #   the first request succeeds or fails.
    # Expectation: Only the first backfill makes a call.
    calls = _install_tool(monkeypatch, answer)
    cache = _build_cache(_build_table("t1", "Count_Person"))
    specification = _build_specification("t1")

    await backfill_variable_metadata(specification, cache, _CAPABILITIES)
    await backfill_variable_metadata(specification, cache, _CAPABILITIES)

    assert len(calls) == 1

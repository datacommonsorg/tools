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
"""Builds the synthesis prompt from the analysis digest and cached tables.

Collects `SynthesisPromptInputs` from the `AnalysisDigest`, the numbered
sources, and an inventory of the cached tables (`build_synthesis_inputs`),
and renders them as the synthesis user message (`render_synthesis_message`).
It also defines `SYNTHESIS_CHUNK_TIMEOUT_SECONDS`, the per-chunk read timeout
for the agent loop to apply to the synthesis stream.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from narratives_agent.analytics.digest import (
    AnalysisDigest,
    format_scaling_factor,
)
from narratives_agent.analytics.metrics import DerivedMetrics
from narratives_agent.analytics.provenance import Source
from narratives_agent.analytics.tables import clean_display_name
from narratives_agent.workflows.charts import (
    INVENTORY_PLACE_CAP,
    ChildCohort,
    find_chart_entry,
    get_chart_cohort,
)
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    ComputeDerivedMetricStep,
)
from narratives_agent.workflows.turn_cache import CachedTable

__all__ = [
    "SYNTHESIS_CHUNK_TIMEOUT_SECONDS",
    "SynthesisPromptInputs",
    "SynthesisSource",
    "TableDerivation",
    "TableInventoryItem",
    "build_synthesis_inputs",
    "render_synthesis_message",
]

# Per-chunk timeout in seconds while reading the synthesis stream.
SYNTHESIS_CHUNK_TIMEOUT_SECONDS = 60.0
# Scale of a per-capita value stated per person, which the chart shows.
_PER_PERSON_SCALE = 1.0
# Unicode control (`Cc`) and format (`Cf`) categories stripped from URLs.
_CONTROL_OR_FORMAT_CATEGORIES = frozenset({"Cc", "Cf"})

# Section headers and the closing instruction of the synthesis user message.
_SOURCES_HEADER = "**NUMBERED SOURCES - cite these numbers, exactly as given:**"
_DIGEST_HEADER = (
    "**ANALYSIS DIGEST (every figure is computed and verified by the server):**"
)
_NO_RESULTS_TEXT = "No results were computed."
_MISSING_DATA_HEADER = "**MISSING DATA:**"
_INVENTORY_HEADER = (
    "**TABLE INVENTORY (the only tables a chart block may reference):**"
)
_CLOSING_INSTRUCTION = (
    "Write the answer now, reporting the digest's figures exactly as "
    "given, with their units, dates, and citations."
)


@dataclass(frozen=True)
class SynthesisSource:
    """One numbered source, as the model cites it and the reader sees it.

    Attributes:
        name: The source's cleaned display name, or its URL when it has no
            name.
        url: The source's cleaned provenance URL.
    """

    name: str
    url: str


@dataclass(frozen=True)
class TableDerivation:
    """How a derived table in the inventory was computed.

    Attributes:
        left: The table id of the derivation's left input.
        right: The table id of the derivation's right input.
        is_charted_per_capita: Whether the table is a per-capita count that
            charts as its fetched numerator normalized by population.
        scale: The multiplier the digest reports the table's values at,
            such as 100000 for values per 100,000 people; None when no
            digest result names it.
    """

    left: str
    right: str
    is_charted_per_capita: bool
    scale: float | None = None


@dataclass(frozen=True)
class TableInventoryItem:
    """One cached table as the synthesis prompt describes it.

    Attributes:
        table_id: The id the model writes in a chart block.
        variable_dcid: The table's variable.
        variable_name: The variable's cleaned display name.
        unit: The cleaned unit of the values; None when the table reports
            none.
        scaling_factor: The scaling factor of the values; None when the
            table reports none.
        cohort: The child-place cohort the table was fetched across; None
            when it was not fetched across one.
        date_span: The earliest and latest observation dates; None when the
            table has no rows.
        place_count: How many places have data.
        places: Up to `INVENTORY_PLACE_CAP` places with data, as DCID and
            cleaned display name pairs.
        derivation: How a derived table was computed; None for a fetched
            table.
    """

    table_id: str
    variable_dcid: str
    variable_name: str
    unit: str | None
    scaling_factor: float | None
    cohort: ChildCohort | None
    date_span: tuple[str, str] | None
    place_count: int
    places: tuple[tuple[str, str], ...]
    derivation: TableDerivation | None = None


@dataclass(frozen=True)
class SynthesisPromptInputs:
    """Everything the synthesis user message is rendered from.

    The digest holds the computed figures and the missing-data notes. The
    other fields hold the sanitized text that came from outside the server:
    the numbered sources and the table inventory with its variable and place
    names.

    Attributes:
        query: The user's question.
        digest: The digest the turn is answered from.
        sources: The numbered sources, in citation order.
        inventory: The cached tables a chart block may reference.
    """

    query: str
    digest: AnalysisDigest
    sources: tuple[SynthesisSource, ...]
    inventory: tuple[TableInventoryItem, ...]


def _clean_source_url(url: str) -> str:
    """Strips whitespace and control or format characters from a URL."""
    return "".join(
        char
        for char in url
        if not char.isspace()
        and unicodedata.category(char) not in _CONTROL_OR_FORMAT_CATEGORIES
    )


def _build_synthesis_source(source: Source) -> SynthesisSource:
    """Builds a single-line numbered source from external provenance."""
    url = _clean_source_url(source.url)
    name = clean_display_name(source.name, "")
    return SynthesisSource(name=name or url, url=url)


def _build_inventory_item(
    entry: CachedTable,
    derivation: TableDerivation | None,
    cohort: ChildCohort | None,
) -> TableInventoryItem:
    """Describes one cached table for the inventory.

    `cohort` is the cohort of the table a chart of `entry` draws, which
    for a per-capita table is its numerator's.
    """
    table = entry.table
    dates = sorted({row.date for row in table.rows})
    places = table.places_with_data
    unit = (
        clean_display_name(table.unit, "") or None
        if table.unit is not None
        else None
    )
    return TableInventoryItem(
        table_id=entry.table_id,
        variable_dcid=table.variable_dcid,
        variable_name=clean_display_name(
            table.variable_name, table.variable_dcid
        ),
        unit=unit,
        scaling_factor=table.scaling_factor,
        cohort=cohort,
        date_span=(dates[0], dates[-1]) if dates else None,
        place_count=len(places),
        places=tuple(
            (place, clean_display_name(table.place_names.get(place, ""), place))
            for place in places[:INVENTORY_PLACE_CAP]
        ),
        derivation=derivation,
    )


def build_synthesis_inputs(
    query: str,
    digest: AnalysisDigest,
    analysis: AnalysisSpecification | None,
    tables: Sequence[CachedTable],
    sources: Sequence[Source],
) -> SynthesisPromptInputs:
    """Collects the typed inputs of the synthesis user message.

    Args:
        query: The user's question.
        digest: The digest the turn is answered from.
        analysis: The specification that produced the digest, used to tell
            derived tables from fetched ones; None when the turn ran no
            specification.
        tables: The cached tables the specification used, fetched first.
        sources: The numbered sources streamed to the browser, in order:
            the digest's sources, or, when the digest cites none, the
            sources the caller cites in their place.

    Returns:
        The inputs, with the specification's `findings` left out: they are
        the model's reading of the fetch summaries' sample rows, and the
        digest holds the computed figures.

    Raises:
        ValueError: If the digest cites sources and `sources` differs from
            them, which would number the digest's citations against another
            list.
    """
    if digest.sources and tuple(sources) != digest.sources:
        raise ValueError(
            "The synthesis sources must be the digest's sources, in order."
        )
    scales = {
        result.step_id: result.metrics.scale
        for result in digest.results
        if isinstance(result.metrics, DerivedMetrics)
    }
    # The inventory and the per-capita check read only the tables the
    # specification used, not the whole cache, so that a stale derived
    # table left behind by an earlier run is never described.
    lookup = {entry.table_id: entry for entry in tables}
    inventory: list[TableInventoryItem] = []
    for entry in tables:
        chart_entry = find_chart_entry(entry.table_id, analysis, lookup)
        # The cohort a chart can draw is the charted table's, so a
        # per-capita table states its numerator's cohort, not the
        # population cohort it may hold.
        cohort = get_chart_cohort((chart_entry or entry).table)
        step = (
            analysis.find_step(entry.table_id) if analysis is not None else None
        )
        derivation = (
            None
            if not isinstance(step, ComputeDerivedMetricStep)
            else TableDerivation(
                left=step.left,
                right=step.right,
                is_charted_per_capita=chart_entry is not None,
                scale=scales.get(step.step_id),
            )
        )
        inventory.append(_build_inventory_item(entry, derivation, cohort))
    return SynthesisPromptInputs(
        query=query,
        digest=digest,
        sources=tuple(_build_synthesis_source(source) for source in sources),
        inventory=tuple(inventory),
    )


def _format_count(number: int, noun: str) -> str:
    """Formats a count with its noun, singular or plural."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _render_inventory_line(item: TableInventoryItem) -> str:
    """Renders one inventory item as a line of the prompt."""
    named = ", ".join(f"{name} ({dcid})" for dcid, name in item.places)
    if item.place_count > len(item.places):
        unnamed = item.place_count - len(item.places)
        named += f", and {_format_count(unnamed, 'more place')}"
    if item.cohort is not None:
        cohort = item.cohort
        scope = f"every {cohort.child_place_type} in {cohort.parent_place}"
    else:
        scope = _format_count(item.place_count, "place")
    span = (
        f"{item.date_span[0]} to {item.date_span[1]}"
        if item.date_span
        else "no dates"
    )
    derivation = item.derivation
    if derivation is None:
        identity = (
            f"{item.table_id}: {item.variable_name} ({item.variable_dcid})"
        )
    elif derivation.is_charted_per_capita:
        # A digest scaled per 1,000 or per 100,000 people would otherwise
        # suggest that scale for a chart that shows values per person.
        scale = derivation.scale
        reported = (
            f"the digest reports values per {format_scaling_factor(scale)} "
            "people and "
            if scale is not None and scale != _PER_PERSON_SCALE
            else ""
        )
        identity = (
            f"{item.table_id} (derived from {derivation.left} and "
            f"{derivation.right}; chartable, {reported}the chart shows "
            f"values per person): {item.variable_name}"
        )
    else:
        identity = (
            f"{item.table_id} (derived from {derivation.left} and "
            f"{derivation.right}; not a Data Commons variable, do not "
            f"chart it): {item.variable_name}"
        )
    unit = item.unit or "unknown"
    if item.scaling_factor is not None:
        factor = format_scaling_factor(item.scaling_factor)
        unit += f" (scaling factor {factor})"
    return (
        f"- {identity}; unit: {unit}; {scope}; dates {span}; places with "
        f"data: {named or 'none'}"
    )


def _label_source(source: SynthesisSource) -> str:
    """Labels a numbered source by name and URL, or by whichever is set.

    A source without a name is named by its URL, so its label states the
    URL once; a source without a URL states its name without a separator.
    """
    if not source.url or source.name == source.url:
        return source.name
    return f"{source.name} - {source.url}"


def render_synthesis_message(inputs: SynthesisPromptInputs) -> str:
    """Renders the user message that carries the analysis to synthesis.

    The numbered sources come first, so that the `[n]` in the prose and the
    `[n]` beside the source resolve to the same row, then the digest's
    results, the missing-data notes, and the table inventory.

    Args:
        inputs: The typed inputs from `build_synthesis_inputs`.

    Returns:
        The user message, its sections separated by blank lines; a section
        whose input is empty is left out, except the digest's, which states
        that no results were computed.
    """
    parts = [f"User Query: {inputs.query}"]
    if inputs.sources:
        numbered = "\n".join(
            f"[{number}] {_label_source(source)}"
            for number, source in enumerate(inputs.sources, start=1)
        )
        parts.append(f"{_SOURCES_HEADER}\n{numbered}")
    # The sources and notes come from their typed fields above and below, so
    # only the digest's results are rendered here.
    results = inputs.digest.format_results_for_prompt()
    parts.append(f"{_DIGEST_HEADER}\n{results or _NO_RESULTS_TEXT}")
    if inputs.digest.missing_notes:
        notes = "\n".join(f"- {note}" for note in inputs.digest.missing_notes)
        parts.append(f"{_MISSING_DATA_HEADER}\n{notes}")
    if inputs.inventory:
        lines = "\n".join(
            _render_inventory_line(item) for item in inputs.inventory
        )
        parts.append(f"{_INVENTORY_HEADER}\n{lines}")
    parts.append(_CLOSING_INSTRUCTION)
    return "\n\n".join(parts)

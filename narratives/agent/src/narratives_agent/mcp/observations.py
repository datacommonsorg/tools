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
"""Parses and merges MCP 1.3.x observation payloads into `ObservationTable`s.

Validates decoded MCP observation payloads through `mcp.wire` models, applies
identifier, date, and value checks and `get_variable_metadata` enrichment, and
constructs immutable `ObservationTable` domain objects for `analytics/`.
"""

import logging
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from pydantic import ValidationError

from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
)
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
    clean_display_name,
    is_inverted_date_range,
    is_valid_dcid,
    is_valid_observation_date,
    is_within_date_range,
)
from narratives_agent.json_value import JsonValue
from narratives_agent.mcp.metadata import (
    VariableMetadataEnrichment,
    get_source_from_observation_metadata,
)
from narratives_agent.mcp.wire import (
    AlternativeSourceWire,
    ColumnarTableWire,
    ObservationPayloadWire,
    validate_observation_payload,
)

__all__ = [
    "ObservationPayloadError",
    "apply_variable_metadata",
    "merge_observation_payloads",
    "parse_observation_table",
]

logger = logging.getLogger(__name__)

_DATA_COLUMNS = ("observationAbout", "date", "value")
_ENTITY_COLUMNS = ("dcid", "name")
# Maximum number of invalid field locations quoted in an
# `ObservationPayloadError` message.
_MAX_REPORTED_FIELDS = 3


class ObservationPayloadError(Exception):
    """An MCP observation payload does not match the observation schema.

    Distinct from the `ValueError` and `TypeError` raised for invalid
    arguments, so a malformed upstream response is never mistaken for a
    caller error.
    """


@dataclass(frozen=True)
class _Observation:
    """A validated observation row before display names are resolved."""

    place_dcid: str
    date: str
    value: float


def _validate_payload(
    payload: ObservationPayloadWire | Mapping[str, JsonValue], subject: str
) -> ObservationPayloadWire:
    """Validates a decoded payload into an `ObservationPayloadWire`.

    Logs a warning that names `subject` when malformed alternative sources are
    dropped.

    Args:
        payload: A validated wire model, or the decoded JSON object a tool
            returned.
        subject: The variable or place named in the error message and the
            warning.

    Raises:
        ObservationPayloadError: If the payload lacks the `variable` block,
            has a structural key of the wrong type, or has a variable DCID or
            served facet ID that is not a valid identifier.
    """
    if isinstance(payload, ObservationPayloadWire):
        return payload
    try:
        wire, dropped = validate_observation_payload(payload)
    except ValidationError as error:
        # Report field locations only; the input values are upstream data.
        fields = ", ".join(
            ".".join(str(part) for part in detail["loc"])
            for detail in error.errors()[:_MAX_REPORTED_FIELDS]
        )
        raise ObservationPayloadError(
            f"The observation payload for {subject} has malformed fields: "
            f"{fields}."
        ) from error
    if dropped:
        logger.warning(
            "Dropped %d malformed alternative source(s) for %s.",
            dropped,
            subject,
        )
    return wire


def _finite_float(value: JsonValue) -> float | None:
    """Returns a numeric `value` as a finite float, or `None`.

    Booleans are rejected even though Python treats them as integers, because
    a `true` in a value column is a malformed row, not the number one.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        # An integer beyond float range is malformed, like a non-finite value.
        return None
    return number if math.isfinite(number) else None


def _columnar_records(
    table: ColumnarTableWire,
) -> list[dict[str, JsonValue]]:
    """Zips each positional row of `table` against `table.columns`.

    A row that is not a list becomes an empty record, which fails every field
    check, so it is dropped and counted like any other malformed row.
    """
    if not table.columns or not table.rows:
        return []
    return [
        dict(zip(table.columns, row, strict=False))
        if isinstance(row, list)
        else {}
        for row in table.rows
    ]


def _read_entity_metadata(
    table: ColumnarTableWire,
) -> tuple[dict[str, str], list[str]]:
    """Extracts `(names_by_dcid, ordered_valid_dcids)` from `entityMetadata`."""
    names: dict[str, str] = {}
    dcids: list[str] = []
    for record in _columnar_records(table):
        raw_dcid = record.get("dcid")
        if not isinstance(raw_dcid, str):
            continue
        dcid = raw_dcid.strip()
        if not is_valid_dcid(dcid):
            continue
        dcids.append(dcid)
        raw_name = record.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            names.setdefault(dcid, raw_name.strip())
    return names, dcids


def _read_observations(
    table: ColumnarTableWire, subject: str
) -> list[_Observation]:
    """Validates every row of a columnar `data` table.

    Rows that are not lists, rows without a valid place DCID, with a
    malformed date, or with a value that is not a finite number are dropped,
    as is a repeat of a `(place, date)` already read, and a warning naming
    `subject` records how many.

    Raises:
        ObservationPayloadError: If the table has rows but lacks one of the
            `observationAbout`, `date`, and `value` columns.
    """
    missing = [name for name in _DATA_COLUMNS if name not in table.columns]
    if table.rows and missing:
        raise ObservationPayloadError(
            f"The observation data for {subject} has rows but lacks the "
            f"column(s): {', '.join(missing)}."
        )
    records = _columnar_records(table)
    observations: list[_Observation] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        raw_place = record.get("observationAbout")
        place = raw_place.strip() if isinstance(raw_place, str) else ""
        raw_date = record.get("date")
        date = raw_date.strip() if isinstance(raw_date, str) else ""
        value = _finite_float(record.get("value"))
        if (
            not is_valid_dcid(place)
            or not is_valid_observation_date(date)
            or value is None
            or (place, date) in seen
        ):
            continue
        seen.add((place, date))
        observations.append(
            _Observation(place_dcid=place, date=date, value=value)
        )
    dropped = len(records) - len(observations)
    if dropped:
        logger.warning(
            "Dropped %d of %d malformed or repeated observation rows for %s.",
            dropped,
            len(records),
            subject,
        )
    return observations


def _truncate(
    observations: list[_Observation], max_rows: int | None
) -> tuple[list[_Observation], bool]:
    """Keeps up to `max_rows` observations, the most recent of each place first.

    Rows are ranked within their own place, newest first, and whole ranks are
    retained while the next rank fits within `max_rows`. Every place's latest
    value is therefore kept before any place's older values, even when places
    report different latest dates. When places share dates, a rank is a date.
    When the latest values alone exceed `max_rows`, the `max_rows` most recent
    of them are kept, ties in place order.
    """
    if max_rows is None or len(observations) <= max_rows:
        return observations, False
    by_place: dict[str, list[_Observation]] = {}
    for item in sorted(observations, key=lambda item: item.date, reverse=True):
        by_place.setdefault(item.place_dcid, []).append(item)
    by_rank: dict[int, list[_Observation]] = {}
    for place_rows in by_place.values():
        for rank, item in enumerate(place_rows):
            by_rank.setdefault(rank, []).append(item)
    kept: list[_Observation] = []
    for rank in sorted(by_rank):
        tier = sorted(by_rank[rank], key=lambda item: item.place_dcid)
        if len(kept) + len(tier) > max_rows:
            if not kept:
                # `sorted` is stable, so equal dates keep their place order.
                newest = sorted(tier, key=lambda item: item.date, reverse=True)
                kept = newest[:max_rows]
            break
        kept.extend(tier)
    return kept, True


def _normalize_alternative_sources(
    entries: Sequence[AlternativeSourceWire],
) -> tuple[AlternativeSource, ...]:
    """Converts `alternativeSources` wire entries into `AlternativeSource`s.

    Entries without a `sourceId` are dropped because they cannot be requested
    through `source_override`. Duplicate `sourceId` entries keep the first
    occurrence.
    """
    normalized: list[AlternativeSource] = []
    seen_ids: set[str] = set()
    for entry in entries:
        meta = entry.source_metadata
        facet_id = meta.source_id
        if not facet_id or facet_id in seen_ids:
            continue
        seen_ids.add(facet_id)
        normalized.append(
            AlternativeSource(
                facet_id=facet_id,
                provenance_url=meta.provenance_url,
                measurement_method=meta.measurement_method,
                observation_period=meta.observation_period,
                unit=meta.unit,
                places_found_count=entry.places_found_count,
            )
        )
    return tuple(normalized)


@dataclass(frozen=True)
class _PlacePayload:
    """One validated per-place payload and the rows read for its place."""

    place_dcid: str
    wire: ObservationPayloadWire
    rows: list[_Observation]


def _read_place_payload(
    place_dcid: str, raw_payload: Mapping[str, JsonValue]
) -> _PlacePayload:
    """Validates one per-place payload and keeps the rows for `place_dcid`.

    Rows for any other place are dropped with a warning, because a payload
    fetched for one place that holds another place's rows is malformed.
    """
    wire = _validate_payload(raw_payload, place_dcid)
    observations = _read_observations(wire.data, place_dcid)
    rows = [item for item in observations if item.place_dcid == place_dcid]
    if len(rows) < len(observations):
        logger.warning(
            "Dropped %d observation row(s) for other places from the payload "
            "for %s.",
            len(observations) - len(rows),
            place_dcid,
        )
    return _PlacePayload(place_dcid=place_dcid, wire=wire, rows=rows)


def _select_header(items: Sequence[_PlacePayload]) -> _PlacePayload:
    """Picks the payload whose facet and `variable` block the merge keeps.

    The header is the first payload with rows from the facet that serves rows
    for the most distinct places, ties going to the facet first seen in
    request order. When no payload with rows names a facet, it is the first
    payload with rows, and when no payload has rows, the first payload.
    """
    places_by_facet: dict[str, set[str]] = {}
    for item in items:
        facet = item.wire.source_metadata.source_id
        if item.rows and facet is not None:
            places_by_facet.setdefault(facet, set()).add(item.place_dcid)
    coverage = Counter(
        {facet: len(places) for facet, places in places_by_facet.items()}
    )
    with_rows = [item for item in items if item.rows]
    if coverage:
        # `most_common` orders equal counts by first insertion, which is the
        # order in which each facet was first seen.
        facet = coverage.most_common(1)[0][0]
        return next(
            item
            for item in with_rows
            if item.wire.source_metadata.source_id == facet
        )
    return with_rows[0] if with_rows else items[0]


def merge_observation_payloads(
    payloads: Sequence[tuple[str, Mapping[str, JsonValue]]],
) -> ObservationPayloadWire:
    """Combines per-place observation payloads into one columnar payload.

    Takes `sourceMetadata` and `variable` from a header payload: the first
    payload with rows from the facet that serves the most distinct places,
    ties going to request order. When no payload with rows names a facet, the
    header is the first payload with rows, and when none has rows, the first
    payload. Only rows served by the header's facet are kept, so a multi-place
    table never blends facets; when the header names no facet, only the
    header payload's own rows are kept, so two unidentified facets are never
    blended either. `alternativeSources` are collected across all
    payloads, together with the facets whose rows were dropped. A `(place,
    date)` row already kept from an earlier payload is dropped, as is any row
    for a place other than the one its payload was fetched for. When more than
    one payload is merged, the alternatives carry no `placesFoundCount`,
    because each payload counts coverage for its own place only.
    `entityMetadata` lists each entity once, under the first name any payload
    gives it.

    Args:
        payloads: `(place_dcid, payload)` pairs in request order, each payload
            the decoded JSON object the tool returned for that place.

    Returns:
        The merged payload, which `parse_observation_table` accepts directly.

    Raises:
        ObservationPayloadError: If a payload lacks the `variable` block,
            has a structural key of the wrong type, or has a variable DCID or
            served facet ID that is not a valid identifier, if its `data`
            table has rows but lacks a required column, or if two payloads
            name different variables.
        ValueError: If `payloads` is empty or a place is not a valid DCID.
            The places are checked before any payload.
    """
    if not payloads:
        raise ValueError("merge_observation_payloads requires a payload.")
    for place_dcid, _ in payloads:
        if not is_valid_dcid(place_dcid):
            raise ValueError(
                f"The merged place {place_dcid!r} is not a valid DCID."
            )

    items: list[_PlacePayload] = []
    entity_names: dict[str, str | None] = {}
    for place_dcid, raw_payload in payloads:
        item = _read_place_payload(place_dcid, raw_payload)
        if items and item.wire.variable.dcid != items[0].wire.variable.dcid:
            raise ObservationPayloadError(
                f"The observation payloads for {items[0].place_dcid} and "
                f"{place_dcid} describe different variables: "
                f"{items[0].wire.variable.dcid!r} and "
                f"{item.wire.variable.dcid!r}."
            )
        items.append(item)
        names, dcids = _read_entity_metadata(item.wire.entity_metadata)
        # An entity listed by several payloads, such as a shared parent, is
        # listed once, under the first name any payload gives it.
        for dcid in dcids:
            if entity_names.get(dcid) is None:
                entity_names[dcid] = names.get(dcid)
    entity_rows: list[JsonValue] = [
        [dcid, name] for dcid, name in entity_names.items()
    ]

    header = _select_header(items)
    header_facet = header.wire.source_metadata.source_id

    kept_rows: list[JsonValue] = []
    kept_keys: set[tuple[str, str]] = set()
    other_facets: list[AlternativeSourceWire] = []
    for item in items:
        served = item.wire.source_metadata.source_id
        if not item.rows:
            continue
        # Rows without a facet ID are kept only from the header payload, so
        # two unidentified facets are never blended.
        if served == header_facet and (served is not None or item is header):
            for obs in item.rows:
                if (obs.place_dcid, obs.date) in kept_keys:
                    continue
                kept_keys.add((obs.place_dcid, obs.date))
                row: JsonValue = [obs.place_dcid, obs.date, obs.value]
                kept_rows.append(row)
            continue
        logger.debug(
            "Dropped %d observation row(s) for %s served by facet %r; the "
            "merged table keeps facet %r.",
            len(item.rows),
            item.place_dcid,
            served,
            header_facet,
        )
        if served is not None:
            other_facets.append(
                AlternativeSourceWire(source_metadata=item.wire.source_metadata)
            )

    ordered_alternatives: list[AlternativeSourceWire] = [
        *header.wire.alternative_sources
    ]
    for item in items:
        if item is not header:
            ordered_alternatives.extend(item.wire.alternative_sources)
    ordered_alternatives.extend(other_facets)

    keep_counts = len(items) == 1
    by_facet: dict[str, AlternativeSourceWire] = {}
    for entry in ordered_alternatives:
        facet = entry.source_metadata.source_id
        if facet and facet != header_facet and facet not in by_facet:
            by_facet[facet] = (
                entry
                if keep_counts
                else AlternativeSourceWire(
                    source_metadata=entry.source_metadata
                )
            )

    return ObservationPayloadWire(
        variable=header.wire.variable,
        data=ColumnarTableWire(columns=_DATA_COLUMNS, rows=tuple(kept_rows)),
        entity_metadata=ColumnarTableWire(
            columns=_ENTITY_COLUMNS, rows=tuple(entity_rows)
        ),
        source_metadata=header.wire.source_metadata,
        alternative_sources=tuple(by_facet.values()),
    )


def parse_observation_table(
    payload: ObservationPayloadWire | Mapping[str, JsonValue],
    *,
    variable_dcid: str,
    requested_places: Sequence[str] = (),
    parent_place_dcid: str | None = None,
    child_place_type: str | None = None,
    date_range: tuple[str, str] | None = None,
    enrichment: VariableMetadataEnrichment | None = None,
    max_rows: int | None = None,
) -> ObservationTable:
    """Parses an MCP 1.3.x observation payload into an `ObservationTable`.

    Args:
        payload: The decoded JSON object the tool returned, or the result of
            `merge_observation_payloads`.
        variable_dcid: The variable whose observations the payload holds.
        requested_places: The places that were asked for. When given, rows
            for other places are dropped. When empty, the universe is the
            sorted distinct places that still have a row after `date_range`
            and `max_rows` are applied, so it is empty when no row remains.
        parent_place_dcid: The parent place of a child-place cohort.
        child_place_type: The child place type of a child-place cohort.
        date_range: Inclusive `(start, end)` bounds applied to the rows
            before `max_rows`, as `is_within_date_range` compares them.
        enrichment: Metadata read by `get_variable_metadata_enrichment`,
            applied over the payload's inline fields by
            `apply_variable_metadata`.
        max_rows: When set, at most this many rows are kept, each place's
            most recent first (see `_truncate`), and the table is marked
            truncated.

    Returns:
        The parsed `ObservationTable`. An empty `data` dict, a `data` dict
        without `rows`, and a missing `data` key all parse as a table with no
        rows.

    Raises:
        ObservationPayloadError: If `payload` lacks the `variable` block, has
            a structural key of the wrong type, has a variable DCID or served
            facet ID that is not a valid identifier, has a `data` table with
            rows but without the `observationAbout`, `date`, or `value`
            column, or names a variable other than `variable_dcid`.
        ValueError: If `variable_dcid` or any entry in `requested_places` is
            not a valid DCID, if a `date_range` bound is not a `YYYY`,
            `YYYY-MM`, or `YYYY-MM-DD` date, if the `date_range` start falls
            after its end, or if `max_rows` is below 1. The arguments are
            checked before the payload, so an invalid argument is never
            reported as a payload error.
        TypeError: If `requested_places` is a single string.
    """
    if not is_valid_dcid(variable_dcid):
        raise ValueError(f"The variable {variable_dcid!r} is not a valid DCID.")
    if isinstance(requested_places, str):
        raise TypeError(
            f"requested_places for {variable_dcid} must be a sequence of "
            "DCIDs, not a string."
        )
    if max_rows is not None and max_rows < 1:
        raise ValueError(
            f"max_rows for {variable_dcid} must be at least 1, not {max_rows}."
        )
    for place in requested_places:
        if not is_valid_dcid(place):
            raise ValueError(
                f"The requested place {place!r} for {variable_dcid} is not "
                "a valid DCID."
            )
    if date_range is not None:
        for bound in date_range:
            if not is_valid_observation_date(bound):
                raise ValueError(
                    f"The date_range bound {bound!r} for {variable_dcid} is "
                    "not a year, a year and month, or a full date."
                )
        if is_inverted_date_range(*date_range):
            raise ValueError(
                f"The date_range {date_range!r} for {variable_dcid} starts "
                "after it ends."
            )

    wire = _validate_payload(payload, variable_dcid)
    if wire.variable.dcid != variable_dcid:
        raise ObservationPayloadError(
            f"The observation payload for {variable_dcid} describes a "
            f"different variable, {wire.variable.dcid!r}."
        )
    names, _ = _read_entity_metadata(wire.entity_metadata)
    observations = _read_observations(wire.data, variable_dcid)
    if requested_places:
        requested = set(requested_places)
        read_count = len(observations)
        observations = [
            observation
            for observation in observations
            if observation.place_dcid in requested
        ]
        if len(observations) < read_count:
            logger.debug(
                "Dropped %d observation row(s) for unrequested places of %s.",
                read_count - len(observations),
                variable_dcid,
            )
    facet_id = wire.source_metadata.source_id

    if date_range is not None:
        start, end = date_range
        observations = [
            observation
            for observation in observations
            if is_within_date_range(observation.date, start, end)
        ]
    rows_before_truncation = len(observations)
    places_before_truncation = {
        observation.place_dcid for observation in observations
    }
    observations, truncated = _truncate(observations, max_rows)
    observations.sort(key=lambda item: (item.place_dcid, item.date))

    # Without requested places, the universe is the places whose rows were
    # kept, so a cohort cut by `date_range` or `max_rows` is evaluated
    # against the places it still contains. Every kept row's place is in the
    # universe either way.
    universe = (
        tuple(dict.fromkeys(requested_places))
        if requested_places
        else tuple(sorted({item.place_dcid for item in observations}))
    )
    place_names = {
        dcid: clean_display_name(names.get(dcid), dcid) for dcid in universe
    }
    rows = tuple(
        ObservationRow(
            place_dcid=observation.place_dcid,
            place_name=place_names[observation.place_dcid],
            date=observation.date,
            value=observation.value,
            facet_id=facet_id,
        )
        for observation in observations
    )

    inline_source = get_source_from_observation_metadata(
        wire.source_metadata.model_dump(by_alias=True, exclude_none=True)
    )

    table = ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=clean_display_name(wire.variable.name, variable_dcid),
        unit=wire.source_metadata.unit,
        scaling_factor=wire.source_metadata.scaling_factor,
        provenance=Provenance(
            sources=(inline_source,) if inline_source is not None else (),
            facet_ids=(facet_id,) if facet_id is not None else (),
        ),
        rows=rows,
        requested_places=universe,
        place_names=place_names,
        measurement_method=wire.source_metadata.measurement_method,
        observation_period=wire.source_metadata.observation_period,
        facet_id=facet_id,
        source=inline_source,
        alternative_sources=_normalize_alternative_sources(
            wire.alternative_sources
        ),
        parent_place_dcid=parent_place_dcid,
        child_place_type=child_place_type,
        truncated=truncated,
        total_rows_before_truncation=(
            rows_before_truncation if truncated else None
        ),
        total_places_before_truncation=(
            len(places_before_truncation) if truncated else None
        ),
    )
    return apply_variable_metadata(table, enrichment)


def apply_variable_metadata(
    table: ObservationTable, enrichment: VariableMetadataEnrichment | None
) -> ObservationTable:
    """Returns `table` with the metadata of its variable and facet applied.

    Facet-level metadata overrides `source`, `unit`, `scaling_factor`,
    `measurement_method`, and `observation_period`; variable-level metadata
    overrides `variable_name` and supplies `unit` when neither the facet nor
    the inline payload declared one. In `provenance.sources`, only the entry
    equal to the old `table.source` is replaced; other sources are kept.

    Args:
        table: The table to update.
        enrichment: The metadata index, or `None` when none was recorded.

    Returns:
        The updated table, or `table` itself when `enrichment` is `None`.
    """
    if enrichment is None:
        return table

    unit = table.unit
    scaling_factor = table.scaling_factor
    measurement_method = table.measurement_method
    observation_period = table.observation_period
    source = table.source
    variable_name = table.variable_name
    facet_updated_unit = False

    facet_meta = (
        enrichment.facet(table.variable_dcid, table.facet_id)
        if table.facet_id is not None
        else None
    )
    if facet_meta is not None:
        if facet_meta.unit is not None:
            unit = facet_meta.unit
            facet_updated_unit = True
        if facet_meta.scaling_factor is not None:
            scaling_factor = facet_meta.scaling_factor
        if facet_meta.measurement_method is not None:
            measurement_method = facet_meta.measurement_method
        if facet_meta.observation_period is not None:
            observation_period = facet_meta.observation_period
        if facet_meta.provenance is not None:
            source = facet_meta.provenance

    variable_meta = enrichment.variables.get(table.variable_dcid)
    if variable_meta is not None:
        if variable_meta.variable_name is not None:
            variable_name = clean_display_name(
                variable_meta.variable_name, table.variable_dcid
            )
        if (
            not facet_updated_unit
            and table.unit is None
            and variable_meta.unit is not None
        ):
            unit = variable_meta.unit

    provenance = replace(
        table.provenance,
        sources=_replace_source(table.provenance.sources, table.source, source),
    )
    return replace(
        table,
        variable_name=variable_name,
        unit=unit,
        scaling_factor=scaling_factor,
        measurement_method=measurement_method,
        observation_period=observation_period,
        source=source,
        provenance=provenance,
    )


def _replace_source(
    sources: tuple[Source, ...], old: Source | None, new: Source | None
) -> tuple[Source, ...]:
    """Returns `sources` with `old` replaced by `new`, keeping other entries.

    When `old` is absent from `sources`, `new` is placed first. Duplicates
    keep their first position.
    """
    if new is None or new == old:
        return sources
    if old is not None and old in sources:
        replaced = tuple(new if item == old else item for item in sources)
    else:
        replaced = (new, *sources)
    return tuple(dict.fromkeys(replaced))

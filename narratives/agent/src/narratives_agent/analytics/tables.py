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
"""Observation table domain types and identifier/date validators.

Defines the immutable `ObservationRow` and `ObservationTable` records that
every analytics script consumes, together with the display-name sanitizer and
DCID, observation-date, and date-range validators shared across the domain and
MCP adapter layers.
"""

import re
import unicodedata
from dataclasses import dataclass

from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
)

__all__ = [
    "MAX_DCID_CHARS",
    "MAX_NAME_CHARS",
    "ObservationRow",
    "ObservationTable",
    "clean_display_name",
    "is_inverted_date_range",
    "is_valid_dcid",
    "is_valid_observation_date",
    "is_within_date_range",
]

# Validated DCIDs and sanitized display names are capped at these lengths.
MAX_DCID_CHARS = 256
MAX_NAME_CHARS = 200

# A DCID is non-empty printable ASCII without whitespace or control characters.
_DCID_PATTERN = re.compile(r"^[!-~]+$")
# Observation dates must be formatted as YYYY, YYYY-MM, or YYYY-MM-DD.
_DATE_PATTERN = re.compile(r"^[0-9]{4}(-[0-9]{2}){0,2}$")
# Display-name sanitization strips Unicode control (`Cc`) and format (`Cf`)
# characters such as C1 controls, bidirectional overrides, and zero-width
# spaces. Whitespace characters (such as newlines and tabs) are preserved
# during filtering so `str.split()` can collapse them into single spaces.
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf"})
# Zero-width non-joiner (U+200C) and zero-width joiner (U+200D) are format
# characters required for word formation in Persian and several Indic scripts,
# so sanitization preserves them.
_KEPT_FORMAT_CHARACTERS = frozenset({"\u200c", "\u200d"})


@dataclass(frozen=True)
class ObservationRow:
    """A single observation recording a numeric value for a place on a date.

    `value` is always finite: `parse_observation_table` drops values that are
    not, so the analytical scripts do not check for `NaN` or infinity.
    """

    place_dcid: str
    place_name: str
    date: str
    value: float
    facet_id: str | None = None


@dataclass(frozen=True)
class ObservationTable:
    """Observations for a single statistical variable from one chosen facet.

    Attributes:
        variable_dcid: DCID of the statistical variable measured by the rows.
        variable_name: Human-readable variable name, falling back to
            `variable_dcid` when no display name is available.
        unit: Measurement unit for the observation values, if reported.
        scaling_factor: Numeric scaling factor for the values, if reported.
        provenance: Source citations, facet IDs, and methodology for the table.
        rows: Observation rows sorted by `place_dcid` and then `date`.
        requested_places: Target place DCIDs in request order, used as the
            denominator when computing cohort coverage.
        place_names: Mapping from place DCID to display name (falling back to
            the DCID) for all requested places and places present in the data.
        measurement_method: Measurement method of the chosen facet, if
            reported.
        observation_period: ISO-8601 observation period of the chosen facet,
            if reported.
        facet_id: Identifier of the facet from which the rows were selected,
            if reported.
        source: Citation record for the chosen facet's data source, if known.
        alternative_sources: Other facets reported by the MCP server for the
            same variable.
        parent_place_dcid: Parent place DCID when the table was fetched for a
            child-place cohort (for example, all counties in a state).
        child_place_type: Child place type when the table was fetched for a
            child-place cohort (for example, `"County"`).
    """

    variable_dcid: str
    variable_name: str
    unit: str | None
    scaling_factor: float | None
    provenance: Provenance
    rows: tuple[ObservationRow, ...]
    requested_places: tuple[str, ...]
    place_names: dict[str, str]
    measurement_method: str | None = None
    observation_period: str | None = None
    facet_id: str | None = None
    source: Source | None = None
    alternative_sources: tuple[AlternativeSource, ...] = ()
    parent_place_dcid: str | None = None
    child_place_type: str | None = None

    @property
    def places_with_data(self) -> tuple[str, ...]:
        """Returns the sorted, distinct place DCIDs that have data."""
        return tuple(sorted({row.place_dcid for row in self.rows}))


def _sanitize_line(text: str) -> str:
    """Strips invisible characters, collapses whitespace, and caps length."""
    visible = "".join(
        character
        for character in text
        if character.isspace()
        or character in _KEPT_FORMAT_CHARACTERS
        or unicodedata.category(character) not in _INVISIBLE_CATEGORIES
    )
    return " ".join(visible.split())[:MAX_NAME_CHARS].rstrip()


def clean_display_name(value: object, fallback: str) -> str:
    """Sanitizes `value` into a single-line display name, or uses `fallback`.

    Strips control and invisible format characters, collapses runs of
    whitespace into a single space, and truncates the result to
    `MAX_NAME_CHARS` so it is safe to embed in prompts and signed state slots.
    If `value` is not a string or is empty after sanitization, returns the
    sanitized `fallback` instead.
    """
    if isinstance(value, str):
        cleaned = _sanitize_line(value)
        if cleaned:
            return cleaned
    return _sanitize_line(fallback)


def is_valid_dcid(dcid: str) -> bool:
    """Returns whether `dcid` is printable ASCII up to `MAX_DCID_CHARS`."""
    return (
        len(dcid) <= MAX_DCID_CHARS
        and _DCID_PATTERN.fullmatch(dcid) is not None
    )


def is_valid_observation_date(date: str) -> bool:
    """Returns whether `date` has the format `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`.

    Checks only the digit pattern; month and day numbers are not validated as
    calendar dates.
    """
    return _DATE_PATTERN.fullmatch(date) is not None


def is_inverted_date_range(start: str, end: str) -> bool:
    """Returns whether `start` comes after `end`.

    When `start` and `end` have different date precisions (year, month, or
    day), they are compared using their shared prefix length. For example,
    `("2020-07", "2020")` is not inverted because `"2020-07"` falls within the
    year `"2020"`, whereas `("2020-07", "2020-03")` is inverted. Both `start`
    and `end` must be valid observation dates (`is_valid_observation_date`).
    """
    width = min(len(start), len(end))
    return start[:width] > end[:width]


def is_within_date_range(date: str, start: str | None, end: str | None) -> bool:
    """Returns whether `date` falls within the inclusive `[start, end]` range.

    When `date` and a bound have different precisions (year, month, or day),
    they are compared using their shared prefix length. For example, an end
    bound of `"2023"` includes `"2023-07-31"`, a start bound of `"2015-01"`
    includes the year-only date `"2015"`, and a start bound of `"2015-07"`
    excludes `"2015-03"`. A bound of `None` leaves that end of the range
    unbounded. `date` and any non-`None` bounds must be valid observation
    dates (`is_valid_observation_date`).
    """
    if start is not None:
        width = min(len(date), len(start))
        if date[:width] < start[:width]:
            return False
    if end is not None:
        width = min(len(date), len(end))
        if date[:width] > end[:width]:
            return False
    return True

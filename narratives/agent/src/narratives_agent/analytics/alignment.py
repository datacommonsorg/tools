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
"""Aligns a cohort to one reference date and checks unit compatibility.

`align_cohort` selects the most recent date on which enough places report a
value and returns one row per contributing place with coverage metadata.
`find_unit_mismatch` reports a unit or scaling conflict across tables and
cohorts before they are combined or compared.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from narratives_agent.analytics.digest import (
    AlignmentRefusalReason,
    CoverageReport,
    UnitMismatchReason,
    conjugate_have,
    format_percent,
    format_scaling_factor,
)
from narratives_agent.analytics.provenance import Provenance
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
    is_valid_observation_date,
)

__all__ = [
    "DEFAULT_MIN_COVERAGE",
    "AlignedCohort",
    "AlignmentRefusal",
    "UnitMismatch",
    "align_cohort",
    "find_unit_mismatch",
    "select_reference_date",
    "validate_alignment_parameters",
]

# At least this share of the cohort's places must report on the reference
# date.
DEFAULT_MIN_COVERAGE: float = 0.5
# A scaling factor that is absent means the values are not scaled.
_UNSCALED = 1.0


@dataclass(frozen=True)
class AlignedCohort:
    """One value per place, all observed on `reference_date`.

    Attributes:
        variable_dcid: The variable the values measure.
        variable_name: The variable's display name.
        reference_date: The single date every row was observed on.
        unit: The unit of the values, when known.
        scaling_factor: The scaling factor of the values, when known.
        provenance: The table's provenance.
        rows: One row per contributing place, sorted by place DCID; never
            empty, because a table with no contributing place is refused.
        place_names: Display names for the table's places.
        coverage: How many of the cohort's places contributed.
        caveats: Qualifications of the alignment to state with its values.
    """

    variable_dcid: str
    variable_name: str
    reference_date: str
    unit: str | None
    scaling_factor: float | None
    provenance: Provenance
    rows: tuple[ObservationRow, ...]
    place_names: dict[str, str]
    coverage: CoverageReport
    caveats: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentRefusal:
    """Why a table could not be aligned, with the coverage that was reached.

    Attributes:
        variable_dcid: The variable the table measures.
        reason: `no_observations` when no target place has a row;
            `insufficient_coverage` when the given `target_date`, or every
            date when none is given, falls below the minimum coverage.
        coverage: The coverage of the given `target_date`, or of the best
            date available when none is given, so the refusal can state the
            figure.
        message: A plain-English statement of the refusal.
    """

    variable_dcid: str
    reason: AlignmentRefusalReason
    coverage: CoverageReport
    message: str


@dataclass(frozen=True)
class UnitMismatch:
    """Why tables or cohorts cannot be combined or compared.

    Attributes:
        reason: `unit_mismatch` when the units differ, `scaling_mismatch`
            when the units agree and the scaling factors differ.
        message: A plain-English statement naming each item's unit or
            scaling factor.
    """

    reason: UnitMismatchReason
    message: str


def _resolve_target_places(table: ObservationTable) -> tuple[str, ...]:
    """Returns the requested places, or the observed places when none are."""
    if table.requested_places:
        return tuple(dict.fromkeys(table.requested_places))
    return table.places_with_data


def _format_variable_label(table: ObservationTable) -> str:
    """Returns the variable as `name (dcid)` for refusal messages."""
    return f"{table.variable_name} ({table.variable_dcid})"


def _has_mixed_vintages(
    rows: tuple[ObservationRow, ...], target_places: frozenset[str]
) -> bool:
    """Returns whether the places' latest observation dates differ."""
    latest: dict[str, str] = {}
    for row in rows:
        if row.place_dcid in target_places and row.date > latest.get(
            row.place_dcid, ""
        ):
            latest[row.place_dcid] = row.date
    return len(set(latest.values())) > 1


def select_reference_date(
    counts_by_date: Mapping[str, int],
    cohort_size: int,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> str:
    """Picks the most recent date with adequate coverage.

    When no date in `counts_by_date` reaches `min_coverage` of
    `cohort_size`, returns the most recent date with the largest place
    count so a caller can use or report the best available date.

    Args:
        counts_by_date: Place counts keyed by observation date; must not
            be empty.
        cohort_size: Total number of places in the cohort; must be at
            least 1.
        min_coverage: Minimum share of `cohort_size` required, from 0 to 1.

    Returns:
        The selected observation date string.

    Raises:
        ValueError: If `counts_by_date` is empty or `cohort_size` is below 1.
    """
    if not counts_by_date:
        raise ValueError("counts_by_date must not be empty.")
    if cohort_size < 1:
        raise ValueError(
            f"The cohort size must be at least 1, not {cohort_size}."
        )
    qualifying = [
        date
        for date, count in counts_by_date.items()
        if count / cohort_size >= min_coverage
    ]
    if qualifying:
        return max(qualifying)
    return max(counts_by_date, key=lambda date: (counts_by_date[date], date))


def validate_alignment_parameters(
    *,
    target_date: str | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> str | None:
    """Checks `target_date` and `min_coverage`, returning an error or None.

    Args:
        target_date: An optional date string to validate with
            `is_valid_observation_date`.
        min_coverage: A coverage threshold that must lie in `[0.0, 1.0]`.

    Returns:
        None when both arguments are valid, or a plain-English error
        sentence naming the first invalid argument.
    """
    if target_date is not None and not is_valid_observation_date(target_date):
        return (
            f"The target date {target_date!r} is not a year, a year and "
            "month, or a full date."
        )
    if not 0.0 <= min_coverage <= 1.0:
        return (
            f"The minimum coverage must be between 0 and 1, not {min_coverage}."
        )
    return None


def _build_insufficient_coverage_message(
    table: ObservationTable,
    coverage: CoverageReport,
    reference_date: str,
    observed_dates: list[str],
    min_coverage: float,
) -> str:
    """Returns the message of an `insufficient_coverage` refusal."""
    label = _format_variable_label(table)
    if coverage.contributing_places == 0:
        # Dates match as exact strings, so a `target_date` of another
        # precision matches no row even when the period has values. A date
        # that overlaps the target period at another precision is the best
        # example; otherwise any date, when no row shares the precision.
        overlapping = [
            date
            for date in observed_dates
            if date.startswith(reference_date)
            or reference_date.startswith(date)
        ]
        precisions = {len(date) for date in observed_dates}
        if overlapping or len(reference_date) not in precisions:
            example = max(overlapping or observed_dates)
            return (
                f"The target date {reference_date} does not match the "
                f"precision of the {label} dates, such as {example}, so no "
                "place can be aligned to it."
            )
        # No threshold is cited, because no value exists to compare.
        return f"No place has a value for {label} ({coverage.describe()})."
    verb = conjugate_have(coverage.contributing_places)
    return (
        f"Only {coverage.describe()} {verb} a value for {label}, below the "
        f"required {format_percent(min_coverage)} coverage."
    )


def align_cohort(
    table: ObservationTable,
    *,
    target_date: str | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> AlignedCohort | AlignmentRefusal:
    """Aligns `table` to one reference date with adequate coverage.

    The target places are `table.requested_places` when the table records
    them, and otherwise the places that have rows. When `target_date` is
    given, that date is used as it is; otherwise the most recent date on
    which at least `min_coverage` of the cohort has a value is selected. A
    place with several rows on the selected date contributes its last row in
    table order. Dates are matched as exact strings and ordered as strings,
    which for ISO dates is chronological by the start of each period. Rows
    at different precisions (`2023` and `2023-07-31`) or on different days
    are therefore different reference dates: a place counts only on the
    date it reports, and is missing on every other. A `target_date` at a
    precision that no row uses is refused with a message that names the
    mismatch.

    Args:
        table: The table to align.
        target_date: A date to align to instead of selecting one.
        min_coverage: The minimum share of the cohort that must have a value
            on the reference date, from 0 to 1.

    Returns:
        The aligned cohort, or a refusal carrying the coverage reached.

    Raises:
        ValueError: If `min_coverage` is outside 0 to 1, or if `target_date`
            is not a `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` date.
    """
    parameter_error = validate_alignment_parameters(
        target_date=target_date, min_coverage=min_coverage
    )
    if parameter_error is not None:
        raise ValueError(parameter_error)
    target_places = _resolve_target_places(table)
    target_place_set = frozenset(target_places)
    by_date: dict[str, dict[str, ObservationRow]] = {}
    for row in table.rows:
        if row.place_dcid in target_place_set:
            by_date.setdefault(row.date, {})[row.place_dcid] = row

    if not by_date:
        coverage = CoverageReport(
            contributing_places=0,
            requested_places=len(target_places),
            coverage_ratio=0.0,
            reference_date=target_date,
            missing_places=target_places,
        )
        message = f"{_format_variable_label(table)} has no observations"
        if target_places:
            message += (
                f" for any of the requested places ({coverage.describe()})"
            )
        return AlignmentRefusal(
            variable_dcid=table.variable_dcid,
            reason="no_observations",
            coverage=coverage,
            message=f"{message}.",
        )

    cohort_size = len(target_places)
    mixed_vintages = _has_mixed_vintages(table.rows, target_place_set)
    reference_date = (
        target_date
        if target_date is not None
        else select_reference_date(
            {date: len(rows) for date, rows in by_date.items()},
            cohort_size,
            min_coverage,
        )
    )
    rows_at_date = by_date.get(reference_date, {})
    contributing = len(rows_at_date)
    coverage = CoverageReport(
        contributing_places=contributing,
        requested_places=cohort_size,
        coverage_ratio=contributing / cohort_size,
        reference_date=reference_date,
        missing_places=tuple(
            place for place in target_places if place not in rows_at_date
        ),
        mixed_vintages=mixed_vintages,
    )

    if contributing == 0 or coverage.coverage_ratio < min_coverage:
        return AlignmentRefusal(
            variable_dcid=table.variable_dcid,
            reason="insufficient_coverage",
            coverage=coverage,
            message=_build_insufficient_coverage_message(
                table, coverage, reference_date, list(by_date), min_coverage
            ),
        )

    return AlignedCohort(
        variable_dcid=table.variable_dcid,
        variable_name=table.variable_name,
        reference_date=reference_date,
        unit=table.unit,
        scaling_factor=table.scaling_factor,
        provenance=table.provenance,
        rows=tuple(rows_at_date[place] for place in sorted(rows_at_date)),
        place_names=dict(table.place_names),
        coverage=coverage,
        caveats=_alignment_caveats(
            table,
            coverage,
            reference_date,
            explicit_date=target_date is not None,
        ),
    )


def _alignment_caveats(
    table: ObservationTable,
    coverage: CoverageReport,
    reference_date: str,
    *,
    explicit_date: bool,
) -> tuple[str, ...]:
    """Returns the qualifications of an aligned cohort, in a fixed order.

    The caveats cover mixed vintages and places missing on `reference_date`.
    """
    caveats: list[str] = []
    if coverage.mixed_vintages:
        if explicit_date:
            caveats.append(
                "The places report different latest observation dates; "
                f"every value is aligned to the requested date "
                f"{reference_date}."
            )
        else:
            caveats.append(
                "The places report different latest observation dates, so "
                f"every value is aligned to {reference_date}."
            )
    if coverage.contributing_places < coverage.requested_places:
        caveats.append(
            f"{coverage.describe()} reported a value for {table.variable_name}."
        )
    return tuple(caveats)


def _normalize_unit(unit: str | None) -> str | None:
    """Returns the unit folded for comparison, or None when unset."""
    if unit is None:
        return None
    folded = unit.strip().casefold()
    return folded or None


def _normalize_scaling(scaling_factor: float | None) -> float:
    """Returns the scaling factor with "absent" read as unscaled."""
    return _UNSCALED if scaling_factor is None else scaling_factor


def find_unit_mismatch(
    *items: ObservationTable | AlignedCohort,
) -> UnitMismatch | None:
    """Reports why tables or cohorts cannot be combined or compared.

    Units are compared after trimming and case folding, with an empty unit
    read as unset; an unset unit conflicts with a set one, because a value
    of unknown unit cannot be added to a value in dollars. Scaling factors
    are compared with an absent factor read as `1.0`.

    Args:
        *items: The tables and cohorts to combine.

    Returns:
        None when every item is compatible, otherwise the mismatch, with a
        unit conflict reported before a scaling conflict. With fewer than
        two items, returns None.
    """
    units = {_normalize_unit(item.unit) for item in items}
    if len(units) > 1:
        reported = "; ".join(
            f"{item.variable_name} ({item.variable_dcid}) reports "
            f"{(item.unit or '').strip() or 'no unit'}"
            for item in items
        )
        return UnitMismatch("unit_mismatch", f"Units differ: {reported}.")
    scalings = {_normalize_scaling(item.scaling_factor) for item in items}
    if len(scalings) > 1:
        reported = "; ".join(
            f"{item.variable_name} ({item.variable_dcid}) reports a scaling "
            f"factor of "
            f"{format_scaling_factor(_normalize_scaling(item.scaling_factor))}"
            for item in items
        )
        return UnitMismatch(
            "scaling_mismatch", f"Scaling factors differ: {reported}."
        )
    return None

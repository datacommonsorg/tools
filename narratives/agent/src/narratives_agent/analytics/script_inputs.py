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
"""Checks the inputs the analytical scripts share and builds their refusals.

Holds the place-list check, the refused-result builders, the resolution of a
cohort-or-table argument into an aligned cohort, and the caveat for focal
places missing from a cohort, so every script applies them identically.
"""

from collections.abc import Sequence
from enum import Enum

from narratives_agent.analytics.alignment import (
    AlignedCohort,
    AlignmentRefusal,
    align_cohort,
    validate_alignment_parameters,
)
from narratives_agent.analytics.digest import (
    CoverageReport,
    RefusalReason,
    RefusedScriptResult,
    conjugate_have,
    format_place_names,
)
from narratives_agent.analytics.metrics import ScriptName
from narratives_agent.analytics.provenance import merge_provenance
from narratives_agent.analytics.tables import ObservationTable, is_valid_dcid

__all__ = [
    "CohortInput",
    "build_invalid_parameters_refusal",
    "build_refusal",
    "describe_missing_focal_places",
    "resolve_aligned_cohort",
    "resolve_target_places",
    "validate_place_dcids",
]

type CohortInput = AlignedCohort | ObservationTable


class _Default(Enum):
    FROM_FIRST_INPUT = "from_first_input"


_FROM_FIRST_INPUT = _Default.FROM_FIRST_INPUT


def _normalize_inputs(
    cohort_or_table: CohortInput | Sequence[CohortInput],
) -> tuple[CohortInput, ...]:
    """Returns one or more script inputs as a tuple."""
    if isinstance(cohort_or_table, (AlignedCohort, ObservationTable)):
        return (cohort_or_table,)
    return tuple(cohort_or_table)


def resolve_target_places(cohort_or_table: CohortInput) -> tuple[str, ...]:
    """Returns the target places of a table or an aligned cohort.

    Args:
        cohort_or_table: The table or aligned cohort to inspect.

    Returns:
        For a table, its deduplicated `requested_places` when present and
        its `places_with_data` otherwise; for an aligned cohort, its
        contributing places followed by its missing places, deduplicated in
        order.
    """
    if isinstance(cohort_or_table, ObservationTable):
        if cohort_or_table.requested_places:
            return tuple(dict.fromkeys(cohort_or_table.requested_places))
        return cohort_or_table.places_with_data
    return tuple(
        dict.fromkeys(
            (
                *(row.place_dcid for row in cohort_or_table.rows),
                *cohort_or_table.coverage.missing_places,
            )
        )
    )


def validate_place_dcids(
    places: Sequence[str], *, parameter_name: str
) -> str | None:
    """Returns why a list of place DCIDs is invalid, or None when it is valid.

    Args:
        places: The places passed to a script.
        parameter_name: The script parameter that holds `places`, named in
            the message.

    Returns:
        A message for a bare string, which the `Sequence[str]` type does not
        exclude, or for the first entry that is not a valid DCID; None
        otherwise. An invalid entry is identified by its position, not
        quoted, so a malformed string never reaches a caveat or the prompt.
    """
    if isinstance(places, str):
        return (
            f"{parameter_name} must be a sequence of DCIDs, not the string "
            f"{places!r}."
        )
    invalid = next(
        (
            position
            for position, place in enumerate(places, start=1)
            if not is_valid_dcid(place)
        ),
        None,
    )
    if invalid is not None:
        return (
            f"{parameter_name} must hold DCIDs, but entry {invalid} of "
            f"{len(places)} is not a valid DCID."
        )
    return None


def build_refusal(
    cohort_or_table: CohortInput | Sequence[CohortInput],
    *,
    script: ScriptName,
    step_id: str,
    reason: RefusalReason,
    coverage: CoverageReport | None,
    caveat: str,
    extra_caveats: Sequence[str] = (),
    unit: str | _Default | None = _FROM_FIRST_INPUT,
    scaling_factor: float | _Default | None = _FROM_FIRST_INPUT,
) -> RefusedScriptResult:
    """Builds a refused result for one or more inputs with `caveat`.

    Args:
        cohort_or_table: The cohort, table, or sequence of cohorts and
            tables the script was given; supplies the variables, default
            unit, default scaling factor, and provenance.
        script: Name of the refusing script.
        step_id: Identifier of the analysis step.
        reason: Why the script refused.
        coverage: The cohort coverage when known, otherwise None.
        caveat: The reason for the refusal, stated for the prompt.
        extra_caveats: Additional caveats (such as skipped pairs) appended
            after `caveat`.
        unit: Resolved unit of the output, or `_FROM_FIRST_INPUT` to use
            the first input's unit.
        scaling_factor: Resolved scaling factor of the output, or
            `_FROM_FIRST_INPUT` to use the first input's scaling factor.

    Returns:
        A `RefusedScriptResult`. Any refused aligned cohort keeps its own
        caveats, which qualify its coverage, ahead of `caveat`.
    """
    inputs = _normalize_inputs(cohort_or_table)
    cohort_caveats = tuple(
        dict.fromkeys(
            cohort_caveat
            for item in inputs
            if isinstance(item, AlignedCohort)
            for cohort_caveat in item.caveats
        )
    )
    provenance = (
        inputs[0].provenance
        if len(inputs) == 1
        else merge_provenance(*(item.provenance for item in inputs))
    )
    variable_names: dict[str, str] = {}
    for item in inputs:
        variable_names.setdefault(item.variable_dcid, item.variable_name)
    resolved_unit = (
        (inputs[0].unit if inputs else None)
        if isinstance(unit, _Default)
        else unit
    )
    resolved_scaling_factor = (
        (inputs[0].scaling_factor if inputs else None)
        if isinstance(scaling_factor, _Default)
        else scaling_factor
    )
    return RefusedScriptResult(
        step_id=step_id,
        script=script,
        refusal_reason=reason,
        variables=tuple(variable_names),
        variable_names=variable_names,
        unit=resolved_unit,
        scaling_factor=resolved_scaling_factor,
        coverage=coverage,
        provenance=provenance,
        caveats=(*cohort_caveats, caveat, *extra_caveats),
    )


def build_invalid_parameters_refusal(
    cohort_or_table: CohortInput | Sequence[CohortInput],
    *,
    script: ScriptName,
    step_id: str,
    caveat: str,
    unit: str | _Default | None = _FROM_FIRST_INPUT,
    scaling_factor: float | _Default | None = _FROM_FIRST_INPUT,
) -> RefusedScriptResult:
    """Builds an `invalid_parameters` refusal for a script's arguments.

    Args:
        cohort_or_table: The cohort, table, or sequence of cohorts and
            tables the script was given.
        script: Name of the refusing script.
        step_id: Identifier of the analysis step.
        caveat: Why the arguments are invalid, stated for the prompt.
        unit: Resolved unit of the output, or `_FROM_FIRST_INPUT` to use
            the first input's unit.
        scaling_factor: Resolved scaling factor of the output, or
            `_FROM_FIRST_INPUT` to use the first input's scaling factor.

    Returns:
        A `RefusedScriptResult` with reason `invalid_parameters`, carrying
        the coverage when the aligned inputs agree on one coverage report,
        and no coverage when no input is aligned or aligned inputs carry
        different coverage reports.
    """
    inputs = _normalize_inputs(cohort_or_table)
    aligned_coverages = {
        item.coverage for item in inputs if isinstance(item, AlignedCohort)
    }
    return build_refusal(
        inputs,
        script=script,
        step_id=step_id,
        reason="invalid_parameters",
        coverage=(
            next(iter(aligned_coverages))
            if len(aligned_coverages) == 1
            else None
        ),
        caveat=caveat,
        unit=unit,
        scaling_factor=scaling_factor,
    )


def resolve_aligned_cohort(
    cohort_or_table: AlignedCohort | ObservationTable,
    *,
    script: ScriptName,
    step_id: str,
    target_date: str | None,
    min_coverage: float,
    operation: str,
    should_check_min_coverage: bool = False,
) -> AlignedCohort | RefusedScriptResult:
    """Returns the aligned cohort a script analyzes, or the script's refusal.

    Args:
        cohort_or_table: An aligned cohort, used as given, or a table,
            aligned with `target_date` and `min_coverage`.
        script: Name of the calling script, for a refusal.
        step_id: Identifier of the analysis step, for a refusal.
        target_date: The requested reference date, or None for the latest.
        min_coverage: The alignment coverage threshold for a table.
        operation: Past participle naming what the script does with the
            cohort (for example, `"ranked"`), used in the caveat for a
            `target_date` other than an aligned cohort's reference date.
        should_check_min_coverage: Whether `min_coverage` is checked for an
            aligned cohort, for a script that uses it beyond alignment. It
            is always checked for a table.

    Returns:
        The aligned cohort, or a refusal with `invalid_parameters` when
        `target_date` is not a valid date or differs from an aligned
        cohort's reference date, or `min_coverage` is checked and outside
        `[0.0, 1.0]`; or with the alignment's reason when the table cannot
        be aligned. A refusal of an aligned cohort carries its coverage.
    """
    if isinstance(cohort_or_table, AlignedCohort):
        error = (
            validate_alignment_parameters(
                target_date=target_date, min_coverage=min_coverage
            )
            if should_check_min_coverage
            else validate_alignment_parameters(target_date=target_date)
        )
        if error is None and target_date not in (
            None,
            cohort_or_table.reference_date,
        ):
            error = (
                f"The cohort is aligned to {cohort_or_table.reference_date}, "
                f"so it cannot be {operation} on the target date "
                f"{target_date}."
            )
        if error is not None:
            return build_invalid_parameters_refusal(
                cohort_or_table, script=script, step_id=step_id, caveat=error
            )
        return cohort_or_table
    error = validate_alignment_parameters(
        target_date=target_date, min_coverage=min_coverage
    )
    if error is not None:
        return build_invalid_parameters_refusal(
            cohort_or_table, script=script, step_id=step_id, caveat=error
        )
    aligned = align_cohort(
        cohort_or_table, target_date=target_date, min_coverage=min_coverage
    )
    if isinstance(aligned, AlignmentRefusal):
        return build_refusal(
            cohort_or_table,
            script=script,
            step_id=step_id,
            reason=aligned.reason,
            coverage=aligned.coverage,
            caveat=aligned.message,
        )
    return aligned


def describe_missing_focal_places(
    aligned: AlignedCohort,
    missing_focal: Sequence[str],
    *,
    cohort_label: str,
    unavailable_figure: str,
) -> str:
    """States which focal places have no value in the analyzed cohort.

    Args:
        aligned: The analyzed cohort.
        missing_focal: The focal places with no value in it, in request
            order; the caveat names a few and counts the rest.
        cohort_label: How the caveat refers to the cohort (for example,
            `"ranked cohort"`).
        unavailable_figure: The figure the missing places lack (for example,
            `"rank"`).

    Returns:
        One caveat sentence, ending with a period.
    """
    names = format_place_names(
        [aligned.place_names.get(place, place) for place in missing_focal]
    )
    return (
        f"{names} {conjugate_have(len(missing_focal))} no value for "
        f"{aligned.variable_name} in the {cohort_label} on "
        f"{aligned.reference_date}, so no {unavailable_figure} is available."
    )

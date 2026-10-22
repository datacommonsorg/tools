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
from narratives_agent.analytics.tables import ObservationTable, is_valid_dcid

__all__ = [
    "build_invalid_parameters_refusal",
    "build_refusal",
    "describe_missing_focal_places",
    "resolve_aligned_cohort",
    "validate_place_dcids",
]


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
    cohort_or_table: AlignedCohort | ObservationTable,
    *,
    script: ScriptName,
    step_id: str,
    reason: RefusalReason,
    coverage: CoverageReport | None,
    caveat: str,
) -> RefusedScriptResult:
    """Builds a refused result for one variable with the refusal's caveat.

    Args:
        cohort_or_table: The cohort or table the script was given; supplies
            the variable, unit, scaling factor, and provenance.
        script: Name of the refusing script.
        step_id: Identifier of the analysis step.
        reason: Why the script refused.
        coverage: The cohort coverage when known, otherwise None.
        caveat: The reason for the refusal, stated for the prompt.

    Returns:
        A `RefusedScriptResult`. A refused aligned cohort keeps its own
        caveats, which qualify its coverage, ahead of `caveat`.
    """
    caveats = (
        (*cohort_or_table.caveats, caveat)
        if isinstance(cohort_or_table, AlignedCohort)
        else (caveat,)
    )
    return RefusedScriptResult(
        step_id=step_id,
        script=script,
        refusal_reason=reason,
        variables=(cohort_or_table.variable_dcid,),
        variable_names={
            cohort_or_table.variable_dcid: cohort_or_table.variable_name
        },
        unit=cohort_or_table.unit,
        scaling_factor=cohort_or_table.scaling_factor,
        coverage=coverage,
        provenance=cohort_or_table.provenance,
        caveats=caveats,
    )


def build_invalid_parameters_refusal(
    cohort_or_table: AlignedCohort | ObservationTable,
    *,
    script: ScriptName,
    step_id: str,
    caveat: str,
) -> RefusedScriptResult:
    """Builds an `invalid_parameters` refusal for a script's arguments.

    Args:
        cohort_or_table: The cohort or table the script was given.
        script: Name of the refusing script.
        step_id: Identifier of the analysis step.
        caveat: Why the arguments are invalid, stated for the prompt.

    Returns:
        A `RefusedScriptResult` with reason `invalid_parameters`, carrying
        the coverage of an aligned cohort, which is already known, and no
        coverage for a table, which has not been aligned.
    """
    return build_refusal(
        cohort_or_table,
        script=script,
        step_id=step_id,
        reason="invalid_parameters",
        coverage=(
            cohort_or_table.coverage
            if isinstance(cohort_or_table, AlignedCohort)
            else None
        ),
        caveat=caveat,
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

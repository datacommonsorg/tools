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
"""Tests for the shared script input checks in `analytics.script_inputs`."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

import pytest

from narratives_agent.analytics.alignment import AlignedCohort, align_cohort
from narratives_agent.analytics.digest import (
    CoverageReport,
    RefusedScriptResult,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.script_inputs import (
    build_invalid_parameters_refusal,
    build_refusal,
    collect_variable_provenance,
    describe_missing_focal_places,
    resolve_aligned_cohort,
    resolve_target_places,
    validate_place_dcids,
)
from narratives_agent.analytics.tables import ObservationRow, ObservationTable


@dataclass(frozen=True)
class _SpanningRow:
    """A test-local `CohortRow` holding one place's value over a window."""

    place_dcid: str
    place_name: str
    value: float


@dataclass(frozen=True)
class _SpanningCohort:
    """A test-local `Cohort` whose reference date is a date window."""

    variable_dcid: str
    variable_name: str
    metric_label: str
    reference_date: str
    unit: str | None
    scaling_factor: float | None
    provenance: Provenance
    rows: tuple[_SpanningRow, ...]
    place_names: dict[str, str]
    coverage: CoverageReport
    caveats: tuple[str, ...] = ()


def _build_spanning_cohort() -> _SpanningCohort:
    """Builds the change in population from 2020 to 2024 for two of three."""
    return _SpanningCohort(
        variable_dcid="Count_Person",
        variable_name="Total population",
        metric_label="change in Total population",
        reference_date="2020..2024",
        unit="Person",
        scaling_factor=None,
        provenance=Provenance(sources=(Source(name="s", url="u"),)),
        rows=(_SpanningRow("a", "A", 5.0), _SpanningRow("b", "B", -2.0)),
        place_names={"a": "A", "b": "B", "c": "C"},
        coverage=CoverageReport(
            contributing_places=2,
            requested_places=3,
            coverage_ratio=2 / 3,
            reference_date="2020..2024",
            missing_places=("c",),
        ),
        caveats=("2 of 3 places from 2020 to 2024 reported a change.",),
    )


def _build_table(
    observations: Sequence[tuple[str, str, float]],
    *,
    variable_dcid: str = "Count_Person",
    variable_name: str = "Total population",
    requested_places: Sequence[str] = (),
    source_id: int = 1,
) -> ObservationTable:
    """Builds a table from `(place, date, value)` triples."""
    places = list(
        dict.fromkeys(
            [*requested_places, *(place for place, _, _ in observations)]
        )
    )
    return ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_name,
        unit="Person",
        scaling_factor=None,
        provenance=Provenance(
            sources=(
                Source(
                    name=f"Source {source_id}",
                    url=f"https://source-{source_id}",
                ),
            ),
            facet_ids=(f"f{source_id}",),
        ),
        rows=tuple(
            ObservationRow(place, place.upper(), date, value)
            for place, date, value in observations
        ),
        requested_places=tuple(requested_places),
        place_names={place: place.upper() for place in places},
    )


def _build_aligned_cohort_with_caveats() -> AlignedCohort:
    """Aligns three requested places, one of them stale, to 2022."""
    aligned = align_cohort(
        _build_table(
            [("a", "2022", 1.0), ("b", "2022", 2.0), ("c", "2021", 3.0)],
            requested_places=["a", "b", "c"],
        )
    )
    assert isinstance(aligned, AlignedCohort)
    assert aligned.caveats
    return aligned


def test_resolve_target_places_reads_requested_observed_and_cohort_places() -> (
    None
):
    # Test: `resolve_target_places` on tables and aligned cohorts.
    # Situation: A table with duplicate requested places, a table without
    #   requested places, and an aligned cohort with two contributing places
    #   and one missing place.
    # Expectation: The first returns the requested places deduplicated in
    #   request order; the second returns `places_with_data`; the third
    #   returns the contributing places followed by the missing places.
    with_requested = _build_table(
        [("a", "2022", 1.0)], requested_places=["b", "a", "b"]
    )
    assert resolve_target_places(with_requested) == ("b", "a")
    observed_only = _build_table([("b", "2022", 1.0), ("a", "2022", 2.0)])
    assert resolve_target_places(observed_only) == ("a", "b")
    aligned = _build_aligned_cohort_with_caveats()
    assert resolve_target_places(aligned) == ("a", "b", "c")


def test_validate_place_dcids_rejects_strings_and_invalid_entries() -> None:
    # Test: The place-list check.
    # Situation: A bare string, a list whose second entry holds a space, a
    #   list of valid DCIDs, and an empty list.
    # Expectation: The string is named and quoted; the invalid entry is
    #   identified by position only; valid and empty lists pass.
    assert validate_place_dcids("geoId/06", parameter_name="places") == (
        "places must be a sequence of DCIDs, not the string 'geoId/06'."
    )
    assert validate_place_dcids(
        ["geoId/06", "not a dcid"], parameter_name="focal_places"
    ) == ("focal_places must hold DCIDs, but entry 2 of 2 is not a valid DCID.")
    assert (
        validate_place_dcids(
            ["geoId/06", "country/FRA"], parameter_name="places"
        )
        is None
    )
    assert validate_place_dcids([], parameter_name="places") is None


def test_refusals_keep_an_aligned_cohorts_caveats_and_coverage() -> None:
    # Test: The refused-result builders.
    # Situation: An `invalid_parameters` refusal of a table and of an
    #   aligned cohort with alignment caveats, and a `no_observations`
    #   refusal of a table.
    # Expectation: A table's refusal has no coverage and only its own
    #   caveat; an aligned cohort's carries its coverage and its caveats
    #   ahead of the refusal's; the variable and provenance come from the
    #   input.
    table = _build_table([("a", "2022", 1.0)])
    refused_table = build_invalid_parameters_refusal(
        table, script="rank_cohort", step_id="s2", caveat="Bad."
    )
    assert refused_table.refusal_reason == "invalid_parameters"
    assert refused_table.script == "rank_cohort"
    assert refused_table.step_id == "s2"
    assert refused_table.coverage is None
    assert refused_table.caveats == ("Bad.",)
    assert refused_table.variables == ("Count_Person",)
    assert refused_table.provenance == table.provenance
    aligned = _build_aligned_cohort_with_caveats()
    refused_cohort = build_invalid_parameters_refusal(
        aligned, script="summarize_distribution", step_id="s1", caveat="Bad."
    )
    assert refused_cohort.coverage == aligned.coverage
    assert refused_cohort.caveats == (*aligned.caveats, "Bad.")
    empty = build_refusal(
        table,
        script="analyze_timeseries",
        step_id="s1",
        reason="no_observations",
        coverage=None,
        caveat="None match.",
    )
    assert empty.refusal_reason == "no_observations"
    assert empty.caveats == ("None match.",)


def test_multi_input_refusals_merge_provenance_and_keep_aligned_caveats() -> (
    None
):
    # Test: `build_refusal` and `build_invalid_parameters_refusal` on
    #   sequences of inputs.
    # Situation: An empty sequence; an aligned cohort paired with a second
    #   table; and two aligned cohorts on different reference dates.
    # Expectation: The empty sequence yields empty variables and no unit;
    #   the cohort-plus-table refusal lists both variables, merges their
    #   provenance, carries the single aligned cohort's coverage, and keeps
    #   its caveats ahead of the refusal's; conflicting aligned coverages
    #   leave `coverage` as None while still keeping both cohorts' caveats.
    empty = build_invalid_parameters_refusal(
        (),
        script="compute_composition",
        step_id="s1",
        caveat="At least one component variable is required.",
    )
    assert empty.variables == ()
    assert empty.unit is None
    assert empty.coverage is None
    assert empty.caveats == ("At least one component variable is required.",)

    aligned = _build_aligned_cohort_with_caveats()
    part = _build_table(
        [("a", "2022", 0.5)],
        variable_dcid="Count_Person_Employed",
        variable_name="Employed population",
        source_id=2,
    )
    combined = build_invalid_parameters_refusal(
        (aligned, part),
        script="compute_composition",
        step_id="s1",
        caveat="Bad parameter.",
    )
    assert combined.variables == ("Count_Person", "Count_Person_Employed")
    assert combined.provenance.facet_ids == ("f1", "f2")
    assert combined.coverage == aligned.coverage
    assert combined.caveats == (*aligned.caveats, "Bad parameter.")

    later = align_cohort(_build_table([("a", "2023", 1.0)], source_id=2))
    assert isinstance(later, AlignedCohort)
    conflicting = build_invalid_parameters_refusal(
        (aligned, later),
        script="compute_composition",
        step_id="s1",
        caveat="Different dates.",
    )
    assert conflicting.variables == ("Count_Person",)
    assert conflicting.coverage is None
    assert conflicting.caveats == (*aligned.caveats, "Different dates.")


def test_refusals_can_override_unit_scaling_and_append_caveats() -> None:
    # Test: Resolved `unit`, `scaling_factor`, and `extra_caveats` overrides
    #   on `build_refusal` and `build_invalid_parameters_refusal`.
    # Situation: A table with unit `"Person"` refused with `unit=None`,
    #   `scaling_factor=None`, and extra skip caveats, and an
    #   `invalid_parameters` refusal overriding `unit="Percent"` and
    #   `scaling_factor=100.0`.
    # Expectation: Explicit `None` overrides the first input's unit and
    #   scaling factor; `extra_caveats` follow `caveat` in order; and
    #   `build_invalid_parameters_refusal` forwards the overrides.
    table = _build_table([("a", "2022", 1.0)])
    cleared = build_refusal(
        table,
        script="compute_derived_metric",
        step_id="s1",
        reason="no_observations",
        coverage=None,
        caveat="No shared observations.",
        extra_caveats=("1 pair skipped.",),
        unit=None,
        scaling_factor=None,
    )
    assert cleared.unit is None
    assert cleared.scaling_factor is None
    assert cleared.caveats == ("No shared observations.", "1 pair skipped.")

    overridden = build_invalid_parameters_refusal(
        table,
        script="compute_derived_metric",
        step_id="s2",
        caveat="Bad scale.",
        unit="Percent",
        scaling_factor=100.0,
    )
    assert overridden.unit == "Percent"
    assert overridden.scaling_factor == 100.0


def test_resolve_aligned_cohort_aligns_tables_and_checks_cohorts() -> None:
    # Test: Resolution of a cohort-or-table argument.
    # Situation: A table aligned with defaults; a table with `min_coverage`
    #   1.5; a table below the default coverage; and an aligned cohort with
    #   its own date, another date, and `min_coverage` 1.5 without and with
    #   the check.
    # Expectation: The table is aligned; the bad `min_coverage` is refused
    #   with `invalid_parameters` and no coverage; the sparse table is
    #   refused with the alignment's reason and coverage; the aligned cohort
    #   is returned as given for its own date and an unchecked
    #   `min_coverage`, and is refused, carrying its coverage, for another
    #   date (naming the operation) and a checked bad `min_coverage`.
    table = _build_table([("a", "2022", 1.0), ("b", "2022", 2.0)])
    resolved = resolve_aligned_cohort(
        table,
        script="rank_cohort",
        step_id="s1",
        target_date=None,
        min_coverage=0.5,
        operation="ranked",
    )
    assert isinstance(resolved, AlignedCohort)
    assert resolved.reference_date == "2022"
    bad_coverage = resolve_aligned_cohort(
        table,
        script="rank_cohort",
        step_id="s1",
        target_date=None,
        min_coverage=1.5,
        operation="ranked",
    )
    assert not isinstance(bad_coverage, AlignedCohort)
    assert bad_coverage.refusal_reason == "invalid_parameters"
    assert bad_coverage.coverage is None
    sparse = resolve_aligned_cohort(
        _build_table(
            [("a", "2022", 1.0)], requested_places=["a", "b", "c", "d"]
        ),
        script="rank_cohort",
        step_id="s1",
        target_date=None,
        min_coverage=0.5,
        operation="ranked",
    )
    assert not isinstance(sparse, AlignedCohort)
    assert sparse.refusal_reason == "insufficient_coverage"
    assert sparse.coverage is not None
    assert sparse.coverage.contributing_places == 1

    aligned = _build_aligned_cohort_with_caveats()
    for target_date, min_coverage in (("2022", 0.5), (None, 1.5)):
        assert (
            resolve_aligned_cohort(
                aligned,
                script="summarize_distribution",
                step_id="s1",
                target_date=target_date,
                min_coverage=min_coverage,
                operation="summarized",
            )
            is aligned
        )
    other_date = resolve_aligned_cohort(
        aligned,
        script="summarize_distribution",
        step_id="s1",
        target_date="2021",
        min_coverage=0.5,
        operation="summarized",
    )
    assert not isinstance(other_date, AlignedCohort)
    assert other_date.coverage == aligned.coverage
    assert other_date.caveats == (
        *aligned.caveats,
        "The cohort is aligned to 2022, so it cannot be summarized on the "
        "target date 2021.",
    )
    checked = resolve_aligned_cohort(
        aligned,
        script="summarize_distribution",
        step_id="s1",
        target_date=None,
        min_coverage=1.5,
        operation="summarized",
        should_check_min_coverage=True,
    )
    assert not isinstance(checked, AlignedCohort)
    assert checked.refusal_reason == "invalid_parameters"
    assert checked.caveats[-1] == (
        "The minimum coverage must be between 0 and 1, not 1.5."
    )


def test_describe_missing_focal_places_names_the_cohort_and_figure() -> None:
    # Test: The caveat for focal places missing from a cohort.
    # Situation: One missing place with a display name and two without.
    # Expectation: The display name is used where known and the DCID
    #   otherwise, the verb agrees with the count, and the cohort label and
    #   the unavailable figure are worded as given.
    aligned = _build_aligned_cohort_with_caveats()
    assert describe_missing_focal_places(
        aligned, ["c"], cohort_label="ranked cohort", unavailable_figure="rank"
    ) == (
        "C has no value for Total population in the ranked cohort on 2022, "
        "so no rank is available."
    )
    assert describe_missing_focal_places(
        aligned,
        ["x", "y"],
        cohort_label="cohort",
        unavailable_figure="benchmark",
    ) == (
        "x and y have no value for Total population in the cohort on 2022, "
        "so no benchmark is available."
    )


@pytest.mark.parametrize(
    ("min_coverage", "should_check"),
    [(1.5, False), (0.5, True)],
    ids=["unchecked-out-of-range", "checked-valid"],
)
def test_resolve_aligned_cohort_passes_a_window_cohort_through(
    min_coverage: float, should_check: bool
) -> None:
    # Test: Resolution of a cohort whose reference date is a date window.
    # Situation: The window cohort with no `target_date`, with an unchecked
    #   `min_coverage` of 1.5 or a valid checked `min_coverage` of 0.5.
    # Expectation: The cohort is returned as given.
    spanning = _build_spanning_cohort()
    assert (
        resolve_aligned_cohort(
            spanning,
            script="rank_cohort",
            step_id="s1",
            target_date=None,
            min_coverage=min_coverage,
            operation="ranked",
            should_check_min_coverage=should_check,
        )
        is spanning
    )


def test_resolve_aligned_cohort_checks_min_coverage_of_a_window_cohort() -> (
    None
):
    # Test: The checked `min_coverage` of a date-window cohort.
    # Situation: The window cohort with `min_coverage` 1.5 and
    #   `should_check_min_coverage=True`.
    # Expectation: An `invalid_parameters` refusal carrying the cohort's
    #   coverage and caveats, followed by the threshold message.
    spanning = _build_spanning_cohort()
    refused = resolve_aligned_cohort(
        spanning,
        script="summarize_distribution",
        step_id="s1",
        target_date=None,
        min_coverage=1.5,
        operation="summarized",
        should_check_min_coverage=True,
    )
    assert isinstance(refused, RefusedScriptResult)
    assert refused.refusal_reason == "invalid_parameters"
    assert refused.coverage == spanning.coverage
    assert refused.caveats == (
        *spanning.caveats,
        "The minimum coverage must be between 0 and 1, not 1.5.",
    )


@pytest.mark.parametrize(
    ("target_date", "message"),
    [
        (
            "latest",
            "The target date 'latest' is not a year, a year and month, or a "
            "full date.",
        ),
        (
            "2024",
            "The cohort spans from 2020 to 2024, so it cannot be ranked on "
            "the single target date 2024.",
        ),
    ],
    ids=["malformed-date", "valid-date"],
)
def test_resolve_aligned_cohort_refuses_a_target_date_for_a_window(
    target_date: str, message: str
) -> None:
    # Test: A `target_date` passed with a date-window cohort.
    # Situation: The window cohort with a malformed `target_date` (`latest`)
    #   or a valid `target_date` (`2024`, the window's end).
    # Expectation: An `invalid_parameters` refusal carrying the cohort's
    #   coverage and caveats; the malformed date reports the date format,
    #   and the valid date reports that the cohort spans a window and names
    #   the operation.
    spanning = _build_spanning_cohort()
    refused = resolve_aligned_cohort(
        spanning,
        script="rank_cohort",
        step_id="s1",
        target_date=target_date,
        min_coverage=0.5,
        operation="ranked",
    )
    assert isinstance(refused, RefusedScriptResult)
    assert refused.refusal_reason == "invalid_parameters"
    assert refused.coverage == spanning.coverage
    assert refused.caveats == (*spanning.caveats, message)


def test_describe_missing_focal_places_reads_a_window_cohort() -> None:
    # Test: The missing focal place caveat for a date-window cohort.
    # Situation: The window cohort, whose figure is labeled `change in Total
    #   population`, with focal place `c` missing.
    # Expectation: The caveat names the figure's label and reads the window
    #   as `"from 2020 to 2024"`.
    assert describe_missing_focal_places(
        _build_spanning_cohort(),
        ["c"],
        cohort_label="ranked cohort",
        unavailable_figure="rank",
    ) == (
        "C has no value for change in Total population in the ranked cohort "
        "from 2020 to 2024, so no rank is available."
    )


def _build_variable_table(
    variable_dcid: str, source_id: int
) -> ObservationTable:
    """Builds a one-row table of `variable_dcid` citing source `source_id`."""
    return _build_table(
        [("a", "2022", 1.0)],
        variable_dcid=variable_dcid,
        variable_name=f"Name of {variable_dcid}",
        source_id=source_id,
    )


def test_collect_variable_provenance_drops_methodology() -> None:
    # Test: The methodology of a collected provenance.
    # Situation: One table whose provenance carries a methodology string.
    # Expectation: The variable maps to the table's sources and facet IDs
    #   with no methodology.
    table = _build_variable_table("Var_A", 1)
    with_methodology = replace(
        table,
        provenance=replace(table.provenance, methodology="Derived."),
    )

    assert collect_variable_provenance(with_methodology) == {
        "Var_A": table.provenance,
    }


def test_collect_variable_provenance_keeps_first_appearance_order() -> None:
    # Test: Distinct variables in the collected mapping.
    # Situation: A table of `Var_B` citing source 2, then a table of `Var_A`
    #   citing source 1.
    # Expectation: The mapping lists `Var_B` then `Var_A`, each with its own
    #   table's provenance.
    table_b = _build_variable_table("Var_B", 2)
    table_a = _build_variable_table("Var_A", 1)

    collected = collect_variable_provenance((table_b, table_a))

    assert list(collected) == ["Var_B", "Var_A"]
    assert collected == {
        "Var_B": table_b.provenance,
        "Var_A": table_a.provenance,
    }


def test_collect_variable_provenance_merges_inputs_of_one_variable() -> None:
    # Test: Inputs that share a variable DCID.
    # Situation: Two tables of `Var_A`, citing sources 1 and 2.
    # Expectation: `Var_A` maps to both sources and both facet IDs, in input
    #   order, with no methodology.
    merged = collect_variable_provenance(
        (_build_variable_table("Var_A", 1), _build_variable_table("Var_A", 2))
    )

    assert merged == {
        "Var_A": Provenance(
            sources=(
                Source(name="Source 1", url="https://source-1"),
                Source(name="Source 2", url="https://source-2"),
            ),
            facet_ids=("f1", "f2"),
        ),
    }


def test_build_refusal_maps_each_variable_to_its_own_source() -> None:
    # Test: The per-variable provenance of a refusal.
    # Situation: `build_refusal` is given a table of `Var_A` citing source 1
    #   and a table of `Var_B` citing source 2.
    # Expectation: The refusal maps each variable to its own table's
    #   provenance.
    table_a = _build_variable_table("Var_A", 1)
    table_b = _build_variable_table("Var_B", 2)

    refused = build_refusal(
        (table_a, table_b),
        script="relate_cohorts",
        step_id="s1",
        reason="no_observations",
        coverage=None,
        caveat="No shared places.",
    )

    assert refused.variable_provenance == {
        "Var_A": table_a.provenance,
        "Var_B": table_b.provenance,
    }

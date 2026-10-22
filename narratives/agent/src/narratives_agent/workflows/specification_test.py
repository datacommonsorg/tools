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
"""Tests for the analysis specification in `specification`.

Covers Pydantic step validation, the generated Gemini declarations, script
literal alignment with `analytics.metrics`, validation against `TurnCache`,
`UnavailableReport` rendering, and `build_default_specification`.
"""

from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

from narratives_agent.analytics.metrics import ScriptMetrics, ScriptName
from narratives_agent.analytics.provenance import Provenance
from narratives_agent.analytics.ranking import DEFAULT_MAX_ENTRIES_PER_END
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.workflows.fetch_requests import NAMED_PLACE_SERIES_LIMIT
from narratives_agent.workflows.specification import (
    _MAX_SPECIFICATION_STEPS,
    _STEP_MODELS,
    REPORT_UNAVAILABLE,
    SUBMIT_SPECIFICATION,
    AnalysisSpecification,
    ComputeDerivedMetricStep,
    RankCohortStep,
    RelateCohortsStep,
    UnavailableReport,
    _Step,
    build_default_specification,
    build_specification_declarations,
    get_step_output_kind,
    list_step_inputs,
    validate_specification,
)
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache


def _build_table(
    table_id: str,
    places: tuple[str, ...] = ("a", "b", "c"),
    *,
    variable_dcid: str = "Count_Person",
    unit: str | None = "Person",
    child_place_type: str | None = None,
) -> CachedTable:
    """Builds a cached table with one 2023 row per place."""
    table = ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_dcid,
        unit=unit,
        scaling_factor=None,
        provenance=Provenance(),
        rows=tuple(
            ObservationRow(place, place.upper(), "2023", float(index + 1))
            for index, place in enumerate(places)
        ),
        requested_places=places,
        place_names={place: place.upper() for place in places},
        parent_place_dcid="country/USA" if child_place_type else None,
        child_place_type=child_place_type,
    )
    return CachedTable(table_id=table_id, table=table)


def _build_cache(*entries: CachedTable) -> TurnCache:
    """Stores the cached tables in a fresh cache, in order."""
    cache = TurnCache()
    for entry in entries:
        cache.store_fetched(entry)
    return cache


def _build_specification(
    *steps: JsonObject, **extra: JsonValue
) -> AnalysisSpecification:
    """Validates a specification from step objects and top-level fields."""
    payload: JsonObject = {"steps": list(steps), **extra}
    return AnalysisSpecification.model_validate(payload)


def _build_classification(pattern: str) -> QueryClassification:
    """Builds a serviceable classification with the given pattern."""
    return QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": pattern,
            "geographic_shape": "child_places",
            "requires_computation": True,
        }
    )


def _list_scripts_and_tables(
    specification: AnalysisSpecification | None,
) -> list[tuple[str, str]]:
    """Lists each step's script and first input, in step order."""
    assert specification is not None
    return [
        (step.script, list_step_inputs(step)[0][1])
        for step in specification.steps
    ]


def _build_state_cohorts() -> TurnCache:
    """Caches two state cohort tables of different variables."""
    return _build_cache(
        _build_table("t1", child_place_type="State"),
        _build_table(
            "t2", variable_dcid="Count_Household", child_place_type="State"
        ),
    )


def test_step_scripts_match_the_analytics_script_names() -> None:
    # Test: Alignment of the step models with `analytics.metrics`.
    # Situation: The `script` literal of each step model, `ScriptName`, and
    #   the scripts the `ScriptMetrics` records declare.
    # Expectation: The step models cover every `ScriptName`, and every
    #   metrics record's script plus `align_cohort`, which has no metrics.
    step_scripts = {
        get_args(model.model_fields["script"].annotation)[0]
        for model in _STEP_MODELS
    }
    metrics_scripts = {
        metrics.script for metrics in get_args(ScriptMetrics.__value__)
    }
    assert step_scripts == set(get_args(ScriptName.__value__))
    assert step_scripts == metrics_scripts | {"align_cohort"}


def test_the_declarations_name_the_two_functions_and_their_fields() -> None:
    # Test: `build_specification_declarations`.
    # Situation: Generating the declarations of `submit_specification` and
    #   `report_unavailable`.
    # Expectation: Both are present, in that order, `steps` is the only
    #   required field of the first and `reason` of the second.
    declarations = build_specification_declarations()
    assert [declaration.name for declaration in declarations] == [
        SUBMIT_SPECIFICATION,
        REPORT_UNAVAILABLE,
    ]
    specification_schema = declarations[0].parameters_json_schema
    unavailable_schema = declarations[1].parameters_json_schema
    assert isinstance(specification_schema, dict)
    assert isinstance(unavailable_schema, dict)
    assert specification_schema.get("required") == ["steps"]
    assert unavailable_schema.get("required") == ["reason"]


def test_the_declarations_carry_only_model_facing_descriptions() -> None:
    # Test: The descriptions `build_parameters_schema` keeps.
    # Situation: The `submit_specification` schema, whose models carry
    #   developer docstrings with `Attributes:` sections.
    # Expectation: The schema has no top-level description, and a step
    #   model under `$defs` keeps only its one-line summary.
    schema = build_specification_declarations()[0].parameters_json_schema
    assert isinstance(schema, dict)
    assert "description" not in schema
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    assert definitions["RankCohortStep"]["description"] == (
        "Ranks the places of a cohort at its reference date."
    )


def test_every_model_field_carries_a_description() -> None:
    # Test: The model-facing field descriptions.
    # Situation: Every field of `_Step`, each step model,
    #   `AnalysisSpecification`, and `UnavailableReport`.
    # Expectation: Each has a non-empty description, so the text the model
    #   reads cannot silently disappear.
    models: tuple[type[BaseModel], ...] = (
        _Step,
        *_STEP_MODELS,
        AnalysisSpecification,
        UnavailableReport,
    )
    for model in models:
        for field_name, field_info in model.model_fields.items():
            assert field_info.description, (
                f"{model.__name__}.{field_name} is missing a description"
            )


def test_steps_validate_into_their_script_models_with_defaults() -> None:
    # Test: The discriminated union of steps.
    # Situation: A derived metric over `t2` and `t1`, then a ranking of its
    #   output that omits its direction and coverage.
    # Expectation: Each step validates into its script's model with the
    #   script's defaults applied, the fetched tables come back in order of
    #   first reference, and the scripts are listed in step order.
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_derived_metric",
            "left": "t2",
            "right": "t1",
            "operation": "per_capita",
            "scale": 100000,
        },
        {"step_id": "s2", "script": "rank_cohort", "table": "s1", "n": 5},
        findings=["Texas leads."],
        focal_places=["geoId/48"],
    )
    first, second = specification.steps
    assert isinstance(first, ComputeDerivedMetricStep)
    assert first.min_coverage == 0.0
    assert isinstance(second, RankCohortStep)
    assert second.direction == "desc"
    assert second.min_coverage == 0.5
    assert specification.list_referenced_table_ids() == ("t2", "t1")
    assert specification.list_script_names() == [
        "compute_derived_metric",
        "rank_cohort",
    ]


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (
            {
                "step_id": "s1",
                "script": "relate_cohorts",
                "target": "t1",
                "by": "t2",
            },
            (("target", "t1"), ("by", "t2")),
        ),
        (
            {
                "step_id": "s1",
                "script": "compute_composition",
                "components": ["t1", "t2"],
                "total": "t3",
            },
            (("components", "t1"), ("components", "t2"), ("total", "t3")),
        ),
        (
            {
                "step_id": "s1",
                "script": "summarize_distribution",
                "table": "t1",
                "weights": "t2",
            },
            (("table", "t1"), ("weights", "t2")),
        ),
        (
            {"step_id": "s1", "script": "rank_cohort", "table": "t1"},
            (("table", "t1"),),
        ),
    ],
    ids=["relation", "composition with total", "weighted", "single table"],
)
def test_step_inputs_are_listed_in_the_order_the_script_takes_them(
    step: JsonObject, expected: tuple[tuple[str, str], ...]
) -> None:
    # Test: `list_step_inputs`.
    # Situation: A relation, a composition with a total, a weighted
    #   distribution, and a ranking.
    # Expectation: The pairs follow the script's argument order, with the
    #   optional total and weights last.
    (parsed,) = _build_specification(step).steps
    assert list_step_inputs(parsed) == expected


@pytest.mark.parametrize(
    ("script", "fields", "expected"),
    [
        ("align_cohort", {"table": "t1"}, "cohort"),
        ("compute_derived_metric", {"left": "t1", "right": "t2"}, "table"),
        ("analyze_timeseries", {"table": "t1"}, "result"),
    ],
)
def test_each_step_reports_what_later_steps_can_read(
    script: str, fields: JsonObject, expected: str
) -> None:
    # Test: `get_step_output_kind`.
    # Situation: An alignment, a derived metric, and a series summary.
    # Expectation: They make a cohort, a table, and only a result available.
    (step,) = _build_specification(
        {"step_id": "s1", "script": script, **fields}
    ).steps
    assert get_step_output_kind(step) == expected


@pytest.mark.parametrize(
    ("document", "fragment"),
    [
        (
            {"steps": [{"step_id": "s1", "script": "regress", "table": "t1"}]},
            "script",
        ),
        (
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "script": "rank_cohort",
                        "table": "t1",
                        "top_n": 5,
                    }
                ]
            },
            "top_n",
        ),
        ({"steps": []}, "at least 1"),
        (
            {
                "steps": [
                    {
                        "step_id": f"s{index}",
                        "script": "analyze_timeseries",
                        "table": "t1",
                    }
                    for index in range(1, _MAX_SPECIFICATION_STEPS + 2)
                ]
            },
            f"at most {_MAX_SPECIFICATION_STEPS}",
        ),
        (
            {
                "steps": [
                    {
                        "step_id": "step1",
                        "script": "analyze_timeseries",
                        "table": "t1",
                    }
                ]
            },
            "step_id",
        ),
        (
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "script": "analyze_timeseries",
                        "table": "x1",
                    }
                ]
            },
            "table",
        ),
        (
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "script": "rank_cohort",
                        "table": "t1",
                        "direction": "down",
                    }
                ]
            },
            "direction",
        ),
        (
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "script": "compute_derived_metric",
                        "left": "t1",
                        "right": "t2",
                        "operation": "product",
                    }
                ]
            },
            "operation",
        ),
        (
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "script": "compute_composition",
                        "components": ["t1"],
                        "mode": "shares",
                    }
                ]
            },
            "mode",
        ),
        (
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "script": "rank_cohort",
                        "table": "t1",
                        "min_coverage": 1.5,
                    }
                ]
            },
            "min_coverage",
        ),
    ],
    ids=[
        "unknown script",
        "unknown parameter",
        "no steps",
        "too many steps",
        "bad step id",
        "bad reference",
        "bad direction",
        "bad operation",
        "bad mode",
        "coverage above one",
    ],
)
def test_malformed_specifications_are_rejected(
    document: JsonObject, fragment: str
) -> None:
    # Test: Pydantic rejection of malformed model output.
    # Situation: An unknown script, a parameter the script does not take, no
    #   steps, more than the step limit, a step id that is not `s<n>`, a
    #   reference that is neither `t<n>` nor `s<n>`, a direction, operation,
    #   or mode outside its `Literal`, and a coverage above one.
    # Expectation: Each raises `ValidationError` naming the field.
    with pytest.raises(ValidationError) as raised:
        AnalysisSpecification.model_validate(document)
    assert fragment in str(raised.value)


def test_a_consistent_chain_passes_validation() -> None:
    # Test: `validate_specification` on a valid chain.
    # Situation: An alignment of `t1` feeds a ranking and a distribution; a
    #   derived metric of `t1` and `t2` feeds a series summary and a
    #   composition whose total is the aligned cohort.
    # Expectation: No problem is reported.
    cache = _build_cache(_build_table("t1"), _build_table("t2"))
    specification = _build_specification(
        {"step_id": "s1", "script": "align_cohort", "table": "t1"},
        {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
        {"step_id": "s3", "script": "summarize_distribution", "table": "s1"},
        {
            "step_id": "s4",
            "script": "compute_derived_metric",
            "left": "t1",
            "right": "t2",
        },
        {"step_id": "s5", "script": "analyze_timeseries", "table": "s4"},
        {
            "step_id": "s6",
            "script": "compute_composition",
            "components": ["t1", "s4"],
            "total": "s1",
        },
    )
    assert validate_specification(specification, cache) is None


def test_a_relation_accepts_an_aligned_cohort_and_a_table() -> None:
    # Test: The inputs `relate_cohorts` accepts.
    # Situation: An alignment of `t1` is related as the target to `t2`, a
    #   table of another variable.
    # Expectation: No problem is reported, and both fetched tables are
    #   listed as referenced.
    cache = _build_cache(
        _build_table("t1"), _build_table("t2", variable_dcid="Count_Household")
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "align_cohort", "table": "t1"},
        {
            "step_id": "s2",
            "script": "relate_cohorts",
            "target": "s1",
            "by": "t2",
        },
    )
    assert validate_specification(specification, cache) is None
    assert specification.list_referenced_table_ids() == ("t1", "t2")


@pytest.mark.parametrize(
    ("steps", "fragments"),
    [
        (
            [{"step_id": "s1", "script": "rank_cohort", "table": "t3"}],
            [
                "s1.table references t3, which is not a cached table; the "
                "cached tables are t1, t2."
            ],
        ),
        (
            [
                {"step_id": "s1", "script": "rank_cohort", "table": "s2"},
                {"step_id": "s2", "script": "align_cohort", "table": "t1"},
            ],
            ["s1.table references s2, which is not the output of an earlier"],
        ),
        (
            [{"step_id": "s1", "script": "rank_cohort", "table": "s1"}],
            ["s1.table references the step itself"],
        ),
        (
            [
                {"step_id": "s1", "script": "rank_cohort", "table": "t1"},
                {
                    "step_id": "s2",
                    "script": "summarize_distribution",
                    "table": "s1",
                },
            ],
            ["s2.table references s1, whose script produces only a result"],
        ),
        (
            [
                {"step_id": "s1", "script": "align_cohort", "table": "t1"},
                {
                    "step_id": "s2",
                    "script": "analyze_timeseries",
                    "table": "s1",
                },
                {
                    "step_id": "s3",
                    "script": "compute_derived_metric",
                    "left": "s1",
                    "right": "t2",
                },
            ],
            [
                "s2.table references the aligned cohort s1, but "
                "analyze_timeseries",
                "s3.left references the aligned cohort s1, but "
                "compute_derived_metric",
            ],
        ),
        (
            [
                {"step_id": "s1", "script": "rank_cohort", "table": "t1"},
                {"step_id": "s1", "script": "rank_cohort", "table": "t2"},
            ],
            ["step_id s1 is used more than once", "step 2 must be s2"],
        ),
        (
            [
                {"step_id": "s1", "script": "align_cohort", "table": "t1"},
                {"step_id": "s2", "script": "rank_cohort", "table": "t2"},
            ],
            ["s1 (align_cohort) is not used by a later step"],
        ),
    ],
    ids=[
        "dangling table",
        "forward reference",
        "self reference",
        "result as input",
        "cohort into table-only scripts",
        "duplicate step id",
        "unused alignment",
    ],
)
def test_inconsistent_references_are_reported(
    steps: list[JsonObject], fragments: list[str]
) -> None:
    # Test: Reference and step-id problems.
    # Situation: A table that was never fetched, a reference to a later
    #   step, a step that references itself, a result-only step used as an
    #   input, an aligned cohort fed to the two table-only scripts, a
    #   repeated step id, and an alignment no step reads.
    # Expectation: Every problem is reported, one per line, naming the step
    #   field and the reference, with the cached table ids listed for a
    #   dangling table.
    cache = _build_cache(_build_table("t1"), _build_table("t2"))
    problems = validate_specification(_build_specification(*steps), cache)
    assert problems is not None
    for fragment in fragments:
        assert fragment in problems
    assert len(problems.splitlines()) == len(fragments)


@pytest.mark.parametrize(
    ("steps", "problem"),
    [
        (
            [
                {
                    "step_id": "s1",
                    "script": "relate_cohorts",
                    "target": "t1",
                    "by": "t1",
                },
            ],
            "s1 (relate_cohorts) uses one table as both target and by "
            "(t1 and t1); name two different tables.",
        ),
        (
            [
                {"step_id": "s1", "script": "align_cohort", "table": "t1"},
                {
                    "step_id": "s2",
                    "script": "relate_cohorts",
                    "target": "s1",
                    "by": "t1",
                },
            ],
            "s2 (relate_cohorts) uses one table as both target and by "
            "(s1 and t1); name two different tables.",
        ),
        (
            [
                {"step_id": "s1", "script": "align_cohort", "table": "t1"},
                {
                    "step_id": "s2",
                    "script": "relate_cohorts",
                    "target": "s1",
                    "by": "t2",
                },
            ],
            "s2 (relate_cohorts) relates Count_Person to itself (t1 and t2); "
            "name tables of two different variables.",
        ),
        (
            [
                {
                    "step_id": "s1",
                    "script": "relate_cohorts",
                    "target": "t1",
                    "by": "t2",
                },
            ],
            "s1 (relate_cohorts) relates Count_Person to itself (t1 and t2); "
            "name tables of two different variables.",
        ),
    ],
    ids=[
        "one table",
        "a table and its alignment",
        "one variable through an alignment",
        "two tables of one variable",
    ],
)
def test_a_relation_of_a_variable_to_itself_is_reported(
    steps: list[JsonObject], problem: str
) -> None:
    # Test: The distinct-inputs check of `relate_cohorts`.
    # Situation: Both cached tables measure `Count_Person`. A relation names
    #   one table twice, a table and its own alignment, an alignment of `t1`
    #   and `t2`, and `t1` and `t2` directly.
    # Expectation: Exactly one problem is reported for each, naming the
    #   step, its two references, and the correction.
    cache = _build_cache(_build_table("t1"), _build_table("t2"))
    problems = validate_specification(_build_specification(*steps), cache)
    assert problems == problem


@pytest.mark.parametrize(
    ("step", "extra", "problem"),
    [
        (
            {
                "step_id": "s1",
                "script": "rank_cohort",
                "table": "t1",
                "focal_places": ["geoId/06", "geo Id/48"],
            },
            {},
            "s1.focal_places must hold DCIDs, but entry 2 of 2 is not a "
            "valid DCID.",
        ),
        (
            {
                "step_id": "s1",
                "script": "analyze_timeseries",
                "table": "t1",
                "places": ["bad\nplace"],
            },
            {},
            "s1.places must hold DCIDs, but entry 1 of 1 is not a valid DCID.",
        ),
        (
            {"step_id": "s1", "script": "rank_cohort", "table": "t1"},
            {"focal_places": ["", "geoId/06"]},
            "focal_places must hold DCIDs, but entry 1 of 2 is not a valid "
            "DCID.",
        ),
    ],
    ids=["step focal places", "step places", "specification focal places"],
)
def test_an_invalid_place_is_reported_by_position(
    step: JsonObject, extra: JsonObject, problem: str
) -> None:
    # Test: Place DCID validation at the model-output boundary.
    # Situation: A step focal place with a space, a step place with a
    #   newline, and an empty specification-level focal place.
    # Expectation: The single problem names the field and the entry's
    #   position and never repeats the string the model sent.
    cache = _build_cache(_build_table("t1"))
    problems = validate_specification(
        _build_specification(step, **extra), cache
    )
    assert problems == problem


@pytest.mark.parametrize(
    ("step", "problem"),
    [
        (
            {
                "step_id": "s1",
                "script": "rank_cohort",
                "table": "t1",
                "target_date": "2023/01",
            },
            "s1.target_date must be a YYYY, YYYY-MM, or YYYY-MM-DD date.",
        ),
        (
            {
                "step_id": "s1",
                "script": "relate_cohorts",
                "target": "t1",
                "by": "t2",
                "by_date": "2021-02-29",
            },
            "s1.by_date must be a YYYY, YYYY-MM, or YYYY-MM-DD date.",
        ),
        (
            {
                "step_id": "s1",
                "script": "analyze_timeseries",
                "table": "t1",
                "start_date": "2020",
                "end_date": "2019-06",
            },
            "s1.start_date is after s1.end_date.",
        ),
        (
            {
                "step_id": "s1",
                "script": "compute_derived_metric",
                "left": "t1",
                "right": "t2",
                "end_date": "last year",
            },
            "s1.end_date must be a YYYY, YYYY-MM, or YYYY-MM-DD date.",
        ),
    ],
    ids=["slash date", "no such day", "inverted window", "words"],
)
def test_an_invalid_date_is_reported_by_field(
    step: JsonObject, problem: str
) -> None:
    # Test: Date validation at the model-output boundary.
    # Situation: A ranking date with slashes, a relation date on a day that
    #   does not exist, a series window whose start follows its end, and a
    #   derived-metric bound written in words.
    # Expectation: The single problem names the step field and never
    #   repeats the date the model sent.
    cache = _build_cache(
        _build_table("t1"), _build_table("t2", variable_dcid="Count_Household")
    )
    problems = validate_specification(_build_specification(step), cache)
    assert problems == problem


def test_the_full_unavailable_report_renders_every_part_in_order() -> None:
    # Test: `UnavailableReport.format_note` with every field set.
    # Situation: A reason, two searched indicators, one place, and one
    #   related indicator.
    # Expectation: The note states the reason, then the searches, the
    #   places, and the related data, each list in full.
    report = UnavailableReport(
        searched_indicators=["happiness index", "Count_Smile"],
        searched_places=["country/FRA"],
        reason="Data Commons has no happiness index.",
        related_available=["Life expectancy"],
    )
    assert report.format_note() == (
        "Data Commons has no happiness index. Searched: happiness index, "
        "Count_Smile. Places: country/FRA. Related data available: Life "
        "expectancy."
    )


def test_a_bare_unavailable_report_renders_its_reason() -> None:
    # Test: `UnavailableReport.format_note` with only a reason.
    # Situation: A report whose lists are empty.
    # Expectation: The note is the reason alone.
    assert UnavailableReport(reason="Nothing.").format_note() == "Nothing."


def test_an_unavailable_report_needs_a_reason() -> None:
    # Test: The `reason` constraint of `UnavailableReport`.
    # Situation: A report with an empty reason.
    # Expectation: Validation fails.
    with pytest.raises(ValidationError):
        UnavailableReport(reason="")


@pytest.mark.parametrize(
    ("pattern", "script"),
    [
        ("top_n_ranking", "rank_cohort"),
        ("distribution", "summarize_distribution"),
        ("single_point", "rank_cohort"),
        ("trend_delta", "rank_cohort"),
        ("composition", "rank_cohort"),
        ("sequential_stages", "rank_cohort"),
        ("exploratory", "rank_cohort"),
    ],
)
def test_the_default_specification_runs_one_step_per_table(
    pattern: str, script: str
) -> None:
    # Test: `build_default_specification` per pattern.
    # Situation: Two state cohort tables are cached, under each pattern
    #   other than a correlation.
    # Expectation: Each table gets one step in fetch order, running the
    #   pattern's script: a distribution summary for a distribution
    #   question, and a ranking of the child-place cohort for every other
    #   pattern, including a composition or stages question, whose fetched
    #   tables may hold only some components.
    cache = _build_state_cohorts()
    specification = build_default_specification(
        _build_classification(pattern), cache
    )
    assert _list_scripts_and_tables(specification) == [
        (script, "t1"),
        (script, "t2"),
    ]
    assert specification is not None
    assert validate_specification(specification, cache) is None


def test_the_default_keeps_every_non_empty_table_in_fetch_order() -> None:
    # Test: The default for a ranking question.
    # Situation: Under `top_n_ranking`, the cache holds a county income
    #   cohort (`t1`), ten named counties (`t2`), an empty table (`t3`), and
    #   a county diabetes cohort (`t4`).
    # Expectation: `t1`, `t2`, and `t4` are ranked in that order, and `t3`
    #   has no step. `t2` is ranked because ten places can be ranked.
    tail = tuple(f"geoId/{index:05d}" for index in range(10))
    cache = _build_cache(
        _build_table(
            "t1",
            ("a", "b", "c", "d"),
            variable_dcid="Median_Income_Household",
            child_place_type="County",
        ),
        _build_table("t2", tail, variable_dcid="Percent_Person_WithDiabetes"),
        _build_table("t3", (), variable_dcid="Percent_Person_WithDiabetes"),
        _build_table(
            "t4",
            ("a", "b", "c"),
            variable_dcid="Percent_Person_WithDiabetes",
            child_place_type="County",
        ),
    )
    specification = build_default_specification(
        _build_classification("top_n_ranking"), cache
    )
    assert _list_scripts_and_tables(specification) == [
        ("rank_cohort", "t1"),
        ("rank_cohort", "t2"),
        ("rank_cohort", "t4"),
    ]


@pytest.mark.parametrize(
    ("pattern", "table", "script"),
    [
        ("distribution", _build_table("t1", ("a", "b")), "analyze_timeseries"),
        (
            "trend_delta",
            _build_table("t1", ("a", "b"), child_place_type="County"),
            "rank_cohort",
        ),
        (
            "trend_delta",
            _build_table("t1", ("a", "b", "c")),
            "analyze_timeseries",
        ),
        (
            "single_point",
            _build_table(
                "t1",
                tuple(f"p{index}" for index in range(NAMED_PLACE_SERIES_LIMIT)),
            ),
            "analyze_timeseries",
        ),
        (
            "single_point",
            _build_table(
                "t1",
                tuple(
                    f"p{index}" for index in range(NAMED_PLACE_SERIES_LIMIT + 1)
                ),
            ),
            "rank_cohort",
        ),
    ],
    ids=[
        "distribution of two places",
        "trend of a county cohort",
        "trend of three named places",
        "single point at the series limit",
        "single point above the series limit",
    ],
)
def test_the_pattern_script_applies_only_to_a_table_of_its_shape(
    pattern: str, table: CachedTable, script: str
) -> None:
    # Test: The shape checks of the default specification.
    # Situation: Two places under `distribution`; a county cohort and three
    #   named places under `trend_delta`; and `NAMED_PLACE_SERIES_LIMIT`
    #   named places and one more under `single_point`.
    # Expectation: Two places get a series summary rather than a
    #   distribution; a county cohort is ranked; three named places keep
    #   their series summary; and named places are ranked only above the
    #   limit at which a fetch treats them as a cohort.
    specification = build_default_specification(
        _build_classification(pattern), _build_cache(table)
    )
    assert _list_scripts_and_tables(specification) == [(script, "t1")]


def test_the_default_keeps_the_earliest_tables_within_the_step_limit() -> None:
    # Test: The step limit of the default specification.
    # Situation: One more non-empty table than the step limit is cached and
    #   no classification is available.
    # Expectation: The earliest-fetched tables are ranked and the latest is
    #   dropped.
    cache = _build_cache(
        *(
            _build_table(f"t{index}", variable_dcid=f"Var_{index}")
            for index in range(1, _MAX_SPECIFICATION_STEPS + 2)
        )
    )
    specification = build_default_specification(None, cache)
    assert _list_scripts_and_tables(specification) == [
        ("rank_cohort", f"t{index}")
        for index in range(1, _MAX_SPECIFICATION_STEPS + 1)
    ]


def test_a_correlation_default_relates_two_tables_of_one_cohort() -> None:
    # Test: The correlation default.
    # Situation: Under `correlation`, two state cohort tables of different
    #   variables are cached.
    # Expectation: The tables are related first, with the earlier table as
    #   `by` and the default group size, followed by a ranking of each.
    cache = _build_state_cohorts()
    specification = build_default_specification(
        _build_classification("correlation"), cache
    )
    assert specification is not None
    assert validate_specification(specification, cache) is None
    relation = specification.steps[0]
    assert isinstance(relation, RelateCohortsStep)
    assert (relation.target, relation.by, relation.n) == (
        "t2",
        "t1",
        DEFAULT_MAX_ENTRIES_PER_END,
    )
    assert _list_scripts_and_tables(specification)[1:] == [
        ("rank_cohort", "t1"),
        ("rank_cohort", "t2"),
    ]


def test_a_correlation_default_keeps_the_relation_within_the_limit() -> None:
    # Test: The step limit with a relation.
    # Situation: Under `correlation`, as many state cohort tables as the step
    #   limit are cached.
    # Expectation: The relation keeps the first step and the earliest tables
    #   fill the rest.
    cache = _build_cache(
        *(
            _build_table(
                f"t{index}",
                variable_dcid=f"Var_{index}",
                child_place_type="State",
            )
            for index in range(1, _MAX_SPECIFICATION_STEPS + 1)
        )
    )
    specification = build_default_specification(
        _build_classification("correlation"), cache
    )
    assert specification is not None
    assert specification.list_script_names()[0] == "relate_cohorts"
    assert _list_scripts_and_tables(specification)[1:] == [
        ("rank_cohort", f"t{index}")
        for index in range(1, _MAX_SPECIFICATION_STEPS)
    ]


def test_a_correlation_default_relates_only_one_cohort() -> None:
    # Test: Tables of different cohorts under `correlation`.
    # Situation: A state cohort and a county cohort are cached.
    # Expectation: No relation is built; each table is ranked.
    cache = _build_cache(
        _build_table("t1", child_place_type="State"),
        _build_table(
            "t2", variable_dcid="Count_Household", child_place_type="County"
        ),
    )
    specification = build_default_specification(
        _build_classification("correlation"), cache
    )
    assert _list_scripts_and_tables(specification) == [
        ("rank_cohort", "t1"),
        ("rank_cohort", "t2"),
    ]


def test_a_correlation_default_never_relates_a_variable_to_itself() -> None:
    # Test: Same-variable tables under `correlation`.
    # Situation: The cache holds diabetes (`t1`), diabetes refetched from
    #   another facet (`t2`), and income (`t3`), all across the states.
    # Expectation: The relation pairs `t1` with `t3`, the earliest two tables
    #   of different variables.
    cache = _build_cache(
        _build_table("t1", variable_dcid="Diabetes", child_place_type="State"),
        _build_table("t2", variable_dcid="Diabetes", child_place_type="State"),
        _build_table("t3", variable_dcid="Income", child_place_type="State"),
    )
    specification = build_default_specification(
        _build_classification("correlation"), cache
    )
    assert specification is not None
    relation = specification.steps[0]
    assert isinstance(relation, RelateCohortsStep)
    assert (relation.target, relation.by) == ("t3", "t1")


def test_the_default_without_a_relation_ranks_each_table() -> None:
    # Test: `should_relate=False`.
    # Situation: Under `correlation`, two state cohort tables of different
    #   variables are cached.
    # Expectation: Only the per-table steps are built.
    specification = build_default_specification(
        _build_classification("correlation"),
        _build_state_cohorts(),
        should_relate=False,
    )
    assert _list_scripts_and_tables(specification) == [
        ("rank_cohort", "t1"),
        ("rank_cohort", "t2"),
    ]


def test_the_default_leaves_out_excluded_tables() -> None:
    # Test: `excluded_table_ids`.
    # Situation: Under `correlation`, three state cohort tables of different
    #   variables are cached and `t1` is excluded.
    # Expectation: The relation pairs `t2` with `t3`, and only those two are
    #   ranked.
    cache = _build_cache(
        _build_table("t1", variable_dcid="Diabetes", child_place_type="State"),
        _build_table("t2", variable_dcid="Income", child_place_type="State"),
        _build_table("t3", variable_dcid="Poverty", child_place_type="State"),
    )
    specification = build_default_specification(
        _build_classification("correlation"),
        cache,
        excluded_table_ids=frozenset({"t1"}),
    )
    assert specification is not None
    relation = specification.steps[0]
    assert isinstance(relation, RelateCohortsStep)
    assert (relation.target, relation.by) == ("t3", "t2")
    assert _list_scripts_and_tables(specification)[1:] == [
        ("rank_cohort", "t2"),
        ("rank_cohort", "t3"),
    ]


def test_the_default_is_none_when_every_table_is_excluded() -> None:
    # Test: `excluded_table_ids` covering every table.
    # Situation: Both cached tables are excluded.
    # Expectation: There is no default.
    specification = build_default_specification(
        None, _build_state_cohorts(), excluded_table_ids=frozenset({"t1", "t2"})
    )
    assert specification is None


def test_the_default_without_a_classification_follows_the_shape() -> None:
    # Test: The default without a classification.
    # Situation: The only cached table covers two named places.
    # Expectation: The table gets a series summary.
    specification = build_default_specification(
        None, _build_cache(_build_table("t1", ("a", "b")))
    )
    assert _list_scripts_and_tables(specification) == [
        ("analyze_timeseries", "t1")
    ]


def test_a_composition_default_ranks_each_table() -> None:
    # Test: The composition fallback.
    # Situation: Under `composition`, two tables of three named places each
    #   are cached.
    # Expectation: Each table is ranked; no composition is attempted.
    specification = build_default_specification(
        _build_classification("composition"),
        _build_cache(
            _build_table("t1", unit="Person"),
            _build_table("t2", unit="USDollar"),
        ),
    )
    assert _list_scripts_and_tables(specification) == [
        ("rank_cohort", "t1"),
        ("rank_cohort", "t2"),
    ]


def test_the_default_is_none_when_no_table_has_rows() -> None:
    # Test: The default over empty tables.
    # Situation: The only cached table has no rows.
    # Expectation: There is no default.
    cache = _build_cache(_build_table("t1", ()))
    assert build_default_specification(None, cache) is None

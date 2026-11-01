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
"""Analysis specification models, their validation, and the default builder.

Defines the Pydantic discriminated union of `AnalysisSpecification` steps and
the `UnavailableReport`, validates a specification against `TurnCache`,
builds a default specification over the fetched tables, and generates the
`submit_specification` and `report_unavailable` Gemini declarations.
"""

import math
from collections.abc import Sequence
from typing import Annotated, Literal

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from narratives_agent.analytics.alignment import DEFAULT_MIN_COVERAGE
from narratives_agent.analytics.derived import SCALED_OPERATIONS
from narratives_agent.analytics.metrics import (
    CompositionMode,
    DerivedOperation,
    RankingDirection,
)
from narratives_agent.analytics.ranking import DEFAULT_MAX_ENTRIES_PER_END
from narratives_agent.analytics.relations import MIN_SHARED_PLACES
from narratives_agent.analytics.script_inputs import validate_place_dcids
from narratives_agent.analytics.tables import (
    ObservationTable,
    is_inverted_date_range,
    is_valid_dcid,
    is_valid_observation_date,
)
from narratives_agent.gemini.schemas import QueryClassification, QueryPattern
from narratives_agent.workflows.fetch import build_parameters_schema
from narratives_agent.workflows.fetch_requests import is_named_place_cohort
from narratives_agent.workflows.turn_cache import (
    DERIVED_TABLE_PREFIX,
    FETCHED_TABLE_PREFIX,
    TABLE_ID_NUMBER_PATTERN,
    CachedTable,
    TurnCache,
)

__all__ = [
    "REPORT_UNAVAILABLE",
    "SUBMIT_SPECIFICATION",
    "TABLE_REFERENCE_PATTERN",
    "AlignCohortStep",
    "AnalysisSpecification",
    "AnalyzeTimeseriesStep",
    "ComputeCompositionStep",
    "ComputeDerivedMetricStep",
    "RankCohortStep",
    "RelateCohortsStep",
    "SpecificationStep",
    "StepOutputKind",
    "SummarizeDistributionStep",
    "UnavailableReport",
    "build_default_specification",
    "build_specification_declarations",
    "get_step_output_kind",
    "list_reference_table_ids",
    "list_step_inputs",
    "list_step_table_ids",
    "validate_specification",
]

# The names of the two functions that end discovery: one submits the
# analysis specification, the other reports that the data is unavailable.
SUBMIT_SPECIFICATION = "submit_specification"
REPORT_UNAVAILABLE = "report_unavailable"

# A specification runs at most this many steps.
_MAX_SPECIFICATION_STEPS = 6
# A step id is a derived table id (`s1`), the id its derived table is stored
# under, so it follows the rule `TurnCache.store_derived` enforces.
_STEP_ID_PATTERN = rf"^{DERIVED_TABLE_PREFIX}{TABLE_ID_NUMBER_PATTERN}$"
# A table reference is a fetched table id (`t1`) or a step id (`s1`).
TABLE_REFERENCE_PATTERN = (
    rf"^[{FETCHED_TABLE_PREFIX}{DERIVED_TABLE_PREFIX}]"
    rf"{TABLE_ID_NUMBER_PATTERN}$"
)
# A fetched table with at least this many places with data can be ranked or
# related: three places give a top, a bottom, and a middle.
_RANKABLE_PLACE_COUNT = 3

_SUBMIT_SPECIFICATION_DESCRIPTION = (
    "Finish discovery by naming the analysis to run on the "
    "cached tables. Steps run in order; each references fetched "
    "tables (t1, t2, ...) or earlier step outputs (s1, s2, "
    "...). The server validates the specification and returns "
    "any problem for you to correct."
)

_REPORT_UNAVAILABLE_DESCRIPTION = (
    "Finish discovery when Data Commons does not have the data "
    "the question needs, after the fallbacks have been tried. "
    "Say what was searched and what related data exists."
)

_TABLE_DESCRIPTION = (
    "The input table: a fetched table id (t1) or an earlier step's "
    "output (s1). Used by align_cohort, analyze_timeseries, "
    "rank_cohort, and summarize_distribution."
)
_TARGET_DATE_DESCRIPTION = (
    "The date to align a cohort to instead of the most recent date "
    "with adequate coverage."
)
_MIN_COVERAGE_DESCRIPTION = (
    "The share of the target places that must have a value on the "
    f"reference date, from 0 to 1 (default {DEFAULT_MIN_COVERAGE}; 0 for "
    "compute_derived_metric)."
)
_PLACES_DESCRIPTION = (
    "Place DCIDs to restrict analyze_timeseries, "
    "compute_composition, or compute_derived_metric to."
)
_FOCAL_PLACES_DESCRIPTION = (
    "Place DCIDs to report wherever they rank or sit in the "
    "distribution (rank_cohort, summarize_distribution)."
)
_START_DATE_DESCRIPTION = (
    "Inclusive window start for analyze_timeseries or compute_derived_metric."
)
_END_DATE_DESCRIPTION = (
    "Inclusive window end for analyze_timeseries or compute_derived_metric."
)

_TableReference = Annotated[str, Field(pattern=TABLE_REFERENCE_PATTERN)]
_Coverage = Annotated[float, Field(ge=0.0, le=1.0)]
# Whether a step makes an aligned cohort, a derived table, or only a result
# available to later steps.
type StepOutputKind = Literal["cohort", "table", "result"]
# Whether a step's inputs accept only a table, or a table or an aligned
# cohort.
type _InputKind = Literal["table", "table_or_cohort"]
# The scripts the default specification runs on a single fetched table.
type _DefaultTableScript = Literal[
    "analyze_timeseries", "rank_cohort", "summarize_distribution"
]


class _Step(BaseModel):
    """The fields every step carries.

    Attributes:
        step_id: Identifier of the analysis step (for example, `"s1"`).
    """

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(
        pattern=_STEP_ID_PATTERN,
        description=(
            "The step's id: s1 for the first step, s2 next, and so on."
        ),
    )


class AlignCohortStep(_Step):
    """Aligns a table to one reference date for later cross-sectional steps.

    Attributes:
        script: Always `"align_cohort"`.
        table: The fetched or derived table to align.
        target_date: The date to align to, or `None` to select the most
            recent date with adequate coverage.
        min_coverage: The share of the table's places that must have a value
            on the reference date.
    """

    script: Literal["align_cohort"] = Field(
        description="The analytical script this step runs."
    )
    table: _TableReference = Field(description=_TABLE_DESCRIPTION)
    target_date: str | None = Field(
        default=None, description=_TARGET_DATE_DESCRIPTION
    )
    min_coverage: _Coverage = Field(
        default=DEFAULT_MIN_COVERAGE, description=_MIN_COVERAGE_DESCRIPTION
    )


class AnalyzeTimeseriesStep(_Step):
    """Summarizes each place's series and compares the places.

    Attributes:
        script: Always `"analyze_timeseries"`.
        table: The fetched or derived table to analyze.
        places: The places to include, or `None` for every place.
        start_date: The inclusive start of the window, or `None` when the
            window is open at the start.
        end_date: The inclusive end of the window, or `None` when the window
            is open at the end.
    """

    script: Literal["analyze_timeseries"] = Field(
        description="The analytical script this step runs."
    )
    table: _TableReference = Field(description=_TABLE_DESCRIPTION)
    places: list[str] | None = Field(
        default=None, description=_PLACES_DESCRIPTION
    )
    start_date: str | None = Field(
        default=None, description=_START_DATE_DESCRIPTION
    )
    end_date: str | None = Field(
        default=None, description=_END_DATE_DESCRIPTION
    )


class RankCohortStep(_Step):
    """Ranks the places of a cohort at its reference date.

    Attributes:
        script: Always `"rank_cohort"`.
        table: The table or aligned cohort to rank.
        direction: `desc` ranks the largest value first, `asc` the smallest.
        n: The most entries listed at each end of the ranking.
        focal_places: Places reported wherever they rank; when empty, the
            specification's `focal_places` are used.
        target_date: The date to align a table to, or `None` to select the
            most recent date with adequate coverage.
        min_coverage: The share of the cohort's places that must have a
            value on the reference date.
    """

    script: Literal["rank_cohort"] = Field(
        description="The analytical script this step runs."
    )
    table: _TableReference = Field(description=_TABLE_DESCRIPTION)
    direction: RankingDirection = Field(
        default="desc",
        description=(
            "rank_cohort: desc ranks the largest value first, asc the "
            "smallest. One step reports both the leading and the trailing "
            "tail."
        ),
    )
    n: int = Field(
        default=DEFAULT_MAX_ENTRIES_PER_END,
        ge=1,
        description=(
            "rank_cohort: how many places each tail reports (default "
            f"{DEFAULT_MAX_ENTRIES_PER_END})."
        ),
    )
    focal_places: list[str] = Field(
        default_factory=list, description=_FOCAL_PLACES_DESCRIPTION
    )
    target_date: str | None = Field(
        default=None, description=_TARGET_DATE_DESCRIPTION
    )
    min_coverage: _Coverage = Field(
        default=DEFAULT_MIN_COVERAGE, description=_MIN_COVERAGE_DESCRIPTION
    )


class SummarizeDistributionStep(_Step):
    """Summarizes the spread of a cohort's values at its reference date.

    Attributes:
        script: Always `"summarize_distribution"`.
        table: The table or aligned cohort to summarize.
        weights: The table or aligned cohort to weight the mean by, or
            `None` for no weighted mean.
        focal_places: Places benchmarked against the cohort; when empty, the
            specification's `focal_places` are used.
        target_date: The date to align a table to, or `None` to select the
            most recent date with adequate coverage.
        min_coverage: The share of the cohort's places that must have a
            value on the reference date.
    """

    script: Literal["summarize_distribution"] = Field(
        description="The analytical script this step runs."
    )
    table: _TableReference = Field(description=_TABLE_DESCRIPTION)
    weights: _TableReference | None = Field(
        default=None,
        description=(
            "summarize_distribution: an optional table, such as population, "
            "to weight the mean by."
        ),
    )
    focal_places: list[str] = Field(
        default_factory=list, description=_FOCAL_PLACES_DESCRIPTION
    )
    target_date: str | None = Field(
        default=None, description=_TARGET_DATE_DESCRIPTION
    )
    min_coverage: _Coverage = Field(
        default=DEFAULT_MIN_COVERAGE, description=_MIN_COVERAGE_DESCRIPTION
    )


class ComputeCompositionStep(_Step):
    """Computes component shares of a total, or transitions across stages.

    Attributes:
        script: Always `"compute_composition"`.
        components: The component tables or cohorts, or the ordered stages.
        total: The total table or cohort, or `None` to take shares of the
            components' sum.
        mode: `composition` for shares of a total, `stages` for transitions
            across ordered stages.
        places: The target places, or `None` to derive them from the inputs.
        target_date: The date to evaluate every input on, or `None` to
            select the most recent date with adequate coverage.
        min_coverage: The share of the target places that must have a value
            in every input on the reference date.
    """

    script: Literal["compute_composition"] = Field(
        description="The analytical script this step runs."
    )
    components: list[_TableReference] = Field(
        min_length=1,
        description=(
            "compute_composition: the component tables, or the ordered "
            "stage tables in stages mode."
        ),
    )
    total: _TableReference | None = Field(
        default=None,
        description="compute_composition: the optional total table.",
    )
    mode: CompositionMode = Field(
        default="composition",
        description=(
            "compute_composition: 'composition' for shares of a total, "
            "'stages' for transitions across ordered tiers."
        ),
    )
    places: list[str] | None = Field(
        default=None, description=_PLACES_DESCRIPTION
    )
    target_date: str | None = Field(
        default=None, description=_TARGET_DATE_DESCRIPTION
    )
    min_coverage: _Coverage = Field(
        default=DEFAULT_MIN_COVERAGE, description=_MIN_COVERAGE_DESCRIPTION
    )


class ComputeDerivedMetricStep(_Step):
    """Derives one table from two by joining on place and date.

    Attributes:
        script: Always `"compute_derived_metric"`.
        left: The numerator, minuend, or later-value table.
        right: The denominator, subtrahend, or baseline table.
        operation: How `left` and `right` combine.
        scale: The multiplier of a quotient, or `None` for the script's
            default scale.
        derived_variable_dcid: The derived variable's identifier, or `None`
            for one built from the inputs.
        derived_variable_name: The derived variable's display name, or
            `None` for one built from the input names.
        derived_unit: The unit of the derived values, or `None` for the unit
            the operation implies.
        places: The target places, or `None` to take them from the inputs.
        start_date: The inclusive start of the window, or `None` when the
            window is open at the start.
        end_date: The inclusive end of the window, or `None` when the window
            is open at the end.
        min_coverage: When above zero, the share of the target places that
            must have at least one derived row.
    """

    script: Literal["compute_derived_metric"] = Field(
        description="The analytical script this step runs."
    )
    left: _TableReference = Field(
        description="compute_derived_metric: the numerator or left table."
    )
    right: _TableReference = Field(
        description="compute_derived_metric: the denominator or right table."
    )
    operation: DerivedOperation = Field(
        default="ratio",
        description="compute_derived_metric: how left and right combine.",
    )
    scale: float | None = Field(
        default=None,
        description=(
            "compute_derived_metric: the multiplier of a quotient, such as "
            "100 for a percentage. Omit it for per_capita and the server "
            "picks per person, per 1,000, or per 100,000 people, whichever "
            "fits the values."
        ),
    )
    derived_variable_dcid: str | None = Field(
        default=None,
        description="compute_derived_metric: an id for the derived variable.",
    )
    derived_variable_name: str | None = Field(
        default=None,
        description=(
            "compute_derived_metric: a display name for the derived variable."
        ),
    )
    derived_unit: str | None = Field(
        default=None,
        description=("compute_derived_metric: the unit of the derived values."),
    )
    places: list[str] | None = Field(
        default=None, description=_PLACES_DESCRIPTION
    )
    start_date: str | None = Field(
        default=None, description=_START_DATE_DESCRIPTION
    )
    end_date: str | None = Field(
        default=None, description=_END_DATE_DESCRIPTION
    )
    min_coverage: _Coverage = Field(
        default=0.0, description=_MIN_COVERAGE_DESCRIPTION
    )


class RelateCohortsStep(_Step):
    """Summarizes one cohort variable over the places ranked by another.

    Attributes:
        script: Always `"relate_cohorts"`.
        target: The table or cohort summarized in each group.
        by: The table or cohort that orders the places into groups.
        n: The requested size of each group.
        target_date: The date to align `target` to, or `None` to select its
            most recent date with adequate coverage.
        by_date: The date to align `by` to, or `None` to select its most
            recent date with adequate coverage.
        min_coverage: The share of each input's places that must have a
            value on its reference date, and the share of each aligned
            input's places that the shared places must make up.
    """

    script: Literal["relate_cohorts"] = Field(
        description="The analytical script this step runs."
    )
    target: _TableReference = Field(
        description=(
            "relate_cohorts: the table whose values are summarized in each "
            "group, such as diabetes prevalence across counties."
        )
    )
    by: _TableReference = Field(
        description=(
            "relate_cohorts: the table whose values order the places into "
            "the highest and the lowest group, such as median household "
            "income across the same counties. Must differ from target."
        )
    )
    n: int = Field(
        default=DEFAULT_MAX_ENTRIES_PER_END,
        ge=1,
        description=(
            "relate_cohorts: how many places each group holds (default "
            f"{DEFAULT_MAX_ENTRIES_PER_END}), "
            "at most half of the places both tables cover."
        ),
    )
    target_date: str | None = Field(
        default=None,
        description=(
            "relate_cohorts: the date to align target to instead of its most "
            "recent date with adequate coverage."
        ),
    )
    by_date: str | None = Field(
        default=None,
        description=(
            "relate_cohorts: the date to align by to instead of its most "
            "recent date with adequate coverage."
        ),
    )
    min_coverage: _Coverage = Field(
        default=DEFAULT_MIN_COVERAGE,
        description=(
            "relate_cohorts: the share, from 0 to 1 (default "
            f"{DEFAULT_MIN_COVERAGE}), of each "
            "table's places that must have a value on its reference date, "
            "and the share of each aligned table's places that the shared "
            "places must make up."
        ),
    )


SpecificationStep = Annotated[
    AlignCohortStep
    | AnalyzeTimeseriesStep
    | RankCohortStep
    | SummarizeDistributionStep
    | ComputeCompositionStep
    | ComputeDerivedMetricStep
    | RelateCohortsStep,
    Field(discriminator="script"),
]


class AnalysisSpecification(BaseModel):
    """The analysis the model asks processing to run on the cached tables.

    Attributes:
        steps: The steps in execution order, at most six.
        findings: The model's notes on why these variables and tables were
            chosen. They are kept for the turn record and are not part of
            the digest, which holds only computed figures.
        missing: Indicators or dimensions the question asked for that Data
            Commons does not have.
        focal_places: The places the question is about, reported by the
            ranking and distribution steps that name none of their own.
    """

    model_config = ConfigDict(extra="forbid")

    steps: list[SpecificationStep] = Field(
        min_length=1,
        max_length=_MAX_SPECIFICATION_STEPS,
        description="At most six steps, in execution order.",
    )
    findings: list[str] = Field(
        default_factory=list,
        description=(
            "Optional short notes on why these variables and tables were "
            "chosen, for the turn record. They are not shown to the reader; "
            "never put figures in them, the server computes those."
        ),
    )
    missing: list[str] = Field(
        default_factory=list,
        description=(
            "Indicators or dimensions the question asked for that Data "
            "Commons does not have."
        ),
    )
    focal_places: list[str] = Field(
        default_factory=list,
        description=(
            "Place DCIDs the question is about, reported wherever they rank."
        ),
    )

    def list_referenced_table_ids(self) -> tuple[str, ...]:
        """Returns the fetched table ids the steps reference.

        Returns:
            The `t<n>` ids, each once, in the order the steps first reference
            them.
        """
        return tuple(
            dict.fromkeys(
                reference
                for step in self.steps
                for _, reference in list_step_inputs(step)
                if reference.startswith(FETCHED_TABLE_PREFIX)
            )
        )

    def list_script_names(self) -> list[str]:
        """Returns the script of each step.

        Returns:
            One script name per step, in step order.
        """
        return [step.script for step in self.steps]

    def find_step(self, step_id: str) -> SpecificationStep | None:
        """Returns the step with an id.

        Args:
            step_id: Identifier of the analysis step (for example, `"s1"`).

        Returns:
            The step, or None when no step has the id.
        """
        return next(
            (step for step in self.steps if step.step_id == step_id), None
        )


class UnavailableReport(BaseModel):
    """The structured note the model files when the data does not exist.

    Attributes:
        searched_indicators: The indicator queries and DCIDs tried.
        searched_places: The places the search covered.
        reason: Why the question cannot be answered from the data.
        related_available: Related indicators that do have data.
    """

    model_config = ConfigDict(extra="forbid")

    searched_indicators: list[str] = Field(
        default_factory=list,
        description="The indicator queries and DCIDs tried.",
    )
    searched_places: list[str] = Field(
        default_factory=list,
        description="The places the search covered.",
    )
    reason: str = Field(
        min_length=1,
        description="Why the question cannot be answered from the data.",
    )
    related_available: list[str] = Field(
        default_factory=list,
        description="Related indicators that do have data.",
    )

    def format_note(self) -> str:
        """Renders the report as one missing-data note for the digest.

        Returns:
            The reason, followed by a sentence for each non-empty list: the
            searched indicators, the searched places, and the related data
            available, each list in full.
        """
        parts = [self.reason]
        if self.searched_indicators:
            parts.append(f"Searched: {', '.join(self.searched_indicators)}.")
        if self.searched_places:
            parts.append(f"Places: {', '.join(self.searched_places)}.")
        if self.related_available:
            parts.append(
                f"Related data available: {', '.join(self.related_available)}."
            )
        return " ".join(parts)


def build_specification_declarations() -> list[types.FunctionDeclaration]:
    """Builds the Gemini declarations of the two functions that end discovery.

    Returns:
        The `submit_specification` declaration, generated from
        `AnalysisSpecification`, then the `report_unavailable` declaration,
        generated from `UnavailableReport`, each schema built by
        `build_parameters_schema`.
    """
    return [
        types.FunctionDeclaration(
            name=SUBMIT_SPECIFICATION,
            description=_SUBMIT_SPECIFICATION_DESCRIPTION,
            parameters_json_schema=build_parameters_schema(
                AnalysisSpecification
            ),
        ),
        types.FunctionDeclaration(
            name=REPORT_UNAVAILABLE,
            description=_REPORT_UNAVAILABLE_DESCRIPTION,
            parameters_json_schema=build_parameters_schema(UnavailableReport),
        ),
    ]


def list_step_inputs(step: SpecificationStep) -> tuple[tuple[str, str], ...]:
    """Lists the table references a step reads.

    Args:
        step: The step to inspect.

    Returns:
        `(field, reference)` pairs in the order the script takes its inputs:
        `left` then `right`, `target` then `by`, each component then any
        `total`, `table` then any `weights`, or the single `table`.
    """
    match step:
        case ComputeDerivedMetricStep():
            return (("left", step.left), ("right", step.right))
        case RelateCohortsStep():
            return (("target", step.target), ("by", step.by))
        case ComputeCompositionStep():
            total = (("total", step.total),) if step.total is not None else ()
            return (
                *(("components", item) for item in step.components),
                *total,
            )
        case SummarizeDistributionStep():
            weights = (
                (("weights", step.weights),) if step.weights is not None else ()
            )
            return (("table", step.table), *weights)
        case _:
            return (("table", step.table),)


def list_reference_table_ids(
    specification: AnalysisSpecification,
    reference: str,
    reader: SpecificationStep,
) -> tuple[str, ...]:
    """Lists the cached table ids one step input reference reads.

    A reference to a fetched table, or to the table a
    `compute_derived_metric` step derives, names that table. A reference to
    any other earlier step, such as an `align_cohort` step, names the
    tables that step reads, followed through the steps it reads in turn.
    Only steps before `reader` are followed, as `validate_specification`
    requires, so a reference to the reader itself or to a later step names
    itself and the walk always ends.

    Args:
        specification: The specification that holds `reader`.
        reference: A table id or step id from `list_step_inputs(reader)`.
        reader: The step whose input `reference` is.

    Returns:
        The `t<n>` and `s<n>` table ids, each once, in input order, or the
        reference itself when it names no earlier step.

    Raises:
        ValueError: If no step of `specification` equals `reader`.
    """
    try:
        position = specification.steps.index(reader)
    except ValueError as error:
        raise ValueError(
            f"Step {reader.step_id} is not a step of this specification."
        ) from error
    earlier = specification.steps[:position]
    source = next((step for step in earlier if step.step_id == reference), None)
    if source is None or isinstance(source, ComputeDerivedMetricStep):
        return (reference,)
    return list_step_table_ids(specification, source)


def list_step_table_ids(
    specification: AnalysisSpecification, step: SpecificationStep
) -> tuple[str, ...]:
    """Lists the cached table ids a step reads, through the steps it reads.

    Args:
        specification: The specification that holds `step`.
        step: The step to inspect.

    Returns:
        The `t<n>` and `s<n>` table ids of every input, as
        `list_reference_table_ids` resolves them, each once, in input order.

    Raises:
        ValueError: If no step of `specification` equals `step`.
    """
    return tuple(
        dict.fromkeys(
            table_id
            for _, reference in list_step_inputs(step)
            for table_id in list_reference_table_ids(
                specification, reference, step
            )
        )
    )


def get_step_output_kind(step: SpecificationStep) -> StepOutputKind:
    """Returns what a step makes available to later steps.

    Args:
        step: The step to inspect.

    Returns:
        `cohort` for `align_cohort`, `table` for `compute_derived_metric`,
        and `result` for every other script, whose output no later step can
        read.
    """
    match step:
        case AlignCohortStep():
            return "cohort"
        case ComputeDerivedMetricStep():
            return "table"
        case _:
            return "result"


def _get_input_kind(step: SpecificationStep) -> _InputKind:
    """Returns whether a step's inputs accept an aligned cohort."""
    match step:
        case (
            AlignCohortStep()
            | AnalyzeTimeseriesStep()
            | ComputeDerivedMetricStep()
        ):
            return "table"
        case _:
            return "table_or_cohort"


def validate_specification(
    specification: AnalysisSpecification, cache: TurnCache
) -> str | None:
    """Checks a specification, which is model output, against the cache.

    Pydantic has already checked each step's field types, `Literal` values,
    reference patterns, and bounds. This function checks what Pydantic
    cannot: step ids are unique and sequential; every `t<n>` names a cached
    table and every `s<n>` a strictly earlier step whose output the
    consuming step accepts; every `align_cohort` step is consumed by a later
    step, because an alignment produces no result of its own; no
    `relate_cohorts`, `compute_derived_metric`, or `compute_composition`
    step reads one table twice, or two fetched tables of one variable,
    directly or through an alignment; every `compute_derived_metric` scale
    and derived variable id is one the script accepts; every place is a
    valid DCID; and every date is a valid observation date, with no
    inverted window. A problem names the step field and repeats only
    references, step ids, and `Literal` values, which Pydantic has already
    matched, and variable DCIDs from the cache, never a value the model
    wrote freely, such as a place, a date, a scale, or an id.

    Args:
        specification: The specification to check.
        cache: The turn's cache.

    Returns:
        `None` when the specification is valid, otherwise every problem
        found, one per line, so the model can correct them all at once.
    """
    problems = [
        *_validate_step_ids(specification.steps),
        *_validate_references(specification.steps, cache),
        *_validate_alignments_are_used(specification.steps),
        *_validate_distinct_inputs(specification.steps, cache),
        *_validate_derived_parameters(specification.steps),
        *_validate_places(specification),
        *_validate_dates(specification.steps),
    ]
    if not problems:
        return None
    return "\n".join(problems)


def _validate_step_ids(steps: Sequence[SpecificationStep]) -> list[str]:
    """Reports repeated step ids and step ids out of sequence."""
    problems: list[str] = []
    seen: set[str] = set()
    for position, step in enumerate(steps, start=1):
        if step.step_id in seen:
            problems.append(f"step_id {step.step_id} is used more than once.")
        seen.add(step.step_id)
        expected = f"{DERIVED_TABLE_PREFIX}{position}"
        if step.step_id != expected:
            problems.append(
                f"step_id {step.step_id} is out of order; step {position} "
                f"must be {expected}."
            )
    return problems


def _validate_references(
    steps: Sequence[SpecificationStep], cache: TurnCache
) -> list[str]:
    """Reports every input reference no earlier step or cached table meets."""
    problems: list[str] = []
    outputs: dict[str, StepOutputKind] = {}
    for step in steps:
        for field_name, reference in list_step_inputs(step):
            problem = _validate_reference(
                step, field_name, reference, outputs, cache
            )
            if problem is not None:
                problems.append(problem)
        outputs[step.step_id] = get_step_output_kind(step)
    return problems


def _validate_reference(
    step: SpecificationStep,
    field_name: str,
    reference: str,
    outputs: dict[str, StepOutputKind],
    cache: TurnCache,
) -> str | None:
    """Returns the problem with one input reference, or `None`.

    Args:
        step: The step that holds the reference.
        field_name: The step field that holds the reference.
        reference: A `t<n>` or `s<n>` reference.
        outputs: The output kind of each earlier step, by step id.
        cache: The turn's cache.
    """
    label = f"{step.step_id}.{field_name}"
    if reference.startswith(FETCHED_TABLE_PREFIX):
        if cache.get(reference) is not None:
            return None
        cached = ", ".join(
            entry.table_id for entry in cache.list_fetched_tables()
        )
        return (
            f"{label} references {reference}, which is not a cached "
            f"table; the cached tables are {cached or 'none'}."
        )
    if reference == step.step_id:
        return f"{label} references the step itself."
    kind = outputs.get(reference)
    if kind is None:
        return (
            f"{label} references {reference}, which is not the output of an "
            "earlier step; a step may only use steps that run before it."
        )
    if kind == "result":
        return (
            f"{label} references {reference}, whose script produces only a "
            "result; only align_cohort and compute_derived_metric outputs "
            "can be used as inputs."
        )
    if kind == "cohort" and _get_input_kind(step) == "table":
        return (
            f"{label} references the aligned cohort {reference}, but "
            f"{step.script} needs a full table (t<n> or a "
            "compute_derived_metric output)."
        )
    return None


def _validate_alignments_are_used(
    steps: Sequence[SpecificationStep],
) -> list[str]:
    """Reports every `align_cohort` step that no step references."""
    referenced = {
        reference for step in steps for _, reference in list_step_inputs(step)
    }
    return [
        f"{step.step_id} (align_cohort) is not used by a later step; an "
        "alignment produces no result on its own, so reference it from "
        "rank_cohort, summarize_distribution, compute_composition, or "
        "relate_cohorts, or remove it."
        for step in steps
        if isinstance(step, AlignCohortStep) and step.step_id not in referenced
    ]


def _validate_distinct_inputs(
    steps: Sequence[SpecificationStep], cache: TurnCache
) -> list[str]:
    """Reports every multi-input step that reads one table or variable twice.

    `relate_cohorts`, `compute_derived_metric`, and `compute_composition`
    each refuse two inputs of one variable. Each input is followed through
    the `align_cohort` step that produced it, so an alignment of `t1` read
    beside `t1` is caught.
    """
    problems: list[str] = []
    aligned_tables: dict[str, str] = {}
    for step in steps:
        if isinstance(
            step,
            RelateCohortsStep
            | ComputeDerivedMetricStep
            | ComputeCompositionStep,
        ):
            problem = _validate_distinct_step_inputs(
                step, aligned_tables, cache
            )
            if problem is not None:
                problems.append(problem)
        if isinstance(step, AlignCohortStep):
            aligned_tables[step.step_id] = step.table
    return problems


def _validate_distinct_step_inputs(
    step: SpecificationStep,
    aligned_tables: dict[str, str],
    cache: TurnCache,
) -> str | None:
    """Returns the first repeated table or variable among a step's inputs.

    Args:
        step: The multi-input step.
        aligned_tables: The table each earlier alignment step aligned, by
            step id.
        cache: The turn's cache.
    """
    inputs = [
        (field_name, reference, aligned_tables.get(reference, reference))
        for field_name, reference in list_step_inputs(step)
    ]
    label = f"{step.step_id} ({step.script})"
    for index, (field_name, reference, table_id) in enumerate(inputs):
        for other_field, other_reference, other_id in inputs[index + 1 :]:
            if table_id != other_id:
                continue
            if field_name == other_field:
                return (
                    f"{label} lists one table twice in {field_name} "
                    f"({reference} and {other_reference}); name different "
                    "tables."
                )
            return (
                f"{label} uses one table as both {field_name} and "
                f"{other_field} ({reference} and {other_reference}); name "
                "two different tables."
            )
    tables_by_variable: dict[str, str] = {}
    for _, _, table_id in inputs:
        # A derived or missing input has no fetched variable to compare; a
        # missing table is reported by `_validate_references`.
        entry = (
            cache.get(table_id)
            if table_id.startswith(FETCHED_TABLE_PREFIX)
            else None
        )
        if entry is None:
            continue
        variable = entry.table.variable_dcid
        earlier = tables_by_variable.setdefault(variable, table_id)
        if earlier != table_id:
            return (
                f"{label} reads {variable} from both {earlier} and "
                f"{table_id}; name tables of different variables."
            )
    return None


def _validate_derived_parameters(
    steps: Sequence[SpecificationStep],
) -> list[str]:
    """Reports every derived-metric scale or variable id the script refuses.

    A problem names the step field, never the value the model sent.
    """
    scaled_operations = " and ".join(sorted(SCALED_OPERATIONS))
    problems: list[str] = []
    for step in steps:
        if not isinstance(step, ComputeDerivedMetricStep):
            continue
        if step.scale is not None:
            if step.operation not in SCALED_OPERATIONS:
                problems.append(
                    f"{step.step_id}.scale applies only to {scaled_operations},"
                    f" not {step.operation}."
                )
            elif not math.isfinite(step.scale) or step.scale <= 0.0:
                problems.append(
                    f"{step.step_id}.scale must be a finite number above zero."
                )
        if step.derived_variable_dcid is not None and not is_valid_dcid(
            step.derived_variable_dcid
        ):
            problems.append(
                f"{step.step_id}.derived_variable_dcid must be a valid DCID."
            )
    return problems


def _list_place_fields(
    step: SpecificationStep,
) -> tuple[tuple[str, Sequence[str]], ...]:
    """Lists a step's place-list fields that are set, by field name."""
    match step:
        case RankCohortStep() | SummarizeDistributionStep():
            return (("focal_places", step.focal_places),)
        case (
            AnalyzeTimeseriesStep()
            | ComputeCompositionStep()
            | ComputeDerivedMetricStep()
        ):
            return (("places", step.places),) if step.places is not None else ()
        case _:
            return ()


def _validate_places(specification: AnalysisSpecification) -> list[str]:
    """Reports every place list that holds an invalid DCID.

    `validate_place_dcids` names an invalid entry by its position, so the
    model's string is never repeated.
    """
    place_lists: list[tuple[str, Sequence[str]]] = [
        ("focal_places", specification.focal_places),
        *(
            (f"{step.step_id}.{field_name}", places)
            for step in specification.steps
            for field_name, places in _list_place_fields(step)
        ),
    ]
    problems: list[str] = []
    for parameter_name, places in place_lists:
        problem = validate_place_dcids(places, parameter_name=parameter_name)
        if problem is not None:
            problems.append(problem)
    return problems


def _list_date_fields(
    step: SpecificationStep,
) -> tuple[tuple[str, str | None], ...]:
    """Lists a step's date fields, by field name, set or not."""
    match step:
        case AnalyzeTimeseriesStep() | ComputeDerivedMetricStep():
            return (
                ("start_date", step.start_date),
                ("end_date", step.end_date),
            )
        case RelateCohortsStep():
            return (
                ("target_date", step.target_date),
                ("by_date", step.by_date),
            )
        case _:
            return (("target_date", step.target_date),)


def _validate_dates(steps: Sequence[SpecificationStep]) -> list[str]:
    """Reports every invalid date and every inverted window.

    A problem names the step field, never the date the model sent.
    """
    problems: list[str] = []
    for step in steps:
        dates = _list_date_fields(step)
        invalid = [
            field_name
            for field_name, date in dates
            if date is not None and not is_valid_observation_date(date)
        ]
        problems.extend(
            f"{step.step_id}.{field_name} must be a YYYY, YYYY-MM, or "
            "YYYY-MM-DD date."
            for field_name in invalid
        )
        if (
            isinstance(step, AnalyzeTimeseriesStep | ComputeDerivedMetricStep)
            and not invalid
            and step.start_date is not None
            and step.end_date is not None
            and is_inverted_date_range(step.start_date, step.end_date)
        ):
            problems.append(
                f"{step.step_id}.start_date is after {step.step_id}.end_date."
            )
    return problems


def _is_rankable_table(table: ObservationTable) -> bool:
    """Returns whether a table has enough places to rank or relate.

    This rule is looser than `_is_fetched_cohort` on purpose: three named
    places can already be ranked or related, while a trend over a few
    named places still reads best as a series summary.
    """
    return (
        table.child_place_type is not None
        or len(table.places_with_data) >= _RANKABLE_PLACE_COUNT
    )


def _is_fetched_cohort(table: ObservationTable) -> bool:
    """Returns whether a table is a cohort by the rule the fetches apply.

    A child-place fetch is always a cohort, and a named-place fetch is one
    when `is_named_place_cohort` says so for its requested places, the
    count the fetch itself used to choose its date window.
    """
    return table.child_place_type is not None or is_named_place_cohort(
        len(table.requested_places)
    )


def _list_default_tables(
    cache: TurnCache, excluded_table_ids: frozenset[str]
) -> list[CachedTable]:
    """Returns the fetched tables with rows outside `excluded_table_ids`.

    `list_fetched_tables` returns the tables in fetch order, which the
    default specification keeps.
    """
    return [
        entry
        for entry in cache.list_fetched_tables()
        if entry.table.rows and entry.table_id not in excluded_table_ids
    ]


def _select_table_script(
    pattern: QueryPattern | None, table: ObservationTable
) -> _DefaultTableScript:
    """Returns the script the default specification runs on one table.

    The pattern's script applies only when the table has the shape it
    needs. A distribution needs a rankable table. A single point or a trend
    ranks only a fetched cohort, so a trend for a few named places keeps
    its series summary. Otherwise a rankable table is ranked and any other
    table gets a series summary.

    A composition or stages question never gets `compute_composition`: the
    default runs over tables the model did not finish choosing, which may
    hold only some components, and nothing here can tell a total from a
    component, so a composition could report shares of a meaningless sum.
    """
    if pattern == "distribution" and _is_rankable_table(table):
        return "summarize_distribution"
    if pattern in ("single_point", "trend_delta"):
        if _is_fetched_cohort(table):
            return "rank_cohort"
        return "analyze_timeseries"
    return "rank_cohort" if _is_rankable_table(table) else "analyze_timeseries"


def _build_table_step(
    step_id: str, table_id: str, script: _DefaultTableScript
) -> SpecificationStep:
    """Builds the single-table step that runs `script` on a table."""
    if script == "rank_cohort":
        return RankCohortStep(
            step_id=step_id, script="rank_cohort", table=table_id
        )
    if script == "summarize_distribution":
        return SummarizeDistributionStep(
            step_id=step_id, script="summarize_distribution", table=table_id
        )
    return AnalyzeTimeseriesStep(
        step_id=step_id, script="analyze_timeseries", table=table_id
    )


def _build_cohort_key(
    table: ObservationTable,
) -> tuple[str | None, str | None, frozenset[str]]:
    """Identifies a table's cohort: its parent and child type, or its places.

    Named places are identified by the places requested, as
    `resolve_target_places` does, so two variables fetched for one list of
    places share a cohort even when one has no data for some of them.
    """
    if table.parent_place_dcid and table.child_place_type:
        return (table.parent_place_dcid, table.child_place_type, frozenset())
    return (
        None,
        None,
        frozenset(table.requested_places or table.places_with_data),
    )


def _count_shared_places(
    first: ObservationTable, second: ObservationTable
) -> int:
    """Returns how many places have data in both tables."""
    return len(set(first.places_with_data) & set(second.places_with_data))


def _find_related_pair(
    tables: Sequence[CachedTable],
) -> tuple[CachedTable, CachedTable] | None:
    """Returns the earliest two same-cohort tables of different variables.

    `tables` is in fetch order, so the pair is the earliest by fetch. A
    refetch of one variable from another facet shares the first fetch's
    cohort, and relating the two would summarize a variable over its own
    ranking, so tables of the same variable never pair. Two tables with
    data for fewer than `MIN_SHARED_PLACES` common places never pair either,
    because `relate_cohorts` always refuses them.

    Returns:
        The earlier-fetched table, then the later one, or `None` when no two
        rankable tables share a cohort and enough places with data, and
        differ in variable.
    """
    rankable = [entry for entry in tables if _is_rankable_table(entry.table)]
    for index, first in enumerate(rankable):
        key = _build_cohort_key(first.table)
        for second in rankable[index + 1 :]:
            if (
                _build_cohort_key(second.table) == key
                and second.table.variable_dcid != first.table.variable_dcid
                and _count_shared_places(first.table, second.table)
                >= MIN_SHARED_PLACES
            ):
                return first, second
    return None


def _build_relation_step(
    tables: Sequence[CachedTable],
) -> RelateCohortsStep | None:
    """Builds the default relation of the earliest related pair, or `None`.

    The earlier-fetched table is `by` and the later one `target`; the
    relation's coverage check is symmetric, so the assignment does not
    decide whether the step passes.
    """
    pair = _find_related_pair(tables)
    if pair is None:
        return None
    by, target = pair
    return RelateCohortsStep(
        step_id=f"{DERIVED_TABLE_PREFIX}1",
        script="relate_cohorts",
        target=target.table_id,
        by=by.table_id,
    )


def _build_table_steps(
    tables: Sequence[CachedTable],
    pattern: QueryPattern | None,
    *,
    first_position: int,
) -> list[SpecificationStep]:
    """Builds one single-table step per table, numbered from a position.

    Only the earliest tables that fit within `_MAX_SPECIFICATION_STEPS`
    steps get one; `tables` is in fetch order, so the latest are dropped.
    """
    room = _MAX_SPECIFICATION_STEPS - first_position + 1
    return [
        _build_table_step(
            f"{DERIVED_TABLE_PREFIX}{position}",
            entry.table_id,
            _select_table_script(pattern, entry.table),
        )
        for position, entry in enumerate(tables[:room], start=first_position)
    ]


def build_default_specification(
    classification: QueryClassification | None,
    cache: TurnCache,
    *,
    should_relate: bool = True,
    excluded_table_ids: frozenset[str] = frozenset(),
) -> AnalysisSpecification | None:
    """Builds a specification over the fetched tables when the model gave none.

    Every non-empty fetched table gets one single-table step, in fetch
    order, so no fetched variable is lost. Each table's script comes from
    the classification's pattern when the table has the shape that script
    needs, and from the table's shape otherwise (`_select_table_script`).

    For a correlation question, when two non-empty rankable tables of
    different variables share a cohort and at least `MIN_SHARED_PLACES`
    places with data, the earliest two are related first with
    `relate_cohorts`. The per-table steps follow, including those for
    the two related tables, so each variable's own ranking is reported.
    Processing stops at the first refused step, so a caller whose relation
    refused builds the default again with `should_relate=False`, and a
    caller whose single-table step refused builds it again with that table
    in `excluded_table_ids`.

    At most six steps are emitted, the specification's limit. When the tables
    need more, the relation step and the earliest-fetched tables are kept
    and the latest-fetched tables are dropped.

    Args:
        classification: The query's classification, or `None` when it is
            not available.
        cache: The turn's cache.
        should_relate: Whether a correlation question gets the relation
            step.
        excluded_table_ids: Fetched table ids to leave out, such as tables
            whose steps refused in an earlier run of the default.

    Returns:
        The specification, or `None` when no fetched table outside
        `excluded_table_ids` has rows.
    """
    tables = _list_default_tables(cache, excluded_table_ids)
    if not tables:
        return None
    pattern = classification.pattern if classification is not None else None
    relation = (
        _build_relation_step(tables)
        if should_relate and pattern == "correlation"
        else None
    )
    steps: list[SpecificationStep] = [relation] if relation is not None else []
    steps.extend(
        _build_table_steps(tables, pattern, first_position=len(steps) + 1)
    )
    return AnalysisSpecification(steps=steps)

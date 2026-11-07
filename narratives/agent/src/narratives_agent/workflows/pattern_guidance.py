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
"""Maps a query classification to the directive appended to a system prompt.

Each pattern has two directives: the discovery directive names the fetch
functions and analytical scripts the discovery loop uses, and the synthesis
directive says how the answer presents the result. Each phase receives only
its own, so the synthesis model is never handed tool calls it cannot make.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, assert_never

from narratives_agent.gemini.schemas import QueryClassification, QueryPattern

__all__ = [
    "Directive",
    "DirectivePhase",
    "append_pattern_guidance",
    "build_pattern_directive",
]

_DIRECTIVE_HEADING = "### Analytical directive for this question"

# The phase a directive is rendered for.
type DirectivePhase = Literal["discovery", "synthesis"]


@dataclass(frozen=True)
class Directive:
    """The two halves of one pattern's guidance.

    Attributes:
        discovery: The fetch functions and scripts the discovery loop uses.
        synthesis: How the answer presents the computed result.
    """

    discovery: str
    synthesis: str

    def get_phase_text(self, phase: DirectivePhase) -> str:
        """Returns the half that applies to `phase`.

        Args:
            phase: The phase the directive is rendered for.

        Returns:
            The discovery half for `"discovery"` and the synthesis half for
            `"synthesis"`.
        """
        match phase:
            case "discovery":
                return self.discovery
            case "synthesis":
                return self.synthesis
            case _:
                assert_never(phase)


# One directive per pattern.
_DIRECTIVES: Mapping[QueryPattern, Directive] = {
    "single_point": Directive(
        discovery=(
            'Choose the indicator and its closest companions as "Choosing '
            'indicators" describes, fetch them for the named place with '
            "`fetch_observations` in the same round, and specify "
            "`analyze_timeseries` on each table."
        ),
        synthesis=(
            "Lead directly with the exact statistical value, its unit of "
            "measurement, its observation date, and the official statistical "
            "agency that published it. When the digest also holds the "
            "indicator's companions, such as its female and male forms, "
            "report them after the headline as supporting figures, never "
            "first."
        ),
    ),
    "top_n_ranking": Directive(
        discovery=(
            "Fetch the cohort with `fetch_child_observations` and specify "
            "`rank_cohort` with the question's `n` and `direction`; one "
            "`rank_cohort` step reports both the leading and the trailing "
            'tail of its table. When "Choosing indicators" calls for a '
            "per-person figure, rank that table: the published rate, or the "
            "`per_capita` derived table. When the question ranks a change "
            "over a period (the largest gains since 2020, the fastest growth "
            "over the decade), specify `reduce_series` on the cohort table "
            "and `rank_cohort` on its output, with the `metric` the change "
            "calls for: `percent_change`, `absolute_change` when the "
            "indicator is itself a percentage, or `cagr` when the question "
            "asks for a growth rate. Once the cohort table is fetched, "
            "fetch the "
            "same variable for the cohort's parent place (the country for "
            "states, the state for counties, the world for countries) with "
            "`fetch_observations`, from the same source when it covers that "
            "place and with `start_date` set to the earliest year the cohort "
            "table covers, so the answer can compare the leaders with it; "
            "specify `analyze_timeseries` on that table, never include it "
            "in the ranking, and skip it when the parent place has no "
            "series. When the question asks for a second "
            "variable across places ranked by another, fetch the ranking "
            "variable and "
            "the target variable across the cohort with "
            "`fetch_child_observations` in the same round, then specify "
            "`relate_cohorts` with the target variable as `target`, the "
            "ranking variable as `by`, and the question's `n`, together with "
            "`rank_cohort` on each table."
        ),
        synthesis=(
            "Answer only the end of the ranking the question asks for, as "
            '"Rankings" describes: name the top place and any tie in the '
            "headline with the shared observation year, or with both dates "
            "when the ranking covers a window from one date to another, cite "
            "the official source agency, and give every ranked place in a "
            "compact table. "
            "After the table, chart a `line` of the places the headline "
            "names, with the parent place when its table is in the table "
            "inventory, not a `ranking`. When the digest relates a "
            "second variable to the ranking, state in plain words the "
            "pattern between the two groups and any notable exception, put "
            "each group's places and figures in a compact table, and name "
            "the places the result reports as left out; chart a `ranking` "
            "for each variable, and optionally pair the two tables in a "
            "`scatter`."
        ),
    ),
    "distribution": Directive(
        discovery=(
            "Fetch the cohort with `fetch_child_observations` and specify "
            "`summarize_distribution` with the place the question names in "
            "`focal_places`, and `rank_cohort` on the same table with that "
            "place in `focal_places`, so the answer can report its rank. "
            "When the question asks how a change over a period is "
            "distributed, specify `reduce_series` on the cohort table first "
            "and run both steps on its output."
        ),
        synthesis=(
            'Compare the focal place with the cohort as "One place among its '
            'peers" describes: lead with its value, its rank, and its gap '
            "to the median in one sentence, then the highest and lowest "
            "places, all at one shared observation year or over one shared "
            "window, and chart a `bar` of the places the answer names, or a "
            "`line` of them when the comparison covers a window."
        ),
    ),
    "trend_delta": Directive(
        discovery=(
            'Choose the indicators as "Choosing indicators" describes: the '
            "named indicator and its closest companions, or one indicator "
            "for each angle of a broad concept. Fetch the full series of "
            "each with `fetch_observations` in the same round and specify "
            "`analyze_timeseries` on each table, with `start_date` and "
            "`end_date` when the question bounds the period, for one place "
            "or up to ten named places. For the change across a larger "
            "cohort, fetch it with `fetch_child_observations` and specify "
            "`reduce_series` with `percent_change`, `absolute_change` when "
            "the indicator is itself a percentage, or `cagr` when the "
            "question asks for a growth rate, followed by `rank_cohort` or "
            "`summarize_distribution` on its output."
        ),
        synthesis=(
            "Report the overall change across the period as a percentage "
            "change, or in percentage points when the indicator is itself "
            "a percentage, and name the key shifts, such as a peak, a low, "
            "or the sharpest rise or fall, in plain words. For a cohort "
            "ranked by its change, name the window's two dates and the "
            "places at the end of the ranking the question asks for, and "
            "chart their trajectories as a `line`."
        ),
    ),
    "outliers": Directive(
        discovery=(
            "Fetch the series across the target entities with "
            "`fetch_observations` or `fetch_child_observations` and specify "
            "`analyze_timeseries` for up to ten places. Across a larger "
            "cohort, specify `reduce_series` with `latest_period_change` or "
            "`latest_period_percent_change`, followed by `rank_cohort` on "
            "its output, to find the places with the largest latest spikes "
            "and drops."
        ),
        synthesis=(
            "Identify the sharpest single-period rises and falls with their "
            "change and the period they occurred in; give the values before "
            "and after only when they help the reader."
        ),
    ),
    "correlation": Directive(
        discovery=(
            "Fetch both indicators over the same places and period with "
            "`fetch_observations` or `fetch_child_observations`, one table "
            "each, in the same round. Use `compute_derived_metric` with "
            "`per_capita` only when a raw count must be normalized by a "
            "population table before the comparison, and never divide one "
            "indicator by the other. Specify `relate_cohorts` with one "
            "indicator as `target` and the other as `by`, and `rank_cohort` "
            "and `summarize_distribution` on both indicator tables; each "
            "table is aligned on its own reference date. Specify "
            "`analyze_timeseries` on both instead when comparing two "
            "trajectories of one place."
        ),
        synthesis=(
            "Pair the two tables in a `scatter` chart and write the answer "
            'as "Relationships between two measures" describes. Describe '
            "the relationship from the figures given: say in plain words how "
            "the indicators move together and name the leading place, then "
            "name the notable exception, or the place at the bottom when "
            "nothing breaks the pattern, without naming any place's ranking "
            "twice, and leave the exact figures to a compact table. Claim no "
            "strength or direction of association beyond what those figures "
            "show, and no cause. Open with that description, not with a "
            "remark about what was or was not computed."
        ),
    ),
    "composition": Directive(
        discovery=(
            "Search for the total and the components, then check them all in "
            "one `get_variable_metadata` round and choose one facet that "
            "covers every component with one set of groups that has no gaps "
            "or overlaps. Fetch the total, when that facet has one, and every "
            "component in the same round with `fetch_observations` or "
            "`fetch_child_observations` and `source_override` set to that "
            "facet, and specify `compute_composition` in `composition` mode "
            "as soon as the tables have rows."
        ),
        synthesis=(
            "Answer the question first, then give every component in a "
            "compact table, largest first, as "
            '"Breakdowns of a total" describes. '
            "Only when the question asks how "
            "one total splits into parts and the digest holds no composition "
            "result, lead with what the digest does show for the components, "
            "never with the total, and close the answer with one short "
            "sentence noting that shares of the total could not be "
            "calculated from consistent data."
        ),
    ),
    "sequential_stages": Directive(
        discovery=(
            "Search for the stages, then check them all in one "
            "`get_variable_metadata` round and choose one facet that covers "
            "every stage. Fetch one table per stage in the same round with "
            "`fetch_observations` or `fetch_child_observations`, in the order "
            "the question gives them, with `source_override` set to that "
            "facet, and specify `compute_composition` in `stages` mode with "
            "`components` in that order."
        ),
        synthesis=(
            "Report each stage's value and its share of the whole, and how "
            "much each stage keeps or loses from the one before it. Only "
            "when the question asks about ordered stages and the digest "
            "holds no stages result, lead with the stages the digest does "
            "cover and close the answer with one short sentence noting that "
            "the stage-to-stage shares could not be calculated."
        ),
    ),
    "clustering": Directive(
        discovery=(
            "Do not attempt a clustering. Fetch the requested variables for "
            "the named entities with `fetch_observations` and specify "
            "`analyze_timeseries` or `rank_cohort` as an exploratory profile."
        ),
        synthesis=(
            "Never sort places into groups or label them with tiers of your "
            'own. Open with the short clause "Caveats and missing data" '
            'describes, then compare the places as "Comparing several '
            'places" describes. Never write "clustering" or "compared '
            'rather than grouped".'
        ),
    ),
    "forecasting": Directive(
        discovery=(
            "Do not attempt a projection yourself. Search for an official "
            "projection of the indicator that a source publishes for the "
            "year asked, and fetch it when one exists. Always fetch the full "
            "historical series with `fetch_observations`, and specify "
            "`analyze_timeseries` on it and on the projection when you "
            "fetched one."
        ),
        synthesis=(
            "Never extrapolate or give a figure for a future year that the "
            "digest does not hold. When it holds a source's official "
            "projection, report it as that source's projection, then the "
            "latest figure and the trend. Otherwise open with the short "
            'clause "Caveats and missing data" describes and report the '
            "latest figure and the trend in the same sentence. Never write "
            '"no projection is performed" or "cannot predict".'
        ),
    ),
    "exploratory": Directive(
        discovery=(
            "Map the core angles of the requested topic and choose one "
            'indicator for each as "Choosing indicators" describes, up to '
            "five, one table each, fetched in the same round with "
            "`fetch_observations` or `fetch_child_observations`, and specify "
            "`analyze_timeseries` or `rank_cohort` on each."
        ),
        synthesis=(
            "Organize the indicators into a structured summary and cite the "
            "authoritative provenance of each metric."
        ),
    ),
    "data_availability": Directive(
        discovery=(
            "Survey the requested topic with `search_indicators` (with "
            "`places` naming the target place and `include_topics` enabled) "
            "and `get_variable_metadata` to learn its coverage, sources, and "
            "date ranges. Always fetch at least one representative table for "
            "the headline indicator with `fetch_observations` or "
            "`fetch_child_observations`, and specify `analyze_timeseries` or "
            "`rank_cohort` on it with `submit_specification`, recording in "
            "`missing` every sub-topic or breakdown that lacks coverage. "
            "Call `report_unavailable` only when no relevant or closely "
            "related indicator has observations for the requested place."
        ),
        synthesis=(
            "Summarize what the catalog covers for that place, with the "
            "headline figure as its anchor."
        ),
    ),
}

# Appended when the query compares a few named places side by side.
_COMPARISON_DIRECTIVE = Directive(
    discovery=(
        "Fetch the exact same indicator for every named place in one "
        "`fetch_observations` call, so that the places share one facet and "
        "year."
    ),
    synthesis=(
        "Compare the places side by side: state the pattern and the notable "
        "exception. Put the exact figures in a compact table when the "
        "comparison covers several indicators or four or more places; for "
        "one indicator across two or three places, give the figures in the "
        "sentence and write no table. State the gap between places only "
        "when the question asks for it."
    ),
)


def build_pattern_directive(
    classification: QueryClassification, phase: DirectivePhase
) -> str:
    """Returns the directive text for a classification and phase.

    Args:
        classification: The classify phase's verdict on the query.
        phase: The phase the text is rendered for.

    Returns:
        The pattern's directive for the phase, followed by the comparison
        directive for the phase when the query compares several places.
    """
    directive = _DIRECTIVES[classification.pattern].get_phase_text(phase)
    if classification.geographic_shape == "comparison":
        return f"{directive} {_COMPARISON_DIRECTIVE.get_phase_text(phase)}"
    return directive


def append_pattern_guidance(
    system_instruction: str,
    classification: QueryClassification | None,
    phase: DirectivePhase,
) -> str:
    """Appends the classification's directive to a system instruction.

    Args:
        system_instruction: The prompt body of the discovery loop or of
            synthesis.
        classification: The classify phase's verdict, or `None` when the
            classifier failed, in which case the instruction is returned
            unchanged.
        phase: Which half of the directive to append.

    Returns:
        The system instruction with the directive appended as its final
        section.
    """
    if classification is None:
        return system_instruction
    directive = build_pattern_directive(classification, phase)
    return f"{system_instruction}\n\n{_DIRECTIVE_HEADING}\n\n{directive}"

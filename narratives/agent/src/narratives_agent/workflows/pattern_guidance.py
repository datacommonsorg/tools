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
from typing import Literal

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
            The discovery half when `phase` is `"discovery"`, and the synthesis
            half otherwise.
        """
        return self.discovery if phase == "discovery" else self.synthesis


# One directive per pattern.
_DIRECTIVES: Mapping[QueryPattern, Directive] = {
    "single_point": Directive(
        discovery=(
            "Fetch the variable for the named place with "
            "`fetch_observations` and specify `analyze_timeseries` on that "
            "table."
        ),
        synthesis=(
            "Lead directly with the exact statistical value, its unit of "
            "measurement, its observation date, and the official statistical "
            "agency that published it."
        ),
    ),
    "top_n_ranking": Directive(
        discovery=(
            "Fetch the cohort with `fetch_child_observations` and specify "
            "`rank_cohort` with the question's `n` and `direction`; one "
            "`rank_cohort` step reports both the leading and the trailing "
            "tail of its table, and a question about one variable needs "
            "nothing more. When the question asks for a second variable "
            "across places ranked by another, fetch the ranking variable and "
            "the target variable across the cohort with "
            "`fetch_child_observations` in the same round, then specify "
            "`relate_cohorts` with the target variable as `target`, the "
            "ranking variable as `by`, and the question's `n`, together with "
            "`rank_cohort` on each table."
        ),
        synthesis=(
            "State the leading and trailing ranks explicitly with their "
            "exact values and the shared observation year, and cite the "
            "official source agency. Chart the ranked cohort as a `ranking` "
            "with the tail the question asked for. When the digest relates a "
            "second variable to the ranking, state in prose each group's "
            "places, its mean and median of the target variable, the "
            "difference between the two group means, and the places the "
            "result reports as left out; chart a `ranking` for each "
            "variable, and optionally pair the two tables in a `scatter`."
        ),
    ),
    "distribution": Directive(
        discovery=(
            "Fetch the cohort with `fetch_child_observations` and specify "
            "`summarize_distribution` with the place the question names in "
            "`focal_places`."
        ),
        synthesis=(
            "Describe the cohort as a whole rather than listing its members: "
            "report the median, the mean, the minimum and maximum, and the "
            "spread between them, all at one shared observation year, and "
            "say where the focal place sits within that range."
        ),
    ),
    "trend_delta": Directive(
        discovery=(
            "Fetch the full series with `fetch_observations` and specify "
            "`analyze_timeseries`, with `start_date` and `end_date` when the "
            "question bounds the period."
        ),
        synthesis=(
            "Report the overall start-to-end change as an absolute delta and "
            "as a percentage growth or decline, and point out the key "
            "inflection points across the period."
        ),
    ),
    "outliers": Directive(
        discovery=(
            "Fetch the series across the target entities with "
            "`fetch_observations` or `fetch_child_observations` and specify "
            "`analyze_timeseries`."
        ),
        synthesis=(
            "Identify the largest period-over-period spikes and drops "
            "explicitly with their exact before and after values."
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
            "Pair the two tables in a `scatter` chart. Describe the "
            "relationship from the figures given: the mean and median of the "
            "target indicator in the groups with the highest and the lowest "
            "values of the other, the difference between them, the places "
            "that rank high or low on both indicators, the ones that "
            "diverge, and the spread of each. Claim no strength or direction "
            "of association beyond what those figures show. Open with that "
            "description, not with a remark about what was or was not "
            "computed."
        ),
    ),
    "composition": Directive(
        discovery=(
            "Fetch one table per component, and the total when it exists, "
            "with `fetch_observations` or `fetch_child_observations` over the "
            "same places and with the same `source_override`, and specify "
            "`compute_composition` in `composition` mode."
        ),
        synthesis=(
            "Report each component's exact percentage share of the total and "
            "the deltas between components. Do not merely list raw numbers."
        ),
    ),
    "sequential_stages": Directive(
        discovery=(
            "Fetch one table per stage with `fetch_observations` or "
            "`fetch_child_observations`, in the order the question gives "
            "them, and specify `compute_composition` in `stages` mode with "
            "`components` in that order."
        ),
        synthesis=(
            "Report each stage's value and its share of the whole, and the "
            "stage-to-stage ratios and deltas across the ordered tiers."
        ),
    ),
    "clustering": Directive(
        discovery=(
            "Do not attempt a clustering. Fetch the requested variables for "
            "the named entities with `fetch_observations` and specify "
            "`analyze_timeseries` or `rank_cohort` as an exploratory profile."
        ),
        synthesis=(
            "Present the figures as an exploratory profile, and say plainly "
            "that no clustering is performed."
        ),
    ),
    "forecasting": Directive(
        discovery=(
            "Do not attempt a projection. Fetch the full historical series "
            "with `fetch_observations` and specify `analyze_timeseries`."
        ),
        synthesis=(
            "Report the trend up to the latest observation, and say plainly "
            "that no projection is performed."
        ),
    ),
    "exploratory": Directive(
        discovery=(
            "Fetch four or five primary indicators spanning the core pillars "
            "of the requested domain, one table each, with "
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
        "Present a direct side-by-side comparison of the places and state "
        "the spread or delta between them as the digest gives it."
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

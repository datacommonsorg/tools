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
"""Maps a `QueryClassification` to an analytical directive for the agent loop.

Appends a pattern-specific instruction section (`with_pattern_guidance`) to the
discovery loop and synthesis system instructions so retrieval and narrative
structure match the classified query pattern and geographic shape.
"""

from narratives_agent.gemini.schemas import QueryClassification, QueryPattern

_DIRECTIVE_HEADING = "### Analytical directive for this question"

# Pattern-specific instructions appended to the discovery and synthesis prompts.
_DIRECTIVES: dict[QueryPattern, str] = {
    "single_point": (
        "Lead directly with the exact statistical value, its unit of "
        "measurement, its observation date, and the official statistical "
        "agency that published it."
    ),
    "top_n_ranking": (
        "Sort every retrieved entity by value, state the top and bottom "
        "ranks explicitly with their exact values and observation years, "
        "and cite the official source agency."
    ),
    "distribution": (
        "Describe the cohort as a whole rather than listing its members: "
        "report the median, the mean, the minimum and maximum, and the "
        "spread between them, all at one shared observation year, and say "
        "where the focal place sits within that range when the question "
        "names one."
    ),
    "trend_delta": (
        "Compute the overall start-to-end change as an absolute delta and "
        "as a percentage growth or decline, and point out the key "
        "inflection points across the period."
    ),
    "outliers": (
        "Retrieve time-series observations across the target entities, "
        "compute period-over-period deltas or percentage spikes and drops, "
        "and identify the largest outliers explicitly with their exact "
        "before and after values."
    ),
    "correlation": (
        "Retrieve aligned observations across the common geographic "
        "entities and the same time frame for both indicators. Describe the "
        "relationship from those figures: the places that rank high or low "
        "on both indicators, the ones that diverge, and the spread of each, "
        "and claim no strength or direction of association beyond what "
        "those figures show. Open with that description, not with a remark "
        "about what was or was not computed."
    ),
    "composition": (
        "Compute exact percentage shares, each component's proportion of "
        "the total, and the deltas between components before writing the "
        "narrative. Do not merely list raw numbers."
    ),
    "sequential_stages": (
        "Keep the stages in the order the question gives them, report each "
        "stage's value and its share of the whole, and compute the "
        "stage-to-stage ratios and deltas across the ordered tiers."
    ),
    "clustering": (
        "Do not attempt a clustering. Answer as an exploratory profile of "
        "the named entities across the requested variables, and say plainly "
        "that no clustering is performed."
    ),
    "forecasting": (
        "Do not attempt a projection. Answer from the historical series, "
        "report the trend up to the latest observation, and say plainly "
        "that no projection is performed."
    ),
    "exploratory": (
        "Retrieve a multi-indicator profile spanning the core pillars of the "
        "requested domain, for example four or five primary indicators, "
        "organize them into a structured summary, and cite the "
        "authoritative provenance of each metric."
    ),
    "data_availability": (
        "Survey the requested topic with `search_indicators` (with `places` "
        "naming the target place and `include_topics` enabled) and "
        "`get_variable_metadata` to learn its coverage, sources, and date "
        "ranges. Fetch a representative series for the headline indicator "
        "with `get_observations` or `get_child_observations` when "
        "observations exist for the requested place, and summarize what the "
        "catalog covers for that place, with the headline figure as its "
        "anchor."
    ),
}

_COMPARISON_DIRECTIVE = (
    "Retrieve aligned observations for the exact same indicator and year "
    "across every named place, present a direct side-by-side comparison, "
    "and compute the spread or delta between them."
)


def pattern_directive(classification: QueryClassification) -> str:
    """Returns the directive text for `classification`.

    Appends `_COMPARISON_DIRECTIVE` when `classification.geographic_shape` is
    `"comparison"`.
    """
    directive = _DIRECTIVES[classification.pattern]
    if classification.geographic_shape == "comparison":
        return f"{directive} {_COMPARISON_DIRECTIVE}"
    return directive


def with_pattern_guidance(
    system_instruction: str, classification: QueryClassification | None
) -> str:
    """Appends the directive for `classification` to `system_instruction`.

    Returns `system_instruction` unchanged when `classification` is `None`.
    """
    if classification is None:
        return system_instruction
    directive = pattern_directive(classification)
    return f"{system_instruction}\n\n{_DIRECTIVE_HEADING}\n\n{directive}"

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
"""Result and digest types produced by the deterministic analytics scripts.

Each analytical script returns a `ScriptResult`: an `OkScriptResult` carrying
computed metrics, or a `RefusedScriptResult` carrying the reason a
precondition failed. Both carry cohort coverage, source provenance, and
caveats. `AnalysisDigest` aggregates the results for a turn, assigns 1-based
citation numbers to all distinct sources, and renders the digest as either
plain JSON (`to_dict`) or rounded text for the synthesis prompt
(`format_for_prompt`). The module also holds the small formatters the
scripts share when they build caveats (`format_percent`, `conjugate_have`,
and `format_place_names`).
"""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Self

from narratives_agent.analytics.metrics import ScriptMetrics, ScriptName
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.json_value import JsonObject, JsonValue, json_safe

__all__ = [
    "PERCENT_SCALE",
    "PLACE_NAME_CAP",
    "AlignmentRefusalReason",
    "AnalysisDigest",
    "CoverageReport",
    "OkScriptResult",
    "RefusalReason",
    "RefusedScriptResult",
    "ResultStatus",
    "ScriptResult",
    "UnitMismatchReason",
    "conjugate_have",
    "format_percent",
    "format_place_names",
    "format_scaling_factor",
]

# Converts a share (0 to 1) to a percentage (0 to 100 scale).
PERCENT_SCALE = 100.0
# A caveat lists place names up to this many and counts the rest.
PLACE_NAME_CAP = 5

type ResultStatus = Literal["ok", "refused"]
# Why `align_cohort` could not align a table.
type AlignmentRefusalReason = Literal[
    "insufficient_coverage", "no_observations"
]
# Why tables or cohorts cannot be combined or compared.
type UnitMismatchReason = Literal["unit_mismatch", "scaling_mismatch"]
type RefusalReason = (
    AlignmentRefusalReason
    | UnitMismatchReason
    | Literal["invalid_parameters", "components_exceed_total"]
)


# In prompt text, floats with magnitude >= 1 are rounded to 2 decimal places,
# and smaller non-zero floats are rounded to 3 significant digits.
_PROMPT_DECIMALS = 2
# Percentages in caveats keep up to this many decimals.
_PERCENT_DECIMALS = 2
_PROMPT_SMALL_SIGNIFICANT_DIGITS = 3
# Whole-number floats below 10^15 are converted to `int` in prompt text;
# larger floats stay in scientific notation because IEEE-754 double precision
# cannot represent every integer digit above 2^53.
_MAX_INTEGER_FLOAT = 1e15


def _display_value(value: JsonValue) -> JsonValue:
    """Recursively rounds floats in `value` for display in the synthesis prompt.

    Rounds floats with magnitude >= 1 to `_PROMPT_DECIMALS` decimal places and
    smaller non-zero floats to `_PROMPT_SMALL_SIGNIFICANT_DIGITS` significant
    digits. Whole-number floats below `_MAX_INTEGER_FLOAT` are converted to
    `int` so they render without a trailing `.0`.
    """
    if isinstance(value, dict):
        return {key: _display_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_display_value(item) for item in value]
    if not isinstance(value, float):
        return value
    if not math.isfinite(value):
        return value
    magnitude = abs(value)
    if magnitude == 0.0:
        return 0
    if magnitude >= 1.0:
        rounded = round(value, _PROMPT_DECIMALS)
    else:
        rounded = float(f"{value:.{_PROMPT_SMALL_SIGNIFICANT_DIGITS}g}")
    if rounded.is_integer() and abs(rounded) < _MAX_INTEGER_FLOAT:
        return int(rounded)
    return rounded


def format_scaling_factor(value: float) -> str:
    """Formats a numeric scaling factor as a plain integer or compact float."""
    if (
        math.isfinite(value)
        and value.is_integer()
        and abs(value) < _MAX_INTEGER_FLOAT
    ):
        return str(int(value))
    return f"{value:g}"


def format_percent(share: float) -> str:
    """Formats a share as a percentage, with decimals only when needed.

    Up to two decimals are kept, so a threshold such as 0.9995 prints as
    99.95% rather than 100%; a share with more decimals is rounded to two.
    """
    return f"{round(share * PERCENT_SCALE, _PERCENT_DECIMALS):g}%"


def conjugate_have(count: int) -> str:
    """Returns the verb `have` in the number that matches `count` places."""
    return "has" if count == 1 else "have"


def format_place_names(names: Sequence[str]) -> str:
    """Lists up to `PLACE_NAME_CAP` place names and counts the rest.

    The cap keeps a caveat one readable sentence when it lists most of a
    large cohort.

    Args:
        names: Display names in the order to list them.

    Returns:
        The names joined for a sentence: `"A"`, `"A and B"`, `"A, B, and
        C"`, or `"A, B, C, D, E, and 3 other places"`.
    """
    listed = ", ".join(names[:PLACE_NAME_CAP])
    remainder = len(names) - PLACE_NAME_CAP
    if remainder > 0:
        noun = "other place" if remainder == 1 else "other places"
        return f"{listed}, and {remainder} {noun}"
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    if len(names) > 2:
        return f"{', '.join(names[:-1])}, and {names[-1]}"
    return listed


@dataclass(frozen=True)
class CoverageReport:
    """Summarizes how many of the target places contributed data to a result.

    Attributes:
        contributing_places: Number of target places (`k`) with valid data on
            `reference_date`.
        requested_places: Total number of target places (`M`).
        coverage_ratio: Ratio `k / M`, or `0.0` when `M` is zero.
        reference_date: Observation date to which the cohort is aligned, or
            `None` when no date could be selected.
        missing_places: Target place DCIDs that had no observation on
            `reference_date`.
        mixed_vintages: Whether places in the unaligned table had different
            latest observation dates before alignment.
    """

    contributing_places: int
    requested_places: int
    coverage_ratio: float
    reference_date: str | None
    missing_places: tuple[str, ...] = ()
    mixed_vintages: bool = False

    def describe(self) -> str:
        """Formats coverage as `"k of M place(s)"` and `" on <date>"`."""
        noun = "place" if self.requested_places == 1 else "places"
        text = f"{self.contributing_places} of {self.requested_places} {noun}"
        if self.reference_date is not None:
            text += f" on {self.reference_date}"
        return text


@dataclass(frozen=True, kw_only=True)
class _ScriptResultBase:
    """Fields shared by `OkScriptResult` and `RefusedScriptResult`.

    Attributes:
        step_id: Identifier of the analysis step (for example, `"s1"`).
        script: Name of the analytical script (for example,
            `"analyze_timeseries"`).
        variables: Statistical variable DCIDs analyzed by the script.
        variable_names: Mapping from variable DCID to display name.
        provenance: Source citations, facet IDs, and methodology for the
            result.
        unit: Measurement unit shared by the input observations, if known.
        scaling_factor: Scaling factor shared by the input observations, if
            known.
        coverage: Cohort coverage summary for cross-sectional scripts.
        caveats: Methodological notes to include in the synthesis prompt, such
            as an undefined growth rate or alignment across mixed vintages.
    """

    step_id: str
    script: ScriptName
    variables: tuple[str, ...]
    variable_names: dict[str, str]
    provenance: Provenance
    unit: str | None = None
    scaling_factor: float | None = None
    coverage: CoverageReport | None = None
    caveats: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class OkScriptResult(_ScriptResultBase):
    """Output of a script run that produced metrics.

    Attributes:
        metrics: Computed metrics record whose `script` matches `script`.
        status: Always `"ok"`.
        refusal_reason: Always `None`.

    Raises:
        ValueError: If `metrics` belongs to a different script.
    """

    metrics: ScriptMetrics
    status: Literal["ok"] = field(default="ok", init=False)
    refusal_reason: None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.metrics.script != self.script:
            raise ValueError(
                f"Script {self.script!r} cannot carry "
                f"{type(self.metrics).__name__}, which holds "
                f"{self.metrics.script!r} metrics."
            )

    def to_dict(self) -> JsonObject:
        """Serializes the result to a JSON-compatible dictionary."""
        return _result_to_dict(self)


@dataclass(frozen=True, kw_only=True)
class RefusedScriptResult(_ScriptResultBase):
    """Output of a script run refused because a precondition failed.

    Attributes:
        refusal_reason: Machine-readable reason the computation was refused.
        status: Always `"refused"`.
        metrics: Always `None`.
    """

    refusal_reason: RefusalReason
    status: Literal["refused"] = field(default="refused", init=False)
    metrics: None = field(default=None, init=False)

    def to_dict(self) -> JsonObject:
        """Serializes the result to a JSON-compatible dictionary."""
        return _result_to_dict(self)


type ScriptResult = OkScriptResult | RefusedScriptResult


def _result_to_dict(result: ScriptResult) -> JsonObject:
    """Serializes `result` to a JSON-compatible dictionary."""
    return {
        "step_id": result.step_id,
        "script": result.script,
        "status": result.status,
        "refusal_reason": result.refusal_reason,
        "variables": json_safe(result.variables),
        "variable_names": json_safe(result.variable_names),
        "unit": result.unit,
        "scaling_factor": json_safe(result.scaling_factor),
        "coverage": json_safe(result.coverage),
        "provenance": json_safe(result.provenance),
        "metrics": json_safe(result.metrics),
        "caveats": json_safe(result.caveats),
    }


@dataclass(frozen=True)
class AnalysisDigest:
    """Aggregated analytical results, numbered sources, and notes for one turn.

    Attributes:
        results: Script results in execution order.
        sources: Distinct `Source` records across `results` in order of first
            appearance, where index `i` corresponds to citation `[i + 1]`. If
            left empty at construction (or when using `from_results`), this
            field is populated automatically from `results`.
        missing_notes: Notes describing requested variables or places for
            which no data was found during discovery.

    Raises:
        ValueError: If a non-empty `sources` tuple is passed and does not
            match the deduplicated sources from `results` in first-appearance
            order.
    """

    results: tuple[ScriptResult, ...]
    sources: tuple[Source, ...] = ()
    missing_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        collected = tuple(
            dict.fromkeys(
                source
                for result in self.results
                for source in result.provenance.sources
            )
        )
        if not self.sources:
            object.__setattr__(self, "sources", collected)
        elif self.sources != collected:
            raise ValueError(
                "AnalysisDigest.sources must list the sources of its results "
                "in order of first appearance."
            )

    @property
    def has_data(self) -> bool:
        """Returns whether at least one script result has `status == "ok"`."""
        return any(result.status == "ok" for result in self.results)

    @classmethod
    def from_results(
        cls,
        results: tuple[ScriptResult, ...],
        *,
        missing_notes: tuple[str, ...] = (),
    ) -> Self:
        """Builds an `AnalysisDigest` with `sources` populated from `results`.

        Deduplicates `Source` records across `results` in order of first
        appearance so they are numbered starting at 1.
        """
        return cls(results=results, missing_notes=missing_notes)

    def citation_label(self, provenance: Provenance) -> str:
        """Returns the 1-based bracketed citation for `provenance`.

        Formats the citation as `"[1]"` or `"[1, 2]"`, or returns `""` when
        `provenance.sources` is empty.

        Raises:
            ValueError: If `provenance` contains a `Source` that is not in
                `self.sources`.
        """
        index_by_source = {
            source: index for index, source in enumerate(self.sources, start=1)
        }
        unknown = [
            source.name
            for source in provenance.sources
            if source not in index_by_source
        ]
        if unknown:
            raise ValueError(
                f"Provenance cites sources the digest does not hold: {unknown}"
            )
        if not provenance.sources:
            return ""
        citation_ids = dict.fromkeys(
            index_by_source[source] for source in provenance.sources
        )
        return "[" + ", ".join(str(item) for item in citation_ids) + "]"

    def to_dict(self) -> JsonObject:
        """Serializes the digest to a finite JSON-compatible dictionary."""
        results_json: list[JsonValue] = [
            result.to_dict() for result in self.results
        ]
        return {
            "has_data": self.has_data,
            "results": results_json,
            "sources": json_safe(self.sources),
            "missing_notes": json_safe(self.missing_notes),
        }

    def format_for_prompt(self) -> str:
        """Renders the digest as compact, human-readable text for synthesis.

        Formats each `ScriptResult` as a block containing a step header, a
        metadata line (unit, scaling factor, coverage, and citation label),
        methodology, a single-line JSON metrics object with floats rounded to
        display precision, and any caveats. Appends the numbered `"Sources:"`
        and `"Missing data:"` sections at the end. Only prompt text is
        rounded; `to_dict` preserves full floating-point precision.
        """
        lines: list[str] = []
        for result in self.results:
            lines.extend(
                _format_result(
                    result,
                    citation_label=self.citation_label(result.provenance),
                )
            )
            lines.append("")
        if self.sources:
            lines.append("Sources:")
            for index, source in enumerate(self.sources, start=1):
                lines.append(f"[{index}] {_format_source(source)}")
            lines.append("")
        if self.missing_notes:
            lines.append("Missing data:")
            lines.extend(f"- {note}" for note in self.missing_notes)
            lines.append("")
        return "\n".join(lines).rstrip("\n")


def _format_result(result: ScriptResult, *, citation_label: str) -> list[str]:
    """Formats one `ScriptResult` as lines of text for `format_for_prompt`."""
    variables = ", ".join(
        f"{result.variable_names.get(dcid, dcid)} ({dcid})"
        for dcid in result.variables
    )
    header = f"Step {result.step_id}: {result.script} on {variables}"
    if result.status == "refused":
        header += f" [refused: {result.refusal_reason}]"
    lines = [header]
    details: list[str] = []
    if result.unit:
        details.append(f"unit: {result.unit}")
    if result.scaling_factor is not None:
        details.append(
            f"scaling factor: {format_scaling_factor(result.scaling_factor)}"
        )
    if result.coverage is not None:
        details.append(f"coverage: {result.coverage.describe()}")
    if citation_label:
        details.append(f"cite: {citation_label}")
    if details:
        lines.append("  " + "; ".join(details))
    if result.provenance.methodology:
        lines.append(f"  method: {result.provenance.methodology}")
    if result.status == "ok":
        metrics = json.dumps(
            _display_value(json_safe(result.metrics)),
            separators=(",", ":"),
            sort_keys=False,
        )
        lines.append(f"  metrics: {metrics}")
    for caveat in result.caveats:
        lines.append(f"  caveat: {caveat}")
    return lines


def _format_source(source: Source) -> str:
    """Formats `source` as `"name (url)"`, or `"name"` when `url` is absent."""
    if source.url and source.url != source.name:
        return f"{source.name} ({source.url})"
    return source.name

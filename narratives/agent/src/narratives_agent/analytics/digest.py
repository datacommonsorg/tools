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

Each analytical script returns a `ScriptResult` containing computed metrics,
cohort coverage, source provenance, and caveats. `AnalysisDigest` aggregates
the results for a turn, assigns 1-based citation numbers to all distinct
sources, and renders the digest as either plain JSON (`to_dict`) or rounded
text for the synthesis prompt (`format_for_prompt`).
"""

import dataclasses
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Self

from narratives_agent.analytics.metrics import (
    METRICS_BY_SCRIPT,
    ScriptMetrics,
    ScriptName,
)
from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
    merge_provenance,
)
from narratives_agent.json_value import JsonObject, JsonValue

__all__ = [
    "AlternativeSource",
    "AnalysisDigest",
    "CoverageReport",
    "Provenance",
    "RefusalReason",
    "ResultStatus",
    "ScriptResult",
    "Source",
    "format_scaling_factor",
    "json_safe",
    "merge_provenance",
]

type ResultStatus = Literal["ok", "refused"]
type RefusalReason = Literal[
    "insufficient_coverage",
    "unit_mismatch",
    "scaling_mismatch",
    "no_observations",
    "invalid_parameters",
    "components_exceed_total",
]


def json_safe(value: object) -> JsonValue:
    """Recursively converts `value` into plain JSON-serializable Python types.

    Converts dataclasses to dicts, tuples and sets to lists, and non-finite
    floats (`NaN`, `Infinity`, `-Infinity`) to `None` so that strict JSON
    encoders (`json.dumps(..., allow_nan=False)`) never reject the output.

    Raises:
        TypeError: If `value` or any nested element cannot be represented in
            JSON.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: json_safe(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((json_safe(item) for item in value), key=str)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str) or value is None:
        return value
    raise TypeError(
        f"Cannot serialize value of type {type(value).__name__} to JSON."
    )


# In prompt text, floats with magnitude >= 1 are rounded to 2 decimal places,
# and smaller non-zero floats are rounded to 3 significant digits.
_PROMPT_DECIMALS = 2
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
        decimals = (
            _PROMPT_SMALL_SIGNIFICANT_DIGITS
            - 1
            - math.floor(math.log10(magnitude))
        )
        rounded = round(value, decimals)
    if rounded.is_integer() and magnitude < _MAX_INTEGER_FLOAT:
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


@dataclass(frozen=True)
class ScriptResult:
    """Output of a single analytical script run on one or more tables.

    Attributes:
        step_id: Identifier of the analysis step (for example, `"s1"`).
        script: Name of the analytical script (for example,
            `"analyze_timeseries"`).
        status: `"ok"` when the script produced `metrics`, or `"refused"` when
            a precondition failed.
        variables: Statistical variable DCIDs analyzed by the script.
        variable_names: Mapping from variable DCID to display name.
        provenance: Source citations, facet IDs, and methodology for the
            result.
        metrics: Computed metrics dataclass for `script` when `status` is
            `"ok"`, or `None` when `status` is `"refused"`.
        refusal_reason: Machine-readable reason the computation was refused
            when `status` is `"refused"`, or `None` when `status` is `"ok"`.
        unit: Measurement unit shared by the input observations, if known.
        scaling_factor: Scaling factor shared by the input observations, if
            known.
        coverage: Cohort coverage summary for cross-sectional scripts.
        caveats: Methodological notes to include in the synthesis prompt, such
            as an undefined growth rate or alignment across mixed vintages.
    """

    step_id: str
    script: ScriptName
    status: ResultStatus
    variables: tuple[str, ...]
    variable_names: dict[str, str]
    provenance: Provenance
    metrics: ScriptMetrics | None = None
    refusal_reason: RefusalReason | None = None
    unit: str | None = None
    scaling_factor: float | None = None
    coverage: CoverageReport | None = None
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "refused":
            if self.metrics is not None:
                raise ValueError(
                    "A refused ScriptResult must have metrics=None."
                )
            if self.refusal_reason is None:
                raise ValueError(
                    "A refused ScriptResult must carry a refusal_reason."
                )
            return
        if self.refusal_reason is not None:
            raise ValueError(
                "An ok ScriptResult must have refusal_reason=None."
            )
        if self.metrics is None:
            raise ValueError(
                "An ok ScriptResult must carry a ScriptMetrics instance."
            )
        expected = METRICS_BY_SCRIPT.get(self.script)
        if expected is None:
            raise ValueError(
                f"Script {self.script!r} has no registered metrics class."
            )
        if not isinstance(self.metrics, expected):
            raise ValueError(
                f"Script {self.script!r} requires {expected.__name__} "
                f"metrics, got {type(self.metrics).__name__}."
            )

    def to_dict(self) -> JsonObject:
        """Serializes the result to a JSON-compatible dictionary."""
        return {
            "step_id": self.step_id,
            "script": self.script,
            "status": self.status,
            "refusal_reason": self.refusal_reason,
            "variables": json_safe(self.variables),
            "variable_names": json_safe(self.variable_names),
            "unit": self.unit,
            "scaling_factor": json_safe(self.scaling_factor),
            "coverage": json_safe(self.coverage),
            "provenance": json_safe(self.provenance),
            "metrics": json_safe(self.metrics),
            "caveats": json_safe(self.caveats),
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
    if result.metrics is not None:
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

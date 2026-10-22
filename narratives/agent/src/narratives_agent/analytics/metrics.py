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
"""Script name and metrics type definitions for the analytics package.

`ScriptName` enumerates the deterministic analytics scripts. Each script
returns a `ScriptResult` whose `metrics` field is an instance of its paired
dataclass in `METRICS_BY_SCRIPT`.
"""

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "METRICS_BY_SCRIPT",
    "ScriptMetrics",
    "ScriptName",
]

type ScriptName = Literal[
    "align_cohort",
    "analyze_timeseries",
    "rank_cohort",
    "summarize_distribution",
    "compute_composition",
    "compute_derived_metric",
]


@dataclass(frozen=True)
class ScriptMetrics:
    """Common base of the metrics records registered in `METRICS_BY_SCRIPT`."""


METRICS_BY_SCRIPT: dict[ScriptName, type[ScriptMetrics]] = {}

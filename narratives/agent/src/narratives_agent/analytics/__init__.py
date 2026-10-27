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
"""Deterministic analytics library for the Narratives agent loop.

Holds the provenance models (`Source`, `Provenance`), the observation table
types, cohort alignment and unit checks, the table summary, the time-series,
cohort ranking, distribution, composition, derived-metric, and two-cohort
relation scripts with the input checks they share and their per-script metric
records, and the `ScriptResult` and `AnalysisDigest` types the analytics
scripts produce. The package may import only the Python standard library,
other `analytics/` modules, and `narratives_agent.json_value`.
"""

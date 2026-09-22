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
"""Tests for observation data availability checks across MCP payload formats.

Verifies that `data_utils.check_data_availability` accurately distinguishes
populated responses from empty responses across both MCP server generations:
- MCP 1.2.x (`place_observations[].time_series` list format)
- MCP 1.3.x+ (`data.rows` columnar format, where an empty response is
  represented as `{"data": {}}`)
"""

import json
from typing import Any

import pytest

from narratives_agent.mcp import data_utils

# ---- payload fixtures, one per server generation -------------------------
V121_WITH_DATA = {
    "place_observations": [
        {
            "place": "country/BEL",
            "time_series": [["2020", 54577.6], ["2021", 59100.1]],
        }
    ]
}
V121_EMPTY = {
    "place_observations": [{"place": "country/BEL", "time_series": []}]
}
V130_WITH_DATA = {
    "data": {
        "rows": [{"entity": "country/BEL", "date": "2021", "value": 59100.1}]
    }
}
V130_EMPTY: dict[str, Any] = {"data": {}}


def tool_call(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap an observation payload in an MCP tool-call result envelope."""
    return {
        "name": name,
        "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }


@pytest.mark.parametrize(
    "payload",
    [V121_WITH_DATA, V130_WITH_DATA],
    ids=["1.2.x populated", "1.3.x populated"],
)
def test_populated_observations_report_data(payload: dict[str, Any]) -> None:
    # Test: Data availability check when observations are present.
    # Situation: `get_observations` returns non-empty observation data in
    #   either the MCP 1.2.x (`place_observations[].time_series`) or MCP 1.3.x
    #   (`data.rows`) format.
    # Expectation: `check_data_availability` returns `has_data: True` for both
    #   formats.
    status = data_utils.check_data_availability(
        [tool_call("get_observations", payload)]
    )
    assert status["has_data"] is True


@pytest.mark.parametrize(
    "payload",
    [V121_EMPTY, V130_EMPTY],
    ids=["1.2.x empty", "1.3.x empty"],
)
def test_empty_observations_report_no_data(payload: dict[str, Any]) -> None:
    # Test: Data availability check when observation results are empty.
    # Situation: `get_observations` returns an empty MCP 1.2.x response
    #   (`"time_series": []`) or an empty MCP 1.3.x response (`{"data": {}}`).
    # Expectation: `check_data_availability` returns `has_data: False` in both
    #   cases.
    status = data_utils.check_data_availability(
        [tool_call("get_observations", payload)]
    )
    assert status["has_data"] is False

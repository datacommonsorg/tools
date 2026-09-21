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
"""Data availability, read from either MCP server generation's payload shape.

Part of the plug-and-play guarantee: one agent, either MCP server generation.
The agent must run unchanged against a CDC services container (MCP 1.2.x, two
fat tools, `place_observations` / `time_series` payloads) and a DCP or public
instance (1.3.x, six tools, columnar `data.rows` payloads).

The case that matters most is the *empty* response. The previous regex-based
check looked for a `"time_series": [[` substring; a 1.3.x server signals "no
data" as `{"data": {}}`, which contains no such substring, so nothing matched,
`all_observations_empty` stayed True and `has_data` came back **True for zero
data**. The agent then confidently narrated numbers it did not have. That is a
silent wrong-answer bug, which is why it is pinned here.
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
    """Wrap a payload the way a tool call carries it.

    MCP wraps results in a content[0].text envelope of double-encoded JSON.
    """
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
    # Test: data availability on a result that carries numbers.
    # Situation: get_observations returns a populated payload, in the 1.2.x
    #   `place_observations[].time_series` shape and in the 1.3.x columnar
    #   `data.rows` shape.
    # Expectation: has_data, whichever generation answered.
    status = data_utils.check_data_availability(
        [tool_call("get_observations", payload)]
    )
    assert status["has_data"] is True


@pytest.mark.parametrize(
    "payload",
    [V121_EMPTY, V130_EMPTY],
    ids=["1.2.x empty", "1.3.x empty (the silent wrong-answer bug)"],
)
def test_empty_observations_report_no_data(payload: dict[str, Any]) -> None:
    # Test: data availability on a result that carries nothing.
    # Situation: the two generations spell "no data" differently -- 1.2.x as
    #   `"time_series": []`, 1.3.x as `{"data": {}}`.
    # Expectation: no data in both cases. The 1.3.x spelling is the one that
    #   regressed: a text search for the 1.2.x markers finds neither marker in
    #   a 1.3.x empty response, so has_data came back True for zero data and
    #   the agent narrated numbers it did not have.
    status = data_utils.check_data_availability(
        [tool_call("get_observations", payload)]
    )
    assert status["has_data"] is False

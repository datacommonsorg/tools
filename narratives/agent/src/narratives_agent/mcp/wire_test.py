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
"""Tests for the MCP observation wire models in `mcp.wire`.

The parser's handling of these models is tested in `observations_test.py`;
this file covers the models and `validate_observation_payload` directly.
"""

import logging
import re

import pytest
from pydantic import ValidationError

from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp.wire import (
    ObservationPayloadWire,
    validate_observation_payload,
)

_VARIABLE: JsonObject = {"dcid": "Count_Person"}
_BAD_ALTERNATIVE: JsonValue = [{"sourceMetadata": {"sourceId": ["f9"]}}]


def test_identifiers_are_checked_after_string_conversion() -> None:
    # Test: Identifier checks on values that Pydantic converts to strings.
    # Situation: The variable DCID and the served facet ID arrive as bytes
    #   containing a newline, and a valid numeric facet ID arrives as an
    #   integer.
    # Expectation: The bytes are rejected by the identifier check rather than
    #   converted and accepted, and the integer facet ID is read as its
    #   decimal string.
    with pytest.raises(ValidationError, match=re.escape("variable.dcid")):
        ObservationPayloadWire.model_validate(
            {"variable": {"dcid": b"Count\nPerson"}}
        )
    with pytest.raises(
        ValidationError, match=re.escape("sourceMetadata.sourceId")
    ):
        ObservationPayloadWire.model_validate(
            {"variable": _VARIABLE, "sourceMetadata": {"sourceId": b"f1\nX"}}
        )
    wire = ObservationPayloadWire.model_validate(
        {
            "variable": _VARIABLE,
            "sourceMetadata": {"sourceId": 9674656028615575584},
        }
    )
    assert wire.source_metadata.source_id == "9674656028615575584"


def test_dropped_alternatives_are_counted_or_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: How a dropped `alternativeSources` entry is reported.
    # Situation: A payload with one malformed alternative is validated
    #   through `validate_observation_payload`, and then directly through
    #   `ObservationPayloadWire`.
    # Expectation: `validate_observation_payload` returns a count of 1 and
    #   logs nothing, leaving the warning to its caller; direct validation
    #   logs one warning without a subject.
    payload: JsonObject = {
        "alternativeSources": _BAD_ALTERNATIVE,
        "variable": _VARIABLE,
    }
    with caplog.at_level(logging.WARNING, logger="narratives_agent"):
        wire, dropped = validate_observation_payload(payload)
        counted = [record.getMessage() for record in caplog.records]
        caplog.clear()

        ObservationPayloadWire.model_validate(payload)
        direct = [record.getMessage() for record in caplog.records]

    assert wire.alternative_sources == ()
    assert dropped == 1
    assert counted == []
    assert direct == ["Dropped 1 malformed alternative source(s)."]

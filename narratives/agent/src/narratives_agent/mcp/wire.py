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
"""Pydantic wire models and validation for MCP 1.3.x observation payloads.

Models the live JSON shapes returned by `get_observations`,
`get_child_observations`, and `get_multi_entity_observations` (`variable`,
`data`, `entityMetadata`, `sourceMetadata`, and `alternativeSources`) with
camelCase aliasing. Unknown keys are ignored. A structural key (a block, its
column list or row list, the variable DCID, or the served facet ID) of the
wrong type fails validation, as does a variable DCID or served facet ID that is
not printable ASCII within the DCID length limit, because both are logged and
sent back to the server. A descriptive scalar of the wrong type is read as
absent, a malformed `alternativeSources` entry is dropped and counted (see
`validate_observation_payload`), and a row that is not a list is dropped by
the parser, so none of them discards the payload's valid rows.
"""

import logging
from collections.abc import Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic.alias_generators import to_camel

from narratives_agent.analytics.tables import is_valid_dcid
from narratives_agent.json_value import JsonValue
from narratives_agent.mcp.metadata import parse_scaling_factor

__all__ = [
    "AlternativeSourceWire",
    "ColumnarTableWire",
    "ObservationPayloadWire",
    "SourceMetadataWire",
    "VariableWire",
    "validate_observation_payload",
]

logger = logging.getLogger(__name__)

# Validation context key under which dropped `alternativeSources` entries are
# counted, so the caller can log them with the variable or place they belong to.
_DROPPED_ALTERNATIVES = "dropped_alternatives"

_WIRE_CONFIG = ConfigDict(
    alias_generator=to_camel,
    validate_by_name=True,
    validate_by_alias=True,
    extra="ignore",
    frozen=True,
    # Validation errors omit the input values, which are upstream data.
    hide_input_in_errors=True,
)


class VariableWire(BaseModel):
    """The `variable` block of an MCP observation response."""

    model_config = _WIRE_CONFIG

    dcid: str
    name: str | None = None

    # Runs after type conversion, so every input Pydantic accepts as a string
    # is checked.
    @field_validator("dcid", mode="after")
    @classmethod
    def _strip_dcid(cls, value: str) -> str:
        dcid = value.strip()
        if not is_valid_dcid(dcid):
            # The value is upstream data, so the message does not repeat it.
            raise ValueError("The variable DCID is not a valid DCID.")
        return dcid

    @field_validator("name", mode="before")
    @classmethod
    def _descriptive(cls, value: object) -> str | None:
        return _descriptive_str(value)


class ColumnarTableWire(BaseModel):
    """A columnar `{"columns": [...], "rows": [[...], ...]}` block.

    Each row is typed as any JSON value, so a row that is not a list reaches
    the parser, which drops and counts it, instead of failing the payload.
    """

    model_config = _WIRE_CONFIG

    columns: tuple[str, ...] = ()
    rows: tuple[JsonValue, ...] = ()


class SourceMetadataWire(BaseModel):
    """The `sourceMetadata` block describing a served or alternative facet."""

    model_config = _WIRE_CONFIG

    source_id: str | None = None
    provenance_url: str | None = None
    import_name: str | None = None
    source_name: str | None = None
    measurement_method: str | None = None
    observation_period: str | None = None
    unit: str | None = None
    scaling_factor: float | None = None

    @field_validator("source_id", mode="before")
    @classmethod
    def _numeric_facet_id(cls, value: object) -> object:
        # A numeric facet ID is read as its decimal string, as `mcp.metadata`
        # reads facet IDs, so both readers agree on the facet's identity.
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return value

    # Runs after type conversion, so every input Pydantic accepts as a string
    # is checked.
    @field_validator("source_id", mode="after")
    @classmethod
    def _facet_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        facet_id = value.strip()
        if not facet_id:
            return None
        if not is_valid_dcid(facet_id):
            # The value is upstream data, so the message does not repeat it.
            # A facet ID is logged and sent back as `source_override`.
            raise ValueError("The facet ID is not a valid identifier.")
        return facet_id

    @field_validator(
        "provenance_url",
        "import_name",
        "source_name",
        "measurement_method",
        "observation_period",
        "unit",
        mode="before",
    )
    @classmethod
    def _descriptive(cls, value: object) -> str | None:
        return _descriptive_str(value)

    @field_validator("scaling_factor", mode="before")
    @classmethod
    def _scaling_factor(cls, value: object) -> float | None:
        if isinstance(value, int | float | str):
            return parse_scaling_factor(value)
        return None


class AlternativeSourceWire(BaseModel):
    """One entry in the top-level `alternativeSources` list."""

    model_config = _WIRE_CONFIG

    source_metadata: SourceMetadataWire = Field(
        default_factory=SourceMetadataWire
    )
    places_found_count: int | None = None

    @field_validator("places_found_count", mode="before")
    @classmethod
    def _count(cls, value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return None


class ObservationPayloadWire(BaseModel):
    """Top-level wire model for MCP 1.3.x observation tool responses.

    `variable` is required. The MCP server includes it in every observation
    response, including an empty one, so a JSON object without it is not an
    observation payload.
    """

    model_config = _WIRE_CONFIG

    variable: VariableWire
    data: ColumnarTableWire = Field(default_factory=ColumnarTableWire)
    entity_metadata: ColumnarTableWire = Field(
        default_factory=ColumnarTableWire
    )
    source_metadata: SourceMetadataWire = Field(
        default_factory=SourceMetadataWire
    )
    alternative_sources: tuple[AlternativeSourceWire, ...] = ()

    @field_validator("alternative_sources", mode="before")
    @classmethod
    def _valid_alternatives(cls, value: object, info: ValidationInfo) -> object:
        # Alternatives are optional metadata, so a malformed entry is dropped
        # rather than failing the payload that carries the rows. A value that
        # is not a list still fails validation.
        if not isinstance(value, list | tuple):
            return value
        entries: list[AlternativeSourceWire] = []
        for entry in value:
            try:
                entries.append(AlternativeSourceWire.model_validate(entry))
            except ValidationError:
                continue
        dropped = len(value) - len(entries)
        if dropped:
            context = info.context
            if isinstance(context, dict) and _DROPPED_ALTERNATIVES in context:
                context[_DROPPED_ALTERNATIVES] += dropped
            else:
                logger.warning(
                    "Dropped %d malformed alternative source(s).", dropped
                )
        return tuple(entries)


def validate_observation_payload(
    payload: Mapping[str, JsonValue],
) -> tuple[ObservationPayloadWire, int]:
    """Validates a decoded observation payload.

    Args:
        payload: The decoded JSON object an observation tool returned.

    Returns:
        The validated payload and the number of malformed
        `alternativeSources` entries dropped from it, which the caller logs
        with the variable or place the payload belongs to.

    Raises:
        ValidationError: If the payload does not match the observation
            schema.
    """
    context = {_DROPPED_ALTERNATIVES: 0}
    wire = ObservationPayloadWire.model_validate(payload, context=context)
    return wire, context[_DROPPED_ALTERNATIVES]


def _descriptive_str(value: object) -> str | None:
    """Reads a descriptive string field, mapping blanks and non-strings to None.

    Descriptive fields label a facet or variable; a malformed one is dropped
    rather than failing the payload that carries the rows.
    """
    if isinstance(value, str):
        return value.strip() or None
    return None

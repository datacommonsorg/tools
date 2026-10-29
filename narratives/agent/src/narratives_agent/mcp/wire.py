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
camelCase aliasing. Unknown keys are ignored. Malformed fields are handled in
three tiers, so only a malformed structure discards the payload's rows:

- A structural field (a block, its column or row list, the variable DCID, or
  the served facet ID) of the wrong type fails validation, as does a variable
  DCID or served facet ID that is not a valid identifier, because both are
  logged and sent back to the server.
- A descriptive scalar of the wrong type, such as a unit, is read as absent.
- A malformed `alternativeSources` entry is dropped and counted (see
  `validate_observation_payload`), and a row that is not a list is dropped and
  counted by the parser.
"""

import logging
from collections.abc import Mapping
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
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
    "ChildObservationsToolArguments",
    "ColumnarTableWire",
    "MultiEntityObservationsToolArguments",
    "ObservationPayloadWire",
    "ObservationsToolArguments",
    "SourceMetadataWire",
    "VariableWire",
    "validate_observation_payload",
]

logger = logging.getLogger(__name__)

# Validation context key under which dropped `alternativeSources` entries are
# counted, so the caller can log them with the variable or place they belong to.
_DROPPED_ALTERNATIVES = "dropped_alternatives"

# Tool arguments are built by the agent, so an unknown field is a bug.
_TOOL_ARGUMENTS_CONFIG = ConfigDict(extra="forbid", frozen=True)


class ObservationsToolArguments(BaseModel):
    """Wire arguments for the MCP `get_observations` tool.

    The observation tools take snake_case arguments, so the argument models
    have no aliases.

    Attributes:
        variable_dcid: The statistical variable DCID.
        place_dcid: The one place to fetch.
        date: `latest`, `all`, `range`, or a `YYYY` year.
        date_range_start: The inclusive range start, or `None` when `date` is
            not `range` or the range is open at the start.
        date_range_end: The inclusive range end, or `None` when `date` is not
            `range` or the range is open at the end.
        source_override: The facet to fetch from, or `None` to let the server
            choose.
    """

    model_config = _TOOL_ARGUMENTS_CONFIG

    variable_dcid: str
    place_dcid: str
    date: str
    date_range_start: str | None = None
    date_range_end: str | None = None
    source_override: str | None = None


class ChildObservationsToolArguments(BaseModel):
    """Wire arguments for the MCP `get_child_observations` tool.

    Attributes:
        variable_dcid: The statistical variable DCID.
        parent_place_dcid: The parent place whose children are fetched.
        child_place_type: The place type of the children, such as `State`.
        date: `latest`, `all`, `range`, or a `YYYY` year.
        date_range_start: The inclusive range start, or `None` when `date` is
            not `range` or the range is open at the start.
        date_range_end: The inclusive range end, or `None` when `date` is not
            `range` or the range is open at the end.
        source_override: The facet to fetch from, or `None` to let the server
            choose.
    """

    model_config = _TOOL_ARGUMENTS_CONFIG

    variable_dcid: str
    parent_place_dcid: str
    child_place_type: str
    date: str
    date_range_start: str | None = None
    date_range_end: str | None = None
    source_override: str | None = None


class MultiEntityObservationsToolArguments(BaseModel):
    """Wire arguments for the MCP `get_multi_entity_observations` tool.

    Attributes:
        variable_dcid: The relationship variable DCID.
        entities: The DCIDs of each entity property.
        parent_entity_property: The entity property expanded into child
            places, or `None` when no property is expanded. The tool takes
            the three expansion fields together or not at all.
        parent_entity_dcid: The parent place of the expansion, or `None` when
            no property is expanded.
        child_entity_type: The child place type of the expansion, or `None`
            when no property is expanded.
        date: `latest`, `all`, `range`, or a `YYYY` year.
        date_range_start: The inclusive range start, or `None` when `date` is
            not `range` or the range is open at the start.
        date_range_end: The inclusive range end, or `None` when `date` is not
            `range` or the range is open at the end.
        source_override: The facet to fetch from, or `None` to let the server
            choose.
    """

    model_config = _TOOL_ARGUMENTS_CONFIG

    variable_dcid: str
    entities: dict[str, list[str]]
    parent_entity_property: str | None = None
    parent_entity_dcid: str | None = None
    child_entity_type: str | None = None
    date: str
    date_range_start: str | None = None
    date_range_end: str | None = None
    source_override: str | None = None


def _descriptive_str(value: object) -> str | None:
    """Reads a descriptive string field, mapping blanks and non-strings to None.

    Descriptive fields label a facet or variable; a malformed one is dropped
    rather than failing the payload that carries the rows.
    """
    if isinstance(value, str):
        return value.strip() or None
    return None


def _scaling_factor(value: object) -> float | None:
    """Reads a scaling factor the way `mcp.metadata` does, or None."""
    if isinstance(value, int | float | str):
        return parse_scaling_factor(value)
    return None


def _count(value: object) -> int | None:
    """Reads a count that is an integer and not a boolean, or None."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _variable_dcid(value: str) -> str:
    """Strips a variable DCID and checks that it is a valid DCID.

    Runs after type conversion, so every input Pydantic accepts as a string is
    checked.
    """
    dcid = value.strip()
    if not is_valid_dcid(dcid):
        # The value is upstream data, so the message does not repeat it.
        raise ValueError("The variable DCID is not a valid DCID.")
    return dcid


def _numeric_facet_id(value: object) -> object:
    """Reads an integer facet ID as its decimal string.

    `mcp.metadata` reads facet IDs the same way, so both readers agree on the
    facet's identity.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def _facet_id(value: str | None) -> str | None:
    """Strips a facet ID, reading a blank one as None, and checks it.

    Runs after type conversion, so every input Pydantic accepts as a string is
    checked.
    """
    if value is None:
        return None
    facet_id = value.strip()
    if not facet_id:
        return None
    if not is_valid_dcid(facet_id):
        # The value is upstream data, so the message does not repeat it. A
        # facet ID is logged and sent back as `source_override`.
        raise ValueError("The facet ID is not a valid identifier.")
    return facet_id


type _DescriptiveStr = Annotated[str | None, BeforeValidator(_descriptive_str)]
type _ScalingFactor = Annotated[float | None, BeforeValidator(_scaling_factor)]
type _Count = Annotated[int | None, BeforeValidator(_count)]
type _VariableDcid = Annotated[str, AfterValidator(_variable_dcid)]
type _FacetId = Annotated[
    str | None,
    BeforeValidator(_numeric_facet_id),
    AfterValidator(_facet_id),
]


class _WireModel(BaseModel):
    """Base for the wire models: camelCase aliases, unknown keys ignored."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        extra="ignore",
        frozen=True,
        # Validation errors omit the input values, which are upstream data.
        hide_input_in_errors=True,
    )


class VariableWire(_WireModel):
    """The `variable` block of an MCP observation response."""

    dcid: _VariableDcid
    name: _DescriptiveStr = None


class ColumnarTableWire(_WireModel):
    """A columnar `{"columns": [...], "rows": [[...], ...]}` block.

    Each row is typed as any JSON value, so a row that is not a list reaches
    the parser, which drops and counts it, instead of failing the payload.
    """

    columns: tuple[str, ...] = ()
    rows: tuple[JsonValue, ...] = ()


class SourceMetadataWire(_WireModel):
    """The `sourceMetadata` block describing a served or alternative facet."""

    source_id: _FacetId = None
    provenance_url: _DescriptiveStr = None
    import_name: _DescriptiveStr = None
    source_name: _DescriptiveStr = None
    measurement_method: _DescriptiveStr = None
    observation_period: _DescriptiveStr = None
    unit: _DescriptiveStr = None
    scaling_factor: _ScalingFactor = None


class AlternativeSourceWire(_WireModel):
    """One entry in the top-level `alternativeSources` list."""

    source_metadata: SourceMetadataWire = Field(
        default_factory=SourceMetadataWire
    )
    places_found_count: _Count = None


class ObservationPayloadWire(_WireModel):
    """Top-level wire model for MCP 1.3.x observation tool responses.

    `variable` is required. The MCP server includes it in every observation
    response, including an empty one, so a JSON object without it is not an
    observation payload.
    """

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

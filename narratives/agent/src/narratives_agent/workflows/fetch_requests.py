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
"""Pydantic request models and validation for server-side fetch functions.

Defines `DateSelection`, `FetchObservationsRequest`,
`FetchChildObservationsRequest`, and `FetchMultiEntityRequest`, along with
`parse_fetch_request` and the model-facing function and parameter descriptions
used to generate Gemini `FunctionDeclaration` schemas.
"""

from collections.abc import Mapping
from typing import Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from narratives_agent.analytics.tables import (
    is_inverted_date_range,
    is_valid_observation_date,
)
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.workflows.transcript import (
    Dcid,
    ObservationDate,
    PlaceType,
)

__all__ = [
    "COHORT_WINDOW_YEARS",
    "FETCH_CHILD_OBSERVATIONS",
    "FETCH_CHILD_OBSERVATIONS_DESCRIPTION",
    "FETCH_FUNCTION_NAMES",
    "FETCH_MULTI_ENTITY_OBSERVATIONS",
    "FETCH_MULTI_ENTITY_OBSERVATIONS_DESCRIPTION",
    "FETCH_OBSERVATIONS",
    "FETCH_OBSERVATIONS_DESCRIPTION",
    "NAMED_PLACE_SERIES_LIMIT",
    "DateSelection",
    "FetchArgumentError",
    "FetchChildObservationsRequest",
    "FetchMultiEntityRequest",
    "FetchObservationsRequest",
    "FetchRequest",
    "parse_fetch_request",
    "validate_date_selection_fields",
]

# The names of the three server-side fetch functions the model calls.
FETCH_OBSERVATIONS = "fetch_observations"
FETCH_CHILD_OBSERVATIONS = "fetch_child_observations"
FETCH_MULTI_ENTITY_OBSERVATIONS = "fetch_multi_entity_observations"

FETCH_FUNCTION_NAMES: frozenset[str] = frozenset(
    {
        FETCH_OBSERVATIONS,
        FETCH_CHILD_OBSERVATIONS,
        FETCH_MULTI_ENTITY_OBSERVATIONS,
    }
)

# The model-facing description of each fetch function, sent with its
# generated declaration.
FETCH_OBSERVATIONS_DESCRIPTION = (
    "Fetch one statistical variable for named places into the "
    "server cache. Returns a compact summary of the cached "
    "table (its table_id, coverage, date range, unit, source, "
    "facet_id, alternative_sources, and sample rows), never the "
    "rows themselves."
)

FETCH_CHILD_OBSERVATIONS_DESCRIPTION = (
    "Fetch one statistical variable across every child place of "
    "a given type within a parent place (every country in the "
    "world, every state in a country, every county in a state) "
    "into the server cache. Returns the compact table summary."
)

FETCH_MULTI_ENTITY_OBSERVATIONS_DESCRIPTION = (
    "Fetch a relationship variable between entities (bilateral "
    "trade, aid flows, migration) into the server cache. Only "
    "for variables whose observations name more than one "
    "entity. Returns the compact table summary, or, when the rows are not "
    "keyed by place or none falls in the requested dates, a compact summary "
    "with a null table_id."
)

# A single fetch_observations call fans out to at most this many places.
_MAX_PLACES_PER_FETCH = 50
# A fetch for more than this many named places is a cohort, which uses the
# cohort date window by default.
NAMED_PLACE_SERIES_LIMIT = 10
# A cohort fetch defaults to this many calendar years ending at the current
# year.
COHORT_WINDOW_YEARS = 10

type DateMode = Literal["latest", "all", "range", "year"]
_DATE_MODES: frozenset[str] = frozenset(get_args(DateMode.__value__))
# A `year` argument is a four-digit `YYYY` year.
_YEAR_LENGTH = 4
# The error for an `entities` argument that is not a non-empty mapping of
# entity property names to DCID lists.
_ENTITIES_ERROR = "entities must map each entity property to a list of DCIDs."
# The error for function-call arguments that are not a JSON object.
_ARGUMENTS_ERROR = "arguments must be a JSON object."
# Pydantic prefixes the message of a `ValueError` raised in a validator with
# this text, and the fallback message covers an error without one.
_PYDANTIC_VALUE_ERROR_PREFIX = "Value error, "
_DEFAULT_VALIDATION_MESSAGE = "Invalid fetch arguments."
# The optional child expansion of a multi-entity fetch, whose fields are
# given together or not at all.
_EXPANSION_FIELDS = (
    "parent_entity_property",
    "parent_entity_dcid",
    "child_entity_type",
)

# Model output may carry keys a request does not define, which are ignored
# rather than rejected; a validated request's attributes cannot be
# reassigned.
_REQUEST_CONFIG = ConfigDict(extra="ignore", frozen=True)


class FetchArgumentError(ValueError):
    """Raised when a fetch fails in a way the model can correct.

    The arguments are invalid, the MCP tool reports an error, or its response
    is not a readable observation payload. The message is written for the
    model, so that the caller can return it as the tool's error and the model
    can correct the call.

    Attributes:
        place_dcid: The place whose call failed, or `None` when the error is
            not tied to one place.
    """

    def __init__(self, message: str, *, place_dcid: str | None = None) -> None:
        super().__init__(message)
        self.place_dcid = place_dcid

    def build_error_response(self) -> JsonObject:
        """Builds the structured error the model receives as a tool response.

        Returns:
            `{"error": message}`, with `place_dcid` added when the error names
            a place.
        """
        result: JsonObject = {"error": str(self)}
        if self.place_dcid is not None:
            result["place_dcid"] = self.place_dcid
        return result


def _read_optional_text(
    arguments: Mapping[str, object], key: str
) -> str | None:
    """Returns the stripped string argument `key`.

    Returns `None` when the argument is absent, null, or blank.

    Raises:
        FetchArgumentError: If the argument is present and not a string.
    """
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise FetchArgumentError(f"{key} must be a string.")
    return value.strip() or None


def _read_required_text(arguments: Mapping[str, object], key: str) -> str:
    """Returns the stripped string argument `key`.

    Raises:
        FetchArgumentError: If the argument is missing or blank, or is
            present and not a string.
    """
    value = _read_optional_text(arguments, key)
    if value is None:
        raise FetchArgumentError(f"{key} is required.")
    return value


def _read_text_list(arguments: Mapping[str, object], key: str) -> list[str]:
    """Returns the deduplicated non-empty strings of the list argument `key`.

    Raises:
        FetchArgumentError: As `_normalize_text_list` documents.
    """
    return _normalize_text_list(arguments.get(key), key)


def _normalize_text_list(value: object, label: str) -> list[str]:
    """Returns the deduplicated non-empty strings of a list value.

    A bare string is read as a one-item list, because a model naming one
    place tends to pass it bare. Blank strings are dropped, and `None` reads
    as an empty list.

    Raises:
        FetchArgumentError: If `value` is neither a string nor a list, or an
            item of the list is not a string. The message names `label`.
    """
    if value is None:
        return []
    if isinstance(value, str):
        items_raw: list[object] = [value]
    elif isinstance(value, list):
        items_raw = list(value)
    else:
        raise FetchArgumentError(f"{label} must be a list of DCID strings.")
    if not all(isinstance(item, str) for item in items_raw):
        raise FetchArgumentError(f"{label} must be a list of DCID strings.")
    items = [item.strip() for item in items_raw if isinstance(item, str)]
    return list(dict.fromkeys(item for item in items if item))


def _is_valid_year(year: str | None) -> bool:
    """Returns whether `year` is a real four-digit `YYYY` year."""
    return (
        year is not None
        and len(year) == _YEAR_LENGTH
        and is_valid_observation_date(year)
    )


def validate_date_selection_fields(
    date_mode: str | None,
    start_date: str | None,
    end_date: str | None,
    year: str | None,
) -> None:
    """Validates the date arguments of a fetch.

    A `start_date` or `end_date` selects a range whatever the mode, so the
    bounds are checked whenever either is given. `year` is checked only when
    `date_mode` is `year`.

    Args:
        date_mode: `latest`, `all`, `range`, `year`, or `None`.
        start_date: The inclusive start of a range, or `None`.
        end_date: The inclusive end of a range, or `None`.
        year: The year of a `year` fetch, or `None`.

    Raises:
        FetchArgumentError: If the mode is unknown, a bound is not a valid
            `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` date, the range is inverted, a
            `range` mode has neither bound, or a `year` mode lacks a valid
            `YYYY` year.
    """
    if date_mode is not None and date_mode not in _DATE_MODES:
        raise FetchArgumentError(
            "date_mode must be one of latest, all, range, or year."
        )
    for label, bound in (("start_date", start_date), ("end_date", end_date)):
        if bound is not None and not is_valid_observation_date(bound):
            raise FetchArgumentError(
                f"{label} must be a YYYY, YYYY-MM, or YYYY-MM-DD date."
            )
    if date_mode == "range" or start_date is not None or end_date is not None:
        if start_date is None and end_date is None:
            raise FetchArgumentError(
                "date_mode 'range' needs start_date, end_date, or both."
            )
        if (
            start_date is not None
            and end_date is not None
            and is_inverted_date_range(start_date, end_date)
        ):
            raise FetchArgumentError("start_date is after end_date.")
        return
    if date_mode == "year" and not _is_valid_year(year):
        raise FetchArgumentError("date_mode 'year' needs year as YYYY.")


def _extract_date_fields(data: Mapping[str, object]) -> dict[str, object]:
    """Extracts and validates the shared date and source override fields."""
    date_mode = _read_optional_text(data, "date_mode")
    start_date = _read_optional_text(data, "start_date")
    end_date = _read_optional_text(data, "end_date")
    year = _read_optional_text(data, "year")
    source_override = _read_optional_text(data, "source_override")
    validate_date_selection_fields(date_mode, start_date, end_date, year)
    return {
        "date_mode": date_mode,
        "start_date": start_date,
        "end_date": end_date,
        "year": year,
        "source_override": source_override,
    }


class DateSelection(BaseModel):
    """Shared date and facet-override fields for the server fetch functions.

    Each request model validates these fields in its own `before` validator,
    through `_extract_date_fields`.

    Attributes:
        date_mode: How much history to fetch, or `None` for the default:
            the full series for up to `NAMED_PLACE_SERIES_LIMIT` named
            places, and the cohort window otherwise.
        start_date: The inclusive start of a range, or `None` when the range
            is open at the start or no range is requested.
        end_date: The inclusive end of a range, or `None` when the range is
            open at the end or no range is requested.
        year: The year of a `year` fetch, or `None` when it is omitted. It is
            read only when `date_mode` is `year`.
        source_override: The facet to fetch from, or `None` to use the facet
            the variable is locked to or, failing that, the server's choice.
    """

    model_config = _REQUEST_CONFIG

    date_mode: DateMode | None = Field(
        default=None,
        description=(
            "How much history to fetch. Omit it for the default: the full "
            f"series for up to {NAMED_PLACE_SERIES_LIMIT} named places, and "
            f"the last {COHORT_WINDOW_YEARS} calendar years for more named "
            "places, for child places, and for a multi-entity child "
            "expansion. 'range' uses start_date and end_date, 'year' uses "
            "year. A start_date or end_date selects a range whatever "
            "date_mode is."
        ),
    )
    start_date: ObservationDate | None = Field(
        default=None,
        description=(
            "Inclusive start of a range as YYYY, YYYY-MM, or YYYY-MM-DD."
        ),
    )
    end_date: ObservationDate | None = Field(
        default=None,
        description=(
            "Inclusive end of a range as YYYY, YYYY-MM, or YYYY-MM-DD."
        ),
    )
    year: str | None = Field(
        default=None,
        description=(
            "The single year to fetch, as YYYY, when date_mode is 'year'."
        ),
    )
    source_override: Dcid | None = Field(
        default=None,
        description=(
            "A facet ID from an earlier summary's facet_id, or a source_id "
            "from its alternative_sources, to fetch from that source. Omit "
            "it to let the server choose, or to reuse the facet an earlier "
            "fetch of the same variable over the same places (named places, "
            "or the same parent and child place type) was served from."
        ),
    )


class FetchObservationsRequest(DateSelection):
    """Arguments for `fetch_observations`, with the `DateSelection` fields.

    Attributes:
        variable_dcid: The statistical variable DCID.
        place_dcids: The distinct place DCIDs to fetch, in request order, at
            least one and at most 50.
    """

    variable_dcid: Dcid = Field(description="The statistical variable DCID.")
    place_dcids: list[Dcid] = Field(
        description=(
            f"The place DCIDs to fetch (at most {_MAX_PLACES_PER_FETCH})."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _validate_request(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            raise FetchArgumentError(_ARGUMENTS_ERROR)
        variable_dcid = _read_required_text(data, "variable_dcid")
        place_dcids = _read_text_list(data, "place_dcids")
        if not place_dcids:
            raise FetchArgumentError(
                "place_dcids is required: a non-empty list of place DCIDs."
            )
        if len(place_dcids) > _MAX_PLACES_PER_FETCH:
            raise FetchArgumentError(
                f"fetch_observations accepts at most {_MAX_PLACES_PER_FETCH} "
                f"places, not {len(place_dcids)}; use "
                "fetch_child_observations for a whole cohort."
            )
        dates = _extract_date_fields(data)
        return {
            "variable_dcid": variable_dcid,
            "place_dcids": place_dcids,
            **dates,
        }


class FetchChildObservationsRequest(DateSelection):
    """Arguments for `fetch_child_observations`, with the date fields.

    Attributes:
        variable_dcid: The statistical variable DCID.
        parent_place_dcid: The parent place whose children are fetched.
        child_place_type: The place type of the children, such as `State`.
    """

    variable_dcid: Dcid = Field(description="The statistical variable DCID.")
    parent_place_dcid: Dcid = Field(
        description="The parent place DCID, such as Earth or country/USA."
    )
    child_place_type: PlaceType = Field(
        description=("The child place type, such as Country, State, or County.")
    )

    @model_validator(mode="before")
    @classmethod
    def _validate_request(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            raise FetchArgumentError(_ARGUMENTS_ERROR)
        variable_dcid = _read_required_text(data, "variable_dcid")
        parent_place_dcid = _read_required_text(data, "parent_place_dcid")
        child_place_type = _read_required_text(data, "child_place_type")
        dates = _extract_date_fields(data)
        return {
            "variable_dcid": variable_dcid,
            "parent_place_dcid": parent_place_dcid,
            "child_place_type": child_place_type,
            **dates,
        }


def _read_entities(data: Mapping[str, object]) -> dict[str, list[str]]:
    """Returns the `entities` argument as deduplicated, non-empty DCID lists.

    Each value is read as `place_dcids` is: a bare string is a one-item list,
    and blank strings are dropped.

    Raises:
        FetchArgumentError: If `entities` is not a non-empty mapping, a key
            is blank or repeats another key once stripped, a value is not a
            string or a list of strings, or a value holds no DCID.
    """
    raw_entities = data.get("entities")
    if not isinstance(raw_entities, Mapping) or not raw_entities:
        raise FetchArgumentError(_ENTITIES_ERROR)
    entities: dict[str, list[str]] = {}
    for key, value in raw_entities.items():
        if not isinstance(key, str) or not key.strip():
            raise FetchArgumentError(_ENTITIES_ERROR)
        name = key.strip()
        if name in entities:
            raise FetchArgumentError(
                "entities names one property more than once."
            )
        dcids = _normalize_text_list(value, "each entities value")
        if not dcids:
            raise FetchArgumentError(_ENTITIES_ERROR)
        entities[name] = dcids
    return entities


def _read_expansion(data: Mapping[str, object]) -> dict[str, str | None]:
    """Returns the child expansion fields of a multi-entity fetch.

    Raises:
        FetchArgumentError: If some of the expansion fields are given and
            others are not.
    """
    expansion = {
        name: _read_optional_text(data, name) for name in _EXPANSION_FIELDS
    }
    given = [value for value in expansion.values() if value is not None]
    if given and len(given) < len(_EXPANSION_FIELDS):
        raise FetchArgumentError(
            "parent_entity_property, parent_entity_dcid, and "
            "child_entity_type must be given together or not at all."
        )
    return expansion


class FetchMultiEntityRequest(DateSelection):
    """Arguments for `fetch_multi_entity_observations`, with the date fields.

    Attributes:
        variable_dcid: The relationship variable DCID.
        entities: The DCIDs of each entity property, at least one property
            with at least one DCID each.
        parent_entity_property: The entity property expanded into child
            places, or `None` when no property is expanded. The three
            expansion fields are all set or all `None`.
        parent_entity_dcid: The parent place of the expansion, or `None` when
            no property is expanded.
        child_entity_type: The child place type of the expansion, or `None`
            when no property is expanded.
    """

    variable_dcid: Dcid = Field(description="The relationship variable DCID.")
    entities: dict[str, list[Dcid]] = Field(
        description=(
            "A JSON object whose keys are entity property names and whose "
            'values are lists of DCIDs, such as {"donor": ["country/ARE"], '
            '"recipient": ["country/AFG"]}.'
        )
    )
    parent_entity_property: str | None = Field(
        default=None,
        description=(
            "The entity property to expand into child places. Give it with "
            "parent_entity_dcid and child_entity_type, or omit all three."
        ),
    )
    parent_entity_dcid: Dcid | None = Field(
        default=None,
        description="The parent place of the child expansion.",
    )
    child_entity_type: PlaceType | None = Field(
        default=None,
        description="The child place type of the expansion.",
    )

    @model_validator(mode="before")
    @classmethod
    def _validate_request(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            raise FetchArgumentError(_ARGUMENTS_ERROR)
        variable_dcid = _read_required_text(data, "variable_dcid")
        entities = _read_entities(data)
        expansion = _read_expansion(data)
        dates = _extract_date_fields(data)
        return {
            "variable_dcid": variable_dcid,
            "entities": entities,
            **expansion,
            **dates,
        }


type FetchRequest = (
    FetchObservationsRequest
    | FetchChildObservationsRequest
    | FetchMultiEntityRequest
)

_MODELS_BY_NAME: dict[str, type[FetchRequest]] = {
    FETCH_OBSERVATIONS: FetchObservationsRequest,
    FETCH_CHILD_OBSERVATIONS: FetchChildObservationsRequest,
    FETCH_MULTI_ENTITY_OBSERVATIONS: FetchMultiEntityRequest,
}


def _unwrap_validation_error(error: ValidationError) -> FetchArgumentError:
    """Converts the first error in `error` into a `FetchArgumentError`.

    A `FetchArgumentError` raised by a validator is returned as raised. Any
    other error is prefixed with the name of the argument it concerns, such
    as `place_dcids`, so the model can tell which argument to correct. The
    position within a list is not reported, because the lists are
    deduplicated and stripped of blanks before validation, so an index would
    not match the arguments the model sent.
    """
    errors = error.errors()
    if not errors:
        return FetchArgumentError(str(error))
    first = errors[0]
    context = first.get("ctx")
    if isinstance(context, Mapping):
        inner = context.get("error")
        if isinstance(inner, FetchArgumentError):
            return inner
        if isinstance(inner, Exception):
            return FetchArgumentError(str(inner))
    message = first.get("msg", _DEFAULT_VALIDATION_MESSAGE)
    message = message.removeprefix(_PYDANTIC_VALUE_ERROR_PREFIX)
    location = first.get("loc", ())
    argument = str(location[0]) if location else ""
    return FetchArgumentError(f"{argument}: {message}" if argument else message)


def parse_fetch_request(
    name: str, arguments: Mapping[str, JsonValue]
) -> FetchRequest:
    """Validates raw function-call arguments into a typed `FetchRequest`.

    Args:
        name: One of `FETCH_FUNCTION_NAMES`.
        arguments: The function call's arguments as the model sent them.

    Returns:
        The validated request model for `name`.

    Raises:
        KeyError: If `name` is not one of the three server fetch functions.
        FetchArgumentError: If `arguments` fails validation.
    """
    model_class = _MODELS_BY_NAME[name]
    try:
        return model_class.model_validate(arguments)
    except ValidationError as error:
        raise _unwrap_validation_error(error) from error

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
"""Loads, verifies, signs, and compacts the client-held transcript.

`Transcript` is the object that holds the conversation history for a turn.
Today, the browser stores that history and sends it with every request:
`load_transcript` validates and verifies the request's history into a
`Transcript`, and `finalize_turn` compacts and signs the completed turn into
the updated window that the browser stores for the next request. Isolating
conversation history in `Transcript` is also a forward-looking design choice:
because the model loop and downstream workflows depend only on `Transcript`,
moving conversation history to server-side session storage later only requires
changing `load_transcript` and `finalize_turn`.

Each `Turn.hmac` is an HMAC-SHA256, under the server's key, of a canonical
JSON encoding of the previous turn's `hmac` (the empty string for the first
turn of the window), the turn's own fields, and the window's
`compacted_summary`. `load_transcript` recomputes the chain from the front
of the window and compares every signature in constant time, so a client
cannot alter, drop, reorder, or splice turns, or swap the summary, without
the request being rejected.

A window holds at most `MAX_VERBATIM_TURNS` turns. When a completed turn
would exceed that limit, `finalize_turn` folds the oldest turns into
`compacted_summary` and re-signs every retained turn from the front of the
window under the new summary. The chain is therefore anchored at the window
rather than at the first turn of the conversation: the browser always holds
a window that the server signed as a unit, verification is one uniform loop,
and no separate anchor signature is needed. A window that starts at turn 0
must not carry a summary, and any other window must.

Without server-side state, a client can resend an older window it was
legitimately given, rolling the conversation back to an earlier point, and
it can drop turns from the end of its window. Neither action introduces
content the server did not sign. Detecting either requires a server-side
session store.
"""

import asyncio
import functools
import hashlib
import hmac
import json
import logging
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from narratives_agent.config import get_gemini_model
from narratives_agent.gemini.client import async_gemini_request
from narratives_agent.settings import get_settings
from narratives_agent.telemetry import TokenUsage

logger = logging.getLogger(__name__)

# These limits bound what a request may carry, and `finalize_turn` never
# signs a turn that would exceed them, so a window the server signed is
# always accepted when it comes back.
MAX_VERBATIM_TURNS = 6
MAX_QUERY_CHARS = 4_000
MAX_RESPONSE_CHARS = 32_000
MAX_SUMMARY_CHARS = 8_000
MAX_IDEMPOTENCY_KEY_CHARS = 128
MAX_SCOPES_PER_TURN = 8
MAX_ENTRIES_PER_SCOPE = 25
MAX_DCID_CHARS = 256
MAX_NAME_CHARS = 200
MAX_PLACE_TYPE_CHARS = 64
# A bound on `turn_index` far above any real conversation, so that a forged
# index cannot be an arbitrarily large integer.
MAX_TURN_INDEX = 1_000_000

# A DCID is non-empty printable ASCII without whitespace or control characters.
DCID_PATTERN = r"^[!-~]+$"
# Display names must not contain newlines or other control characters,
# because they are formatted into single-line summaries in model prompts.
DISPLAY_NAME_PATTERN = r"^[^\x00-\x1f\x7f]+$"
# A place type is a schema class name such as "State" or
# "AdministrativeArea1".
PLACE_TYPE_PATTERN = r"^[A-Za-z0-9]+$"
# An observation date is a year, a year and month, or a full date.
DATE_PATTERN = r"^[0-9]{4}(-[0-9]{2}){0,2}$"

# `COMPACTION_TIMEOUT_SECONDS` bounds the compaction model call. The answer
# has already streamed when compaction runs, so a slow call falls back to
# the structured summary rather than delaying the terminal event further.
COMPACTION_TIMEOUT_SECONDS = 5
_COMPACTION_TEMPERATURE = 0.1
_SUMMARY_WORD_BUDGET = 300
# Maximum characters of each evicted answer quoted to the compaction model.
_COMPACTION_RESPONSE_CHARS = 4_000
# Maximum characters of each evicted query and answer kept by the structured
# fallback summary.
_FALLBACK_QUERY_CHARS = 300
_FALLBACK_RESPONSE_CHARS = 600

# `_HMAC_DOMAIN` separates turn signatures from anything else that might
# one day be signed with the same key, and versions the payload layout.
# Change its version whenever a signed field or the state-slot schema
# changes, so that windows signed under the old layout fail verification
# with a clear reason rather than by accident.
_HMAC_DOMAIN = "narratives.transcript.turn.v1"
_GENERATED_KEY_BYTES = 32

_COMPACTION_INSTRUCTION = (
    "You condense the earlier turns of a conversation about statistical "
    "data into a factual summary. Later turns read the summary to resolve "
    'references such as "them" or "that period". Keep every place and '
    "variable with its DCID, every date range, and each key figure and "
    "conclusion. Do not add facts that are not in the input. Write plain "
    f"prose of at most {_SUMMARY_WORD_BUDGET} words."
)

type Dcid = Annotated[
    str, StringConstraints(pattern=DCID_PATTERN, max_length=MAX_DCID_CHARS)
]
type DisplayName = Annotated[
    str,
    StringConstraints(
        pattern=DISPLAY_NAME_PATTERN, min_length=1, max_length=MAX_NAME_CHARS
    ),
]
type PlaceType = Annotated[
    str,
    StringConstraints(
        pattern=PLACE_TYPE_PATTERN, max_length=MAX_PLACE_TYPE_CHARS
    ),
]
type ObservationDate = Annotated[str, StringConstraints(pattern=DATE_PATTERN)]
type IdempotencyKey = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_IDEMPOTENCY_KEY_CHARS)
]
type SummaryText = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_SUMMARY_CHARS)
]


class _WireModel(BaseModel):
    """Rejects unknown fields, since every field is covered by a signature."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class QueryScope(_WireModel):
    """Records the places, variables, and date range of one data query or chart.

    The places are either listed explicitly in `places` or specified as a
    cohort of every place of type `child_place_type` within `parent_place`.
    The `places`, `parent_place`, and `variables` dicts map each DCID to its
    display name.
    """

    places: dict[Dcid, DisplayName] = Field(
        default_factory=dict, max_length=MAX_ENTRIES_PER_SCOPE
    )
    parent_place: (
        Annotated[dict[Dcid, DisplayName], Field(min_length=1, max_length=1)]
        | None
    ) = None
    child_place_type: PlaceType | None = None
    variables: dict[Dcid, DisplayName] = Field(
        default_factory=dict, max_length=MAX_ENTRIES_PER_SCOPE
    )
    date_range: tuple[ObservationDate, ObservationDate] | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        """Rejects a scope that is empty or internally inconsistent.

        Raises:
            ValueError: The scope has no variables, has neither places nor a
                cohort, has half a cohort, or has a date range that ends
                before it starts.
        """
        if (self.parent_place is None) != (self.child_place_type is None):
            raise ValueError("a cohort needs both a parent and a place type")
        if not self.variables:
            raise ValueError("a scope needs at least one variable")
        if not self.places and self.parent_place is None:
            raise ValueError("a scope needs places or a cohort")
        if self.date_range and self.date_range[0] > self.date_range[1]:
            raise ValueError("a date range must not end before it starts")
        return self


class ConversationStateSlots(_WireModel):
    """Holds the query scopes (places, variables, and date ranges) from a turn.

    Storing these scopes in the transcript lets later turns resolve
    references such as "compare them to Germany" or "what about 2020?" to
    the exact DCIDs and dates from earlier turns instead of parsing them out
    of prose answers.
    """

    scopes: list[QueryScope] = Field(
        default_factory=list, max_length=MAX_SCOPES_PER_TURN
    )


class Turn(_WireModel):
    """Represents one completed, signed turn stored and sent by the browser.

    `turn_index` counts signed turns from 0 across the whole conversation,
    so it keeps increasing after older turns are compacted away. `hmac` is
    the hex HMAC-SHA256 signature described in the module docstring.
    """

    turn_index: int = Field(ge=0, le=MAX_TURN_INDEX)
    idempotency_key: IdempotencyKey
    user_query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    model_response: str = Field(min_length=1, max_length=MAX_RESPONSE_CHARS)
    state_slots: ConversationStateSlots
    hmac: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Transcript:
    """Holds the verified context handed to the model loop for one turn.

    `turns` is the sliding window of recent verified turns, oldest first.
    `compacted_summary` summarizes the turns compacted out of the window and
    is `None` until the window first overflows.
    """

    turns: list[Turn]
    compacted_summary: str | None
    current_query: str
    current_idempotency_key: str


@dataclass(frozen=True)
class SignedWindow:
    """Holds the window signed at the end of a turn.

    `turns` is the complete window the browser must send with its next
    request, oldest first, ending with the turn that just completed. Every
    `hmac` in it may differ from the one the browser holds, because
    compaction re-signs the whole window.
    """

    turns: list[Turn]
    compacted_summary: str | None

    @property
    def turn(self) -> Turn:
        """Returns the turn that just completed."""
        return self.turns[-1]


class _Window(_WireModel):
    """Validates the transcript fields of a request as one unit."""

    turns: list[Turn] = Field(max_length=MAX_VERBATIM_TURNS)
    compacted_summary: SummaryText | None


class TranscriptRequest(Protocol):
    """Describes the request fields from which a transcript is loaded.

    `turns` and `compacted_summary` arrive unvalidated, as decoded JSON, so
    that a window that does not match the schema is reported by
    `load_transcript` as a `TranscriptError`, the same as one whose
    signatures do not match, rather than as a generic validation failure.
    """

    @property
    def message(self) -> str: ...

    @property
    def idempotency_key(self) -> str: ...

    @property
    def turns(self) -> object: ...

    @property
    def compacted_summary(self) -> object: ...


class TranscriptError(Exception):
    """Raised when a request's transcript fails verification.

    `reason` is a short machine-readable code for logs. The message is safe
    to return to the client.
    """

    def __init__(self, reason: str) -> None:
        super().__init__("The conversation history could not be verified.")
        self.reason = reason


@functools.cache
def _signing_key() -> bytes:
    """Returns the transcript signing key, resolved once per process.

    The key is `TRANSCRIPT_HMAC_SECRET` when it is set. Otherwise it is a
    random key that lives as long as the process, which suffices for a
    single local server; on Cloud Run, where requests reach several
    instances and instances restart, a warning is logged.
    """
    settings = get_settings()
    secret = settings.transcript_hmac_secret.get_secret_value()
    if secret:
        return secret.encode("utf-8")
    if settings.k_service:
        logger.warning(
            "TRANSCRIPT_HMAC_SECRET is not set, so transcripts are signed "
            "with a key that exists only in this instance. A follow-up turn "
            "that reaches another instance, or arrives after a restart, "
            "fails verification and loses its earlier context. Set "
            "TRANSCRIPT_HMAC_SECRET to a secret shared by every instance."
        )
    return secrets.token_bytes(_GENERATED_KEY_BYTES)


def reset_signing_key() -> None:
    """Makes the next signature resolve the signing key again."""
    _signing_key.cache_clear()


def _turn_signature(
    prev_hmac: str, turn: Turn, compacted_summary: str | None
) -> str:
    """Returns the hex HMAC-SHA256 that chains `turn` to its predecessor.

    The payload is canonical JSON (sorted keys, no insignificant
    whitespace, ASCII escapes), so the browser's copy of a turn, parsed back
    into a `Turn`, encodes to exactly the bytes that were signed. The turn's
    own `hmac` is not part of the payload.
    """
    payload: dict[str, Any] = {
        "domain": _HMAC_DOMAIN,
        "prev_hmac": prev_hmac,
        "turn_index": turn.turn_index,
        "idempotency_key": turn.idempotency_key,
        "user_query": turn.user_query,
        "model_response": turn.model_response,
        "state_slots": turn.state_slots.model_dump(mode="json"),
        "compacted_summary": compacted_summary,
    }
    message = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        _signing_key(), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _sign_window(
    turns: Sequence[Turn], compacted_summary: str | None
) -> list[Turn]:
    """Returns `turns` re-signed as one chain from the front of the window."""
    signed: list[Turn] = []
    prev_hmac = ""
    for turn in turns:
        signature = _turn_signature(prev_hmac, turn, compacted_summary)
        signed.append(turn.model_copy(update={"hmac": signature}))
        prev_hmac = signature
    return signed


def _reject(reason: str) -> TranscriptError:
    """Logs a rejected transcript and returns the error to raise."""
    logger.warning("Rejected the request transcript: %s", reason)
    return TranscriptError(reason)


def _check_window_shape(
    turns: Sequence[Turn],
    compacted_summary: str | None,
    current_idempotency_key: str,
) -> None:
    """Checks the structure of a window before its signatures.

    Raises:
        TranscriptError: A summary arrives without turns, the window's
            first index disagrees with the presence of a summary, the
            indexes are not contiguous, or an idempotency key repeats.
    """
    if not turns:
        if compacted_summary is not None:
            raise _reject("summary_without_turns")
        return
    first_index = turns[0].turn_index
    if (first_index == 0) != (compacted_summary is None):
        raise _reject("window_start_mismatch")
    for offset, turn in enumerate(turns):
        if turn.turn_index != first_index + offset:
            raise _reject("non_contiguous_turns")
    keys = [turn.idempotency_key for turn in turns]
    keys.append(current_idempotency_key)
    if len(set(keys)) != len(keys):
        raise _reject("duplicate_idempotency_key")


def load_transcript(request: TranscriptRequest) -> Transcript:
    """Returns the verified transcript a request carries.

    This is the only way the model loop obtains conversation history. It
    validates the window against its schema and caps, then checks its
    structure and its signature chain.

    Args:
        request: The request object carrying `message`, `idempotency_key`,
            `turns`, and `compacted_summary`.

    Returns:
        The verified `Transcript` for the turn.

    Raises:
        TranscriptError: The window does not match its schema, is malformed,
            or any signature does not match.
    """
    try:
        window = _Window.model_validate(
            {
                "turns": request.turns,
                "compacted_summary": request.compacted_summary,
            }
        )
    except ValidationError as error:
        logger.warning(
            "Rejected the request transcript: invalid_window (%d errors)",
            error.error_count(),
        )
        raise TranscriptError("invalid_window") from error
    turns = window.turns
    summary = window.compacted_summary
    _check_window_shape(turns, summary, request.idempotency_key)
    prev_hmac = ""
    for turn in turns:
        expected = _turn_signature(prev_hmac, turn, summary)
        if not hmac.compare_digest(expected, turn.hmac):
            raise _reject("signature_mismatch")
        prev_hmac = turn.hmac
    return Transcript(
        turns=turns,
        compacted_summary=summary,
        current_query=request.message,
        current_idempotency_key=request.idempotency_key,
    )


async def finalize_turn(
    transcript: Transcript,
    model_response: str,
    state_slots: ConversationStateSlots,
    config: dict[str, Any],
    token_usage: TokenUsage | None = None,
) -> SignedWindow | None:
    """Appends the completed turn to the window and signs the result.

    When the window would exceed `MAX_VERBATIM_TURNS`, the oldest turns are
    compacted into `compacted_summary`, and the retained window is re-signed
    under the new summary. Compaction never fails the turn: if the model
    call fails, times out, or returns no text, a structured summary is
    built from the evicted turns instead.

    Args:
        transcript: The verified transcript the turn ran with.
        model_response: The complete answer text streamed to the browser.
        state_slots: The scopes extracted from the turn's tool calls.
        config: The agent configuration used to select the compaction model.
        token_usage: Optional turn totals that receive the compaction call's
            token counts.

    Returns:
        The signed window, or `None` when the answer exceeds
        `MAX_RESPONSE_CHARS`. Signing such an answer would produce a turn
        that request validation rejects on the next request, so the turn
        stays unsigned: the browser leaves it out of later requests and
        keeps sending the previous window, which remains valid.
    """
    if len(model_response) > MAX_RESPONSE_CHARS:
        logger.warning(
            "The answer has %d characters, more than %d, so the turn is not "
            "signed and is left out of later context",
            len(model_response),
            MAX_RESPONSE_CHARS,
        )
        return None
    previous = transcript.turns
    # Every field was validated already: the query and key on the request,
    # the slots by their own model, and the answer length above. The
    # placeholder `hmac` is replaced by `_sign_window` before the turn
    # leaves here.
    completed = Turn.model_construct(
        turn_index=previous[-1].turn_index + 1 if previous else 0,
        idempotency_key=transcript.current_idempotency_key,
        user_query=transcript.current_query,
        model_response=model_response,
        state_slots=state_slots,
        hmac="",
    )
    window = [*previous, completed]
    summary = transcript.compacted_summary
    if len(window) > MAX_VERBATIM_TURNS:
        evicted = window[:-MAX_VERBATIM_TURNS]
        window = window[-MAX_VERBATIM_TURNS:]
        summary = await _compact(summary, evicted, config, token_usage)
    return SignedWindow(
        turns=_sign_window(window, summary), compacted_summary=summary
    )


def _format_entities(entities: dict[str, str]) -> str:
    """Renders a DCID-to-name mapping as "Name (dcid)" items."""
    return ", ".join(
        dcid if name == dcid else f"{name} ({dcid})"
        for dcid, name in entities.items()
    )


def describe_scope(scope: QueryScope) -> str:
    """Renders a scope as one line of text for a model prompt.

    Args:
        scope: The query scope to format.

    Returns:
        A semicolon-separated description of the scope's places, variables,
        and date range.
    """
    parts: list[str] = []
    if scope.places:
        parts.append(f"places: {_format_entities(scope.places)}")
    if scope.parent_place:
        place_type = scope.child_place_type or "place"
        parts.append(
            f"places: every {place_type} in "
            f"{_format_entities(scope.parent_place)}"
        )
    if scope.variables:
        parts.append(f"variables: {_format_entities(scope.variables)}")
    if scope.date_range:
        start, end = scope.date_range
        parts.append(
            f"dates: {start}" if start == end else f"dates: {start} to {end}"
        )
    return "; ".join(parts)


def _excerpt(text: str, limit: int) -> str:
    """Returns `text` cut to `limit` characters, marked when it was cut."""
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _compaction_prompt(previous: str | None, evicted: Sequence[Turn]) -> str:
    """Builds the request that asks the model to extend the summary."""
    sections = [f"Earlier summary:\n{previous or '(none)'}"]
    sections.append("Turns to add to the summary, oldest first:")
    for turn in evicted:
        lines = [
            f"Turn {turn.turn_index + 1}",
            f"User: {turn.user_query}",
            "Assistant: "
            f"{_excerpt(turn.model_response, _COMPACTION_RESPONSE_CHARS)}",
        ]
        lines.extend(
            f"Data scope: {describe_scope(scope)}"
            for scope in turn.state_slots.scopes
        )
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _fallback_summary(previous: str | None, evicted: Sequence[Turn]) -> str:
    """Builds a summary from the evicted turns without a model call.

    When the result exceeds `MAX_SUMMARY_CHARS`, its oldest material is
    dropped, since later turns are the likelier referents.
    """
    lines = [previous] if previous else []
    for turn in evicted:
        lines.append(
            f"Turn {turn.turn_index + 1}. The user asked: "
            f"{_excerpt(turn.user_query, _FALLBACK_QUERY_CHARS)}"
        )
        lines.extend(
            f"Data scope: {describe_scope(scope)}"
            for scope in turn.state_slots.scopes
        )
        lines.append(
            "The answer began: "
            f"{_excerpt(turn.model_response, _FALLBACK_RESPONSE_CHARS)}"
        )
    return "\n".join(lines)[-MAX_SUMMARY_CHARS:]


def _response_text(response: dict[str, Any]) -> str:
    """Returns the text of a Gemini response, or "" when it has none."""
    candidates = response.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(
        str(part.get("text", "")) for part in parts if not part.get("thought")
    )


async def _compact(
    previous: str | None,
    evicted: Sequence[Turn],
    config: dict[str, Any],
    token_usage: TokenUsage | None,
) -> str:
    """Folds the evicted turns into the summary of earlier turns.

    Returns:
        The model's summary cut to `MAX_SUMMARY_CHARS`, or the structured
        fallback summary when the model call fails, times out, or returns
        no text.
    """
    try:
        async with asyncio.timeout(COMPACTION_TIMEOUT_SECONDS):
            response = await async_gemini_request(
                messages=[
                    {
                        "role": "user",
                        "parts": [
                            {"text": _compaction_prompt(previous, evicted)}
                        ],
                    }
                ],
                system_instruction=_COMPACTION_INSTRUCTION,
                model=get_gemini_model(config),
                temperature=_COMPACTION_TEMPERATURE,
                thinking_level="minimal",
                token_usage=token_usage,
            )
    except TimeoutError:
        logger.warning(
            "Compaction did not finish within %d seconds; using the "
            "structured summary",
            COMPACTION_TIMEOUT_SECONDS,
        )
        return _fallback_summary(previous, evicted)
    except Exception as error:
        # The answer has already streamed, so a compaction failure must not
        # fail the turn. The error type alone is logged because the request
        # carries conversation text.
        logger.warning(
            "Compaction failed with %s; using the structured summary",
            type(error).__name__,
        )
        return _fallback_summary(previous, evicted)
    summary = _response_text(response).strip()
    if not summary:
        logger.warning(
            "Compaction returned no summary text; using the structured summary"
        )
        return _fallback_summary(previous, evicted)
    return summary[:MAX_SUMMARY_CHARS]

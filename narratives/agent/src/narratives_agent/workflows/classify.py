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
"""Runs the classify phase, the admission step of the agent loop.

Applies a deterministic regex pre-filter (`prefilter_match`) to reject prompt
injections and exploit payloads before any model call, then requests a
structured `QueryClassification` from Gemini at temperature zero to refuse
adversarial or off-domain queries, return a clarification question, or admit
the query with its analytical pattern.
"""

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from narratives_agent.config import get_gemini_classify_model
from narratives_agent.gemini.client import (
    GeminiBlocked,
    async_gemini_request,
)
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.telemetry import TurnTelemetry
from narratives_agent.workflows.mcp_loop import MCP_HISTORY_RESPONSE_CHARS
from narratives_agent.workflows.messages import (
    OFF_DOMAIN_TEMPLATE,
    REFUSED_MESSAGE,
)
from narratives_agent.workflows.transcript import (
    Transcript,
    transcript_contents,
)

logger = logging.getLogger(__name__)

type RefusedReason = Literal["adversarial", "off_domain", "safety_blocked"]

# Upper bound in seconds for the classification model call before the turn
# proceeds unclassified.
CLASSIFY_TIMEOUT_SECONDS = 10

_CLASSIFY_TEMPERATURE = 0.0
# Sent on every classifier call; the configured `gemini.classify_model`
# must support `ThinkingLevel.MINIMAL` (see `_THINKING_LEVELS` in
# `gemini/client.py`).
_CLASSIFY_THINKING_LEVEL = "minimal"

# Maximum character length for the sanitized premise quoted in an off-domain
# refusal message.
MAX_PREMISE_CHARS = 80

# Zero-width spaces, joiners, byte-order marks, and soft hyphens stripped prior
# to pre-filter matching.
_INVISIBLE_CHARS = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")

# Compiled regex patterns paired with the attack family logged on a match.
# Instruction-override rules require an explicit instruction noun paired with
# `all`, `any`, `your`, or `system` so conversational self-corrections
# ("ignore the previous prompt, I meant Texas") and analytical constraints
# ("ignore the previous constraints on years") pass through to the classifier.
PREFILTER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (family, re.compile(pattern, re.IGNORECASE))
    for family, pattern in (
        (
            "instruction_override",
            r"\b(ignore|disregard|forget)\s+"
            r"((all|any|your)\s+(of\s+)?(the\s+)?"
            r"(previous|prior|above|earlier|preceding)\s+"
            r"(system\s+)?(instructions?|prompts?|directives?)|"
            r"(the\s+)?(previous|prior|above|earlier|preceding)\s+"
            r"system\s+(instructions?|prompts?|directives?))\b",
        ),
        (
            "persona_override",
            r"\byou\s+are\s+now\s+(acting\s+as\s+)?(an?\s+)?"
            r"(unrestricted|unfiltered|unmoderated)\b",
        ),
        (
            "persona_override",
            r"\bpretend\s+(you\s+are|to\s+be|you're)\s+(an?\s+)?"
            r"(unmoderated|unrestricted|unfiltered)\b",
        ),
        (
            "secret_exfiltration",
            r"\b(reveal|print|output|dump|show|display|repeat|leak|"
            r"exfiltrate)\b[^.?!]{0,40}?"
            r"\b(system|initial|original|hidden)\s*(prompt|instructions)\b",
        ),
        (
            "secret_exfiltration",
            r"\b(GEMINI_API_KEY(_SECRET)?|DC_API_KEY|TRANSCRIPT_HMAC_SECRET)"
            r"\b|\.env\.local\b",
        ),
        (
            "jailbreak_mode",
            r"\b(DAN\s+mode|developer\s+mode|god\s+mode|system\s+override|"
            r"new\s+system\s+directive)\b",
        ),
        (
            "injection_payload",
            r";\s*DROP\s+TABLE\b"
            r"|\bUNION\s+(ALL\s+)?SELECT\s+(NULL\b|\*|[^.?!]*"
            r"\b(information_schema|sqlite_master|pg_catalog|password)\b)"
            r"|'\s*OR\s+'?1'?\s*=\s*'?1"
            r"|\$\{jndi:ldap://"
            r"|/etc/passwd\b"
            r"|169\.254\.169\.254"
            r"|metadata\.google\.internal",
        ),
    )
)


class TurnRefusedError(Exception):
    """Raised when a turn ends in the `refused` terminal state.

    `reason` is the machine-readable refusal reason recorded in telemetry, and
    the exception message is the user-safe notice sent to the browser.
    """

    def __init__(self, reason: RefusedReason, message: str) -> None:
        super().__init__(message)
        self.reason: RefusedReason = reason


@dataclass(frozen=True)
class Clarification:
    """Represents a serviceable query that requires disambiguation first.

    `question` is streamed as the turn's response and signed into the
    transcript window so the user's follow-up reply carries context.
    """

    question: str
    classification: QueryClassification


@dataclass(frozen=True)
class Admitted:
    """Represents a query admitted into the discovery phase.

    `classification` is `None` when the classifier call failed, in which case
    the turn proceeds without a pattern directive and is recorded as
    `exploratory`.
    """

    classification: QueryClassification | None


def normalize_query(text: str) -> str:
    """Normalizes `text` for pre-filter pattern matching.

    Applies NFKC compatibility decomposition, strips invisible formatting
    characters, and collapses whitespace runs to a single space.
    """
    folded = unicodedata.normalize("NFKC", text)
    return " ".join(_INVISIBLE_CHARS.sub("", folded).split())


def prefilter_match(query: str) -> str | None:
    """Returns the first pre-filter family matched by `query`, or `None`."""
    normalized = normalize_query(query)
    for family, pattern in PREFILTER_PATTERNS:
        if pattern.search(normalized):
            return family
    return None


def off_domain_message(premise: str) -> str:
    """Formats the off-domain refusal message with a sanitized premise.

    Control characters and newlines are stripped and the result is truncated to
    `MAX_PREMISE_CHARS`. When the sanitized premise is empty, the parenthetical
    is omitted.
    """
    plain = " ".join(_CONTROL_CHARS.sub(" ", premise).split())
    plain = plain[:MAX_PREMISE_CHARS].strip()
    return OFF_DOMAIN_TEMPLATE.format(premise=f" ({plain})" if plain else "")


def _candidate_text(candidate: dict[str, Any]) -> str:
    """Returns the non-thought text content of `candidate`."""
    parts = candidate.get("content", {}).get("parts", [])
    return "".join(
        str(part.get("text", "")) for part in parts if not part.get("thought")
    )


async def _request_classification(
    transcript: Transcript, config: dict[str, Any], telemetry: TurnTelemetry
) -> QueryClassification | None:
    """Requests a `QueryClassification` from the configured classifier model.

    Returns:
        The validated classification, or `None` when the prompt is unconfigured,
        the request fails or times out, no candidates are returned, or the
        output fails schema validation.

    Raises:
        TurnRefusedError: If Gemini blocks the prompt or stops the candidate
            with a safety finish reason.
    """
    prompt = config.get("prompts", {}).get("classify", "")
    if not prompt:
        logger.warning(
            "The classify prompt is not configured; proceeding unclassified"
        )
        return None
    messages = transcript_contents(
        transcript,
        transcript.current_query,
        max_response_chars=MCP_HISTORY_RESPONSE_CHARS,
    )
    try:
        async with asyncio.timeout(CLASSIFY_TIMEOUT_SECONDS):
            response = await async_gemini_request(
                messages=messages,
                system_instruction=prompt,
                model=get_gemini_classify_model(config),
                temperature=_CLASSIFY_TEMPERATURE,
                thinking_level=_CLASSIFY_THINKING_LEVEL,
                response_schema=QueryClassification,
                token_usage=telemetry.tokens,
            )
    except TimeoutError:
        logger.warning(
            "Classifier request timed out after %d seconds; proceeding "
            "unclassified",
            CLASSIFY_TIMEOUT_SECONDS,
        )
        return None
    if isinstance(response, GeminiBlocked):
        raise TurnRefusedError("safety_blocked", REFUSED_MESSAGE)
    if "error" in response:
        # The Gemini client has already logged the redacted upstream error.
        logger.warning("Classifier request failed; proceeding unclassified")
        return None
    candidates = response.get("candidates") or []
    if not candidates:
        logger.warning(
            "Classifier returned no candidates; proceeding unclassified"
        )
        return None
    try:
        return QueryClassification.model_validate_json(
            _candidate_text(candidates[0])
        )
    except ValidationError as error:
        # Raw output is omitted from logs because it may contain query text.
        logger.warning(
            "Classifier output failed validation (%d errors); proceeding "
            "unclassified",
            error.error_count(),
        )
        return None


async def classify_query(
    transcript: Transcript, config: dict[str, Any], telemetry: TurnTelemetry
) -> Clarification | Admitted:
    """Runs the classify phase for one turn.

    Args:
        transcript: Verified transcript holding the current query and prior
            conversation context.
        config: Agent configuration supplying the classify prompt and model.
        telemetry: Turn telemetry accumulator receiving token counts.

    Returns:
        `Clarification` when the query requires disambiguation before discovery,
        or `Admitted` when the turn continues into the discovery phase.

    Raises:
        TurnRefusedError: If the pre-filter matches, the classifier marks the
            query unserviceable, or Gemini blocks the classification call.
    """
    family = prefilter_match(transcript.current_query)
    if family is not None:
        logger.warning("Pre-filter matched %s; refusing turn", family)
        raise TurnRefusedError("adversarial", REFUSED_MESSAGE)
    classification = await _request_classification(
        transcript, config, telemetry
    )
    if classification is None:
        return Admitted(None)
    if not classification.serviceable:
        if classification.refusal_reason == "off_domain":
            raise TurnRefusedError(
                "off_domain",
                off_domain_message(classification.off_topic_premise),
            )
        raise TurnRefusedError("adversarial", REFUSED_MESSAGE)
    question = (classification.clarification or "").strip()
    if question:
        return Clarification(question, classification)
    return Admitted(classification)

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

Applies the deterministic regex pre-filter in `prefilter.py` to reject prompt
injections and exploit payloads before any external call, optionally screens
the query against Google Cloud Model Armor (`model_armor.py`), and then
requests a structured `QueryClassification` from Gemini at temperature zero to
refuse adversarial or off-domain queries, return a clarification question, or
admit the query with its analytical pattern. When Model Armor does not return a
complete result or the classifier does not return a valid verdict, the phase
raises `ScreeningUnavailableError` and the turn ends without reaching discovery.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import ValidationError

from narratives_agent.config import get_current_date
from narratives_agent.config_model import AgentConfig, GeminiRole
from narratives_agent.gemini.client import (
    GeminiBlockedError,
    GeminiError,
    async_gemini_request,
)
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.model_armor import (
    ModelArmorUnavailableError,
    screen_user_prompt,
)
from narratives_agent.telemetry import ErrorType, TurnTelemetry
from narratives_agent.workflows.mcp_loop import MCP_HISTORY_RESPONSE_CHARS
from narratives_agent.workflows.messages import (
    OFF_DOMAIN_NAMED_SUBJECT,
    OFF_DOMAIN_TEMPLATE,
    OFF_DOMAIN_UNNAMED_SUBJECT,
    REFUSED_MESSAGE,
    SAFETY_REFUSED_MESSAGE,
)
from narratives_agent.workflows.prefilter import prefilter_match
from narratives_agent.workflows.transcript import (
    Transcript,
    transcript_contents,
)

logger = logging.getLogger(__name__)


class RefusedReason(StrEnum):
    """Machine-readable reasons a turn ends in the `refused` terminal state."""

    ADVERSARIAL = "adversarial"
    OFF_DOMAIN = "off_domain"
    SAFETY_BLOCKED = "safety_blocked"


# Upper bound in seconds for one classification model call. A call that
# exceeds it counts as a failed attempt.
CLASSIFY_TIMEOUT_SECONDS = 10

# Maximum classification model calls in one turn. A failed attempt that a
# repeated call can fix is followed by one more attempt, without a delay.
_MAX_CLASSIFY_ATTEMPTS = 2

# Maximum character length for the sanitized premise quoted in an off-domain
# refusal message.
MAX_PREMISE_CHARS = 80

# `_CURRENT_DATE_HEADER_TEMPLATE` is the server-authored line that opens the
# classify system instruction. It holds the date without a time, so the
# instruction changes once a day.
_CURRENT_DATE_HEADER_TEMPLATE = "**Current Date**: {current_date}\n\n"

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")


class TurnRefusedError(Exception):
    """Raised when a turn ends in the `refused` terminal state.

    `reason` is the machine-readable refusal reason recorded in telemetry, and
    the exception message is the user-safe notice sent to the browser.
    """

    def __init__(self, reason: RefusedReason, message: str) -> None:
        super().__init__(message)
        self.reason: RefusedReason = reason


class ScreeningUnavailableError(Exception):
    """Raised when the classify phase cannot screen the query.

    Model Armor did not return a complete result, or the classifier did not
    return a valid verdict. The message is an internal description of the
    failure and is not shown to the user.

    Attributes:
        error_type: Short machine-readable failure category for telemetry.
        is_retryable: False only when the failure is identified as
            permanent. Every other failure is retryable.
    """

    def __init__(
        self, error_type: ErrorType, message: str, *, is_retryable: bool
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.is_retryable = is_retryable


class _ClassifierAttemptError(Exception):
    """Raised when one classifier attempt does not return a valid verdict.

    Attributes:
        is_retryable: Whether a repeated request can succeed. False only
            when Gemini rejected the request permanently.
    """

    def __init__(self, message: str, *, is_retryable: bool) -> None:
        super().__init__(message)
        self.is_retryable = is_retryable


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

    `classification` is the classifier's verdict. Its pattern is recorded in
    telemetry and selects the pattern directive of the later phases.
    """

    classification: QueryClassification


def off_domain_message(premise: str) -> str:
    """Formats the off-domain refusal message with a sanitized premise.

    Control characters, newlines, and double quotes are stripped and the result
    is truncated to `MAX_PREMISE_CHARS`. When the sanitized premise is empty,
    the message names no topic.
    """
    plain = " ".join(_CONTROL_CHARS.sub(" ", premise).replace('"', "").split())
    plain = plain[:MAX_PREMISE_CHARS].strip()
    subject = (
        OFF_DOMAIN_NAMED_SUBJECT.format(premise=plain)
        if plain
        else OFF_DOMAIN_UNNAMED_SUBJECT
    )
    return OFF_DOMAIN_TEMPLATE.format(subject=subject)


def _compose_classify_instruction(prompt: str) -> str:
    """Returns the classify system instruction: the date line, then `prompt`.

    The date is the turn's pinned date (`get_current_date`). The date line
    opens the system instruction and `prompt` ends it, because a date line
    in the user message or a contract after `prompt` lowers the rate at
    which the classifier returns a clarification question for an ambiguous
    query.

    Args:
        prompt: The configured classify prompt.
    """
    header = _CURRENT_DATE_HEADER_TEMPLATE.format(
        current_date=get_current_date()
    )
    return f"{header}{prompt}"


async def _attempt_classification(
    transcript: Transcript,
    prompt: str,
    config: AgentConfig,
    telemetry: TurnTelemetry,
    *,
    attempt: int,
) -> QueryClassification:
    """Sends one classifier request and validates its reply.

    Args:
        transcript: Verified transcript holding the current query and prior
            conversation context.
        prompt: The configured classify prompt, which is not empty.
        config: The agent configuration that selects the classifier model.
        telemetry: Turn telemetry accumulator receiving token counts.
        attempt: 1-based attempt number logged when this request fails.

    Returns:
        The validated classification.

    Raises:
        _ClassifierAttemptError: If the request times out or fails, the
            reply is empty, or the output fails schema validation.
        GeminiBlockedError: If Gemini blocks the prompt or stops the
            candidate with a safety finish reason. The error propagates so
            that the turn ends as `refused`.
    """
    messages = transcript_contents(
        transcript,
        transcript.current_query,
        max_response_chars=MCP_HISTORY_RESPONSE_CHARS,
    )
    role = config.resolve_role_config(GeminiRole.CLASSIFY)
    try:
        async with asyncio.timeout(CLASSIFY_TIMEOUT_SECONDS):
            response = await async_gemini_request(
                messages=messages,
                system_instruction=_compose_classify_instruction(prompt),
                model=role.model,
                temperature=role.temperature,
                thinking_level=role.thinking_level,
                response_schema=QueryClassification,
                token_usage=telemetry.tokens,
                token_role=GeminiRole.CLASSIFY,
            )
    except TimeoutError as error:
        logger.warning(
            "Classifier request timed out after %d seconds (attempt %d/%d)",
            CLASSIFY_TIMEOUT_SECONDS,
            attempt,
            _MAX_CLASSIFY_ATTEMPTS,
        )
        raise _ClassifierAttemptError(
            "The classifier request timed out", is_retryable=True
        ) from error
    except GeminiBlockedError:
        # Propagates to `run_turn`, which ends the turn as `refused`.
        raise
    except GeminiError as error:
        # The Gemini client has already logged the redacted upstream error.
        logger.warning(
            "Classifier request failed (attempt %d/%d, retryable: %s)",
            attempt,
            _MAX_CLASSIFY_ATTEMPTS,
            error.is_retryable,
        )
        raise _ClassifierAttemptError(
            "The classifier request failed", is_retryable=error.is_retryable
        ) from error
    if not response.text.strip():
        logger.warning(
            "Classifier returned no text (attempt %d/%d, finish reason: %s)",
            attempt,
            _MAX_CLASSIFY_ATTEMPTS,
            response.finish_reason,
        )
        raise _ClassifierAttemptError(
            "The classifier returned an empty reply", is_retryable=True
        )
    try:
        return QueryClassification.model_validate_json(response.text)
    except ValidationError as error:
        # Raw output is omitted from logs because it may contain query text.
        logger.warning(
            "Classifier output failed validation (attempt %d/%d, %d errors)",
            attempt,
            _MAX_CLASSIFY_ATTEMPTS,
            error.error_count(),
        )
        raise _ClassifierAttemptError(
            "The classifier output failed validation", is_retryable=True
        ) from error


async def _request_classification(
    transcript: Transcript, config: AgentConfig, telemetry: TurnTelemetry
) -> QueryClassification:
    """Requests a `QueryClassification` from the configured classifier model.

    Makes at most `_MAX_CLASSIFY_ATTEMPTS` requests. A retryable failed
    attempt is followed by the next attempt at once, and every attempt adds
    its token counts to `telemetry`.

    Args:
        transcript: Verified transcript holding the current query and prior
            conversation context.
        config: The agent configuration. `prompts.classify` is the configured
            prompt of the system instruction and `gemini.classify_model` is
            the model.
        telemetry: Turn telemetry accumulator receiving token counts.

    Returns:
        The validated classification.

    Raises:
        ScreeningUnavailableError: With `classifier_unavailable`. The error
            is not retryable if the classify prompt is empty, in which case
            a request is not sent, or if Gemini rejects a request
            permanently. It is retryable if `_MAX_CLASSIFY_ATTEMPTS`
            attempts fail for other reasons.
        GeminiBlockedError: If Gemini blocks the prompt or stops the
            candidate with a safety finish reason. The error propagates so
            that the turn ends as `refused`.
    """
    prompt = config.prompts.classify
    if not prompt.strip():
        logger.warning("The classify prompt is not configured")
        raise ScreeningUnavailableError(
            ErrorType.CLASSIFIER_UNAVAILABLE,
            "The classify prompt is not configured",
            is_retryable=False,
        )
    attempt = 1
    while True:
        try:
            return await _attempt_classification(
                transcript, prompt, config, telemetry, attempt=attempt
            )
        except _ClassifierAttemptError as error:
            if not error.is_retryable or attempt >= _MAX_CLASSIFY_ATTEMPTS:
                raise ScreeningUnavailableError(
                    ErrorType.CLASSIFIER_UNAVAILABLE,
                    f"Classifier attempt {attempt} failed: {error}",
                    is_retryable=error.is_retryable,
                ) from error
            # The failed attempt is logged, and the next attempt replaces it.
        attempt += 1


async def _screen_with_model_armor(query: str) -> None:
    """Screens `query` with Model Armor and refuses the turn on a match.

    Args:
        query: The user query text to screen.

    Raises:
        TurnRefusedError: If a Model Armor filter matches.
        ScreeningUnavailableError: With `model_armor_unavailable` if a
            template is configured and Model Armor did not return a complete
            result, preserving `ModelArmorUnavailableError.is_retryable`.
    """
    try:
        model_armor_match = await screen_user_prompt(query)
    except ModelArmorUnavailableError as error:
        # `screen_user_prompt` has already logged the failure.
        raise ScreeningUnavailableError(
            ErrorType.MODEL_ARMOR_UNAVAILABLE,
            "Model Armor did not return a complete result",
            is_retryable=error.is_retryable,
        ) from error
    if model_armor_match is not None:
        logger.warning(
            "Model Armor matched %s; refusing turn", model_armor_match
        )
        raise TurnRefusedError(
            RefusedReason.SAFETY_BLOCKED, SAFETY_REFUSED_MESSAGE
        )


async def classify_query(
    transcript: Transcript, config: AgentConfig, telemetry: TurnTelemetry
) -> Clarification | Admitted:
    """Runs the classify phase for one turn.

    Args:
        transcript: Verified transcript holding the current query and prior
            conversation context.
        config: The agent configuration. `prompts.classify` is the configured
            prompt of the system instruction and `gemini.classify_model` is
            the model.
        telemetry: Turn telemetry accumulator receiving token counts.

    Returns:
        `Clarification` when the query requires disambiguation before discovery,
        or `Admitted` when the turn continues into the discovery phase.

    Raises:
        TurnRefusedError: If the pre-filter or Model Armor matches, or the
            classifier marks the query unserviceable.
        ScreeningUnavailableError: If Model Armor does not return a
            complete result (`model_armor_unavailable`) or the classifier
            does not return a valid verdict (`classifier_unavailable`).
        GeminiBlockedError: If Gemini blocks the classification call.
    """
    family = prefilter_match(transcript.current_query)
    if family is not None:
        logger.warning("Pre-filter matched %s; refusing turn", family)
        raise TurnRefusedError(
            RefusedReason.ADVERSARIAL, SAFETY_REFUSED_MESSAGE
        )
    await _screen_with_model_armor(transcript.current_query)
    classification = await _request_classification(
        transcript, config, telemetry
    )
    if not classification.serviceable:
        if classification.refusal_reason == "off_domain":
            raise TurnRefusedError(
                RefusedReason.OFF_DOMAIN,
                off_domain_message(classification.off_topic_premise),
            )
        raise TurnRefusedError(RefusedReason.ADVERSARIAL, REFUSED_MESSAGE)
    question = (classification.clarification or "").strip()
    if question:
        return Clarification(question, classification)
    return Admitted(classification)

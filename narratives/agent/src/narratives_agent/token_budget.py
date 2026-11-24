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
"""In-memory per-instance daily Gemini token budget.

Tracks cumulative Gemini tokens consumed by one agent process during the
current UTC calendar day and resets automatically when the UTC date advances.
Emits at most one `warning` and one `exhausted` structured telemetry event per
UTC day as thresholds are crossed.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from narratives_agent.settings import get_settings
from narratives_agent.telemetry import BudgetEventState, record_budget_event

# Percentage of the daily token budget at which the warning event fires.
WARNING_THRESHOLD_PERCENT = 80
_PERCENT_BASE = 100

type UtcDayClock = Callable[[], date]


def _current_utc_day() -> date:
    """Returns the current calendar date in UTC."""
    return datetime.now(UTC).date()


class DailyTokenBudget:
    """Enforces a single-process daily Gemini token cap with UTC rollover.

    Intended for single-process asyncio servers (one Uvicorn worker per pod).
    Counters live in process memory, so a pod restart starts fresh at zero for
    the current UTC day.
    """

    def __init__(
        self,
        limit_tokens: int,
        *,
        clock: UtcDayClock = _current_utc_day,
    ) -> None:
        """Initializes the budget for the current UTC day.

        Args:
            limit_tokens: Maximum total Gemini tokens allowed per UTC day.
            clock: Zero-argument callable returning the current UTC date.

        Raises:
            ValueError: `limit_tokens` is not positive.
        """
        if limit_tokens <= 0:
            raise ValueError("limit_tokens must be positive")
        self._limit_tokens = limit_tokens
        self._clock = clock
        self._utc_day = clock()
        self._used_tokens = 0
        self._has_emitted_warning = False
        self._has_emitted_exhausted = False

    @property
    def limit_tokens(self) -> int:
        """Returns the configured per-instance daily token cap."""
        return self._limit_tokens

    def _roll_over_if_needed(self) -> None:
        """Resets daily counters once the UTC calendar date advances."""
        today = self._clock()
        # Require strictly forward movement so minor backward clock skew across
        # midnight cannot double-reset a newly started UTC day.
        if today > self._utc_day:
            self._utc_day = today
            self._used_tokens = 0
            self._has_emitted_warning = False
            self._has_emitted_exhausted = False

    def is_exhausted(self) -> bool:
        """Returns whether today's token budget has reached its cap."""
        self._roll_over_if_needed()
        return self._used_tokens >= self._limit_tokens

    def record(self, tokens: int) -> None:
        """Adds `tokens` spent by one turn and emits threshold telemetry once.

        Non-positive values are ignored. Crossing the warning and exhausted
        thresholds emits one structured `daily_token_budget` telemetry record
        each per UTC day.

        Args:
            tokens: Total Gemini tokens consumed by the turn.
        """
        if tokens <= 0:
            return
        self._roll_over_if_needed()
        self._used_tokens += tokens
        utc_day = self._utc_day.isoformat()
        if (
            not self._has_emitted_warning
            and self._used_tokens * _PERCENT_BASE
            >= self._limit_tokens * WARNING_THRESHOLD_PERCENT
        ):
            self._has_emitted_warning = True
            record_budget_event(
                BudgetEventState.WARNING,
                used_tokens=self._used_tokens,
                limit_tokens=self._limit_tokens,
                utc_day=utc_day,
            )
        if (
            not self._has_emitted_exhausted
            and self._used_tokens >= self._limit_tokens
        ):
            self._has_emitted_exhausted = True
            record_budget_event(
                BudgetEventState.EXHAUSTED,
                used_tokens=self._used_tokens,
                limit_tokens=self._limit_tokens,
                utc_day=utc_day,
            )


@dataclass
class _BudgetState:
    """Holds the process-wide daily token budget instance."""

    budget: DailyTokenBudget | None = None


_STATE = _BudgetState()


def get_daily_token_budget() -> DailyTokenBudget | None:
    """Returns the configured per-instance daily token budget, or `None`.

    Reads `DAILY_TOKEN_BUDGET_PER_INSTANCE` via `get_settings()` and caches one
    `DailyTokenBudget` instance for the lifetime of the process (cleared by
    `reset_daily_token_budget()`).
    """
    limit = get_settings().daily_token_budget_per_instance
    if limit is None:
        return None
    if _STATE.budget is None:
        _STATE.budget = DailyTokenBudget(limit)
    return _STATE.budget


def reset_daily_token_budget() -> None:
    """Clears the cached daily token budget (for testing)."""
    _STATE.budget = None


__all__ = [
    "WARNING_THRESHOLD_PERCENT",
    "DailyTokenBudget",
    "UtcDayClock",
    "get_daily_token_budget",
    "reset_daily_token_budget",
]

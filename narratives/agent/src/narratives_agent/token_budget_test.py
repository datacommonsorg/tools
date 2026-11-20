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
"""Tests for the per-instance daily Gemini token budget.

Verifies that `DailyTokenBudget` and its process accessor:
1. Reject non-positive token limits.
2. Accumulate token counts across turns and exhaust at the exact limit.
3. Emit `warning` once at 80% and `exhausted` once at 100% per UTC day,
   including when a single turn crosses both thresholds.
4. Ignore zero and negative token counts.
5. Reset counters and re-arm telemetry when the UTC date advances, while
   ignoring backward clock skew.
6. Resolve from `DAILY_TOKEN_BUDGET_PER_INSTANCE` as a process singleton and
   reset cleanly via `reset_daily_token_budget`.
"""

import json
import logging
from collections.abc import Iterator
from datetime import date

import pytest

from narratives_agent import telemetry
from narratives_agent.settings import (
    DAILY_TOKEN_BUDGET_PER_INSTANCE_ENV,
    get_settings,
)
from narratives_agent.telemetry import BudgetEventState
from narratives_agent.token_budget import (
    DailyTokenBudget,
    get_daily_token_budget,
    reset_daily_token_budget,
)

_DAY_ONE = date(2026, 11, 20)
_DAY_TWO = date(2026, 11, 21)


class _RecordCollector(logging.Handler):
    """Collects JSON lines emitted on the telemetry logger."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, object]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(json.loads(record.getMessage()))


@pytest.fixture
def budget_records() -> Iterator[list[dict[str, object]]]:
    """Captures structured `daily_token_budget` events emitted to stdout."""
    collector = _RecordCollector()
    logger = telemetry._turn_logger
    previous_level = logger.level
    logger.addHandler(collector)
    logger.setLevel(logging.INFO)
    yield collector.records
    logger.removeHandler(collector)
    logger.setLevel(previous_level)


@pytest.mark.parametrize("limit", [0, -1, -100])
def test_non_positive_limit_is_rejected(limit: int) -> None:
    # Test: Limit validation on `DailyTokenBudget`.
    # Situation: A caller constructs `DailyTokenBudget` with zero or a negative
    #   token limit.
    # Expectation: Construction raises `ValueError`.
    with pytest.raises(ValueError, match="limit_tokens"):
        DailyTokenBudget(limit)


def test_budget_exhausts_at_exact_limit_and_emits_each_threshold_once(
    budget_records: list[dict[str, object]],
) -> None:
    # Test: Token accumulation, boundary exhaustion, and once-per-day events.
    # Situation: A 100-token budget records 79 tokens (below warning), 1 token
    #   (hits 80% warning), 19 tokens (99 total, still below cap), 1 token
    #   (hits exact 100-token cap), and another 50 tokens after exhaustion.
    # Expectation: `is_exhausted()` turns True at 100 tokens (not 99);
    #   `warning` is emitted once at 80 and `exhausted` is emitted once at 100.
    budget = DailyTokenBudget(100, clock=lambda: _DAY_ONE)

    budget.record(79)
    assert not budget.is_exhausted()
    assert budget_records == []

    budget.record(1)
    assert not budget.is_exhausted()
    assert budget_records == [
        {
            "severity": "WARNING",
            "message": "daily token budget warning",
            "event": "daily_token_budget",
            "state": BudgetEventState.WARNING,
            "used_tokens": 80,
            "limit_tokens": 100,
            "utc_day": "2026-11-20",
        }
    ]

    budget.record(19)
    assert not budget.is_exhausted()
    assert len(budget_records) == 1

    budget.record(1)
    assert budget.is_exhausted()
    assert budget_records == [
        budget_records[0],
        {
            "severity": "ERROR",
            "message": "daily token budget exhausted",
            "event": "daily_token_budget",
            "state": BudgetEventState.EXHAUSTED,
            "used_tokens": 100,
            "limit_tokens": 100,
            "utc_day": "2026-11-20",
        },
    ]

    budget.record(50)
    assert budget.is_exhausted()
    assert len(budget_records) == 2


def test_single_turn_crossing_both_thresholds_emits_warning_and_exhausted(
    budget_records: list[dict[str, object]],
) -> None:
    # Test: Single turn jumping from 0% past 100%.
    # Situation: A 1-token budget records a 250-token turn.
    # Expectation: Both `warning` and `exhausted` events are emitted once, and
    #   the budget is exhausted.
    budget = DailyTokenBudget(1, clock=lambda: _DAY_ONE)

    budget.record(250)

    assert budget.is_exhausted()
    assert [r["state"] for r in budget_records] == [
        BudgetEventState.WARNING,
        BudgetEventState.EXHAUSTED,
    ]
    assert all(r["used_tokens"] == 250 for r in budget_records)


@pytest.mark.parametrize("tokens", [0, -1, -500])
def test_non_positive_recorded_tokens_are_ignored(
    tokens: int,
    budget_records: list[dict[str, object]],
) -> None:
    # Test: Non-positive token counts passed to `record()`.
    # Situation: A budget with 10-token cap records 0 or a negative count.
    # Expectation: The budget stays unexhausted and emits no telemetry.
    budget = DailyTokenBudget(10, clock=lambda: _DAY_ONE)

    budget.record(tokens)

    assert not budget.is_exhausted()
    assert budget_records == []


def test_budget_resets_when_utc_day_advances_and_ignores_backward_skew(
    budget_records: list[dict[str, object]],
) -> None:
    # Test: UTC midnight rollover and monotonicity under clock skew.
    # Situation: A 100-token budget is exhausted on day 1, the clock advances
    #   to day 2, tokens are recorded on day 2, and the clock steps backward
    #   to day 1 before more tokens are recorded.
    # Expectation: Advancing to day 2 resets usage and re-arms both threshold
    #   events; stepping backward to day 1 does not reset day 2's usage.
    current_day = _DAY_ONE
    budget = DailyTokenBudget(100, clock=lambda: current_day)

    budget.record(100)
    assert budget.is_exhausted()
    assert len(budget_records) == 2

    current_day = _DAY_TWO
    assert not budget.is_exhausted()

    budget.record(60)
    assert not budget.is_exhausted()

    # Simulate minor backward clock skew across midnight.
    current_day = _DAY_ONE
    budget.record(40)
    assert budget.is_exhausted()
    assert [
        (r["state"], r["utc_day"], r["used_tokens"]) for r in budget_records
    ] == [
        (BudgetEventState.WARNING, "2026-11-20", 100),
        (BudgetEventState.EXHAUSTED, "2026-11-20", 100),
        (BudgetEventState.WARNING, "2026-11-21", 100),
        (BudgetEventState.EXHAUSTED, "2026-11-21", 100),
    ]


def test_get_daily_token_budget_returns_none_when_unset_and_caches_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Process singleton resolution and reset for `get_daily_token_budget`.
    # Situation: `DAILY_TOKEN_BUDGET_PER_INSTANCE` is unset, then set to a
    #   positive integer, queried twice, and reset with
    #   `reset_daily_token_budget()`.
    # Expectation: Returns `None` when unset, returns the same instance with
    #   preserved usage while set, and yields a fresh instance after reset.
    assert get_daily_token_budget() is None

    monkeypatch.setenv(DAILY_TOKEN_BUDGET_PER_INSTANCE_ENV, "500")
    get_settings.cache_clear()

    first = get_daily_token_budget()
    assert first is not None
    assert first.limit_tokens == 500
    first.record(500)
    assert first.is_exhausted()

    second = get_daily_token_budget()
    assert second is first
    assert second.is_exhausted()

    reset_daily_token_budget()
    third = get_daily_token_budget()
    assert third is not None
    assert third is not first
    assert not third.is_exhausted()

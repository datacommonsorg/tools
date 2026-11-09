#!/usr/bin/env python3
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
"""Compares saved evaluation runs side by side.

Reads `runs/<label>/runs.jsonl` for each label given and prints a markdown
summary: completion, speed and phase timings, tool calls, streamed thought
volume, the Data gaps label, voice slips, and each question's opening
sentence per run. Uses only the Python standard library.

Usage, from `narratives/`:

    python3 editorial/compare_runs.py after-fit low-thinking
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_VOICE = re.compile(r"\b(we|We|our|Our|I|sorry|the system|the model)\b")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LABEL = re.compile(r"^\*\*[^*]+:\*\*\s*")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORD = re.compile(r"[a-z']+")


def _load(label: str) -> list[dict[str, Any]]:
    """Returns the saved runs of a label."""
    path = _HERE / "runs" / label / "runs.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _median(values: list[float]) -> str:
    """Formats the median of the values, or a dash when there are none."""
    return f"{statistics.median(values):.1f}" if values else "–"


def _thought_chars(run: dict[str, Any]) -> int:
    """Counts streamed thought characters, from the frames when needed."""
    thoughts = run["summary"].get("thoughts")
    if thoughts is not None:
        return sum(thoughts.values())
    return sum(
        len(str(frame["data"].get("thought", "")))
        for frame in run.get("frames", [])
        if frame["event"] == "thought" and isinstance(frame["data"], dict)
    )


def _tool_calls(run: dict[str, Any]) -> int:
    """Counts tool calls, from the frames when the summary lacks them."""
    calls = run["summary"].get("tool_calls")
    if calls is not None:
        return int(calls)
    return sum(
        1
        for frame in run.get("frames", [])
        if isinstance(frame["data"], dict) and "tool_call" in frame["data"]
    )


def _opening(answer: str) -> str:
    """Returns the first line of the answer, shortened."""
    first = answer.strip().split("\n", 1)[0] if answer else ""
    return (first[:260] + "…") if len(first) > 260 else first


def _bullets(answer: str) -> list[str]:
    """Returns the answer's analysis bullets, label removed.

    Items listed under `**Data gaps:**` are not analysis bullets and are
    left out.
    """
    analysis = answer.split("**Data gaps:**", 1)[0]
    return [
        _LABEL.sub("", line[2:]).strip()
        for line in analysis.splitlines()
        if line.startswith("- ")
    ]


def _repeated_openings(answer: str) -> int:
    """Counts bullets whose first three words repeat an earlier bullet's."""
    seen: set[str] = set()
    repeated = 0
    for bullet in _bullets(answer):
        opening = " ".join(_WORD.findall(bullet.lower())[:3])
        if opening in seen:
            repeated += 1
        seen.add(opening)
    return repeated


def _numbers(answer: str) -> set[str]:
    """Returns every number in the answer's bold figures, commas removed."""
    return {
        number.replace(",", "")
        for bold in _BOLD.findall(answer)
        for number in _NUMBER.findall(bold)
    }


def _summary_row(label: str, runs: list[dict[str, Any]]) -> str:
    """Builds the overall summary row of one label."""
    complete = [r for r in runs if r["summary"]["terminal_state"] == "complete"]
    seconds = [r["seconds"] for r in complete]
    synthesis = [
        t["terminal_s"] - t["synthesis_start_s"]
        for r in complete
        if (t := r["summary"].get("timing"))
        and "terminal_s" in t
        and "synthesis_start_s" in t
    ]
    first_block = [
        t["first_block_s"]
        for r in complete
        if (t := r["summary"].get("timing")) and "first_block_s" in t
    ]
    with_gaps = [
        r for r in complete if (r["summary"]["finish"].get("missing") or [])
    ]
    gaps_labelled = sum(
        "**Data gaps:**" in r["summary"]["answer"] for r in with_gaps
    )
    voice = sum(bool(_VOICE.search(r["summary"]["answer"])) for r in complete)
    bullets = [len(_bullets(r["summary"]["answer"])) for r in complete]
    repeats = sum(_repeated_openings(r["summary"]["answer"]) for r in complete)
    return (
        f"| {label} | {len(complete)}/{len(runs)} | {_median(seconds)} | "
        f"{statistics.mean(seconds):.1f} | {_median(first_block)} | "
        f"{_median(synthesis)} | {_median([_tool_calls(r) for r in complete])} | "
        f"{_median([_thought_chars(r) for r in complete])} | "
        f"{gaps_labelled}/{len(with_gaps)} | {voice} | "
        f"{statistics.mean(bullets):.1f} | {repeats} |"
    )


def main() -> int:
    """Prints the comparison of the labels given on the command line."""
    labels = sys.argv[1:]
    if not labels:
        print(__doc__, file=sys.stderr)
        return 2
    loaded = {label: _load(label) for label in labels}

    print("## Overall\n")
    print(
        "| Run | Completed | Median s | Mean s | First block s (median) | "
        "Synthesis s (median) | Tool calls (median) | Thought chars "
        "(median) | Data gaps labelled | Voice slips | Bullets per answer "
        "(mean) | Bullets repeating an opening |"
    )
    print(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
        "| --- |"
    )
    for label, runs in loaded.items():
        print(_summary_row(label, runs))

    if len(labels) > 1:
        newest, earlier = labels[-1], labels[:-1]
        print(f"\n## Figures in `{newest}` not seen in earlier runs\n")
        print(
            "Numbers in bold figures of the newest run that no earlier run of "
            "the same question contained. Each must trace to the digest; a "
            "new selection of computed figures is expected, an invented one "
            "is not.\n"
        )
        for run in loaded[newest]:
            if run["summary"]["terminal_state"] != "complete":
                continue
            seen = set().union(
                *(
                    _numbers(r["summary"]["answer"])
                    for label in earlier
                    for r in loaded[label]
                    if r["id"] == run["id"]
                )
            )
            new = sorted(_numbers(run["summary"]["answer"]) - seen)
            if new:
                print(
                    f"- **{run['id']} run {run['repeat']}:** {', '.join(new)}"
                )

    print("\n## Per question: median seconds and tool calls\n")
    print("| Question | " + " | ".join(labels) + " |")
    print("| --- | " + " | ".join("---" for _ in labels) + " |")
    ids = list(dict.fromkeys(r["id"] for runs in loaded.values() for r in runs))
    for question_id in ids:
        cells = []
        for label in labels:
            done = [
                r
                for r in loaded[label]
                if r["id"] == question_id
                and r["summary"]["terminal_state"] == "complete"
            ]
            failed = sum(
                1
                for r in loaded[label]
                if r["id"] == question_id
                and r["summary"]["terminal_state"] != "complete"
            )
            cell = (
                f"{_median([r['seconds'] for r in done])}s, "
                f"{_median([_tool_calls(r) for r in done])} calls"
            )
            if failed:
                cell += f", {failed} not completed"
            cells.append(cell)
        print(f"| {question_id} | " + " | ".join(cells) + " |")

    print("\n## Openings\n")
    for question_id in ids:
        print(f"### {question_id}\n")
        for label in labels:
            by_run: dict[int, str] = defaultdict(str)
            for r in loaded[label]:
                if r["id"] != question_id:
                    continue
                state = r["summary"]["terminal_state"]
                by_run[r["repeat"]] = (
                    _opening(r["summary"]["answer"])
                    if state == "complete"
                    else f"({state}: {r['summary'].get('terminal_error') or ''})"
                )
            for repeat, text in sorted(by_run.items()):
                print(f"- **{label} {repeat}:** {text}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

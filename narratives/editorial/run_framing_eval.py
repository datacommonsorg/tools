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
"""Runs the answer framing evaluation against a running agent.

Sends each question in `framing_questions.json` to the agent's chat stream
a number of times, and writes the raw frames to `runs/<label>/runs.jsonl`
and a side-by-side report to `runs/<label>/report.md`. Uses only the Python
standard library, so it runs with any Python 3.9 or later.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_DEFAULT_URL = "http://localhost:5001/agent/chat/stream"
_TIMEOUT_SECONDS = 300
_FINISH_TOOLS = ("submit_specification", "report_unavailable")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_HAS_DIGIT = re.compile(r"\d")


def _read_frames(url: str, question: str) -> list[dict[str, Any]]:
    """Sends one question and returns the SSE frames of the turn.

    Args:
        url: The agent's chat stream endpoint.
        question: The question to send.

    Returns:
        Each frame as `{"event": ..., "data": ..., "t": ...}`, where `t` is
        the seconds since the request was sent; heartbeats left out.
    """
    started = time.monotonic()
    body = json.dumps({"message": question}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    frames: list[dict[str, Any]] = []
    event = "message"
    data_lines: list[str] = []
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        for raw in response:
            line = raw.decode("utf-8").rstrip("\r\n")
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())
            elif not line:
                if data_lines and event != "heartbeat":
                    text = "\n".join(data_lines)
                    try:
                        data: Any = json.loads(text)
                    except json.JSONDecodeError:
                        data = text
                    frames.append(
                        {
                            "event": event,
                            "data": data,
                            "t": round(time.monotonic() - started, 1),
                        }
                    )
                event = "message"
                data_lines = []
    return frames


def _summarize(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Pulls the answer, the missing data, and the figures from the frames.

    Args:
        frames: The frames of one turn.

    Returns:
        The answer markdown, the chart count, the data status, the finishing
        tool's name and its missing-data fields, the bold figures, the
        follow-up questions, and the terminal state.
    """
    texts: list[tuple[int, str]] = []
    charts = 0
    data_status: Any = None
    finish: dict[str, Any] = {}
    follow_ups: list[str] = []
    terminal: Any = None
    tool_calls = 0
    thoughts: dict[str, int] = {}
    timing: dict[str, Any] = {}
    for frame in frames:
        data = frame["data"]
        if not isinstance(data, dict):
            continue
        elapsed = frame.get("t")
        if frame["event"] == "terminal":
            terminal = data
            timing["terminal_s"] = elapsed
        elif frame["event"] == "follow_ups":
            follow_ups = list(data.get("follow_up_questions", []))
        elif frame["event"] == "thought":
            phase = str(data.get("phase", "unknown"))
            thoughts[phase] = thoughts.get(phase, 0) + len(
                str(data.get("thought", ""))
            )
        elif frame["event"] == "status":
            phase = data.get("phase")
            if phase in ("discovery", "synthesis"):
                timing.setdefault(f"{phase}_start_s", elapsed)
        elif "block" in data:
            timing.setdefault("first_block_s", elapsed)
            block = data["block"]
            if block.get("type") == "text":
                texts.append((block.get("index", 0), block.get("markdown", "")))
            else:
                charts += 1
        elif "data_status" in data:
            data_status = data["data_status"]
        elif "tool_call" in data:
            tool_calls += 1
            call = data["tool_call"]
            if any(name in str(call.get("name", "")) for name in _FINISH_TOOLS):
                arguments = call.get("arguments") or {}
                finish = {
                    "tool": call.get("name"),
                    "missing": arguments.get("missing"),
                    "reason": arguments.get("reason"),
                    "searched_indicators": arguments.get("searched_indicators"),
                    "related_available": arguments.get("related_available"),
                }
    answer = "\n\n".join(text for _, text in sorted(texts))
    figures = [
        match for match in _BOLD.findall(answer) if _HAS_DIGIT.search(match)
    ]
    return {
        "answer": answer,
        "charts": charts,
        "data_status": data_status,
        "finish": finish,
        "figures": figures,
        "follow_ups": follow_ups,
        "terminal_state": (terminal or {}).get("state"),
        "terminal_error": (terminal or {}).get("error"),
        "tool_calls": tool_calls,
        "thoughts": thoughts,
        "timing": timing,
    }


def _write_report(
    path: Path, label: str, results: list[dict[str, Any]]
) -> None:
    """Writes the side-by-side markdown report.

    Args:
        path: The report file to write.
        label: The run label, shown in the title.
        results: One entry per run, in question order.
    """
    lines = [f"# Answer framing evaluation: {label}", ""]
    by_question: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_question.setdefault(result["id"], []).append(result)
    for question_id, runs in by_question.items():
        first = runs[0]
        lines += [
            f"## {question_id} ({first['case']}): {first['question']}",
            "",
        ]
        figure_sets = [
            set(run["summary"]["figures"])
            for run in runs
            if run["summary"]["terminal_state"] == "complete"
        ]
        shared = set.intersection(*figure_sets) if figure_sets else set()
        if any(figures != shared for figures in figure_sets):
            lines += [
                "> [!NOTE]",
                "> Runs report different figures; each run lists the ones the "
                "others do not all share. A different subset is expected; a "
                "different value for the same measure is not.",
                "",
            ]
        for run in runs:
            summary = run["summary"]
            lines += [f"### Run {run['repeat']}", ""]
            if run.get("error"):
                lines += [f"Request failed: {run['error']}", ""]
                continue
            lines += [
                f"- Terminal: {summary['terminal_state']}"
                + (
                    f" ({summary['terminal_error']})"
                    if summary["terminal_error"]
                    else ""
                ),
                f"- Data status: {json.dumps(summary['data_status'])}",
                f"- Finished with: {summary['finish'].get('tool')}",
                "- MISSING DATA: "
                + json.dumps(
                    {
                        key: value
                        for key, value in summary["finish"].items()
                        if key != "tool" and value
                    }
                ),
                f"- Figures: {', '.join(summary['figures']) or '(none)'}",
                "- Not in every run: "
                + (
                    ", ".join(
                        figure
                        for figure in summary["figures"]
                        if figure not in shared
                    )
                    or "(none)"
                ),
                f"- Charts: {summary['charts']}",
                f"- Seconds: {run.get('seconds')}; phases: "
                f"{json.dumps(summary.get('timing', {}))}",
                f"- Tool calls: {summary.get('tool_calls')}; thought "
                f"characters: {json.dumps(summary.get('thoughts', {}))}",
                f"- Follow-ups: {json.dumps(summary['follow_ups'])}",
                "",
                "Answer:",
                "",
            ]
            lines += [f"> {line}" for line in summary["answer"].splitlines()]
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """Runs the evaluation and writes its outputs.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="Run folder name.")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--url", default=_DEFAULT_URL)
    parser.add_argument(
        "--only", default="", help="Comma-separated question ids to run."
    )
    parser.add_argument(
        "--questions",
        default="framing_questions.json",
        help="Question set file in editorial/ (default: %(default)s).",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Rebuild report.md from the label's saved runs.jsonl.",
    )
    args = parser.parse_args()

    out_dir = _HERE / "runs" / args.label
    if args.report_only:
        saved = [
            json.loads(line)
            for line in (out_dir / "runs.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        _write_report(out_dir / "report.md", args.label, saved)
        print(f"Wrote {out_dir / 'report.md'}", file=sys.stderr)
        return 0

    questions = json.loads(
        (_HERE / args.questions).read_text(encoding="utf-8")
    )
    if args.only:
        wanted = {item.strip() for item in args.only.split(",")}
        questions = [item for item in questions if item["id"] in wanted]

    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    with (out_dir / "runs.jsonl").open("w", encoding="utf-8") as raw_file:
        for item in questions:
            for repeat in range(1, args.repeats + 1):
                print(f"{item['id']} run {repeat}...", file=sys.stderr)
                started = time.monotonic()
                result: dict[str, Any] = {**item, "repeat": repeat}
                try:
                    frames = _read_frames(args.url, item["question"])
                    result["summary"] = _summarize(frames)
                except (urllib.error.URLError, TimeoutError, OSError) as error:
                    frames = []
                    result["error"] = str(error)
                    result["summary"] = _summarize([])
                result["seconds"] = round(time.monotonic() - started, 1)
                raw_file.write(json.dumps({**result, "frames": frames}) + "\n")
                results.append(result)
    _write_report(out_dir / "report.md", args.label, results)
    print(f"Wrote {out_dir / 'report.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

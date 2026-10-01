"""The thread protocol: plain text that people read and code parses.

Every runner message starts with one header line:

    ▶ train · run 3 started
    ▹ train · run 3 output
    ✓ train · run 3 passed · exit 0 · 4.2s
    ✗ train · run 3 failed · exit 1 · 4.2s

The rest of the message is detail for people and agents.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

GLYPHS = {
    "started": "▶",
    "output": "▹",
    "passed": "✓",
    "failed": "✗",
}
HEADER = re.compile(r"(?P<glyph>\S) (?P<name>.+?) · run (?P<run>\d+) (?P<event>[a-z]+)(?: · (?P<detail>.*))?")
RESULT_PREFIX = "::result "
MAX_TEXT = 3500  # below Zulip's 10 000 and Buzz's 64 KiB limits, with room for headers


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    run: int
    event: str  # a key of GLYPHS
    detail: str


def title(name: str, run: int) -> str:
    return f"{name} · run {run}"


def run_number(thread_title: str, name: str) -> int | None:
    """The run number of a thread opened by runner `name`, if it is one."""
    match = re.search(rf"(?:^|\s){re.escape(name)} · run (\d+)\b", thread_title)
    return int(match[1]) if match else None


def header(name: str, run: int, event: str, detail: str = "") -> str:
    line = f"{GLYPHS[event]} {title(name, run)} {event}"
    return f"{line} · {detail}" if detail else line


def parse(text: str) -> Event | None:
    """The runner event a message carries, or None for chat."""
    match = HEADER.fullmatch(text.split("\n", 1)[0])
    if not match or GLYPHS.get(match["event"]) != match["glyph"]:
        return None
    return Event(match["name"], int(match["run"]), match["event"], match["detail"] or "")


def started(name: str, run: int, params: Mapping[str, Any], argv: list[str]) -> str:
    body = "\n".join(f"{key} = {toml_value(value)}" for key, value in params.items())
    parts = [header(name, run, "started")]
    if body:
        parts.append(f"```toml\n{body}\n```")
    parts.append(f"`{shlex.join(argv)}`")
    return "\n\n".join(parts)


def output(name: str, run: int, lines: list[str]) -> str:
    head = header(name, run, "output")
    room = MAX_TEXT - len(head) - len("\n```\n\n```") - len(f"… {len(lines)} lines skipped\n")
    kept: list[str] = []
    for line in reversed(lines):
        room -= len(line) + 1
        if room < 0:
            break
        kept.append(line)
    kept.reverse()
    skipped = len(lines) - len(kept)
    if skipped:
        kept.insert(0, f"… {skipped} lines skipped")
    return head + "\n```\n" + "\n".join(kept) + "\n```"


def finished(name: str, run: int, event: str, detail: str, results: Iterable[str] = ()) -> str:
    text = header(name, run, event, detail)
    lines = list(results)
    return text + "\n\n" + "\n".join(lines) if lines else text


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)

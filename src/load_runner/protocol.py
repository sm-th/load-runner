"""The thread protocol: plain text that people read and code parses.

Every runner message starts with one header line:

    ▶ train · run 3 started
    ▹ train · run 3 output
    ✓ train · run 3 passed · exit 0 · 4.2s
    ✗ train · run 3 failed · exit 1 · 4.2s
    ■ train · run 3 stopped · by andy · 2.0s
    ↻ train · run 3 restarting · by agent
    ⚙ train · run 3 set · lr = 0.03 for the next run · by agent
    ⊘ train · run 3 refused · /stop from mallory

The rest of the message is detail for people and agents. Anyone else in the
thread commands the runner with lines such as `/stop`, `/restart`,
`/set lr=0.03`, and `/unset lr`.
"""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

GLYPHS = {
    "started": "▶",
    "output": "▹",
    "passed": "✓",
    "failed": "✗",
    "stopped": "■",
    "restarting": "↻",
    "set": "⚙",
    "refused": "⊘",
}
HEADER = re.compile(r"(?P<glyph>\S) (?P<name>.+?) · run (?P<run>\d+) (?P<event>[a-z]+)(?: · (?P<detail>.*))?")
COMMAND = re.compile(r"\s*/(?P<verb>stop|restart|set|unset)(?:\s+(?P<args>.*))?")
KEY = re.compile(r"[A-Za-z_]\w*")
RESULT_PREFIX = "::result "
MAX_TEXT = 3500  # below Zulip's 10 000 and Buzz's 64 KiB limits, with room for headers


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    run: int
    event: str  # a key of GLYPHS
    detail: str


@dataclass(frozen=True, slots=True)
class Command:
    verb: str  # stop | restart | set | unset
    values: dict[str, Any] = field(default_factory=dict)  # set
    keys: tuple[str, ...] = ()  # unset
    error: str = ""  # why the line could not be understood


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


def commands(text: str) -> list[Command]:
    """Commands on their own lines of a chat message, in order."""
    found = []
    for line in text.splitlines():
        match = COMMAND.fullmatch(line.rstrip())
        if match:
            found.append(_command(match["verb"], match["args"] or ""))
    return found


def _command(verb: str, args: str) -> Command:
    if verb in ("stop", "restart"):
        return Command(verb)
    try:
        tokens = shlex.split(args)
    except ValueError as error:
        return Command(verb, error=str(error))
    if not tokens:
        return Command(verb, error=f"/{verb} needs at least one key")
    if verb == "unset":
        bad = [t for t in tokens if not KEY.fullmatch(t)]
        return Command(verb, keys=tuple(tokens), error=f"bad keys {bad}" if bad else "")
    values = {}
    for token in tokens:
        key, eq, raw = token.partition("=")
        if not eq or not KEY.fullmatch(key):
            return Command(verb, error=f"expected key=value, got {token!r}")
        values[key] = _value(raw)
    return Command(verb, values=values)


def _value(raw: str) -> Any:
    """A TOML value (`0.03`, `true`, `"text"`), or the raw text."""
    try:
        return tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        return raw


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

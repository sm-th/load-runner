"""Following the bus in a terminal: every thread, in arrival order."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import TextIO

from . import protocol
from .bus import Bus, Message

# Andy Smith design system, dark terminal: one blue, muted success and failure.
BLUE = "\x1b[38;2;89;141;249m"
GREEN = "\x1b[38;2;118;190;134m"
RED = "\x1b[38;2;235;131;115m"
GREY = "\x1b[38;2;134;134;134m"
RESET = "\x1b[0m"
EVENT_COLORS = {"passed": GREEN, "failed": RED, "refused": RED}


class Watcher:
    def __init__(self, bus: Bus, out: TextIO = sys.stdout, color: bool | None = None):
        self.bus = bus
        self.out = out
        self.color = out.isatty() and "NO_COLOR" not in os.environ if color is None else color
        self._titles: dict[str, str] = {}

    def follow(self, poll: float = 1.0) -> None:
        _, cursor = self.bus.feed(None)
        while True:
            cursor = self.step(cursor)
            time.sleep(poll)

    def step(self, cursor: str) -> str:
        messages, cursor = self.bus.feed(cursor)
        for message in messages:
            self.out.write(self.render(message))
        self.out.flush()
        return cursor

    def render(self, message: Message) -> str:
        at = datetime.fromtimestamp(message.at).strftime("%H:%M:%S")
        first, _, rest = message.text.partition("\n")
        event = protocol.parse(message.text)
        if event:
            first = self._paint(EVENT_COLORS.get(event.event, BLUE), first)
        head = f"{self._paint(GREY, at)}  {self._paint(GREY, self._title(message.thread))}  {message.author}"
        body = "".join(f"\n    {line}" if line else "\n" for line in rest.strip("\n").splitlines())
        return f"{head}\n    {first}{body}\n"

    def _title(self, thread: str) -> str:
        if thread not in self._titles:
            self._titles.update((t.id, t.title) for t in self.bus.threads(limit=50))
        return self._titles.get(thread, thread)

    def _paint(self, color: str, text: str) -> str:
        return f"{color}{text}{RESET}" if self.color else text

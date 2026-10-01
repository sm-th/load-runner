"""The message bus: the one place where runners, agents, and people talk.

A bus is a channel of threads. A runner opens one thread per run; everyone else
reads the channel feed and replies in threads. Adapters map this onto a real
platform (a SQLite file, Buzz, Zulip) and hide its API from the rest of the code.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    thread: str
    author: str
    text: str
    at: float  # unix seconds


@dataclass(frozen=True, slots=True)
class Thread:
    id: str
    title: str


class BusError(RuntimeError):
    """The platform refused or failed an operation."""


class Bus(Protocol):
    def start_thread(self, title: str, text: str) -> Message:
        """Open a thread; `text` is its root message.

        Buses without thread titles (Buzz) show the first line of the root message
        as the title instead, so put what identifies the thread there too.
        """
        ...

    def post(self, thread: str, text: str) -> Message:
        """Reply in a thread."""
        ...

    def thread(self, thread: str) -> list[Message]:
        """Every message of a thread, oldest first, root included."""
        ...

    def feed(self, cursor: str | None) -> tuple[list[Message], str]:
        """Messages of every thread posted after `cursor`, oldest first, and the next cursor.

        `None` subscribes from now: no history, just a cursor.
        """
        ...

    def threads(self, limit: int = 20) -> list[Thread]:
        """The `limit` most recent threads, oldest first."""
        ...


def open_bus(config: Mapping[str, Any], identity: str) -> Bus:
    """Open the bus described by a `[bus]` config table, speaking as `identity`.

    `identity` names the author on buses without accounts (SQLite); platforms with
    accounts take the author from their credentials.
    """
    kind = config.get("kind", "sqlite")
    match kind:
        case "sqlite":
            from .sqlite import SqliteBus

            return SqliteBus(Path(config.get("path", ".load-runner/bus.db")), identity)
        case "buzz":
            from .buzz import BuzzBus

            if "channel" not in config:
                raise BusError("[bus] kind = 'buzz' needs channel = '<channel uuid>'")
            return BuzzBus(config["channel"], [config.get("bin", "buzz")])
        case "zulip":
            from .zulip import ZulipBus

            missing = [key for key in ("site", "stream") if key not in config]
            missing += [var for var in ("ZULIP_EMAIL", "ZULIP_API_KEY") if not os.environ.get(var)]
            if missing:
                raise BusError(f"[bus] kind = 'zulip' needs {', '.join(missing)}")
            return ZulipBus(
                config["site"], config["stream"], os.environ["ZULIP_EMAIL"], os.environ["ZULIP_API_KEY"]
            )
        case _:
            raise BusError(f"unknown bus kind {kind!r}; expected sqlite, buzz, or zulip")

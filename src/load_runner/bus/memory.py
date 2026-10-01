"""In-process bus for tests and for embedding runners and agents in one program."""

from __future__ import annotations

import threading
import time

from . import BusError, Message, Thread


class MemoryHub:
    """Shared state; every `connect` is one participant."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._messages: list[Message] = []
        self._titles: dict[str, str] = {}

    def connect(self, identity: str) -> MemoryBus:
        return MemoryBus(self, identity)


class MemoryBus:
    def __init__(self, hub: MemoryHub, identity: str) -> None:
        self._hub = hub
        self.identity = identity

    def start_thread(self, title: str, text: str) -> Message:
        hub = self._hub
        with hub._lock:
            thread = str(len(hub._titles) + 1)
            hub._titles[thread] = title
            return self._append(thread, text)

    def post(self, thread: str, text: str) -> Message:
        with self._hub._lock:
            if thread not in self._hub._titles:
                raise BusError(f"no thread {thread!r}")
            return self._append(thread, text)

    def thread(self, thread: str) -> list[Message]:
        with self._hub._lock:
            return [m for m in self._hub._messages if m.thread == thread]

    def feed(self, cursor: str | None) -> tuple[list[Message], str]:
        with self._hub._lock:
            end = len(self._hub._messages)
            start = end if cursor is None else int(cursor)
            return self._hub._messages[start:end], str(end)

    def threads(self, limit: int = 20) -> list[Thread]:
        with self._hub._lock:
            return [Thread(id, title) for id, title in list(self._hub._titles.items())[-limit:]]

    def _append(self, thread: str, text: str) -> Message:
        messages = self._hub._messages
        message = Message(str(len(messages) + 1), thread, self.identity, text, time.time())
        messages.append(message)
        return message

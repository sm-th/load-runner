"""A bus in one SQLite file: several processes on one machine, no server.

WAL mode lets a runner, an agent, and `load-runner say` write while others read.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from . import BusError, Message, Thread

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread INTEGER NOT NULL REFERENCES threads(id),
    author TEXT NOT NULL,
    text TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_thread ON messages(thread, id);
"""

FEED_PAGE = 500


class SqliteBus:
    def __init__(self, path: Path, identity: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.identity = identity
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)

    def start_thread(self, title: str, text: str) -> Message:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                thread = self._db.execute("INSERT INTO threads(title) VALUES (?)", (title,)).lastrowid
                message = self._insert(str(thread), text)
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
            return message

    def post(self, thread: str, text: str) -> Message:
        with self._lock:
            try:
                return self._insert(thread, text)
            except sqlite3.IntegrityError as error:
                raise BusError(f"no thread {thread!r}") from error

    def thread(self, thread: str) -> list[Message]:
        return self._select("WHERE thread = ? ORDER BY id", (int(thread),))

    def feed(self, cursor: str | None) -> tuple[list[Message], str]:
        if cursor is None:
            with self._lock:
                (last,) = self._db.execute("SELECT coalesce(max(id), 0) FROM messages").fetchone()
            return [], str(last)
        messages = self._select("WHERE id > ? ORDER BY id LIMIT ?", (int(cursor), FEED_PAGE))
        return messages, messages[-1].id if messages else cursor

    def threads(self, limit: int = 20) -> list[Thread]:
        with self._lock:
            rows = self._db.execute("SELECT id, title FROM threads ORDER BY id DESC LIMIT ?", (limit,))
            return [Thread(str(id), title) for id, title in reversed(rows.fetchall())]

    def _insert(self, thread: str, text: str) -> Message:
        at = time.time()
        sql = "INSERT INTO messages(thread, author, text, at) VALUES (?, ?, ?, ?)"
        id = self._db.execute(sql, (int(thread), self.identity, text, at)).lastrowid
        return Message(str(id), thread, self.identity, text, at)

    def _select(self, where: str, args: tuple) -> list[Message]:
        with self._lock:
            rows = self._db.execute(f"SELECT id, thread, author, text, at FROM messages {where}", args)
            return [Message(str(id), str(thread), author, text, at) for id, thread, author, text, at in rows]

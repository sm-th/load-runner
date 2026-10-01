"""Zulip over its REST API: a stream is the bus, a topic is a thread.

Standard library HTTP only. Credentials come from ZULIP_EMAIL and ZULIP_API_KEY.
Zulip creates a topic on first post, so `post` checks that a topic exists before
it writes into it the first time; a typo must not open a new thread silently.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import BusError, Message, Thread

TOPIC_LIMIT = 60
PAGE = 1000


class ZulipBus:
    def __init__(self, site: str, stream: str, email: str, api_key: str):
        self.site = site.rstrip("/")
        self.stream = stream
        token = base64.b64encode(f"{email}:{api_key}".encode()).decode()
        self._headers = {"Authorization": f"Basic {token}", "User-Agent": "load-runner"}
        self._topics: set[str] = set()
        self._me: str | None = None
        self._stream_id: int | None = None

    def start_thread(self, title: str, text: str) -> Message:
        return self._send(title[:TOPIC_LIMIT], text)

    def post(self, thread: str, text: str) -> Message:
        if thread not in self._topics and not self._messages([("topic", thread)], anchor="oldest", after=1):
            raise BusError(f"no topic {thread!r} in #{self.stream}")
        return self._send(thread, text)

    def thread(self, thread: str) -> list[Message]:
        return self._messages([("topic", thread)], anchor="oldest", after=PAGE)

    def feed(self, cursor: str | None) -> tuple[list[Message], str]:
        if cursor is None:
            latest = self._messages([], anchor="newest", before=1)
            return [], latest[-1].id if latest else "0"
        messages = [m for m in self._messages([], anchor=cursor, after=PAGE) if int(m.id) > int(cursor)]
        return messages, messages[-1].id if messages else cursor

    def threads(self, limit: int = 20) -> list[Thread]:
        if self._stream_id is None:
            self._stream_id = self._api("GET", "get_stream_id", {"stream": self.stream})["stream_id"]
        topics = self._api("GET", f"users/me/{self._stream_id}/topics", {})["topics"][:limit]
        self._topics.update(t["name"] for t in topics)
        return [Thread(t["name"], t["name"]) for t in reversed(topics)]

    def _send(self, topic: str, text: str) -> Message:
        params = {"type": "stream", "to": self.stream, "topic": topic, "content": text}
        sent = self._api("POST", "messages", params)
        self._topics.add(topic)
        return Message(str(sent["id"]), topic, self._identity(), text, time.time())

    def _identity(self) -> str:
        if self._me is None:
            self._me = self._api("GET", "users/me", {})["full_name"]
        return self._me

    def _messages(
        self, narrow: list[tuple[str, str]], anchor: str, before: int = 0, after: int = 0
    ) -> list[Message]:
        filters = [{"operator": "stream", "operand": self.stream}]
        filters += [{"operator": op, "operand": value} for op, value in narrow]
        params = {
            "anchor": anchor,
            "num_before": before,
            "num_after": after,
            "narrow": json.dumps(filters),
            "apply_markdown": "false",
        }
        found = self._api("GET", "messages", params)["messages"]
        self._topics.update(m["subject"] for m in found)
        return [
            Message(str(m["id"]), m["subject"], m["sender_full_name"], m["content"], float(m["timestamp"]))
            for m in found
        ]

    def _api(self, method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        data = urllib.parse.urlencode(params)
        url = f"{self.site}/api/v1/{path}"
        if method == "GET" and data:
            url += f"?{data}"
        body = data.encode() if method != "GET" else None
        request = urllib.request.Request(url, data=body, method=method, headers=self._headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            try:
                payload = json.load(error)
            except ValueError:
                raise BusError(f"zulip {path}: HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise BusError(f"zulip unreachable at {self.site}: {error.reason}") from error
        if payload.get("result") != "success":
            raise BusError(f"zulip {path}: {payload.get('msg', payload)}")
        return payload

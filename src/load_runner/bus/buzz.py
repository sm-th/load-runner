"""Buzz (github.com/block/buzz) through its agent-first `buzz` CLI: JSON in, JSON out.

Buzz is a Nostr relay; every message is a signed event and every participant has its
own keypair. Driving the CLI keeps key handling inside Buzz: `BUZZ_PRIVATE_KEY` and
`BUZZ_RELAY_URL` come from the environment and never pass through this code.

Threads are NIP-10: a reply carries an `e` tag marked `root`. Buzz has no thread
titles, so a thread's title is the first line of its root message.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Mapping, Sequence
from typing import Any

from . import BusError, Message, Thread

STREAM_MESSAGE = "9"
PAGE = 500


class BuzzBus:
    def __init__(
        self, channel: str, command: Sequence[str] = ("buzz",), env: Mapping[str, str] | None = None
    ):
        self.channel = channel
        self._command = list(command)
        self._env = dict(env) if env is not None else None
        self._names: dict[str, str] = {}
        self._me: str | None = None

    def start_thread(self, title: str, text: str) -> Message:
        return self._send(text)

    def post(self, thread: str, text: str) -> Message:
        return self._send(text, "--reply-to", thread)

    def thread(self, thread: str) -> list[Message]:
        events = self._cli(
            "messages", "thread", "--channel", self.channel, "--event", thread, "--limit", str(PAGE)
        )
        return self._messages(events)

    def feed(self, cursor: str | None) -> tuple[list[Message], str]:
        if cursor is None:
            latest = self._get("--limit", "1")
            return [], _cursor(latest) if latest else f"{int(time.time())}|"
        since, _, seen = cursor.partition("|")
        events = [
            e for e in self._get("--since", since, "--limit", str(PAGE)) if e["id"] not in seen.split(",")
        ]
        if not events:
            return [], cursor
        return self._messages(events), _cursor(events, since, seen)

    def threads(self, limit: int = 20) -> list[Thread]:
        roots = [e for e in self._get("--limit", str(PAGE)) if _root(e) is None][-limit:]
        return [Thread(e["id"], e["content"].split("\n", 1)[0]) for e in roots]

    def _send(self, text: str, *reply: str) -> Message:
        sent = self._cli("messages", "send", "--channel", self.channel, "--content", "-", *reply, input=text)
        if not sent.get("accepted"):
            raise BusError(f"buzz refused the message: {sent.get('message', sent)}")
        thread = reply[1] if reply else sent["event_id"]
        return Message(sent["event_id"], thread, self._identity(), text, time.time())

    def _get(self, *args: str) -> list[dict[str, Any]]:
        return self._cli("messages", "get", "--channel", self.channel, "--kinds", STREAM_MESSAGE, *args)

    def _messages(self, events: list[dict[str, Any]]) -> list[Message]:
        self._learn_names({e["pubkey"] for e in events})
        return [
            Message(
                e["id"], _root(e) or e["id"], self._names[e["pubkey"]], e["content"], float(e["created_at"])
            )
            for e in events
        ]

    def _identity(self) -> str:
        if self._me is None:
            [profile] = self._cli("users", "get")
            self._me = _display_name(profile)
            self._names[profile["pubkey"]] = self._me
        return self._me

    def _learn_names(self, pubkeys: set[str]) -> None:
        unknown = sorted(pubkeys - self._names.keys())
        if not unknown:
            return
        args = [arg for pubkey in unknown for arg in ("--pubkey", pubkey)]
        for profile in self._cli("users", "get", *args):
            self._names[profile["pubkey"]] = _display_name(profile)
        for pubkey in unknown:
            self._names.setdefault(pubkey, pubkey[:8])

    def _cli(self, *args: str, input: str | None = None) -> Any:
        try:
            done = subprocess.run(
                [*self._command, *args],
                input=input,
                capture_output=True,
                text=True,
                timeout=60,
                env=self._env,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BusError(f"cannot run {self._command[0]}: {error}") from error
        if done.returncode != 0:
            try:
                detail = json.loads(done.stderr)["message"]
            except (ValueError, KeyError, TypeError):
                detail = done.stderr.strip() or f"exit {done.returncode}"
            raise BusError(f"buzz {' '.join(args[:2])}: {detail}")
        return json.loads(done.stdout) if done.stdout.strip() else None


def _root(event: Mapping[str, Any]) -> str | None:
    """The NIP-10 thread root of a reply; None for a top-level message."""
    marked = {tag[3]: tag[1] for tag in event.get("tags", []) if len(tag) >= 4 and tag[0] == "e"}
    return marked.get("root") or marked.get("reply")


def _cursor(events: list[dict[str, Any]], since: str = "", seen: str = "") -> str:
    """Nostr `since` is inclusive and in whole seconds: remember the ids already read in the last second."""
    last = max(int(e["created_at"]) for e in events)
    ids = [e["id"] for e in events if int(e["created_at"]) == last]
    if str(last) == since:
        ids = [*seen.split(","), *ids]
    return f"{last}|{','.join(filter(None, ids))}"


def _display_name(profile: Mapping[str, Any]) -> str:
    return profile.get("display_name") or profile.get("name") or profile["pubkey"][:8]

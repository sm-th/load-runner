"""The agent bridge: intelligence that sleeps until a result or a person needs it.

It follows the bus feed. A run result, or a message from someone else, wakes it;
intermediate output does not, unless it matches `wake_output`. Awake, it hands the
whole thread to a brain command (`claude -p`, `codex exec`, a script) and posts
what the brain says. Commands in that reply steer the runner through the thread.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime

from . import protocol
from .bus import Bus, Message
from .config import AgentConfig

log = logging.getLogger(__name__)

PROMPT = """\
You watch a mechanical runner through a shared thread. People read and write in the same thread.

The runner posts one header line per message:
  ▶ started (parameters and command)   ▹ output   ✓ passed   ✗ failed
  ■ stopped   ↻ restarting   ⚙ parameter changed   ⊘ command refused

Reply briefly, for people. To steer the runner, put commands on their own lines:
  /set key=value   change a parameter for the next run (TOML value)
  /unset key       go back to the config value
  /restart         kill the current run and start the next one now
  /stop            stop the loop
If a person asked for something, do it. If the result is fine, say so in one line.
If nothing needs saying, reply with nothing.
"""

Think = Callable[[str, str], str]  # (prompt, thread id) -> reply


class Agent:
    def __init__(self, bus: Bus, config: AgentConfig, think: Think | None = None):
        self.bus = bus
        self.config = config
        self.think = think or self._run_brain
        self._pattern = re.compile(config.wake_output) if config.wake_output else None
        self._mine: set[str] = set()
        self._replies: Counter[str] = Counter()

    def loop(self) -> None:
        _, cursor = self.bus.feed(None)
        log.info("agent %s listening", self.config.identity)
        while True:
            cursor = self.step(cursor)
            time.sleep(self.config.poll)

    def step(self, cursor: str) -> str:
        """Read what is new; answer every thread that woke the agent. Returns the next cursor."""
        messages, cursor = self.bus.feed(cursor)
        woken = dict.fromkeys(m.thread for m in messages if self._wakes(m))
        for thread in woken:
            self._answer(thread)
        return cursor

    def _wakes(self, message: Message) -> bool:
        if message.id in self._mine:
            return False
        event = protocol.parse(message.text)
        if event is None:
            return "chat" in self.config.wake
        if event.event in self.config.wake:
            return True
        matches = self._pattern is not None and self._pattern.search(message.text) is not None
        return event.event == "output" and matches

    def _answer(self, thread: str) -> None:
        if self._replies[thread] >= self.config.max_replies:
            log.warning("thread %s: reached max_replies=%d, staying quiet", thread, self.config.max_replies)
            return
        history = transcript(self.bus.thread(thread))
        prompt = "\n".join(filter(None, [PROMPT, self.config.instructions, history]))
        reply = self.think(prompt, thread).strip()
        if not reply:
            return
        posted = self.bus.post(thread, reply)
        self._mine.add(posted.id)
        self._replies[thread] += 1
        log.info("thread %s: replied", thread)

    def _run_brain(self, prompt: str, thread: str) -> str:
        try:
            done = subprocess.run(
                self.config.command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env=os.environ | {"LOAD_RUNNER_THREAD": thread},
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            log.error("brain %s: %s", self.config.command[0], error)
            return ""
        if done.returncode != 0:
            log.error("brain %s exited %d: %s", self.config.command[0], done.returncode, done.stderr.strip())
            return ""
        return done.stdout


def transcript(messages: list[Message]) -> str:
    """The thread as the brain reads it: time, author, text."""
    lines = ["Thread:"]
    for message in messages:
        at = datetime.fromtimestamp(message.at).strftime("%H:%M:%S")
        lines.append(f"[{at}] {message.author}: {message.text}")
    return "\n".join(lines)

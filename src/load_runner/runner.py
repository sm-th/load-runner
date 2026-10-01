"""The runner: mechanical work, one thread per run.

Loop: read the config, open a thread, run the command, stream its output into the
thread, post the result, wait, repeat. No intelligence here; it only follows code.
While it works it reads its threads and obeys commands that agents and people post
there (`/stop`, `/restart`, `/set`, `/unset`), acknowledging each one in the thread.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import IO, Any

from . import protocol
from .bus import Bus, Message
from .config import Config, ConfigError, RunnerConfig

log = logging.getLogger(__name__)

PLACEHOLDER = re.compile(r"\{(\w+)\}")
KILL_GRACE = 5.0


@dataclass(frozen=True)
class Control:
    verb: str  # stop | restart
    author: str


@dataclass(frozen=True)
class Outcome:
    event: str  # passed | failed | stopped | restarting
    detail: str
    results: tuple[str, ...] = ()
    thread: str = ""


class Runner:
    def __init__(self, bus: Bus, load: Callable[[], Config], *, clock: Callable[[], float] = time.monotonic):
        self.bus = bus
        self.load = load
        self.clock = clock
        self.overrides: dict[str, Any] = {}  # set from the thread; outlive config reloads
        self._cursor: str | None = None
        self._watched: dict[str, int] = {}  # thread -> run: the current and the previous run

    def loop(self) -> None:
        run = self._next_run(_runner(self.load()).name)
        done = 0
        while True:
            config = self.load()
            runner = _runner(config)
            outcome = self.run_once(runner, run, {**config.params, **self.overrides})
            done += 1
            run += 1
            if outcome.event == "stopped" or (runner.runs and done >= runner.runs):
                return
            if outcome.event == "restarting":
                continue
            control = self._pause(runner)
            if control and control.verb == "stop":
                return

    def run_once(self, config: RunnerConfig, run: int, params: Mapping[str, Any]) -> Outcome:
        if self._cursor is None:
            _, self._cursor = self.bus.feed(None)
        name = protocol.title(config.name, run)
        argv = expand(config.command, {**params, "run": run})
        root = self.bus.start_thread(name, protocol.started(config.name, run, params, argv))
        self._watched = {t: r for t, r in self._watched.items() if r == run - 1} | {root.thread: run}
        log.info("%s started", name)
        outcome = self._execute(config, run, argv, params, root.thread)
        text = protocol.finished(config.name, run, outcome.event, outcome.detail, outcome.results)
        self.bus.post(root.thread, text)
        log.info("%s %s · %s", name, outcome.event, outcome.detail)
        return replace(outcome, thread=root.thread)

    def _execute(
        self, config: RunnerConfig, run: int, argv: list[str], params: Mapping[str, Any], thread: str
    ) -> Outcome:
        env = os.environ | {"PYTHONUNBUFFERED": "1", "LOAD_RUNNER_RUN": str(run)}
        env |= {"LOAD_RUNNER_THREAD": thread}
        env |= {f"LOAD_RUNNER_PARAM_{key.upper()}": str(value) for key, value in params.items()}
        began = self.clock()
        try:
            process = subprocess.Popen(
                argv,
                cwd=config.cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
                start_new_session=True,
            )
        except OSError as error:
            return Outcome("failed", f"could not start: {error.strerror or error}")

        lines: queue.Queue[str] = queue.Queue()
        reader = threading.Thread(target=_pump, args=(process.stdout, lines), daemon=True)
        reader.start()
        pending: list[str] = []
        results: list[str] = []
        flushed = began
        ended: Outcome | None = None
        while True:
            exited = process.poll() is not None
            if exited:
                reader.join(KILL_GRACE)
            _collect(lines, pending, results)
            if pending and (exited or self.clock() - flushed >= config.flush):
                self.bus.post(thread, protocol.output(config.name, run, pending))
                pending = []
                flushed = self.clock()
            if exited:
                break
            took = f"{self.clock() - began:.1f}s"
            if config.timeout and self.clock() - began > config.timeout:
                ended = Outcome("failed", f"timed out after {config.timeout:g}s")
            elif control := self._obey(config, self._listen()):
                verb = "stopped" if control.verb == "stop" else "restarting"
                ended = Outcome(verb, f"by {control.author} · {took}")
            if ended:
                _kill(process)
                continue
            time.sleep(config.poll)

        if ended:
            return replace(ended, results=tuple(results))
        took = f"{self.clock() - began:.1f}s"
        code = process.returncode
        return Outcome("passed" if code == 0 else "failed", f"exit {code} · {took}", tuple(results))

    def _pause(self, config: RunnerConfig) -> Control | None:
        """Wait between runs, obeying commands; with `wait_for_reply`, until someone answers."""
        until = self.clock() + config.interval
        replied = not config.wait_for_reply
        while True:
            messages = self._listen()
            replied = replied or bool(messages)
            control = self._obey(config, messages)
            if control:
                run = max(self._watched.values())
                thread = next(t for t, r in self._watched.items() if r == run)
                verb = "stopped" if control.verb == "stop" else "restarting"
                self.bus.post(thread, protocol.header(config.name, run, verb, f"by {control.author}"))
                return control
            if replied and self.clock() >= until:
                return None
            time.sleep(config.poll)

    def _listen(self) -> list[Message]:
        """New chat in the watched threads: what agents and people said."""
        messages, self._cursor = self.bus.feed(self._cursor)
        return [m for m in messages if m.thread in self._watched and protocol.parse(m.text) is None]

    def _obey(self, config: RunnerConfig, messages: list[Message]) -> Control | None:
        """Apply `/set` and `/unset` now; return the strongest of `/stop` and `/restart`."""
        control: Control | None = None
        for message in messages:
            run = self._watched[message.thread]
            for command in protocol.commands(message.text):
                ack = self._apply(config, message, command)
                if ack:
                    self.bus.post(message.thread, protocol.header(config.name, run, *ack))
                elif command.verb == "stop" or (command.verb == "restart" and control is None):
                    control = Control(command.verb, message.author)
        return control

    def _apply(
        self, config: RunnerConfig, message: Message, command: protocol.Command
    ) -> tuple[str, str] | None:
        """Change state for one command; the (event, detail) acknowledgement to post, if any."""
        if config.allow and message.author not in config.allow:
            return "refused", f"/{command.verb} from {message.author}"
        if command.error:
            return "refused", f"/{command.verb}: {command.error}"
        if command.verb == "set":
            self.overrides.update(command.values)
            values = ", ".join(f"{k} = {protocol.toml_value(v)}" for k, v in command.values.items())
            return "set", f"{values} for the next run · by {message.author}"
        if command.verb == "unset":
            for key in command.keys:
                self.overrides.pop(key, None)
            return "set", f"{', '.join(command.keys)} back to config · by {message.author}"
        return None

    def _next_run(self, name: str) -> int:
        numbers = (protocol.run_number(t.title, name) for t in self.bus.threads(limit=50))
        return max((n for n in numbers if n is not None), default=0) + 1


def expand(command: list[str], values: Mapping[str, Any]) -> list[str]:
    """Replace `{key}` with a parameter; leave unknown braces alone."""
    return [PLACEHOLDER.sub(lambda m: str(values[m[1]]) if m[1] in values else m[0], arg) for arg in command]


def _runner(config: Config) -> RunnerConfig:
    if config.runner is None:
        raise ConfigError(f"{config.path}: no [runner] section")
    return config.runner


def _pump(stream: IO[str], lines: queue.Queue[str]) -> None:
    for line in stream:
        lines.put(line.rstrip("\n"))
    stream.close()


def _collect(lines: queue.Queue[str], pending: list[str], results: list[str]) -> None:
    """Move what the process printed into output lines and `::result` lines."""
    while True:
        try:
            line = lines.get_nowait()
        except queue.Empty:
            return
        if line.startswith(protocol.RESULT_PREFIX):
            results.append(line.removeprefix(protocol.RESULT_PREFIX))
        else:
            pending.append(line)


def _kill(process: subprocess.Popen[str]) -> None:
    """Stop the whole process group: politely, then for sure."""
    for sig, grace in ((signal.SIGTERM, KILL_GRACE), (signal.SIGKILL, None)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(grace)
            return
        except subprocess.TimeoutExpired:
            continue

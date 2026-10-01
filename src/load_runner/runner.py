"""The runner: mechanical work, one thread per run.

Loop: read the config, open a thread, run the command, stream its output into the
thread, post the result, wait, repeat. No intelligence here; it only follows code.
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
from dataclasses import dataclass
from typing import IO, Any

from . import protocol
from .bus import Bus
from .config import Config, ConfigError, RunnerConfig

log = logging.getLogger(__name__)

PLACEHOLDER = re.compile(r"\{(\w+)\}")
KILL_GRACE = 5.0


@dataclass(frozen=True)
class Outcome:
    event: str  # passed | failed
    detail: str
    results: tuple[str, ...] = ()


class Runner:
    def __init__(self, bus: Bus, load: Callable[[], Config], *, clock: Callable[[], float] = time.monotonic):
        self.bus = bus
        self.load = load
        self.clock = clock

    def loop(self) -> None:
        run = self._next_run(_runner(self.load()).name)
        done = 0
        while True:
            config = self.load()
            runner = _runner(config)
            self.run_once(runner, run, config.params)
            done += 1
            run += 1
            if runner.runs and done >= runner.runs:
                return
            time.sleep(runner.interval)

    def run_once(self, config: RunnerConfig, run: int, params: Mapping[str, Any]) -> Outcome:
        name = protocol.title(config.name, run)
        argv = expand(config.command, {**params, "run": run})
        root = self.bus.start_thread(name, protocol.started(config.name, run, params, argv))
        log.info("%s started", name)
        outcome = self._execute(config, run, argv, params, root.thread)
        text = protocol.finished(config.name, run, outcome.event, outcome.detail, outcome.results)
        self.bus.post(root.thread, text)
        log.info("%s %s · %s", name, outcome.event, outcome.detail)
        return outcome

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
        timed_out = False
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
            if config.timeout and self.clock() - began > config.timeout:
                timed_out = True
                _kill(process)
                continue
            time.sleep(config.poll)

        if timed_out:
            return Outcome("failed", f"timed out after {config.timeout:g}s", tuple(results))
        took = f"{self.clock() - began:.1f}s"
        code = process.returncode
        return Outcome("passed" if code == 0 else "failed", f"exit {code} · {took}", tuple(results))

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

"""TOML configuration. Secrets never live here: adapters read them from the environment."""

from __future__ import annotations

import shlex
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from .protocol import GLYPHS


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RunnerConfig:
    name: str
    command: list[str]
    identity: str = "runner"
    cwd: str | None = None
    interval: float = 5.0  # seconds between runs
    runs: int = 0  # 0 runs forever
    flush: float = 2.0  # seconds between output messages
    timeout: float = 0  # 0 never times out
    poll: float = 0.5  # seconds between bus reads
    allow: tuple[str, ...] = ()  # who may command the runner; empty allows everyone in the thread
    wait_for_reply: bool = False  # hold the next run until someone replies to the result


@dataclass(frozen=True)
class AgentConfig:
    command: list[str]  # the brain: prompt on stdin, reply on stdout
    identity: str = "agent"
    wake: tuple[str, ...] = ("passed", "failed", "chat")  # runner events, or chat from anyone else
    wake_output: str = ""  # regex: also wake on output batches that match, e.g. "nan|Traceback"
    instructions: str = ""  # appended to the built-in prompt
    max_replies: int = 5  # per thread, so two agents cannot talk forever
    timeout: float = 300  # seconds the brain may think
    poll: float = 2.0  # seconds between bus reads


@dataclass(frozen=True)
class Config:
    path: Path
    bus: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    runner: RunnerConfig | None = None
    agent: AgentConfig | None = None


def load(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"{path}: {error}") from error
    unknown = set(data) - {"bus", "params", "runner", "agent"}
    if unknown:
        raise ConfigError(f"{path}: unknown sections {sorted(unknown)}")
    runner, agent = data.get("runner"), data.get("agent")
    return Config(
        path=path,
        bus=data.get("bus", {}),
        params=data.get("params", {}),
        runner=_runner(path, runner) if runner is not None else None,
        agent=_agent(path, agent) if agent is not None else None,
    )


def _runner(path: Path, table: dict[str, Any]) -> RunnerConfig:
    table = dict(table)
    table["command"] = _command(path, "runner", table.get("command"))
    if "allow" in table:
        table["allow"] = tuple(table["allow"])
    return _build(path, "runner", RunnerConfig, table)


def _agent(path: Path, table: dict[str, Any]) -> AgentConfig:
    table = dict(table)
    table["command"] = _command(path, "agent", table.get("command"))
    if "wake" in table:
        table["wake"] = tuple(table["wake"])
        unknown = set(table["wake"]) - {*GLYPHS, "chat"}
        if unknown:
            raise ConfigError(f"{path}: [agent] wake: unknown events {sorted(unknown)}")
    return _build(path, "agent", AgentConfig, table)


def _command(path: Path, section: str, command: Any) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command)
    if isinstance(command, list) and command and all(isinstance(a, str) for a in command):
        return command
    raise ConfigError(f"{path}: [{section}] command must be a string or a list of strings")


def _build(path: Path, section: str, cls: type, table: dict[str, Any]) -> Any:
    known = {f.name for f in fields(cls)}
    unknown = set(table) - known
    if unknown:
        raise ConfigError(f"{path}: unknown keys in [{section}]: {sorted(unknown)}")
    try:
        return cls(**table)
    except TypeError as error:
        raise ConfigError(f"{path}: [{section}] {error}") from error

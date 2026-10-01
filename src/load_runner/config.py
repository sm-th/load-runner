"""TOML configuration. Secrets never live here: adapters read them from the environment."""

from __future__ import annotations

import shlex
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


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


@dataclass(frozen=True)
class Config:
    path: Path
    bus: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    runner: RunnerConfig | None = None


def load(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"{path}: {error}") from error
    unknown = set(data) - {"bus", "params", "runner"}
    if unknown:
        raise ConfigError(f"{path}: unknown sections {sorted(unknown)}")
    runner = data.get("runner")
    return Config(
        path=path,
        bus=data.get("bus", {}),
        params=data.get("params", {}),
        runner=_runner(path, runner) if runner is not None else None,
    )


def _runner(path: Path, table: dict[str, Any]) -> RunnerConfig:
    table = dict(table)
    command = table.get("command")
    if isinstance(command, str):
        table["command"] = shlex.split(command)
    elif not (isinstance(command, list) and command and all(isinstance(a, str) for a in command)):
        raise ConfigError(f"{path}: [runner] command must be a string or a list of strings")
    return _build(path, "runner", RunnerConfig, table)


def _build(path: Path, section: str, cls: type, table: dict[str, Any]) -> Any:
    known = {f.name for f in fields(cls)}
    unknown = set(table) - known
    if unknown:
        raise ConfigError(f"{path}: unknown keys in [{section}]: {sorted(unknown)}")
    try:
        return cls(**table)
    except TypeError as error:
        raise ConfigError(f"{path}: [{section}] {error}") from error

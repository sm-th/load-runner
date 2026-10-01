"""Command line: `load-runner <command>`."""

from __future__ import annotations

import argparse
import logging
import sys
from importlib.metadata import version
from pathlib import Path

from .agent import Agent
from .bus import BusError, open_bus
from .config import ConfigError, load
from .runner import Runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="load-runner",
        description="Mechanical runners, AI agents, and people in one thread.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('load-runner')}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    run = commands.add_parser("run", help="run the command in a loop, one thread per run")
    run.add_argument("-c", "--config", type=Path, default=Path("load-runner.toml"))
    run.set_defaults(handler=_run)

    agent = commands.add_parser("agent", help="wake an agent on results and messages, post its replies")
    agent.add_argument("-c", "--config", type=Path, default=Path("load-runner.toml"))
    agent.set_defaults(handler=_agent)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        args.handler(args)
    except (ConfigError, BusError) as error:
        print(f"load-runner: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


def _run(args: argparse.Namespace) -> None:
    config = load(args.config)
    if config.runner is None:
        raise ConfigError(f"{args.config}: no [runner] section")
    bus = open_bus(config.bus, config.runner.identity)
    Runner(bus, lambda: load(args.config)).loop()


def _agent(args: argparse.Namespace) -> None:
    config = load(args.config)
    if config.agent is None:
        raise ConfigError(f"{args.config}: no [agent] section")
    Agent(open_bus(config.bus, config.agent.identity), config.agent).loop()

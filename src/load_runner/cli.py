"""Command line: `load-runner <command>`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from importlib.metadata import version
from pathlib import Path

from .agent import Agent
from .bus import BusError, open_bus
from .config import ConfigError, load
from .runner import Runner
from .watch import Watcher


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

    watch = commands.add_parser("watch", help="follow every thread live")
    watch.add_argument("-c", "--config", type=Path, default=Path("load-runner.toml"))
    watch.set_defaults(handler=_watch)

    say = commands.add_parser("say", help="post into a thread, as a person")
    say.add_argument("-c", "--config", type=Path, default=Path("load-runner.toml"))
    say.add_argument("--thread", help="thread id (default: the latest thread)")
    say.add_argument("--as", dest="identity", default=os.environ.get("USER", "person"), help="author name")
    say.add_argument("text", nargs="+")
    say.set_defaults(handler=_say)

    threads = commands.add_parser("threads", help="list recent threads")
    threads.add_argument("-c", "--config", type=Path, default=Path("load-runner.toml"))
    threads.add_argument("-n", "--limit", type=int, default=20)
    threads.set_defaults(handler=_threads)
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


def _watch(args: argparse.Namespace) -> None:
    Watcher(open_bus(load(args.config).bus, "watcher")).follow()


def _say(args: argparse.Namespace) -> None:
    bus = open_bus(load(args.config).bus, args.identity)
    thread = args.thread
    if thread is None:
        latest = bus.threads(limit=1)
        if not latest:
            raise BusError("no threads yet; pass --thread")
        thread = latest[0].id
    print(bus.post(thread, " ".join(args.text)).id)


def _threads(args: argparse.Namespace) -> None:
    for thread in open_bus(load(args.config).bus, "watcher").threads(limit=args.limit):
        print(f"{thread.id}\t{thread.title}")

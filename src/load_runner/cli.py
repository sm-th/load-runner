"""Command line: `load-runner <command>`."""

from __future__ import annotations

import argparse
from importlib.metadata import version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="load-runner",
        description="Mechanical runners, AI agents, and people in one thread.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('load-runner')}")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0

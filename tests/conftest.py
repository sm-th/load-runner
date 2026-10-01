import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from load_runner.bus import Bus
from load_runner.bus.buzz import BuzzBus
from load_runner.bus.memory import MemoryHub
from load_runner.bus.sqlite import SqliteBus

BusFactory = Callable[[str], Bus]
FAKE_BUZZ = [sys.executable, str(Path(__file__).with_name("fake_buzz.py"))]
CHANNEL = "123e4567-e89b-12d3-a456-426614174000"


def buzz(tmp_path: Path) -> Callable[..., BuzzBus]:
    """Participants of one fake Buzz relay; `channel` may differ from the relay's to provoke errors."""

    def connect(identity: str, channel: str = CHANNEL) -> BuzzBus:
        env = os.environ | {
            "BUZZ_PRIVATE_KEY": identity,
            "FAKE_BUZZ_STATE": str(tmp_path / "buzz.json"),
            "FAKE_BUZZ_CHANNEL": CHANNEL,
        }
        return BuzzBus(channel, FAKE_BUZZ, env)

    return connect


@pytest.fixture
def buzz_relay(tmp_path) -> Callable[..., BuzzBus]:
    return buzz(tmp_path)


@pytest.fixture(params=["memory", "sqlite", "buzz"])
def connect(request, tmp_path) -> BusFactory:
    """`connect(identity)` joins one shared bus of each kind as a participant."""
    match request.param:
        case "memory":
            return MemoryHub().connect
        case "sqlite":
            return lambda identity: SqliteBus(tmp_path / "bus.db", identity)
        case "buzz":
            return buzz(tmp_path)

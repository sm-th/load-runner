from collections.abc import Callable

import pytest

from load_runner.bus import Bus
from load_runner.bus.memory import MemoryHub
from load_runner.bus.sqlite import SqliteBus

BusFactory = Callable[[str], Bus]


@pytest.fixture(params=["memory", "sqlite"])
def connect(request, tmp_path) -> BusFactory:
    """`connect(identity)` joins one shared bus of each kind as a participant."""
    if request.param == "memory":
        return MemoryHub().connect
    return lambda identity: SqliteBus(tmp_path / "bus.db", identity)

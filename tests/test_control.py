"""People and agents steer the runner by writing in its thread."""

import sys
import threading
import time
from pathlib import Path

import pytest

from load_runner import protocol
from load_runner.bus.memory import MemoryHub
from load_runner.config import Config, RunnerConfig
from load_runner.runner import Runner

SLOW = [sys.executable, "-c", "import sys, time; print('lr', sys.argv[1]); time.sleep(30)", "{lr}"]
QUICK = [sys.executable, "-c", "print('ok')"]


def config(command, **runner) -> Config:
    settings = {"interval": 0, "flush": 0.05, "poll": 0.02, "runs": 3} | runner
    return Config(Path("test.toml"), params={"lr": 0.3}, runner=RunnerConfig("train", command, **settings))


def start(cfg: Config) -> tuple[MemoryHub, threading.Thread]:
    hub = MemoryHub()
    loop = threading.Thread(target=Runner(hub.connect("runner"), lambda: cfg).loop, daemon=True)
    loop.start()
    return hub, loop


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not (value := predicate()):
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)
    return value


def texts(hub: MemoryHub) -> list[list[str]]:
    bus = hub.connect("observer")
    return [[m.text for m in bus.thread(t.id)] for t in bus.threads()]


def events(hub: MemoryHub, thread: int) -> list[str]:
    return [e.event for text in texts(hub)[thread] if (e := protocol.parse(text))]


def test_a_person_stops_the_loop_in_the_middle_of_a_run():
    hub, loop = start(config(SLOW))
    wait_for(lambda: "output" in events(hub, 0))

    hub.connect("andy").post("1", "No, that's enough. Stop it.\n/stop")
    loop.join(10)

    assert not loop.is_alive()
    [thread] = texts(hub)
    assert thread[-1].startswith("■ train · run 1 stopped · by andy · ")


def test_the_agent_changes_a_parameter_and_restarts_the_run():
    hub, loop = start(config(SLOW))
    wait_for(lambda: "output" in events(hub, 0))

    hub.connect("agent").post("1", "Loss diverged. Lowering the learning rate.\n/set lr=0.03\n/restart")
    second = wait_for(lambda: texts(hub)[1:] and texts(hub)[1])

    first = texts(hub)[0]
    assert "⚙ train · run 1 set · lr = 0.03 for the next run · by agent" in first
    assert first[-1].startswith("↻ train · run 1 restarting · by agent · ")
    assert second[0].startswith("▶ train · run 2 started")
    assert "lr = 0.03" in second[0]
    hub.connect("andy").post("2", "/stop")
    loop.join(10)


def test_commands_from_outside_the_allow_list_are_refused():
    hub, loop = start(config(SLOW, allow=("agent", "andy")))
    wait_for(lambda: "output" in events(hub, 0))

    hub.connect("mallory").post("1", "/stop")
    wait_for(lambda: "refused" in events(hub, 0))
    assert loop.is_alive()
    assert "⊘ train · run 1 refused · /stop from mallory" in texts(hub)[0]

    hub.connect("andy").post("1", "/stop")
    loop.join(10)
    assert not loop.is_alive()


def test_wait_for_reply_holds_the_next_run_until_someone_answers():
    hub, loop = start(config(QUICK, wait_for_reply=True))
    wait_for(lambda: "passed" in events(hub, 0))
    time.sleep(0.3)
    assert len(texts(hub)) == 1

    hub.connect("agent").post("1", "Got it, everything is okay.")
    wait_for(lambda: len(texts(hub)) == 2)
    hub.connect("andy").post("2", "/stop")
    loop.join(10)


def test_stop_between_runs_ends_the_loop_with_an_acknowledgement():
    hub, loop = start(config(QUICK, wait_for_reply=True))
    wait_for(lambda: "passed" in events(hub, 0))

    hub.connect("andy").post("1", "/stop")
    loop.join(10)

    assert not loop.is_alive()
    assert texts(hub)[0][-1] == "■ train · run 1 stopped · by andy"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/set lr=0.03 warm=true tag=x", [protocol.Command("set", {"lr": 0.03, "warm": True, "tag": "x"})]),
        ("Looks fine.\n  /restart  \nthanks", [protocol.Command("restart")]),
        ("/unset lr warmup", [protocol.Command("unset", keys=("lr", "warmup"))]),
        ("/settings are fine, /stop is not a line command here", []),
    ],
)
def test_commands_are_read_from_their_own_lines(text, expected):
    assert protocol.commands(text) == expected


def test_malformed_set_is_reported_not_applied():
    [command] = protocol.commands("/set lr")

    assert command.error
    assert command.values == {}

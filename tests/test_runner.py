import sys
import time
from pathlib import Path

from load_runner import protocol
from load_runner.bus.memory import MemoryHub
from load_runner.config import Config, RunnerConfig
from load_runner.runner import Runner


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def config(command: list[str], params=None, **runner) -> Config:
    settings = {"interval": 0, "flush": 0.05, "poll": 0.02, "runs": 1} | runner
    return Config(Path("test.toml"), params=params or {}, runner=RunnerConfig("train", command, **settings))


def run(cfg: Config, hub: MemoryHub | None = None) -> list[list[str]]:
    hub = hub or MemoryHub()
    bus = hub.connect("runner")
    Runner(bus, lambda: cfg).loop()
    return [[m.text for m in bus.thread(t.id)] for t in bus.threads()]


def test_a_run_is_one_thread_started_output_result():
    code = "import sys; print('epoch 1 loss', sys.argv[1]); print('::result loss=0.12')"
    [thread] = run(config([*python(code), "{lr}"], params={"lr": 0.3}))

    started, *outputs, result = thread
    assert started.startswith("▶ train · run 1 started")
    assert "lr = 0.3" in started
    assert "epoch 1 loss 0.3" in "\n".join(outputs)
    assert "::result" not in "\n".join(outputs)
    assert result.startswith("✓ train · run 1 passed · exit 0 · ")
    assert result.endswith("\n\nloss=0.12")


def test_a_failing_command_reports_its_exit_code():
    [thread] = run(config(python("raise SystemExit(3)")))

    assert protocol.parse(thread[-1]).event == "failed"
    assert thread[-1].startswith("✗ train · run 1 failed · exit 3 · ")


def test_a_missing_command_fails_the_run_instead_of_the_runner():
    [thread] = run(config(["/nonexistent/load-runner-command"]))

    assert thread[-1].startswith("✗ train · run 1 failed · could not start")


def test_timeout_kills_the_whole_process_group():
    began = time.monotonic()
    [thread] = run(config(["sh", "-c", "sleep 30 & sleep 30; wait"], timeout=0.3))

    assert thread[-1] == "✗ train · run 1 failed · timed out after 0.3s"
    assert time.monotonic() - began < 5


def test_run_numbers_continue_from_the_bus():
    hub = MemoryHub()
    hub.connect("runner").start_thread("train · run 4", "▶ train · run 4 started")

    threads = run(config(python("pass")), hub)

    assert threads[-1][0].startswith("▶ train · run 5 started")


def test_config_is_read_again_before_every_run():
    before, after = (config(python("pass"), {"lr": lr}, runs=2) for lr in (0.3, 0.03))
    loads = iter([before, before, after])
    bus = MemoryHub().connect("runner")

    Runner(bus, lambda: next(loads)).loop()

    first, second = (bus.thread(t.id)[0].text for t in bus.threads())
    assert "lr = 0.3" in first
    assert "lr = 0.03" in second

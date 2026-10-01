"""What a person does from a terminal on the local bus."""

import io
import subprocess
import sys
import time

from load_runner.bus.sqlite import SqliteBus
from load_runner.cli import main
from load_runner.watch import Watcher

CONFIG = """
[bus]
kind = "sqlite"
path = "{bus}"

[runner]
name = "train"
command = ["{python}", "-c", "import time; print('epoch 1'); time.sleep(30)"]
flush = 0.1
poll = 0.1
"""


def test_say_stops_a_runner_started_in_another_terminal(tmp_path, capsys):
    bus_path = tmp_path / "bus.db"
    config = tmp_path / "load-runner.toml"
    config.write_text(CONFIG.format(bus=bus_path, python=sys.executable))
    runner = subprocess.Popen([sys.executable, "-m", "load_runner", "run", "-c", str(config)])
    bus = SqliteBus(bus_path, "observer")
    deadline = time.monotonic() + 10
    while not any("epoch 1" in m.text for m in bus.feed("0")[0]):
        assert time.monotonic() < deadline
        time.sleep(0.05)

    assert main(["say", "-c", str(config), "--as", "andy", "/stop"]) == 0

    assert runner.wait(10) == 0
    [thread] = bus.threads()
    assert bus.thread(thread.id)[-1].text.startswith("■ train · run 1 stopped · by andy")
    main(["threads", "-c", str(config)])
    assert capsys.readouterr().out.endswith(f"{thread.id}\ttrain · run 1\n")


def test_watch_shows_every_thread_in_arrival_order(tmp_path):
    runner = SqliteBus(tmp_path / "bus.db", "runner")
    out = io.StringIO()
    watcher = Watcher(SqliteBus(tmp_path / "bus.db", "watcher"), out, color=False)
    _, cursor = watcher.bus.feed(None)

    one = runner.start_thread("train · run 1", "✓ train · run 1 passed · exit 0 · 1.0s")
    two = runner.start_thread("train · run 2", "▶ train · run 2 started\n\n```toml\nlr = 0.03\n```")
    SqliteBus(tmp_path / "bus.db", "andy").post(one.thread, "Nice.")
    watcher.step(cursor)

    lines = [line.split("  ", 1)[1] for line in out.getvalue().splitlines() if not line.startswith("    ")]
    assert lines == ["train · run 1  runner", "train · run 2  runner", "train · run 1  andy"]
    assert "    lr = 0.03" in out.getvalue()
    assert two.thread != one.thread

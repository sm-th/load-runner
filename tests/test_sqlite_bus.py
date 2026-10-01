import subprocess
import sys

from load_runner.bus.sqlite import SqliteBus

WRITER = """
import sys
from pathlib import Path
from load_runner.bus.sqlite import SqliteBus
bus = SqliteBus(Path(sys.argv[1]), "runner")
root = bus.start_thread("train · run 1", "started")
bus.post(root.thread, "passed")
"""


def test_two_processes_share_one_file(tmp_path):
    path = tmp_path / "bus.db"
    person = SqliteBus(path, "andy")
    _, cursor = person.feed(None)

    subprocess.run([sys.executable, "-c", WRITER, str(path)], check=True)

    messages, _ = person.feed(cursor)
    assert [(m.author, m.text) for m in messages] == [("runner", "started"), ("runner", "passed")]

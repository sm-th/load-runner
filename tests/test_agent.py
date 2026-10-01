import sys
import threading
import time
from pathlib import Path

from load_runner import protocol
from load_runner.agent import Agent
from load_runner.bus.memory import MemoryHub
from load_runner.config import AgentConfig, Config, RunnerConfig
from load_runner.runner import Runner


class Brain:
    def __init__(self, reply="Got it, everything is okay."):
        self.reply = reply
        self.prompts: list[str] = []

    def __call__(self, prompt: str, thread: str) -> str:
        self.prompts.append(prompt)
        return self.reply


def setup(brain: Brain, **agent):
    hub = MemoryHub()
    bus = hub.connect("agent")
    bot = Agent(bus, AgentConfig(command=["unused"], **agent), think=brain)
    _, cursor = bus.feed(None)
    runner = hub.connect("runner")
    root = runner.start_thread("train · run 1", protocol.header("train", 1, "started"))
    return hub, bot, cursor, runner, root.thread


def test_output_does_not_wake_the_agent_but_the_result_does():
    brain = Brain()
    hub, bot, cursor, runner, thread = setup(brain)

    runner.post(thread, protocol.output("train", 1, ["epoch 1 loss 2.31"]))
    cursor = bot.step(cursor)
    assert brain.prompts == []

    runner.post(thread, protocol.finished("train", 1, "passed", "exit 0 · 4.2s"))
    bot.step(cursor)

    assert len(brain.prompts) == 1
    assert "epoch 1 loss 2.31" in brain.prompts[0]
    assert [m.text for m in hub.connect("andy").thread(thread)][-1] == "Got it, everything is okay."


def test_a_person_wakes_the_agent_and_is_in_the_transcript():
    brain = Brain("Stopping.\n/stop")
    hub, bot, cursor, _, thread = setup(brain)

    hub.connect("andy").post(thread, "No, that's enough. Stop it.")
    bot.step(cursor)

    assert "andy: No, that's enough. Stop it." in brain.prompts[0]


def test_the_agent_never_wakes_on_its_own_reply():
    brain = Brain()
    hub, bot, cursor, _, thread = setup(brain)
    hub.connect("andy").post(thread, "How is it going?")

    cursor = bot.step(cursor)
    bot.step(cursor)

    assert len(brain.prompts) == 1


def test_matching_output_wakes_the_agent():
    brain = Brain()
    _, bot, cursor, runner, thread = setup(brain, wake_output="nan|Traceback")

    runner.post(thread, protocol.output("train", 1, ["epoch 3 loss nan"]))
    bot.step(cursor)

    assert len(brain.prompts) == 1


def test_max_replies_ends_a_conversation_between_agents():
    brain = Brain("Interesting.")
    hub, bot, cursor, _, thread = setup(brain, max_replies=2)
    other = hub.connect("other-agent")

    for _ in range(4):
        other.post(thread, "Interesting.")
        cursor = bot.step(cursor)

    assert len(brain.prompts) == 2


def test_an_empty_reply_posts_nothing():
    brain = Brain("   ")
    hub, bot, cursor, runner, thread = setup(brain)

    runner.post(thread, protocol.finished("train", 1, "passed", "exit 0 · 1.0s"))
    bot.step(cursor)

    assert len(hub.connect("andy").thread(thread)) == 2


TRAIN = """
import sys
lr = float(sys.argv[1])
print("epoch 1 loss", "nan" if lr > 0.1 else 0.12)
sys.exit(1 if lr > 0.1 else 0)
"""

BRAIN = """
import sys
thread = sys.stdin.read()
if "failed" in thread.rsplit("▶", 1)[-1]:
    print("Loss diverged. Lowering the learning rate.\\n/set lr=0.03\\n/restart")
else:
    print("Got it, everything is okay.")
"""


def test_end_to_end_a_failed_run_is_fixed_by_the_agent():
    hub = MemoryHub()
    cfg = Config(
        Path("test.toml"),
        params={"lr": 0.3},
        runner=RunnerConfig(
            "train",
            [sys.executable, "-c", TRAIN, "{lr}"],
            interval=0,
            flush=0.05,
            poll=0.02,
            runs=2,
            wait_for_reply=True,
        ),
    )
    agent = Agent(hub.connect("agent"), AgentConfig([sys.executable, "-c", BRAIN], poll=0.02))
    threading.Thread(target=agent.loop, daemon=True).start()
    time.sleep(0.1)  # the agent subscribes from now

    Runner(hub.connect("runner"), lambda: cfg).loop()

    bus = hub.connect("andy")
    first, second = ([m.text for m in bus.thread(t.id)] for t in bus.threads())
    assert first[-4].startswith("✗ train · run 1 failed")
    assert first[-3].startswith("Loss diverged.")
    assert first[-2:] == [
        "⚙ train · run 1 set · lr = 0.03 for the next run · by agent",
        "↻ train · run 1 restarting · by agent",
    ]
    assert "lr = 0.03" in second[0]
    assert any(text.startswith("✓ train · run 2 passed") for text in second)

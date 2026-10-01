"""Every adapter must pass these: they are the bus contract."""

import pytest

from load_runner import protocol
from load_runner.bus import BusError


def test_thread_holds_root_and_replies_in_order_with_authors(connect):
    runner, agent = connect("runner"), connect("agent")
    root = runner.start_thread("train · run 1", "started")
    agent.post(root.thread, "looks fine")
    runner.post(root.thread, "passed")

    messages = agent.thread(root.thread)

    assert [(m.author, m.text) for m in messages] == [
        ("runner", "started"),
        ("agent", "looks fine"),
        ("runner", "passed"),
    ]
    assert {m.thread for m in messages} == {root.thread}


def test_feed_subscribes_from_now_and_returns_new_messages_across_threads(connect):
    runner, person = connect("runner"), connect("andy")
    old = runner.start_thread("train · run 1", "history")
    messages, cursor = person.feed(None)
    assert messages == []

    new = runner.start_thread("train · run 2", "started")
    person.post(old.thread, "/stop")
    messages, cursor = person.feed(cursor)

    assert [(m.thread, m.author, m.text) for m in messages] == [
        (new.thread, "runner", "started"),
        (old.thread, "andy", "/stop"),
    ]
    assert person.feed(cursor) == ([], cursor)


def test_threads_lists_most_recent_oldest_first_with_findable_run_numbers(connect):
    runner = connect("runner")
    for n in range(1, 5):
        runner.start_thread(f"train · run {n}", f"▶ train · run {n} started")

    threads = runner.threads(limit=2)

    assert [protocol.run_number(t.title, "train") for t in threads] == [3, 4]
    assert [m.text for m in runner.thread(threads[-1].id)] == ["▶ train · run 4 started"]


def test_post_to_unknown_thread_fails(connect):
    with pytest.raises(BusError):
        connect("runner").post("999", "hello")

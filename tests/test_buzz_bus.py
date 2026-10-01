import pytest

from load_runner.bus import BusError, open_bus


def test_cli_errors_surface_with_buzz_message(buzz_relay):
    wrong = buzz_relay("runner", channel="00000000-0000-0000-0000-000000000000")

    with pytest.raises(BusError, match="buzz messages send: channel not found"):
        wrong.start_thread("train · run 1", "started")


def test_a_missing_cli_is_a_bus_error():
    bus = open_bus({"kind": "buzz", "channel": "c", "bin": "/nonexistent/buzz"}, "runner")

    with pytest.raises(BusError, match="cannot run /nonexistent/buzz"):
        bus.threads()


def test_feed_does_not_repeat_messages_from_the_same_second(buzz_relay):
    runner, person = buzz_relay("runner"), buzz_relay("andy")
    root = runner.start_thread("train · run 1", "started")
    _, cursor = person.feed(None)

    seen = []
    for text in ("one", "two", "three"):
        runner.post(root.thread, text)
        messages, cursor = person.feed(cursor)
        seen += [m.text for m in messages]

    assert seen == ["one", "two", "three"]

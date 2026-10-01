import pytest

from load_runner.bus import BusError, open_bus
from load_runner.bus.zulip import ZulipBus


def test_api_errors_surface_with_zulip_message(zulip):
    bus = ZulipBus(zulip.site, "no-such-stream", "runner@example.com", "key")

    with pytest.raises(BusError, match="zulip get_stream_id: Invalid channel name 'no-such-stream'"):
        bus.threads()


def test_an_unreachable_server_is_a_bus_error():
    bus = ZulipBus("http://127.0.0.1:9", "runs", "runner@example.com", "key")

    with pytest.raises(BusError, match="zulip unreachable"):
        bus.feed(None)


def test_credentials_come_from_the_environment(monkeypatch):
    monkeypatch.delenv("ZULIP_API_KEY", raising=False)
    monkeypatch.setenv("ZULIP_EMAIL", "runner@example.com")

    with pytest.raises(BusError, match="needs ZULIP_API_KEY"):
        open_bus({"kind": "zulip", "site": "https://chat.example.com", "stream": "runs"}, "runner")


def test_long_titles_fit_a_zulip_topic(zulip):
    bus = ZulipBus(zulip.site, "runs", "runner@example.com", "key")

    root = bus.start_thread("a-very-long-runner-name-for-nightly-regression-checks · run 12345", "started")

    assert len(root.thread) == 60
    assert [m.text for m in bus.thread(root.thread)] == ["started"]

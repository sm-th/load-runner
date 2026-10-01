from load_runner import protocol


def test_runner_messages_parse_back_and_chat_does_not():
    text = protocol.finished("train", 3, "failed", "exit 1 · 4.2s", ["loss=nan"])

    assert protocol.parse(text) == protocol.Event("train", 3, "failed", "exit 1 · 4.2s")
    assert protocol.parse("Loss diverged. Lowering the learning rate.") is None
    assert protocol.parse("✓ train · run 3 failed") is None  # glyph and event disagree


def test_long_output_keeps_the_tail_within_the_size_limit():
    lines = [f"step {n} loss {1 / (n + 1):.6f}" for n in range(2000)]

    text = protocol.output("train", 1, lines)

    assert len(text) <= protocol.MAX_TEXT
    assert "step 1999 " in text
    assert "lines skipped" in text.split("\n")[2]


def test_run_number_is_read_from_any_thread_title_shape():
    assert protocol.run_number("train · run 12", "train") == 12
    assert protocol.run_number("▶ train · run 12 started", "train") == 12
    assert protocol.run_number("pretrain · run 12", "train") is None

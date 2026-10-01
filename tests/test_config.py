import pytest

from load_runner.config import ConfigError, load

VALID = """
[runner]
name = "train"
command = "python train.py --lr {lr}"
allow = ["agent", "andy"]

[agent]
command = ["claude", "-p"]
wake = ["failed", "chat"]
"""


def test_a_full_config_loads(tmp_path):
    path = tmp_path / "load-runner.toml"
    path.write_text(VALID)

    config = load(path)

    assert config.runner.command == ["python", "train.py", "--lr", "{lr}"]
    assert config.runner.allow == ("agent", "andy")
    assert config.agent.wake == ("failed", "chat")


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("[runer]\nname = 'x'", "unknown sections ['runer']"),
        ("[runner]\nname = 'x'\ncommand = 'true'\nintervall = 1", "unknown keys in [runner]: ['intervall']"),
        ("[runner]\nname = 'x'\ncommand = []", "command must be a string or a list of strings"),
        ("[agent]\ncommand = 'claude -p'\nwake = ['done']", "wake: unknown events ['done']"),
    ],
)
def test_mistakes_are_named(tmp_path, text, complaint):
    path = tmp_path / "load-runner.toml"
    path.write_text(text)

    with pytest.raises(ConfigError, match=complaint.replace("[", r"\[").replace("]", r"\]")):
        load(path)

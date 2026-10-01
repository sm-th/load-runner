from importlib.metadata import version

import pytest

from load_runner.cli import main


def test_version_matches_package_metadata(capsys):
    with pytest.raises(SystemExit) as exit_:
        main(["--version"])
    assert exit_.value.code == 0
    assert capsys.readouterr().out.strip() == f"load-runner {version('load-runner')}"

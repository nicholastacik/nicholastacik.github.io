from click.testing import CliRunner
from jeopardy.main import cli


def test_cli_exposes_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("crawl", "build", "all"):
        assert cmd in result.output

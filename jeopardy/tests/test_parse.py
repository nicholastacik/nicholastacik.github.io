from pathlib import Path
from jeopardy.parse import parse_game

FIXTURES = Path(__file__).parent / "fixtures"


def _modern():
    return (FIXTURES / "game_modern.html").read_text()


def test_parse_game_metadata():
    game = parse_game(_modern())
    assert game is not None
    assert game["show_number"] == 8235
    assert game["air_date"] == "2020-06-12"
    assert "Zach Newkirk" in game["game_comments"]


def test_parse_game_missing_returns_none():
    assert parse_game("<html><body>nothing here</body></html>") is None

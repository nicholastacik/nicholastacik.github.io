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


def _clue_at(game, round_, col, row):
    for c in game["clues"]:
        if c["round"] == round_ and c["col"] == col and c["row"] == row:
            return c
    raise AssertionError(f"no clue at {round_} col={col} row={row}")


def test_board_clue_counts():
    game = parse_game(_modern())
    board = [c for c in game["clues"] if c["round"] in ("J", "DJ")]
    assert len(board) == 60  # 30 per round, fully revealed game
    assert sum(c["is_daily_double"] for c in board) == 3


def test_first_jeopardy_clue():
    c = _clue_at(parse_game(_modern()), "J", 1, 1)
    assert c["category"] == "CLASSIC AUTOMOBILES"
    assert c["value"] == 200
    assert c["is_daily_double"] is False
    assert c["dd_wager"] is None
    assert c["clue"].startswith("In 1913 this model from Ford")
    assert c["answer"] == "the Model T"
    assert c["order_number"] == 17


def test_category_entities_unescaped():
    game = parse_game(_modern())
    cats = {c["category"] for c in game["clues"] if c["round"] == "J"}
    assert "WORDS & PHRASES" in cats  # was "WORDS &amp; PHRASES"


def test_daily_double_has_wager_not_value():
    game = parse_game(_modern())
    dds = [c for c in game["clues"] if c["is_daily_double"]]
    assert dds  # at least one
    for c in dds:
        assert c["value"] is None
        assert isinstance(c["dd_wager"], int) and c["dd_wager"] > 0


def test_final_jeopardy_clue():
    game = parse_game(_modern())
    finals = [c for c in game["clues"] if c["round"] == "Final"]
    assert len(finals) == 1
    fj = finals[0]
    assert fj["category"] == "AUTHORS"
    assert fj["row"] is None and fj["col"] is None and fj["value"] is None
    assert fj["clue"]  # non-empty
    assert fj["answer"]  # non-empty

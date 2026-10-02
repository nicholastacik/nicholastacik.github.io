import math
from pathlib import Path
from pipeline.scrape_correctness import parse_game_correctness

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return (FIXTURES / name).read_text()


def _find(rows, round_, row, col):
    for r in rows:
        row_match = (math.isnan(r["row"]) and row is None) or r["row"] == row
        col_match = (math.isnan(r["column"]) and col is None) or r["column"] == col
        if r["round"] == round_ and row_match and col_match:
            return r
    raise AssertionError(f"no row for {round_} row={row} col={col}")


def test_normal_clue_right_and_wrong():
    rows = parse_game_correctness(_load("game_9489.html"), game_id=9489)
    clue = _find(rows, "Jeopardy", row=1, col=1)
    assert clue["n_right"] == 1
    assert clue["n_wrong"] == 1
    assert clue["is_triple_stumper"] is False
    assert clue["game_id"] == 9489


def test_triple_stumper_not_counted_as_wrong():
    rows = parse_game_correctness(_load("game_9489.html"), game_id=9489)
    clue = _find(rows, "Jeopardy", row=2, col=2)
    assert clue["n_right"] == 0
    assert clue["n_wrong"] == 0
    assert clue["is_triple_stumper"] is True


def test_final_jeopardy_null_coordinates():
    rows = parse_game_correctness(_load("game_9489.html"), game_id=9489)
    fj = _find(rows, "Final", row=None, col=None)
    assert math.isnan(fj["row"])
    assert math.isnan(fj["column"])
    assert fj["n_wrong"] == 3
    assert fj["n_right"] == 0
    assert fj["is_triple_stumper"] is False


def test_round_names_are_full():
    rows = parse_game_correctness(_load("game_9489.html"), game_id=9489)
    rounds = {r["round"] for r in rows}
    assert rounds <= {"Jeopardy", "Double Jeopardy", "Final"}

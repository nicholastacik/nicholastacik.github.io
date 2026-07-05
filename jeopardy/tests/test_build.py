from pathlib import Path

from jeopardy.build_parquet import board_value, classify_game_type, game_rows
from jeopardy.parse import parse_game

FIXTURES = Path(__file__).parent / "fixtures"


def test_board_value_modern():
    assert board_value("J", 1, "2020-06-12") == 200
    assert board_value("J", 5, "2020-06-12") == 1000
    assert board_value("DJ", 1, "2020-06-12") == 400
    assert board_value("DJ", 5, "2020-06-12") == 2000


def test_board_value_pre_2001_halved():
    assert board_value("J", 5, "2000-01-01") == 500
    assert board_value("DJ", 5, "2000-01-01") == 1000


def test_board_value_final_is_none():
    assert board_value("Final", None, "2020-06-12") is None


def test_classify_named_season():
    assert classify_game_type("goattournament", "") == "goat"
    assert classify_game_type("jm", "") == "jeopardy_masters"


def test_classify_from_comments():
    assert classify_game_type("35", "Tournament of Champions final game 2.") == "toc"
    assert classify_game_type("30", "Teen Tournament quarterfinal.") == "teen"
    assert classify_game_type("36", "Zach Newkirk game 4.") == "regular"


def test_game_rows_shape_and_derivation():
    record = {
        "game_id": 6699, "season": "36", "show_number": 8235,
        "air_date": "2020-06-12", "game_comments": "Zach Newkirk game 4.",
        "clues": [
            {"round": "J", "row": 3, "col": 2, "category": "X", "value": 600,
             "is_daily_double": False, "dd_wager": None, "clue": "c", "answer": "a",
             "order_number": 5},
            {"round": "DJ", "row": 1, "col": 1, "category": "Y", "value": None,
             "is_daily_double": True, "dd_wager": 1600, "clue": "d", "answer": "b",
             "order_number": 9},
        ],
    }
    rows = game_rows(record)
    assert len(rows) == 2
    r0, r1 = rows
    assert r0["round"] == "Jeopardy" and r0["column"] == 2 and r0["clue_value"] == 600
    assert r0["game_type"] == "regular" and r0["season"] == "36"
    # DD: clue_value is the derived board value, wager preserved separately
    assert r1["round"] == "Double Jeopardy"
    assert r1["clue_value"] == 400 and r1["dd_wager"] == 1600
    assert set(r0.keys()) == {
        "game_id", "air_date", "season", "game_type", "round", "category",
        "clue_value", "row", "column", "is_daily_double", "dd_wager", "clue", "answer",
    }


def test_tournament_fixture_daily_double_gets_doubled_era_value():
    # Regression: tournament title format ("...game #N, aired DATE") has no
    # "Show #" prefix, so the old air_date regex returned None and board_value()
    # fell back to the pre-2001 halved ladder. This DD is post-2001 (2020-01-07)
    # so it must get the doubled Double Jeopardy value: 400 * row.
    record = parse_game((FIXTURES / "game_tournament.html").read_text())
    assert record["air_date"] == "2020-01-07"
    record["game_id"] = 1
    record["season"] = "goattournament"
    rows = game_rows(record)
    dd = next(
        r for r in rows
        if r["round"] == "Double Jeopardy" and r["is_daily_double"] and r["dd_wager"] == 8600
    )
    assert dd["row"] == 3
    assert dd["clue_value"] == 1200  # 400 * row(3); would be 600 with the pre-2001 halved ladder


def test_pre2001_fixture_daily_double_gets_halved_era_value():
    record = parse_game((FIXTURES / "game_pre2001.html").read_text())
    assert record["air_date"] == "1984-09-10"
    record["game_id"] = 2
    record["season"] = "1"
    rows = game_rows(record)
    dd = next(
        r for r in rows
        if r["round"] == "Jeopardy" and r["is_daily_double"] and r["dd_wager"] == 800
    )
    assert dd["row"] == 3
    assert dd["clue_value"] == 300  # 100 * row(3), pre-2001 halved ladder


def test_fixture_game_produces_valid_rows():
    record = parse_game((FIXTURES / "game_modern.html").read_text())
    record["game_id"] = 6699
    record["season"] = "36"
    rows = game_rows(record)
    assert len(rows) == 61  # 60 board + 1 final
    finals = [r for r in rows if r["round"] == "Final"]
    assert len(finals) == 1 and finals[0]["clue_value"] is None
    # every board row has a positive derived value and a category
    for r in rows:
        if r["round"] != "Final":
            assert r["clue_value"] and r["clue_value"] > 0
            assert r["category"]

import json
from pathlib import Path
from jeopardy.crawl import parse_season_ids, parse_game_ids, existing_game_ids

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_season_ids():
    ids = parse_season_ids((FIXTURES / "listseasons.html").read_text())
    assert "36" in ids
    assert "goattournament" in ids
    assert len(ids) == len(set(ids))  # deduped
    assert len(ids) >= 45


def test_parse_game_ids():
    ids = parse_game_ids((FIXTURES / "season36.html").read_text())
    assert 6699 in ids
    assert all(isinstance(i, int) for i in ids)
    assert len(ids) == len(set(ids))


def test_existing_game_ids(tmp_path):
    p = tmp_path / "games.jsonl"
    p.write_text(json.dumps({"game_id": 1}) + "\n" + json.dumps({"game_id": 2}) + "\n")
    assert existing_game_ids(p) == {1, 2}


def test_existing_game_ids_missing_file(tmp_path):
    assert existing_game_ids(tmp_path / "nope.jsonl") == set()

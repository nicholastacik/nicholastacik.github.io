from fakes import FakeSpreadsheet, get_cell, make_spreadsheet

from job.sheet import HEADERS, Sheet, Update, column_letter

TRACKED = {"tmdb_id": 1, "tvmaze_id": "", "name": "One", "active": True, "added_at": "2026-09-20"}


def test_column_letter():
    assert [column_letter(i) for i in (0, 12, 25, 26, 27)] == ["A", "M", "Z", "AA", "AB"]


def test_read_all_returns_string_rows_with_row_numbers_and_skips_blanks():
    sp = make_spreadsheet(Tracked=[TRACKED])
    sp.grid["Tracked"].append([])
    sp.grid["Tracked"].append(["2", "", "Two"])
    tracked = Sheet(sp).read_all()["Tracked"]
    assert [(r["tmdb_id"], r["name"], r["active"], r["_row"]) for r in tracked] == [("1", "One", "TRUE", 2), ("2", "Two", "", 4)]
    assert tracked[1]["poster_url"] == ""


def test_write_updates_every_row_with_the_key_located_fresh():
    sp = make_spreadsheet(Tracked=[TRACKED, {**TRACKED, "tmdb_id": 2, "name": "Two"}, TRACKED])
    sheet = Sheet(sp)
    sheet.read_all()
    sp.grid["Tracked"].insert(1, ["9", "", "Hand inserted"])
    sheet.write([Update("Tracked", 1, {"tvmaze_id": 44})], {})
    assert [row[1] for row in sp.grid["Tracked"][1:]] == ["", "44", "", "44"]


def test_write_appends_after_last_row_in_one_batch():
    sp = make_spreadsheet(Cards=[{"card_id": "a", "status": "noted"}])
    Sheet(sp).write([Update("Cards", "a", {"headline": "H"})], {"Cards": [{"card_id": "b", "current": True, "status": "new"}]})
    assert len(sp.batch_updates) == 1
    assert sp.batch_updates[0]["valueInputOption"] == "RAW"
    assert get_cell(sp, "Cards", "a", "headline") == "H"
    assert get_cell(sp, "Cards", "a", "status") == "noted"
    assert get_cell(sp, "Cards", "b", "current") == "TRUE"
    assert sp.grid["Cards"][2][0] == "b"


def test_write_with_nothing_to_do_makes_no_calls():
    sp = make_spreadsheet()
    Sheet(sp).write([], {"Cards": []})
    assert sp.batch_updates == []


def test_replace_clears_rows_beyond_the_new_length():
    sp = make_spreadsheet(Schedule=[{"tmdb_id": 1, "airstamp": "a"}, {"tmdb_id": 2, "airstamp": "b"}])
    Sheet(sp).replace("Schedule", [{"tmdb_id": 3, "airstamp": "c"}])
    rows = Sheet(sp).read_all()["Schedule"]
    assert [(r["tmdb_id"], r["airstamp"]) for r in rows] == [("3", "c")]


def test_replace_with_no_rows_leaves_only_the_header():
    sp = make_spreadsheet(Schedule=[{"tmdb_id": 1, "airstamp": "a"}])
    Sheet(sp).replace("Schedule", [])
    assert Sheet(sp).read_all()["Schedule"] == []


def test_ensure_tabs_creates_missing_tabs_and_writes_headers():
    sp = FakeSpreadsheet({"Tracked": []})
    assert Sheet(sp).ensure_tabs() == ["Cards", "Schedule", "Meta"]
    assert all(sp.grid[tab][0] == header for tab, header in HEADERS.items())

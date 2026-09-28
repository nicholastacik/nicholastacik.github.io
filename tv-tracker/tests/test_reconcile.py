from datetime import date

from job.reconcile import content_updates, reconcile_seasons
from job.sheet import Update

TODAY = date(2026, 9, 27)


def test_content_updates_only_changed_fields_of_existing_cards():
    existing = {"ep:1:S01E01": {"card_id": "ep:1:S01E01", "show_name": "One", "headline": "S01E01 · TBA", "date": "2026-09-27", "image_url": "i", "status": "noted"}}
    facts = [
        {"card_id": "ep:1:S01E01", "show_name": "One", "headline": "S01E01 · Pilot", "date": "2026-09-27", "image_url": "i"},
        {"card_id": "ep:1:S01E02", "show_name": "One", "headline": "new", "date": "2026-09-27", "image_url": "i"},
    ]
    assert content_updates(existing, facts, ("show_name", "headline", "date", "image_url")) == [
        Update("Cards", "ep:1:S01E01", {"headline": "S01E01 · Pilot"})
    ]


def season_card(date_, current="TRUE", status="new"):
    return {"card_id": f"season:1:2:{date_}", "current": current, "status": status}


def run(air_date, cards, seasons=None):
    data = {"seasons": seasons if seasons is not None else [{"season_number": 1, "air_date": "2025-01-01"}, {"season_number": 2, "air_date": air_date, "poster_path": "/s2.jpg"}]}
    return reconcile_seasons(1, "One", data, cards, TODAY, "poster", "T")


def test_announced_date_appends_current_card():
    appends, updates = run("2026-12-01", [])
    assert updates == []
    [card] = appends
    assert card["card_id"] == "season:1:2:2026-12-01"
    assert (card["type"], card["headline"], card["date"], card["current"], card["status"]) == ("season", "Season 2 premieres", "2026-12-01", True, "new")
    assert card["link"] == "https://www.themoviedb.org/tv/1/season/2"
    assert card["image_url"] == "https://image.tmdb.org/t/p/w342/s2.jpg"


def test_date_change_hides_old_and_appends_new():
    appends, updates = run("2026-12-15", [season_card("2026-12-01")])
    assert [c["card_id"] for c in appends] == ["season:1:2:2026-12-15"]
    assert updates == [Update("Cards", "season:1:2:2026-12-01", {"current": False})]


def test_date_changing_back_reactivates_original():
    cards = [season_card("2026-12-01", current="FALSE"), season_card("2026-12-15")]
    appends, updates = run("2026-12-01", cards)
    assert appends == []
    assert updates == [
        Update("Cards", "season:1:2:2026-12-01", {"current": True}),
        Update("Cards", "season:1:2:2026-12-15", {"current": False}),
    ]


def test_withdrawn_date_and_removed_season_hide_cards():
    _, updates = run(None, [season_card("2026-12-01")])
    assert updates == [Update("Cards", "season:1:2:2026-12-01", {"current": False})]
    _, updates = run("x", [season_card("2026-12-01")], seasons=[{"season_number": 1, "air_date": "2025-01-01"}])
    assert updates == [Update("Cards", "season:1:2:2026-12-01", {"current": False})]


def test_date_corrected_into_the_past_hides_card_without_appending():
    appends, updates = run("2026-09-26", [season_card("2026-09-30")])
    assert appends == []
    assert updates == [Update("Cards", "season:1:2:2026-09-30", {"current": False})]


def test_premiered_on_announced_date_stays_current_and_never_touches_status():
    appends, updates = run("2026-09-20", [season_card("2026-09-20", status="noted")])
    assert (appends, updates) == ([], [])


def test_show_not_yet_aired_gets_season_card():
    appends, _ = run("x", [], seasons=[{"season_number": 1, "air_date": "2026-11-01"}])
    assert [c["card_id"] for c in appends] == ["season:1:1:2026-11-01"]


def test_premiere_today_is_announced():
    appends, _ = run("2026-09-27", [])
    assert [c["card_id"] for c in appends] == ["season:1:2:2026-09-27"]

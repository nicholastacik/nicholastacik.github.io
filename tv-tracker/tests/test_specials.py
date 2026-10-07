from datetime import date, datetime

import pytest
from fakes import FakeTmdb, FakeTvmaze, make_spreadsheet
from job.config import TZ
from job.daily import run_daily
from job.sheet import Sheet
from job.specials import Special, merge_specials, slug, special_rows
from job.state import Show

NOW = datetime(2026, 10, 7, 6, 0, tzinfo=TZ)
LINKS = {1434: {"tvmaze_series": [80348]}}
HULU = {"name": "Family Guy Hulu Exclusives", "webChannel": {"name": "Hulu"}}


def hulu_episode(name, airdate, airstamp, **extra):
    return {
        "name": name,
        "season": 2026,
        "number": 1,
        "type": "regular",
        "airdate": airdate,
        "airstamp": airstamp,
        "airtime": "",
        "url": "https://www.tvmaze.com/episodes/1/x",
        **extra,
    }


HAPPY = hulu_episode(
    "Halloween Special 2026: Happy Hell-o-ween",
    "2026-10-05",
    "2026-10-05T16:00:00+00:00",
)


def parent_special(name, airdate, season=6):
    return {
        "name": name,
        "season": season,
        "number": None,
        "type": "significant_special",
        "airdate": airdate,
        "airstamp": None,
        "airtime": "",
        "url": "https://www.tvmaze.com/episodes/2/y",
    }


def tracked_row(added_at="2026-09-28"):
    return {
        "tmdb_id": 1434,
        "tvmaze_id": 84,
        "name": "Family Guy",
        "first_air_year": 1999,
        "poster_url": "",
        "added_at": added_at,
        "source": "import",
        "active": True,
    }


def guy_json(with_specials_season=True):
    seasons = [{"season_number": 24, "air_date": "2025-01-01"}]
    if with_specials_season:
        seasons.insert(0, {"season_number": 0})
    return {
        "id": 1434,
        "name": "Family Guy",
        "poster_path": "/fg.jpg",
        "external_ids": {"imdb_id": "tt0182576"},
        "seasons": seasons,
        "next_episode_to_air": None,
    }


def tmdb_special(name, air_date, number=30):
    return {
        "episodes": [
            {
                "season_number": 0,
                "episode_number": number,
                "name": name,
                "air_date": air_date,
                "still_path": None,
            }
        ]
    }


def world(
    *,
    cards=(),
    schedule=(),
    tvmaze_specials=None,
    hulu_episodes=(HAPPY,),
    tmdb_season0=None,
    broken=(),
    added_at="2026-09-28",
):
    sp = make_spreadsheet(
        Tracked=[tracked_row(added_at)], Cards=list(cards), Schedule=list(schedule)
    )
    tmdb = FakeTmdb(
        {1434: guy_json(with_specials_season=tmdb_season0 is not None)},
        {(1434, 0): tmdb_season0} if tmdb_season0 else {},
        broken=broken,
    )
    tvmaze = FakeTvmaze(
        {"tt0182576": 84},
        {84: {}, 80348: HULU},
        broken=broken,
        specials={84: tvmaze_specials or [], 80348: list(hulu_episodes)},
    )
    return sp, Sheet(sp), tmdb, tvmaze


def run(sheet, tmdb, tvmaze, links=LINKS, now=NOW):
    return run_daily(
        sheet, tmdb, tvmaze, None, lambda url: None, now, special_links=links
    )


def special_cards(sheet):
    return [c for c in sheet.read_all()["Cards"] if c["type"] == "special"]


def news_row(card_id, headline, day, status="new", body=""):
    return {
        "card_id": card_id,
        "type": "news",
        "tmdb_id": 1434,
        "show_name": "Family Guy",
        "headline": headline,
        "body": body,
        "date": day,
        "current": True,
        "status": status,
        "created_at": "2026-09-28T11:00:00-04:00",
    }


def test_separately_catalogued_special_gets_a_release_card_under_the_parent():
    _sp, sheet, tmdb, tvmaze = world()
    report = run(sheet, tmdb, tvmaze)
    assert report.ok
    [card] = special_cards(sheet)
    assert card["card_id"] == "special:1434:2026-10-05:happy-hell-o-ween"
    assert (card["tmdb_id"], card["show_name"]) == ("1434", "Family Guy")
    assert card["headline"] == "Halloween Special 2026: Happy Hell-o-ween"
    assert (card["date"], card["status"], card["current"]) == (
        "2026-10-05",
        "new",
        "TRUE",
    )
    assert card["link"] == "https://www.tvmaze.com/episodes/1/x"
    assert card["image_url"] == "https://image.tmdb.org/t/p/w342/fg.jpg"


def test_without_a_link_the_separate_series_is_not_discovered():
    _sp, sheet, tmdb, tvmaze = world()
    run(sheet, tmdb, tvmaze, links={})
    assert special_cards(sheet) == []


def test_season_zero_specials_on_tmdb_become_cards():
    _sp, sheet, tmdb, tvmaze = world(
        hulu_episodes=(), tmdb_season0=tmdb_special("Happy Hell-o-ween", "2026-10-05")
    )
    run(sheet, tmdb, tvmaze)
    [card] = special_cards(sheet)
    assert card["card_id"] == "special:1434:2026-10-05:happy-hell-o-ween"
    assert card["link"] == "https://www.themoviedb.org/tv/1434/season/0/episode/30"
    assert not any(c["type"] == "episode" for c in sheet.read_all()["Cards"])


def test_tvmaze_specials_attached_to_the_parent_become_cards():
    _sp, sheet, tmdb, tvmaze = world(
        hulu_episodes=(),
        tvmaze_specials=[
            parent_special("Old Clip Show", "2007-11-04"),
            parent_special("Family Guy Live", "2026-10-06", season=25),
        ],
    )
    run(sheet, tmdb, tvmaze)
    assert [c["headline"] for c in special_cards(sheet)] == ["Family Guy Live"]


def test_provider_overlap_yields_one_card_even_with_different_titles():
    _sp, sheet, tmdb, tvmaze = world(
        tmdb_season0=tmdb_special("Happy Hell-o-ween", "2026-10-05")
    )
    run(sheet, tmdb, tvmaze)
    assert len(special_cards(sheet)) == 1


def test_repeated_runs_and_a_late_second_provider_do_not_duplicate():
    _sp, sheet, tmdb, tvmaze = world()
    run(sheet, tmdb, tvmaze)
    assert run(sheet, tmdb, tvmaze).appended == 0
    tmdb.shows[1434] = guy_json()
    tmdb.seasons[(1434, 0)] = tmdb_special("A Different Title", "2026-10-05")
    run(sheet, tmdb, tvmaze)
    assert len(special_cards(sheet)) == 1


def test_announcement_news_does_not_suppress_the_release_card_and_is_preserved():
    trailer = news_row(
        "news:1434:2edddad4",
        "Family Guy releases trailer for 2026 Halloween special",
        "2026-09-26",
        status="noted",
        body="The trailer for “Happy Hell-o-ween” sends Brian and Stewie to Hell",
    )
    _sp, sheet, tmdb, tvmaze = world(cards=[trailer])
    run(sheet, tmdb, tvmaze)
    cards = {c["card_id"]: c for c in sheet.read_all()["Cards"]}
    assert "special:1434:2026-10-05:happy-hell-o-ween" in cards
    assert cards["news:1434:2edddad4"]["status"] == "noted"
    assert cards["news:1434:2edddad4"]["current"] == "TRUE"


def test_existing_available_now_news_card_prevents_a_duplicate_release_card():
    manual = news_row(
        "news:1434:2026-10-05:happy-helloween-is-now-available",
        "Happy Hell-o-ween is now available",
        "2026-10-05",
    )
    _sp, sheet, tmdb, tvmaze = world(cards=[manual])
    report = run(sheet, tmdb, tvmaze)
    assert special_cards(sheet) == []
    assert report.appended == 0


def test_future_and_unknown_dates_make_no_card_but_upcoming_ones_are_scheduled():
    soon = hulu_episode(
        "Holiday Special 2026: Soon", "2026-10-10", "2026-10-10T17:00:00+00:00"
    )
    undated = hulu_episode("Holiday Special 2026: TBA", None, None)
    far = hulu_episode(
        "Holiday Special 2026: Far", "2026-12-25", "2026-12-25T17:00:00+00:00"
    )
    _sp, sheet, tmdb, tvmaze = world(hulu_episodes=(soon, undated, far))
    run(sheet, tmdb, tvmaze)
    assert special_cards(sheet) == []
    schedule = sheet.read_all()["Schedule"]
    assert [
        (r["airstamp"], r["tmdb_id"], r["show_name"], r["network"]) for r in schedule
    ] == [("2026-10-10", "1434", "Family Guy", "Hulu")]
    assert schedule[0]["episode_label"] == "Special · Holiday Special 2026: Soon"


def test_a_special_that_just_aired_is_scheduled_in_eastern_time():
    timed = hulu_episode(
        "Holiday Special 2026: Timed",
        "2026-10-09",
        "2026-10-09T17:00:00+00:00",
        airtime="13:00",
    )
    _sp, sheet, tmdb, tvmaze = world(hulu_episodes=(HAPPY, timed))
    run(sheet, tmdb, tvmaze)
    assert [r["airstamp"] for r in sheet.read_all()["Schedule"]] == [
        "2026-10-05",
        "2026-10-09T13:00-04:00",
    ]


def test_unnumbered_specials_with_the_same_season_do_not_collide():
    _sp, sheet, tmdb, tvmaze = world(
        hulu_episodes=(),
        tvmaze_specials=[
            parent_special("Special A", "2026-10-05", season=25),
            parent_special("Special B", "2026-10-05", season=25),
            parent_special("Special A", "2026-10-06", season=25),
        ],
    )
    run(sheet, tmdb, tvmaze)
    assert sorted(c["card_id"] for c in special_cards(sheet)) == [
        "special:1434:2026-10-05:special-a",
        "special:1434:2026-10-05:special-b",
        "special:1434:2026-10-06:special-a",
    ]
    assert run(sheet, tmdb, tvmaze).appended == 0


def test_specials_before_the_grace_window_of_a_new_show_are_not_carded():
    older = hulu_episode(
        "Holiday Special 2026: Old", "2026-10-01", "2026-10-01T16:00:00+00:00"
    )
    _sp, sheet, tmdb, tvmaze = world(added_at="2026-10-06", hulu_episodes=(older,))
    run(sheet, tmdb, tvmaze)
    assert special_cards(sheet) == []


def test_one_failing_source_is_reported_and_the_others_still_work():
    _sp, sheet, tmdb, tvmaze = world(
        tmdb_season0=tmdb_special("Happy Hell-o-ween", "2026-10-05"),
        broken={("specials", 80348)},
    )
    report = run(sheet, tmdb, tvmaze)
    assert not report.ok
    assert report.failed_steps == ["specials:1434:tvmaze:80348"]
    assert report.failed_shows == []
    assert len(special_cards(sheet)) == 1


def test_season_zero_failure_is_reported_and_isolated():
    _sp, sheet, tmdb, tvmaze = world(
        tmdb_season0=tmdb_special("Happy Hell-o-ween", "2026-10-05"),
        broken={(1434, 0, "season")},
    )
    report = run(sheet, tmdb, tvmaze)
    assert report.failed_steps == ["specials:1434:tmdb"]
    assert [c["card_id"] for c in special_cards(sheet)] == [
        "special:1434:2026-10-05:happy-hell-o-ween"
    ]


def test_failed_discovery_keeps_the_previous_special_schedule_rows():
    previous = {
        "tmdb_id": 1434,
        "airstamp": "2026-10-10",
        "show_name": "Family Guy",
        "episode_label": "Special · Holiday Special 2026: Soon",
        "network": "Hulu",
        "link": "https://x",
    }
    _sp, sheet, tmdb, tvmaze = world(
        schedule=[previous], hulu_episodes=(), broken={("specials", 80348)}
    )
    run(sheet, tmdb, tvmaze)
    assert [r["episode_label"] for r in sheet.read_all()["Schedule"]] == [
        "Special · Holiday Special 2026: Soon"
    ]


def test_link_to_an_unrelated_series_is_refused():
    _sp, sheet, tmdb, tvmaze = world()
    tvmaze.shows[80348] = {"name": "Some Other Show"}
    report = run(sheet, tmdb, tvmaze)
    assert special_cards(sheet) == []
    assert report.failed_steps == ["specials:1434:tvmaze:80348"]


def test_linked_film_becomes_a_special_card():
    _sp, sheet, tmdb, tvmaze = world(hulu_episodes=())
    tmdb.shows[("movie", 55)] = {
        "title": "Family Guy: The Movie",
        "release_date": "2026-10-06",
        "poster_path": "/m.jpg",
    }
    run(sheet, tmdb, tvmaze, links={1434: {"tmdb_movies": [55]}})
    [card] = special_cards(sheet)
    assert card["card_id"] == "special:1434:2026-10-06:the-movie"
    assert card["link"] == "https://www.themoviedb.org/movie/55"


def test_merge_keeps_same_titled_specials_from_different_dates_apart():
    a = Special("Holiday Special", date(2025, 12, 1), "tvmaze")
    b = Special("Holiday Special", date(2026, 12, 1), "tvmaze")
    assert len(merge_specials([a, b])) == 2
    undated = Special("Holiday Special", None, "tmdb", link="https://x")
    merged = merge_specials(
        [Special("Holiday Special", date(2026, 12, 1), "tvmaze"), undated]
    )
    assert [(m.date, m.link) for m in merged] == [(date(2026, 12, 1), "https://x")]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Halloween Special 2026: Happy Hell-o-ween", "happy-hell-o-ween"),
        ("Gift of the White Guy", "gift-of-the-white-guy"),
        ("", "untitled"),
        ("Café Noël", "cafe-noel"),
    ],
)
def test_slug(title, expected):
    assert slug(title) == expected


def test_special_rows_skip_rows_the_schedule_already_has():
    show = Show(1434, "Family Guy", 1999, "", date(2026, 9, 28), 84)
    existing = [
        {"airstamp": "2026-10-08T21:00-04:00", "episode_label": "S25E03 · Same Name"}
    ]
    special = Special(
        "Same Name", date(2026, 10, 8), "tmdb", airstamp="2026-10-09T01:00:00+00:00"
    )
    assert special_rows(show, [special], existing, date(2026, 10, 7), "now", "") == []

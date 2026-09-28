from datetime import date

from job.schedule import in_window, merge_schedule, schedule_rows, window_start
from job.state import Show

TODAY = date(2026, 9, 30)  # window is 09-28 .. 10-07
SHOW = Show(1, "One", 2020, "https://poster", date(2026, 9, 1), 11)


def ep(season, number, airstamp, airtime="21:00", name="Ep", image=None):
    return {
        "season": season,
        "number": number,
        "name": name,
        "airstamp": airstamp,
        "airtime": airtime,
        "image": image,
    }


def tv(*episodes, network="FX", web=None):
    return {
        "network": {"name": network} if network else None,
        "webChannel": {"name": web} if web else None,
        "image": {"medium": "https://tvm"},
        "_embedded": {"episodes": list(episodes)},
    }


def test_window_is_two_days_back_through_seven_ahead():
    assert window_start(TODAY) == date(2026, 9, 28)
    assert in_window("2026-09-28", TODAY) and in_window("2026-10-07T23:30-04:00", TODAY)
    assert not in_window("2026-09-27", TODAY) and not in_window("2026-10-08", TODAY)


def test_rows_in_toronto_week_with_times_and_labels():
    show_json = tv(
        ep(1, 1, "2026-09-28T01:00:00+00:00"),  # Sun 09-27 21:00 local: last week
        ep(1, 2, "2026-09-29T01:00:00+00:00", name="Two"),  # Mon 09-28 21:00
        ep(1, 3, "2026-10-05T01:00:00+00:00"),  # Sun 10-04 21:00: in window
        ep(1, 5, "2026-10-09T01:00:00+00:00"),  # Thu 10-08 21:00: past the window
        ep(1, 4, None),
    )
    rows = schedule_rows(SHOW, show_json, {}, TODAY, "T")
    assert [(r["airstamp"], r["episode_label"]) for r in rows] == [
        ("2026-09-28T21:00-04:00", "S01E02 · Two"),
        ("2026-10-04T21:00-04:00", "S01E03 · Ep"),
    ]
    assert rows[0] == {
        "tmdb_id": 1,
        "airstamp": "2026-09-28T21:00-04:00",
        "show_name": "One",
        "episode_label": "S01E02 · Two",
        "network": "FX",
        "image_url": "https://tvm",
        "refreshed_at": "T",
        "link": "",
    }


def test_streaming_without_airtime_is_date_only_and_uses_web_channel():
    rows = schedule_rows(
        SHOW,
        tv(
            ep(6, 1, "2026-09-30T12:00:00+00:00", airtime=""),
            network=None,
            web="Apple TV",
        ),
        {},
        TODAY,
        "T",
    )
    assert [(r["airstamp"], r["network"]) for r in rows] == [("2026-09-30", "Apple TV")]


def test_special_with_no_number():
    rows = schedule_rows(
        SHOW,
        tv(ep(3, None, "2026-10-01T01:00:00+00:00", name="Halloween")),
        {},
        TODAY,
        "T",
    )
    assert rows[0]["episode_label"] == "S03 special · Halloween"


def test_tmdb_fallback_when_tvmaze_has_nothing_this_week():
    tmdb = {
        "poster_path": "/p.jpg",
        "networks": [{"name": "Cartoon Network"}],
        "next_episode_to_air": {
            "air_date": "2026-10-03",
            "season_number": 1,
            "episode_number": 7,
            "name": "Special",
        },
    }
    rows = schedule_rows(SHOW, {}, tmdb, TODAY, "T")
    assert [
        (r["airstamp"], r["episode_label"], r["network"], r["image_url"]) for r in rows
    ] == [
        (
            "2026-10-03",
            "S01E07 · Special",
            "Cartoon Network",
            "https://image.tmdb.org/t/p/w342/p.jpg",
        )
    ]
    later = {
        "next_episode_to_air": {
            "air_date": "2026-10-10",
            "season_number": 1,
            "episode_number": 7,
            "name": "x",
        }
    }
    assert schedule_rows(SHOW, {}, later, TODAY, "T") == []


def test_no_tmdb_fallback_when_tvmaze_has_rows():
    tmdb = {
        "next_episode_to_air": {
            "air_date": "2026-10-03",
            "season_number": 1,
            "episode_number": 7,
            "name": "x",
        }
    }
    rows = schedule_rows(
        SHOW, tv(ep(1, 6, "2026-09-29T01:00:00+00:00")), tmdb, TODAY, "T"
    )
    assert len(rows) == 1


def test_merge_carries_failed_shows_in_window_and_sorts():
    fresh = {1: [{"tmdb_id": 1, "airstamp": "2026-10-01T21:00-04:00"}]}
    previous = [
        {"tmdb_id": "2", "airstamp": "2026-09-29", "show_name": "Two", "_row": 2},
        {"tmdb_id": "2", "airstamp": "2026-09-21", "show_name": "Two", "_row": 3},
        {"tmdb_id": "1", "airstamp": "2026-09-30", "show_name": "One", "_row": 4},
        {"tmdb_id": "3", "airstamp": "2026-09-30", "show_name": "Gone", "_row": 5},
    ]
    merged = merge_schedule(fresh, {2}, previous, TODAY)
    assert merged == [
        {"tmdb_id": "2", "airstamp": "2026-09-29", "show_name": "Two"},
        {"tmdb_id": 1, "airstamp": "2026-10-01T21:00-04:00"},
    ]


def test_rows_get_links_from_the_lookup_by_season_and_episode():
    seen = []

    def link_for(season, number, airdate):
        seen.append((season, number))
        return f"https://www.imdb.com/title/tt{season}{number or 0}/"

    show_json = tv(
        ep(1, 2, "2026-09-29T01:00:00+00:00"), ep(3, None, "2026-10-01T01:00:00+00:00")
    )
    rows = schedule_rows(SHOW, show_json, {}, TODAY, "T", link_for)
    assert [r["link"] for r in rows] == [
        "https://www.imdb.com/title/tt12/",
        "https://www.imdb.com/title/tt30/",
    ]
    assert seen == [(1, 2), (3, None)]
    tmdb = {
        "next_episode_to_air": {
            "air_date": "2026-10-03",
            "season_number": 1,
            "episode_number": 7,
            "name": "x",
        }
    }
    assert (
        schedule_rows(SHOW, {}, tmdb, TODAY, "T", link_for)[0]["link"]
        == "https://www.imdb.com/title/tt17/"
    )

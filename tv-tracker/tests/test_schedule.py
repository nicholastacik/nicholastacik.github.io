from datetime import date

from job.schedule import in_week, merge_schedule, schedule_rows, week_start
from job.state import Show

TODAY = date(2026, 9, 30)  # Wednesday; week is Mon 09-28 .. Sun 10-04
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


def test_week_bounds():
    assert week_start(TODAY) == date(2026, 9, 28)
    assert week_start(date(2026, 9, 28)) == date(2026, 9, 28)
    assert in_week("2026-09-28", TODAY) and in_week("2026-10-04T23:30-04:00", TODAY)
    assert not in_week("2026-09-27", TODAY) and not in_week("2026-10-05", TODAY)


def test_rows_in_toronto_week_with_times_and_labels():
    show_json = tv(
        ep(1, 1, "2026-09-28T01:00:00+00:00"),  # Sun 09-27 21:00 local: last week
        ep(1, 2, "2026-09-29T01:00:00+00:00", name="Two"),  # Mon 09-28 21:00
        ep(1, 3, "2026-10-05T01:00:00+00:00"),  # Sun 10-04 21:00: this week
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


def test_merge_carries_failed_shows_in_week_and_sorts():
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

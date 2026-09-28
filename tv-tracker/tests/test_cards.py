from datetime import date

from job.cards import episode_facts, episode_link, new_card, seasons_to_fetch
from job.state import Show

SHOW = Show(1, "One", 2020, "https://poster", date(2026, 9, 20), None)
SEASONS = [
    {"season_number": 0, "air_date": "2019-01-01"},
    {"season_number": 1, "air_date": "2025-01-10"},
    {"season_number": 2, "air_date": "2026-08-01"},
    {"season_number": 3, "air_date": "2026-09-25"},
    {"season_number": 4, "air_date": "2027-01-01"},
    {"season_number": 5, "air_date": None},
]


def test_seasons_from_the_one_current_at_tracking_through_latest_aired():
    assert seasons_to_fetch(
        {"seasons": SEASONS}, date(2026, 9, 20), date(2026, 9, 28)
    ) == [2, 3]


def test_seasons_when_tracked_before_any_premiere_start_at_first_aired():
    assert seasons_to_fetch(
        {"seasons": SEASONS}, date(2020, 1, 1), date(2026, 9, 28)
    ) == [1, 2, 3]


def test_seasons_for_a_show_that_has_never_aired():
    assert (
        seasons_to_fetch(
            {"seasons": [{"season_number": 1, "air_date": "2027-01-01"}]},
            date(2026, 9, 20),
            date(2026, 9, 28),
        )
        == []
    )
    assert seasons_to_fetch({}, date(2026, 9, 20), date(2026, 9, 28)) == []


def test_seasons_capped_at_nineteen_most_recent():
    many = [{"season_number": n, "air_date": f"{2000 + n}-01-01"} for n in range(1, 25)]
    assert seasons_to_fetch(
        {"seasons": many}, date(1990, 1, 1), date(2026, 9, 28)
    ) == list(range(6, 25))


def episode(season, number, air_date, name="Ep", still=None):
    return {
        "season_number": season,
        "episode_number": number,
        "air_date": air_date,
        "name": name,
        "still_path": still,
    }


def test_episode_facts_window_is_inclusive_and_builds_fields():
    data = {
        "name": "One (TMDB)",
        "poster_path": "/p.jpg",
        "season/3": {
            "episodes": [
                episode(3, 1, "2026-09-17"),
                episode(3, 2, "2026-09-20", "Two", "/s.jpg"),
                episode(3, 3, "2026-09-28", "TBA"),
                episode(3, 4, "2026-09-29"),
                episode(3, 5, None),
            ]
        },
    }
    facts = episode_facts(SHOW, data, date(2026, 9, 28))
    assert [f["card_id"] for f in facts] == ["ep:1:S03E02", "ep:1:S03E03"]
    first = facts[0]
    assert first["headline"] == "S03E02 · Two"
    assert first["show_name"] == "One (TMDB)"
    assert first["image_url"] == "https://image.tmdb.org/t/p/w342/s.jpg"
    assert facts[1]["image_url"] == "https://image.tmdb.org/t/p/w342/p.jpg"
    assert (
        first["type"],
        first["tmdb_id"],
        first["date"],
        first["season"],
        first["episode"],
    ) == ("episode", 1, "2026-09-20", 3, 2)


def test_episode_facts_falls_back_to_tracked_name_and_poster():
    data = {"season/1": {"episodes": [episode(1, 1, "2026-09-21", name="")]}}
    [fact] = episode_facts(SHOW, data, date(2026, 9, 28))
    assert (fact["show_name"], fact["image_url"], fact["headline"]) == (
        "One",
        "https://poster",
        "S01E01 · TBA",
    )


def test_new_card_defaults():
    card = new_card(now="T", card_id="x", type="news", headline="h")
    assert card == {
        "body": "",
        "link": "",
        "image_url": "",
        "source_url": "",
        "card_id": "x",
        "type": "news",
        "headline": "h",
        "created_at": "T",
        "current": True,
        "status": "new",
        "updated_at": "T",
    }


def test_episode_link_prefers_episode_then_imdb_season_list_then_tmdb():
    assert (
        episode_link(lambda *a: "tt9", 1, "tt1", 3, 2)
        == "https://www.imdb.com/title/tt9/"
    )
    assert (
        episode_link(lambda *a: None, 1, "tt1", 3, 2)
        == "https://www.imdb.com/title/tt1/episodes/?season=3"
    )
    assert (
        episode_link(lambda *a: None, 1, None, 3, 2)
        == "https://www.themoviedb.org/tv/1/season/3/episode/2"
    )


def test_episodes_up_to_two_days_before_tracking_still_get_cards():
    data = {
        "season/3": {
            "episodes": [
                episode(3, 1, "2026-09-17"),
                episode(3, 2, "2026-09-18"),
                episode(3, 3, "2026-09-19"),
            ]
        }
    }
    assert [f["card_id"] for f in episode_facts(SHOW, data, date(2026, 9, 28))] == [
        "ep:1:S03E02",
        "ep:1:S03E03",
    ]

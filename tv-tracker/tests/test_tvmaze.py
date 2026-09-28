from datetime import UTC, datetime

import httpx
from job.tvmaze import Tvmaze, next_airing


def test_lookup_follows_redirect_to_show():
    def handler(request):
        if request.url.path == "/lookup/shows":
            assert request.url.params["imdb"] == "tt11280740"
            return httpx.Response(
                301, headers={"Location": "https://api.tvmaze.com/shows/44933"}
            )
        return httpx.Response(200, json={"id": 44933})

    assert (
        Tvmaze(transport=httpx.MockTransport(handler)).lookup_imdb("tt11280740")
        == 44933
    )


def test_lookup_missing_show_returns_none():
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    assert Tvmaze(transport=transport).lookup_imdb("tt0") is None


def test_episodes():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=[{"id": 1}])
    )
    assert Tvmaze(transport=transport).episodes(44933) == [{"id": 1}]


def test_next_airing_picks_earliest_future_episode():
    now = datetime(2026, 9, 27, 12, tzinfo=UTC)
    episodes = [
        {"id": 1, "airstamp": "2026-09-20T02:00:00+00:00"},
        {"id": 3, "airstamp": "2026-10-04T02:00:00+00:00"},
        {"id": 2, "airstamp": "2026-09-28T02:00:00+00:00"},
        {"id": 4, "airstamp": None},
    ]
    assert next_airing(episodes, now)["id"] == 2


def test_next_airing_none_when_nothing_upcoming():
    now = datetime(2026, 9, 27, 12, tzinfo=UTC)
    assert (
        next_airing([{"id": 1, "airstamp": "2026-09-20T02:00:00+00:00"}], now) is None
    )


def test_eastern_converts_utc_airstamp_to_toronto_time():
    from job.tvmaze import eastern

    assert eastern("2026-09-29T01:00:00+00:00") == "2026-09-28 21:00 EDT"
    assert eastern("2026-12-08T17:00:00+00:00") == "2026-12-08 12:00 EST"


def test_show_with_episodes_embeds_episodes():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": 5, "_embedded": {"episodes": []}})

    assert Tvmaze(transport=httpx.MockTransport(handler)).show_with_episodes(5)["id"] == 5
    assert seen[0].url.path == "/shows/5"
    assert seen[0].url.params["embed"] == "episodes"

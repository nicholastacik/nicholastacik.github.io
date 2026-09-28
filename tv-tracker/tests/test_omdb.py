import httpx
from job.omdb import Omdb

SEASON = {
    "Title": "The Simpsons",
    "Season": "38",
    "Response": "True",
    "Episodes": [
        {
            "Title": "The Children's Book Job",
            "Released": "2026-09-27",
            "Episode": "1",
            "imdbID": "tt36414313",
        },
        {
            "Title": "Diary of a Chimpy Kid",
            "Released": "2026-10-04",
            "Episode": "2",
            "imdbID": "tt36414314",
        },
        {
            "Title": "Double A",
            "Released": "2026-10-11",
            "Episode": "3",
            "imdbID": "tt300",
        },
        {
            "Title": "Double B",
            "Released": "2026-10-11",
            "Episode": "4",
            "imdbID": "tt400",
        },
        {
            "Title": "No page yet",
            "Released": "2026-10-18",
            "Episode": "5",
            "imdbID": "N/A",
        },
    ],
}


def omdb(body, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=body)

    return Omdb("KEY", transport=httpx.MockTransport(handler))


def test_matches_by_release_date_and_sends_key_show_and_season():
    seen = []
    client = omdb(SEASON, seen)
    assert client.episode_imdb("tt0096697", 38, "2026-09-27", 1) == "tt36414313"
    params = seen[0].url.params
    assert (params["apikey"], params["i"], params["Season"]) == (
        "KEY",
        "tt0096697",
        "38",
    )


def test_same_day_episodes_use_the_number_and_ambiguity_is_none():
    client = omdb(SEASON)
    assert client.episode_imdb("tt0096697", 38, "2026-10-11", 4) == "tt400"
    assert client.episode_imdb("tt0096697", 38, "2026-10-11", None) is None


def test_missing_ids_errors_and_no_match_are_none():
    assert omdb(SEASON).episode_imdb("tt0096697", 38, "2026-10-18", 5) is None
    assert omdb(SEASON).episode_imdb("tt0096697", 38, "2027-01-01", 9) is None
    assert (
        omdb(
            {"Response": "False", "Error": "Series or season not found!"}
        ).episode_imdb("tt1", 1, "2026-09-27", 1)
        is None
    )
    broken = Omdb("KEY", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert broken.episode_imdb("tt1", 1, "2026-09-27", 1) is None


def test_each_season_is_fetched_once_per_run():
    seen = []
    client = omdb(SEASON, seen)
    client.episode_imdb("tt0096697", 38, "2026-09-27", 1)
    client.episode_imdb("tt0096697", 38, "2026-10-04", 2)
    assert len(seen) == 1

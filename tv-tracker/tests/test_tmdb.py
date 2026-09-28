import httpx
from job.tmdb import Tmdb, image_url


def recording(json_body):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=json_body)

    return httpx.MockTransport(handler), seen


def test_show_appends_external_ids_and_seasons():
    transport, seen = recording({"id": 95396})
    tmdb = Tmdb("tok", transport=transport)
    assert tmdb.show(95396, seasons=[1, 2]) == {"id": 95396}
    request = seen[0]
    assert request.url.path == "/3/tv/95396"
    assert request.url.params["append_to_response"] == "external_ids,season/1,season/2"
    assert request.headers["authorization"] == "Bearer tok"


def test_show_without_seasons_only_appends_external_ids():
    transport, seen = recording({"id": 1})
    Tmdb("tok", transport=transport).show(1)
    assert seen[0].url.params["append_to_response"] == "external_ids"


def test_search_returns_results_list():
    transport, seen = recording({"results": [{"id": 7, "name": "Shōgun"}]})
    assert Tmdb("tok", transport=transport).search("Shōgun") == [
        {"id": 7, "name": "Shōgun"}
    ]
    assert seen[0].url.path == "/3/search/tv"
    assert seen[0].url.params["query"] == "Shōgun"


def test_image_url():
    assert image_url("/abc.jpg") == "https://image.tmdb.org/t/p/w342/abc.jpg"
    assert image_url(None) == ""
    assert image_url("") == ""


def test_episode_imdb():
    transport, seen = recording({"imdb_id": "tt9"})
    assert Tmdb("tok", transport=transport).episode_imdb(1, 2, 3) == "tt9"
    assert seen[0].url.path == "/3/tv/1/season/2/episode/3/external_ids"


def test_episode_imdb_missing_episode_is_none():
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    assert Tmdb("tok", transport=transport).episode_imdb(1, 9, 99) is None

from collections.abc import Iterable

import httpx

from job.http import get_json

BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w342"


def image_url(path: str | None) -> str:
    return f"{IMAGE_BASE}{path}" if path else ""


class Tmdb:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            base_url=BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            transport=transport,
        )

    def show(self, tmdb_id: int, seasons: Iterable[int] = ()) -> dict:
        parts = ["external_ids", *(f"season/{n}" for n in seasons)]
        return get_json(
            self.client, f"/tv/{tmdb_id}", {"append_to_response": ",".join(parts)}
        )

    def season(self, tmdb_id: int, number: int) -> dict:
        return get_json(self.client, f"/tv/{tmdb_id}/season/{number}")

    def movie(self, tmdb_id: int) -> dict:
        return get_json(self.client, f"/movie/{tmdb_id}")

    def search(self, title: str) -> list[dict]:
        return get_json(self.client, "/search/tv", {"query": title})["results"]

    def episode_imdb(self, tmdb_id: int, season: int, episode: int) -> str | None:
        path = f"/tv/{tmdb_id}/season/{season}/episode/{episode}/external_ids"
        try:
            return get_json(self.client, path).get("imdb_id")
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                return None
            raise

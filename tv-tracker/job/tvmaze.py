from datetime import datetime

import httpx

from job.config import TZ
from job.http import get_json

BASE = "https://api.tvmaze.com"


class Tvmaze:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            base_url=BASE, timeout=10, follow_redirects=True, transport=transport
        )

    def lookup_imdb(self, imdb_id: str) -> int | None:
        try:
            return get_json(self.client, "/lookup/shows", {"imdb": imdb_id})["id"]
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                return None
            raise

    def episodes(self, tvmaze_id: int) -> list[dict]:
        return get_json(self.client, f"/shows/{tvmaze_id}/episodes")


def next_airing(episodes: list[dict], now: datetime) -> dict | None:
    upcoming = [
        (datetime.fromisoformat(e["airstamp"]), e)
        for e in episodes
        if e.get("airstamp") and datetime.fromisoformat(e["airstamp"]) >= now
    ]
    return min(upcoming, key=lambda pair: pair[0], default=(None, None))[1]


def eastern(airstamp: str) -> str:
    return datetime.fromisoformat(airstamp).astimezone(TZ).strftime("%Y-%m-%d %H:%M %Z")

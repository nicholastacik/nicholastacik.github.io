import httpx

from job.http import get_json

BASE = "https://www.omdbapi.com/"


class Omdb:
    def __init__(self, key: str, transport: httpx.BaseTransport | None = None):
        self.key = key
        self.client = httpx.Client(timeout=10, transport=transport)
        self.seasons: dict[tuple[str, int], list[dict]] = {}

    def _season(self, show_imdb: str, season: int) -> list[dict]:
        if (show_imdb, season) not in self.seasons:
            try:
                data = get_json(
                    self.client,
                    BASE,
                    {"apikey": self.key, "i": show_imdb, "Season": season},
                    tries=1,
                )
            except httpx.HTTPError:
                data = {}
            self.seasons[(show_imdb, season)] = (
                data.get("Episodes", []) if data.get("Response") == "True" else []
            )
        return self.seasons[(show_imdb, season)]

    def episode_imdb(
        self, show_imdb: str, season: int, airdate: str, number: int | None
    ) -> str | None:
        same_day = [
            e for e in self._season(show_imdb, season) if e.get("Released") == airdate
        ]
        match = next((e for e in same_day if e.get("Episode") == str(number)), None)
        if match is None and len(same_day) == 1:
            match = same_day[0]
        imdb_id = (match or {}).get("imdbID", "")
        return imdb_id if imdb_id.startswith("tt") else None

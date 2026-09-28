from dataclasses import dataclass
from datetime import date


def truthy(value) -> bool:
    return str(value).strip().upper() == "TRUE"


@dataclass
class Show:
    tmdb_id: int
    name: str
    first_air_year: int | None
    poster_url: str
    added_at: date
    tvmaze_id: int | None


def _int(value: str) -> int | None:
    return int(value) if str(value).strip().isdigit() else None


def active_shows(rows: list[dict]) -> list[Show]:
    shows: dict[int, Show] = {}
    for row in rows:
        tmdb_id = _int(row["tmdb_id"])
        if not truthy(row["active"]) or tmdb_id is None:
            continue
        try:
            added_at = date.fromisoformat(row["added_at"])
        except ValueError:
            continue
        tvmaze_id = _int(row["tvmaze_id"])
        show = shows.get(tmdb_id)
        if show is None:
            shows[tmdb_id] = Show(
                tmdb_id,
                row["name"],
                _int(row["first_air_year"]),
                row["poster_url"],
                added_at,
                tvmaze_id,
            )
        else:
            show.added_at = min(show.added_at, added_at)
            show.tvmaze_id = show.tvmaze_id or tvmaze_id
    return list(shows.values())


def all_tracked_ids(rows: list[dict]) -> set[int]:
    return {tmdb_id for row in rows if (tmdb_id := _int(row["tmdb_id"])) is not None}

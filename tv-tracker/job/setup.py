from datetime import datetime

from job.state import all_tracked_ids
from job.tmdb import image_url


def import_rows(
    tracked: list[dict], existing_rows: list[dict], tmdb, now: datetime
) -> list[dict]:
    have = all_tracked_ids(existing_rows)
    stamp = now.isoformat(timespec="seconds")
    rows = []
    for show in tracked:
        if show["tmdb_id"] in have:
            continue
        data = tmdb.show(show["tmdb_id"])
        rows.append(
            {
                "tmdb_id": show["tmdb_id"],
                "tvmaze_id": "",
                "name": show["name"],
                "first_air_year": show["first_air_year"],
                "poster_url": image_url(data.get("poster_path")),
                "added_at": now.date().isoformat(),
                "source": "import",
                "active": True,
                "updated_at": stamp,
            }
        )
        have.add(show["tmdb_id"])
    return rows

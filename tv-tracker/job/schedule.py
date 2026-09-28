from datetime import date, datetime, timedelta

from job.config import TZ
from job.state import Show
from job.tmdb import image_url

DAYS_BACK = 2
DAYS_AHEAD = 7


def window_start(today: date) -> date:
    return today - timedelta(days=DAYS_BACK)


def in_window(stamp: str, today: date) -> bool:
    day = date.fromisoformat(stamp[:10])
    return window_start(today) <= day <= today + timedelta(days=DAYS_AHEAD)


def _label(season: int, number: int | None, name: str | None) -> str:
    code = f"S{season:02}E{number:02}" if number else f"S{season:02} special"
    return f"{code} · {name}" if name else code


def _row(
    show: Show, airstamp: str, label: str, network: str, image: str, now: str
) -> dict:
    return {
        "tmdb_id": show.tmdb_id,
        "airstamp": airstamp,
        "show_name": show.name,
        "episode_label": label,
        "network": network,
        "image_url": image,
        "refreshed_at": now,
    }


def schedule_rows(
    show: Show, tvmaze_show: dict, tmdb_data: dict, today: date, now: str
) -> list[dict]:
    network = (tvmaze_show.get("network") or tvmaze_show.get("webChannel") or {}).get(
        "name", ""
    )
    show_image = (
        (tvmaze_show.get("image") or {}).get("medium")
        or image_url(tmdb_data.get("poster_path"))
        or show.poster_url
    )
    rows = []
    for episode in tvmaze_show.get("_embedded", {}).get("episodes", []):
        if not episode.get("airstamp"):
            continue
        local = datetime.fromisoformat(episode["airstamp"]).astimezone(TZ)
        stamp = (
            local.isoformat(timespec="minutes")
            if episode.get("airtime")
            else local.date().isoformat()
        )
        if in_window(stamp, today):
            image = (episode.get("image") or {}).get("medium") or show_image
            label = _label(
                episode["season"], episode.get("number"), episode.get("name")
            )
            rows.append(_row(show, stamp, label, network, image, now))

    upcoming = tmdb_data.get("next_episode_to_air") or {}
    if not rows and upcoming.get("air_date") and in_window(upcoming["air_date"], today):
        tmdb_network = (tmdb_data.get("networks") or [{}])[0].get("name", "")
        label = _label(
            upcoming["season_number"],
            upcoming.get("episode_number"),
            upcoming.get("name"),
        )
        image = image_url(upcoming.get("still_path")) or show_image
        rows.append(
            _row(show, upcoming["air_date"], label, network or tmdb_network, image, now)
        )
    return rows


def merge_schedule(
    fresh: dict[int, list[dict]], failed: set[int], previous: list[dict], today: date
) -> list[dict]:
    carried = [
        {key: value for key, value in row.items() if key != "_row"}
        for row in previous
        if row["tmdb_id"].isdigit()
        and int(row["tmdb_id"]) in failed
        and row["airstamp"]
        and in_window(row["airstamp"], today)
    ]
    rows = [row for show_rows in fresh.values() for row in show_rows] + carried
    return sorted(rows, key=lambda row: row["airstamp"])

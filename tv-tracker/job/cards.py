from datetime import date, timedelta

from job.schedule import DAYS_BACK
from job.state import Show
from job.tmdb import image_url

EPISODE_CONTENT = ("show_name", "headline", "date", "image_url")
MAX_SEASONS = 19


def parse_date(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def new_card(*, now: str, **fields) -> dict:
    return {
        "body": "",
        "link": "",
        "image_url": "",
        "source_url": "",
        **fields,
        "created_at": now,
        "current": True,
        "status": "new",
        "updated_at": now,
    }


def seasons_to_fetch(data: dict, added_at: date, today: date) -> list[int]:
    aired = []
    for season in data.get("seasons", []):
        premiered = parse_date(season.get("air_date"))
        if season["season_number"] > 0 and premiered and premiered <= today:
            aired.append((season["season_number"], premiered))
    aired.sort()
    if not aired:
        return []
    started = [number for number, premiered in aired if premiered <= added_at]
    first = started[-1] if started else aired[0][0]
    return [number for number, _ in aired if number >= first][-MAX_SEASONS:]


def all_episode_facts(show: Show, data: dict, today: date) -> list[dict]:
    show_name = data.get("name") or show.name
    poster = image_url(data.get("poster_path")) or show.poster_url
    facts = []
    for key, season in data.items():
        if not key.startswith("season/"):
            continue
        for episode in season.get("episodes", []):
            aired = parse_date(episode.get("air_date"))
            s, e = episode["season_number"], episode["episode_number"]
            facts.append(
                {
                    "card_id": f"ep:{show.tmdb_id}:S{s:02}E{e:02}",
                    "type": "episode",
                    "tmdb_id": show.tmdb_id,
                    "show_name": show_name,
                    "headline": f"S{s:02}E{e:02} · {episode.get('name') or 'TBA'}",
                    "date": aired.isoformat() if aired else "",
                    "image_url": image_url(episode.get("still_path")) or poster,
                    "season": s,
                    "episode": e,
                    "eligible": aired is not None
                    and show.added_at - timedelta(days=DAYS_BACK) <= aired <= today,
                    "released": aired is not None and aired <= today,
                }
            )
    return facts


def episode_facts(show: Show, data: dict, today: date) -> list[dict]:
    return [fact for fact in all_episode_facts(show, data, today) if fact["eligible"]]


def episode_link(
    lookup, tmdb_id: int, show_imdb: str | None, season: int, episode: int
) -> str:
    imdb_id = lookup(tmdb_id, season, episode) or show_imdb
    if imdb_id:
        return f"https://www.imdb.com/title/{imdb_id}/"
    return f"https://www.themoviedb.org/tv/{tmdb_id}/season/{season}/episode/{episode}"

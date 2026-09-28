from datetime import date

from job.cards import new_card, parse_date
from job.sheet import Update
from job.state import truthy
from job.tmdb import image_url


def content_updates(existing: dict[str, dict], facts: list[dict], fields) -> list[Update]:
    updates = []
    for fact in facts:
        row = existing.get(fact["card_id"])
        if row is None:
            continue
        changed = {field: fact[field] for field in fields if str(fact[field]) != str(row[field])}
        if changed:
            updates.append(Update("Cards", fact["card_id"], changed))
    return updates


def reconcile_seasons(
    tmdb_id: int, show_name: str, data: dict, cards: list[dict], today: date, poster: str, now: str
) -> tuple[list[dict], list[Update]]:
    seasons = {s["season_number"]: s for s in data.get("seasons", []) if s["season_number"] > 0}
    prefix = f"season:{tmdb_id}:"
    by_number: dict[int, list[dict]] = {}
    for card in cards:
        if card["card_id"].startswith(prefix):
            by_number.setdefault(int(card["card_id"].split(":")[2]), []).append(card)

    upcoming = {n for n, s in seasons.items() if (d := parse_date(s.get("air_date"))) is None or d >= today}
    appends, updates = [], []
    for number in sorted(upcoming | set(by_number)):
        season = seasons.get(number, {})
        air = parse_date(season.get("air_date"))
        target = f"{prefix}{number}:{air.isoformat()}" if air else None
        existing = by_number.get(number, [])
        if target and air >= today and target not in {c["card_id"] for c in existing}:
            appends.append(
                new_card(
                    now=now,
                    card_id=target,
                    type="season",
                    tmdb_id=tmdb_id,
                    show_name=show_name,
                    headline=f"Season {number} premieres",
                    date=air.isoformat(),
                    link=f"https://www.themoviedb.org/tv/{tmdb_id}/season/{number}",
                    image_url=image_url(season.get("poster_path")) or poster,
                )
            )
        for card in existing:
            wanted = card["card_id"] == target
            if truthy(card["current"]) != wanted:
                updates.append(Update("Cards", card["card_id"], {"current": wanted}))
    return appends, updates

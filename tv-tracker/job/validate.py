from dataclasses import dataclass

from job.tmdb import image_url


@dataclass
class Suggestion:
    tmdb_id: int
    name: str
    year: int
    reason: str
    poster_url: str
    link: str


def _year(result: dict) -> int | None:
    prefix = (result.get("first_air_date") or "")[:4]
    return int(prefix) if prefix.isdigit() else None


def _names(result: dict) -> set[str]:
    return {(result.get(key) or "").casefold().strip() for key in ("name", "original_name")}


def pick_match(results: list[dict], title: str, year: int) -> dict | None:
    wanted = title.casefold().strip()
    near = None
    for result in results:
        result_year = _year(result)
        if wanted not in _names(result) or result_year is None or abs(result_year - year) > 1:
            continue
        if result_year == year:
            return result
        near = near or result
    return near


def resolve_suggestions(raw: list[dict], search, known_ids: set[int]) -> tuple[list[Suggestion], list[str]]:
    kept, dropped, seen = [], [], set(known_ids)
    for item in raw:
        label = f"{item['title']} ({item['year']})"
        match = pick_match(search(item["title"]), item["title"], item["year"])
        if match is None:
            dropped.append(f"{label}: no TMDB match")
            continue
        if match["id"] in seen:
            dropped.append(f"{label}: already tracked, ignored or suggested")
            continue
        seen.add(match["id"])
        kept.append(
            Suggestion(
                tmdb_id=match["id"],
                name=match["name"],
                year=_year(match),
                reason=item["reason"],
                poster_url=image_url(match.get("poster_path")),
                link=f"https://www.themoviedb.org/tv/{match['id']}",
            )
        )
    return kept, dropped

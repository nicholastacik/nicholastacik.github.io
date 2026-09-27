import re
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

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
    return {
        (result.get(key) or "").casefold().strip() for key in ("name", "original_name")
    }


def pick_match(results: list[dict], title: str, year: int) -> dict | None:
    wanted = title.casefold().strip()
    near = None
    for result in results:
        result_year = _year(result)
        if (
            wanted not in _names(result)
            or result_year is None
            or abs(result_year - year) > 1
        ):
            continue
        if result_year == year:
            return result
        near = near or result
    return near


def resolve_suggestions(
    raw: list[dict], search, known_ids: set[int]
) -> tuple[list[Suggestion], list[str]]:
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


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

DATE_PATTERNS = [
    re.compile(
        r"<meta[^>]+property=[\"']article:published_time[\"'][^>]+content=[\"']([^\"']+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']article:published_time",
        re.IGNORECASE,
    ),
    re.compile(r"\"datePublished\"\s*:\s*\"([^\"]+)\""),
    re.compile(r"<time[^>]+datetime=[\"']([^\"']+)", re.IGNORECASE),
]


@dataclass
class NewsItem:
    tmdb_id: int
    headline: str
    summary: str
    source_url: str
    published: date


TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "cmpid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    params = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.startswith("utm_") and key not in TRACKING_PARAMS
    )
    query = f"?{urlencode(params)}" if params else ""
    return parts.netloc.lower().removeprefix("www.") + parts.path.rstrip("/") + query


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def published_date(html: str) -> date | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(html)
        if match and (parsed := _parse_date(match.group(1))):
            return parsed
    return None


def fetch_page(url: str, client: httpx.Client | None = None) -> str | None:
    client = client or httpx.Client(timeout=5, follow_redirects=True)
    try:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError:
        return None
    return response.text if response.is_success else None


def validate_news(
    raw: list[dict],
    sources: set[str],
    tracked_ids: set[int],
    fetch,
    today: date,
    window_days: int,
) -> tuple[list[NewsItem], list[str]]:
    allowed = {normalize_url(url) for url in sources}
    cutoff = today - timedelta(days=window_days)
    kept, dropped, seen = [], [], set()

    for item in raw:
        headline, url = item["headline"], item["source_url"]
        key = normalize_url(url)
        if item["tmdb_id"] not in tracked_ids:
            dropped.append(f"{headline}: not a tracked show")
        elif not url.startswith(("http://", "https://")):
            dropped.append(f"{headline}: not an http(s) URL")
        elif key not in allowed:
            dropped.append(f"{headline}: URL not among search sources")
        elif (item["tmdb_id"], key) in seen:
            dropped.append(f"{headline}: duplicate URL")
        elif (html := fetch(url)) is None:
            dropped.append(f"{headline}: page unreachable")
        elif (
            published := published_date(html) or _parse_date(item["published_date"])
        ) is None:
            dropped.append(f"{headline}: no usable publish date")
        elif not cutoff <= published <= today:
            dropped.append(
                f"{headline}: published {published.isoformat()}, outside window"
            )
        else:
            seen.add((item["tmdb_id"], key))
            kept.append(
                NewsItem(item["tmdb_id"], headline, item["summary"], url, published)
            )
    return kept, dropped

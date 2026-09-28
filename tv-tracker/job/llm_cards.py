import hashlib
from datetime import date, timedelta

from job.cards import new_card
from job.state import Show, all_tracked_ids
from job.validate import NewsItem, Suggestion, normalize_url


def suggestion_card(s: Suggestion, now: str) -> dict:
    return new_card(
        now=now,
        card_id=f"sugg:{s.tmdb_id}",
        type="suggestion",
        tmdb_id=s.tmdb_id,
        show_name=s.name,
        headline=s.name,
        body=s.reason,
        date=str(s.year),
        link=s.link,
        image_url=s.poster_url,
    )


def news_card_id(tmdb_id: int, url: str) -> str:
    return f"news:{tmdb_id}:{hashlib.sha1(normalize_url(url).encode()).hexdigest()[:8]}"


def news_card(item: NewsItem, show_name: str, poster: str, now: str) -> dict:
    return new_card(
        now=now,
        card_id=news_card_id(item.tmdb_id, item.source_url),
        type="news",
        tmdb_id=item.tmdb_id,
        show_name=show_name,
        headline=item.headline,
        body=item.summary,
        date=item.published.isoformat(),
        link=item.source_url,
        image_url=poster,
        source_url=item.source_url,
    )


def _as_show(card: dict) -> dict:
    return {
        "tmdb_id": int(card["tmdb_id"]),
        "name": card["show_name"],
        "first_air_year": card["date"],
    }


def llm_inputs(
    shows: list[Show],
    tracked_rows: list[dict],
    cards: list[dict],
    today: date,
    memory_days: int,
) -> dict:
    suggestions = [
        c for c in cards if c["type"] == "suggestion" and c["tmdb_id"].isdigit()
    ]
    cutoff = (today - timedelta(days=memory_days)).isoformat()
    return {
        "tracked": [
            {
                "tmdb_id": s.tmdb_id,
                "name": s.name,
                "first_air_year": s.first_air_year or "?",
            }
            for s in shows
        ],
        "ignored": [_as_show(c) for c in suggestions if c["status"] == "ignored"],
        "pending": [_as_show(c) for c in suggestions if c["status"] == "new"],
        "recent_news": [
            {"show": c["show_name"], "headline": c["headline"]}
            for c in cards
            if c["type"] == "news" and c["created_at"][:10] >= cutoff
        ],
        "other_known_ids": sorted(
            all_tracked_ids(tracked_rows) | {int(c["tmdb_id"]) for c in suggestions}
        ),
    }

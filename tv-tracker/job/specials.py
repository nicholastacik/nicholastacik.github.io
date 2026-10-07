import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from job.cards import new_card, parse_date
from job.config import TZ
from job.schedule import DAYS_BACK, _row, in_window
from job.state import Show
from job.tmdb import image_url

LABEL = "Special"


@dataclass
class Special:
    title: str
    date: date | None
    source: str
    link: str = ""
    image: str = ""
    airstamp: str = ""
    has_time: bool = False
    network: str = ""


def norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", plain.lower())


def short_title(title: str) -> str:
    return (title.rsplit(":", 1)[-1] or title).strip()


def title_keys(title: str) -> set[str]:
    return {key for key in (norm(title), norm(short_title(title))) if key}


def slug(title: str) -> str:
    text = unicodedata.normalize("NFKD", short_title(title)).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", "-", text.decode().lower()).strip("-") or "untitled"


def special_id(tmdb_id: int, special: Special) -> str:
    return f"special:{tmdb_id}:{special.date.isoformat()}:{slug(special.title)}"


def _verify(parent_name: str, linked_name: str) -> None:
    if norm(parent_name) not in norm(linked_name):
        raise ValueError("linked special does not match its parent show")


def tmdb_season_specials(tmdb_id: int, season: dict) -> list[Special]:
    return [
        Special(
            title=episode.get("name") or "",
            date=parse_date(episode.get("air_date")),
            source="tmdb",
            link=f"https://www.themoviedb.org/tv/{tmdb_id}/season/0/episode/{episode['episode_number']}",
            image=image_url(episode.get("still_path")),
        )
        for episode in season.get("episodes", [])
    ]


def tvmaze_specials(episodes: list[dict], network: str = "") -> list[Special]:
    found = []
    for episode in episodes:
        stamp = episode.get("airstamp") or ""
        day = (
            datetime.fromisoformat(stamp).astimezone(TZ).date()
            if stamp
            else parse_date(episode.get("airdate"))
        )
        found.append(
            Special(
                title=episode.get("name") or "",
                date=day,
                source="tvmaze",
                link=episode.get("url") or "",
                image=(episode.get("image") or {}).get("medium") or "",
                airstamp=stamp,
                has_time=bool(episode.get("airtime")),
                network=network,
            )
        )
    return found


def _network(show: dict) -> str:
    return (show.get("network") or show.get("webChannel") or {}).get("name", "")


def discover_specials(
    show: Show, data: dict, tmdb, tvmaze, links: dict
) -> tuple[list[Special], list[tuple[str, Exception]]]:
    parent = data.get("name") or show.name
    found: list[Special] = []
    failures: list[tuple[str, Exception]] = []

    def attempt(source: str, discover) -> None:
        try:
            found.extend(discover())
        except Exception as error:  # noqa: BLE001 — one source failing never blocks the others
            failures.append((source, error))

    if show.tvmaze_id:
        attempt(
            "tvmaze",
            lambda: tvmaze_specials(
                [
                    e
                    for e in tvmaze.specials(show.tvmaze_id)
                    if e.get("type") != "regular"
                ]
            ),
        )
    for series_id in links.get("tvmaze_series", []):

        def linked_series(series_id=series_id):
            series = tvmaze.show(series_id)
            _verify(parent, series.get("name", ""))
            return tvmaze_specials(tvmaze.specials(series_id), _network(series))

        attempt(f"tvmaze:{series_id}", linked_series)
    if any(s.get("season_number") == 0 for s in data.get("seasons", [])):
        attempt(
            "tmdb",
            lambda: tmdb_season_specials(show.tmdb_id, tmdb.season(show.tmdb_id, 0)),
        )
    for movie_id in links.get("tmdb_movies", []):

        def linked_movie(movie_id=movie_id):
            movie = tmdb.movie(movie_id)
            _verify(parent, movie.get("title", ""))
            return [
                Special(
                    title=movie.get("title") or "",
                    date=parse_date(movie.get("release_date")),
                    source="tmdb",
                    link=f"https://www.themoviedb.org/movie/{movie_id}",
                    image=image_url(movie.get("poster_path")),
                )
            ]

        attempt(f"tmdb-movie:{movie_id}", linked_movie)
    return merge_specials(found), failures


def _same(a: Special, b: Special) -> bool:
    dates_agree = a.date is None or b.date is None or a.date == b.date
    if a.date and a.date == b.date and a.source != b.source:
        return True
    return dates_agree and bool(title_keys(a.title) & title_keys(b.title))


def merge_specials(found: list[Special]) -> list[Special]:
    merged: list[Special] = []
    for special in found:
        kept = next((m for m in merged if _same(m, special)), None)
        if kept is None:
            merged.append(special)
            continue
        for field in ("date", "link", "image", "airstamp", "network"):
            if not getattr(kept, field):
                setattr(kept, field, getattr(special, field))
        kept.has_time = kept.has_time or special.has_time
    return merged


def _announced(cards: list[dict], tmdb_id: int, special: Special) -> bool:
    keys = {key for key in title_keys(special.title) if len(key) >= 5}
    for card in cards:
        if card["type"] != "news" or str(card["tmdb_id"]) != str(tmdb_id):
            continue
        if str(card["date"])[:10] >= special.date.isoformat() and any(
            key in norm(f"{card['headline']} {card['body']}") for key in keys
        ):
            return True
    return False


def _carded(cards: list[dict], tmdb_id: int, special: Special) -> bool:
    prefix = f"special:{tmdb_id}:"
    return any(
        card["card_id"].startswith(prefix)
        and card["card_id"].split(":")[2] == special.date.isoformat()
        for card in cards
    )


def special_cards(
    show: Show,
    parent_name: str,
    specials: list[Special],
    cards: list[dict],
    today: date,
    poster: str,
    now: str,
) -> list[dict]:
    new = []
    for special in specials:
        if special.date is None or not (
            show.added_at - timedelta(days=DAYS_BACK) <= special.date <= today
        ):
            continue
        if _carded(cards, show.tmdb_id, special) or _announced(
            cards, show.tmdb_id, special
        ):
            continue
        new.append(
            new_card(
                now=now,
                card_id=special_id(show.tmdb_id, special),
                type="special",
                tmdb_id=show.tmdb_id,
                show_name=parent_name,
                headline=special.title or "Special",
                date=special.date.isoformat(),
                link=special.link,
                image_url=special.image or poster,
            )
        )
    return new


def special_rows(
    show: Show,
    specials: list[Special],
    existing: list[dict],
    today: date,
    now: str,
    show_image: str,
) -> list[dict]:
    rows = []
    for special in specials:
        if special.airstamp:
            local = datetime.fromisoformat(special.airstamp).astimezone(TZ)
            stamp = (
                local.isoformat(timespec="minutes")
                if special.has_time
                else local.date().isoformat()
            )
        elif special.date:
            stamp = special.date.isoformat()
        else:
            continue
        if not in_window(stamp, today):
            continue
        keys = title_keys(special.title)
        if any(
            row["airstamp"][:10] == stamp[:10]
            and keys & title_keys(row["episode_label"].split(" · ", 1)[-1])
            for row in [*existing, *rows]
        ):
            continue
        label = f"{LABEL} · {special.title}" if special.title else LABEL
        rows.append(
            _row(
                show,
                stamp,
                label,
                special.network,
                special.image or show_image,
                now,
                special.link,
            )
        )
    return rows

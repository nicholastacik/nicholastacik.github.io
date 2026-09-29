import os
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime

from job import config
from job.cards import (
    all_episode_facts,
    episode_link,
    new_card,
    seasons_to_fetch,
)
from job.llm_cards import llm_inputs, news_card, suggestion_card
from job.reconcile import episode_updates, reconcile_seasons
from job.schedule import merge_schedule, schedule_rows, window_start
from job.sheet import Update
from job.state import active_shows, truthy
from job.steps import run_news, run_suggestions
from job.tmdb import image_url

CARD_FIELDS = (
    "card_id",
    "type",
    "tmdb_id",
    "show_name",
    "headline",
    "date",
    "image_url",
)


@dataclass
class RunReport:
    appended: int = 0
    updated: int = 0
    failed_shows: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed_shows and not self.failed_steps


def meta_rows(report: RunReport, now: str, today: date) -> list[dict]:
    values = {
        "last_run_at": now,
        "last_run_ok": report.ok,
        "schedule_from": window_start(today).isoformat(),
        "failed_shows": ", ".join(report.failed_shows),
        "failed_steps": ", ".join(report.failed_steps),
    }
    return [{"key": key, "value": value} for key, value in values.items()]


def ran_today(meta: list[dict], today: date) -> bool:
    values = {row["key"]: row["value"] for row in meta}
    try:
        last = (
            datetime.fromisoformat(values["last_run_at"]).astimezone(config.TZ).date()
        )
    except (KeyError, ValueError):
        return False
    return truthy(values.get("last_run_ok", "")) and last == today


def _failed(what: str, error: Exception) -> None:
    status = getattr(getattr(error, "response", None), "status_code", None)
    print(f"FAILED {what}: {type(error).__name__}{f' {status}' if status else ''}")
    if os.environ.get("TV_TRACKER_DEBUG") == "1":
        traceback.print_exc()


def run_daily(
    sheet, tmdb, tvmaze, llm_client, fetch, now: datetime, omdb=None
) -> RunReport:
    today, stamp = now.date(), now.isoformat(timespec="seconds")
    state = sheet.read_all()
    cards = state["Cards"]
    existing = {card["card_id"]: card for card in cards}
    shows = active_shows(state["Tracked"])
    report = RunReport()
    appends: list[dict] = []
    updates: list[Update] = []
    fresh: dict[int, list[dict]] = {}
    failed: set[int] = set()
    posters: dict[int, str] = {}

    def add(card: dict) -> None:
        if card["card_id"] not in existing:
            existing[card["card_id"]] = card
            appends.append(card)

    for number, show in enumerate(shows, start=1):
        try:
            data = tmdb.show(show.tmdb_id)
            poster = posters[show.tmdb_id] = (
                image_url(data.get("poster_path")) or show.poster_url
            )
            show_imdb = data["external_ids"].get("imdb_id")
            if show_imdb and show.imdb_id != show_imdb:
                updates.append(Update("Tracked", show.tmdb_id, {"imdb_id": show_imdb}))
            if show.tvmaze_id is None and show_imdb:
                show.tvmaze_id = tvmaze.lookup_imdb(show_imdb)
                if show.tvmaze_id:
                    updates.append(
                        Update("Tracked", show.tmdb_id, {"tvmaze_id": show.tvmaze_id})
                    )
            if numbers := seasons_to_fetch(data, show.added_at, today):
                data = tmdb.show(show.tmdb_id, numbers)
            all_facts = all_episode_facts(show, data, today)
            updates += episode_updates(existing, all_facts)
            facts = [fact for fact in all_facts if fact["eligible"]]
            for fact in facts:
                if fact["card_id"] not in existing:
                    link = episode_link(
                        tmdb.episode_imdb,
                        show.tmdb_id,
                        show_imdb,
                        fact["season"],
                        fact["episode"],
                    )
                    add(
                        new_card(
                            now=stamp,
                            link=link,
                            **{key: fact[key] for key in CARD_FIELDS},
                        )
                    )
            season_appends, season_updates = reconcile_seasons(
                show.tmdb_id,
                data.get("name") or show.name,
                data,
                cards,
                today,
                poster,
                stamp,
            )
            for card in season_appends:
                add(card)
            updates += season_updates
            tvmaze_show = (
                tvmaze.show_with_episodes(show.tvmaze_id) if show.tvmaze_id else {}
            )

            by_date: dict[str, list[tuple[int, int]]] = {}
            for key, season_data in data.items():
                if key.startswith("season/"):
                    for ep in season_data.get("episodes", []):
                        if ep.get("air_date"):
                            by_date.setdefault(ep["air_date"], []).append(
                                (ep["season_number"], ep["episode_number"])
                            )

            def link_for(
                season,
                number,
                airdate,
                tmdb_id=show.tmdb_id,
                show_imdb=show_imdb,
                by_date=by_date,
            ):
                candidates = by_date.get(airdate, [])
                match = next((c for c in candidates if c[1] == number), None)
                if match is None and len(candidates) == 1:
                    match = candidates[0]
                listed_season, listed_number = season, number
                season, number = match or (season, number)
                if not number:
                    return (
                        f"https://www.imdb.com/title/{show_imdb}/episodes/?season={season}"
                        if show_imdb
                        else ""
                    )

                def lookup(tmdb_id, season, number):
                    found = tmdb.episode_imdb(tmdb_id, season, number)
                    if found or omdb is None or not show_imdb:
                        return found
                    found = omdb.episode_imdb(show_imdb, season, airdate, number)
                    if found is None and listed_season != season:
                        found = omdb.episode_imdb(
                            show_imdb, listed_season, airdate, listed_number
                        )
                    return found

                return episode_link(lookup, tmdb_id, show_imdb, season, number)

            fresh[show.tmdb_id] = schedule_rows(
                show, tvmaze_show, data, today, stamp, link_for
            )
        except Exception as error:  # noqa: BLE001 — spec: log and skip the show
            _failed(f"show {number} of {len(shows)} (name in the Meta tab)", error)
            report.failed_shows.append(show.name)
            failed.add(show.tmdb_id)

    inputs = llm_inputs(shows, state["Tracked"], cards, today, config.NEWS_MEMORY_DAYS)
    try:
        outcome = run_suggestions(inputs, llm_client, tmdb.search)
        for suggestion in outcome[1] if outcome else []:
            add(suggestion_card(suggestion, stamp))
    except Exception as error:  # noqa: BLE001 — spec: a failed step never blocks fact cards
        _failed("suggestions", error)
        report.failed_steps.append("suggestions")
    try:
        outcome = run_news(inputs, llm_client, fetch, today)
        names = {show.tmdb_id: show.name for show in shows}
        for item in outcome[1] if outcome else []:
            add(
                news_card(
                    item, names[item.tmdb_id], posters.get(item.tmdb_id, ""), stamp
                )
            )
    except Exception as error:  # noqa: BLE001 — spec: a failed step never blocks fact cards
        _failed("news", error)
        report.failed_steps.append("news")

    report.appended, report.updated = len(appends), len(updates)
    sheet.write(updates, {"Cards": appends})
    sheet.replace("Schedule", merge_schedule(fresh, failed, state["Schedule"], today))
    sheet.replace("Meta", meta_rows(report, stamp, today))
    return report

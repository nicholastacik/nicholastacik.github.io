import traceback
from dataclasses import dataclass, field
from datetime import date, datetime

from job import config
from job.cards import (
    EPISODE_CONTENT,
    episode_facts,
    episode_link,
    new_card,
    seasons_to_fetch,
)
from job.llm_cards import llm_inputs, news_card, suggestion_card
from job.reconcile import content_updates, reconcile_seasons
from job.schedule import merge_schedule, schedule_rows, week_start
from job.sheet import Update
from job.state import active_shows
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
        "schedule_week": week_start(today).isoformat(),
        "failed_shows": ", ".join(report.failed_shows),
        "failed_steps": ", ".join(report.failed_steps),
    }
    return [{"key": key, "value": value} for key, value in values.items()]


def _failed(what: str) -> None:
    print(f"FAILED {what}:")
    traceback.print_exc()


def run_daily(sheet, tmdb, tvmaze, llm_client, fetch, now: datetime) -> RunReport:
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
            if show.tvmaze_id is None and show_imdb:
                show.tvmaze_id = tvmaze.lookup_imdb(show_imdb)
                if show.tvmaze_id:
                    updates.append(
                        Update("Tracked", show.tmdb_id, {"tvmaze_id": show.tvmaze_id})
                    )
            if numbers := seasons_to_fetch(data, show.added_at, today):
                data = tmdb.show(show.tmdb_id, numbers)
            facts = episode_facts(show, data, today)
            updates += content_updates(existing, facts, EPISODE_CONTENT)
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
            fresh[show.tmdb_id] = schedule_rows(show, tvmaze_show, data, today, stamp)
        except Exception:  # noqa: BLE001 — spec: log and skip the show
            _failed(f"show {number} of {len(shows)} (name in the Meta tab)")
            report.failed_shows.append(show.name)
            failed.add(show.tmdb_id)

    inputs = llm_inputs(shows, state["Tracked"], cards, today, config.NEWS_MEMORY_DAYS)
    try:
        outcome = run_suggestions(inputs, llm_client, tmdb.search)
        for suggestion in outcome[1] if outcome else []:
            add(suggestion_card(suggestion, stamp))
    except Exception:  # noqa: BLE001 — spec: a failed step never blocks fact cards
        _failed("suggestions")
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
    except Exception:  # noqa: BLE001 — spec: a failed step never blocks fact cards
        _failed("news")
        report.failed_steps.append("news")

    report.appended, report.updated = len(appends), len(updates)
    sheet.write(updates, {"Cards": appends})
    sheet.replace("Schedule", merge_schedule(fresh, failed, state["Schedule"], today))
    sheet.replace("Meta", meta_rows(report, stamp, today))
    return report

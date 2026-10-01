import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from job import config, llm, validate
from job.daily import ran_today, run_daily
from job.omdb import Omdb
from job.setup import import_rows
from job.sheet import Sheet
from job.steps import run_news, run_suggestions
from job.tmdb import Tmdb
from job.tvmaze import Tvmaze, eastern, next_airing


def print_facts(tracked: list[dict], tmdb: Tmdb, tvmaze: Tvmaze, now: datetime) -> None:
    print("== Facts (TMDB + TVmaze) ==")
    for show in tracked:
        try:
            data = tmdb.show(show["tmdb_id"])
            imdb_id = data["external_ids"].get("imdb_id")
            tvmaze_id = tvmaze.lookup_imdb(imdb_id) if imdb_id else None
            upcoming = (
                next_airing(tvmaze.episodes(tvmaze_id), now) if tvmaze_id else None
            )
            next_tmdb = data.get("next_episode_to_air") or {}
            print(
                f"- {data['name']} (tmdb {show['tmdb_id']}, imdb {imdb_id}, tvmaze {tvmaze_id})"
            )
            print(
                f"    seasons: {data.get('number_of_seasons')}, status: {data.get('status')}"
            )
            print(
                f"    TMDB next: {next_tmdb.get('air_date')} {next_tmdb.get('name') or ''}"
            )
            print(
                f"    TVmaze next: {eastern(upcoming['airstamp']) if upcoming else None}"
            )
        except Exception as error:  # noqa: BLE001 — spec: log and skip the show
            print(f"- {show['name']}: FAILED ({error!r})")


def print_usage(result: llm.LlmResult) -> None:
    print(
        f"  [tokens in/out {result.input_tokens}/{result.output_tokens}, web searches {result.searches}]"
    )


def print_dropped(dropped: list[str]) -> None:
    for reason in dropped:
        print(f"  dropped: {reason}")


def open_sheet() -> Sheet:
    return Sheet.open(config.service_account_info(), config.sheet_id())


def setup(shows_path: Path) -> None:
    sheet = open_sheet()
    print(f"created tabs: {sheet.ensure_tabs() or 'none'}")
    tracked = json.loads(shows_path.read_text())["tracked"]
    rows = import_rows(
        tracked,
        sheet.read_all()["Tracked"],
        Tmdb(config.tmdb_token()),
        datetime.now(config.TZ),
    )
    sheet.write([], {"Tracked": rows})
    print(f"imported {len(rows)} show(s)")


def run(skip_if_ran_today: bool = False) -> None:
    from openai import OpenAI

    sheet = open_sheet()
    now = datetime.now(config.TZ)
    if skip_if_ran_today and ran_today(sheet.read_all()["Meta"], now.date()):
        print("already ran successfully today; skipping")
        return

    omdb = Omdb(key) if (key := config.omdb_key()) else None
    report = run_daily(
        sheet,
        Tmdb(config.tmdb_token()),
        Tvmaze(),
        OpenAI() if config.openai_key() else None,
        validate.fetch_page,
        now,
        omdb=omdb,
    )
    print(f"appended {report.appended} card(s), updated {report.updated} cell group(s)")
    if not config.openai_key():
        print(
            "research off: no OPENAI_API_KEY (suggestions and news come from the ChatGPT task)"
        )
    if not report.ok:
        print(
            f"failed shows: {len(report.failed_shows)} (names in the Meta tab); failed steps: {report.failed_steps}"
        )
        sys.exit(1)


def dry_run(args) -> None:
    from openai import OpenAI

    shows = json.loads(args.shows.read_text())
    now = datetime.now(config.TZ)
    tmdb = Tmdb(config.tmdb_token())
    client = OpenAI()
    print(
        f"model {config.OPENAI_MODEL}, effort suggestions/news {config.SUGGESTIONS_EFFORT}/{config.NEWS_EFFORT}, {now:%Y-%m-%d %H:%M %Z}\n"
    )

    if "facts" not in args.skip:
        print_facts(shows["tracked"], tmdb, Tvmaze(), now)

    if "suggestions" not in args.skip:
        print("\n== Suggestions ==")
        outcome = run_suggestions(shows, client, tmdb.search)
        if outcome is None:
            print("  skipped: nothing tracked or pending queue full")
        else:
            result, kept, dropped = outcome
            for s in kept:
                print(
                    f"- {s.name} ({s.year}) tmdb {s.tmdb_id}\n    {s.reason}\n    {s.link}"
                )
            print_dropped(dropped)
            print_usage(result)

    if "news" not in args.skip:
        print("\n== News ==")
        outcome = run_news(shows, client, validate.fetch_page, now.date())
        if outcome is None:
            print("  skipped: nothing tracked")
        else:
            result, kept, dropped = outcome
            names = {s["tmdb_id"]: s["name"] for s in shows["tracked"]}
            print(f"  model proposed {len(result.data['news'])} item(s)")
            for n in kept:
                print(
                    f"- [{names[n.tmdb_id]}] {n.headline} ({n.published})\n    {n.summary}\n    {n.source_url}"
                )
            print_dropped(dropped)
            print(f"  sources returned by search: {len(result.sources)}")
            print_usage(result)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="job")
    parser.add_argument("command", nargs="?", choices=["run", "setup"], default="run")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-if-ran-today", action="store_true")
    parser.add_argument("--shows", type=Path, default=Path("shows.example.json"))
    parser.add_argument(
        "--skip", action="append", choices=["facts", "suggestions", "news"], default=[]
    )
    args = parser.parse_args(argv)
    if args.command == "setup":
        setup(args.shows)
    elif args.dry_run:
        dry_run(args)
    else:
        run(args.skip_if_ran_today)


if __name__ == "__main__":
    main()

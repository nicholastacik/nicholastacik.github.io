import argparse
import json
from datetime import date, datetime
from pathlib import Path

from job import config, llm, validate
from job.tmdb import Tmdb
from job.tvmaze import Tvmaze, next_airing


def run_suggestions(shows: dict, client, search):
    pending = shows.get("pending", [])
    k = config.MAX_PENDING_SUGGESTIONS - len(pending)
    if k <= 0 or not shows["tracked"]:
        return None
    prompt = llm.suggestions_prompt(
        shows["tracked"], shows.get("ignored", []), pending, k
    )
    result = llm.run(
        client,
        prompt,
        "suggestions",
        llm.SUGGESTIONS_SCHEMA,
        effort=config.SUGGESTIONS_EFFORT,
    )
    known = {
        s["tmdb_id"]
        for key in ("tracked", "ignored", "pending")
        for s in shows.get(key, [])
    }
    kept, dropped = validate.resolve_suggestions(
        result.data["suggestions"], search, known
    )
    dropped += [f"{s.name} ({s.year}): over queue capacity" for s in kept[k:]]
    return result, kept[:k], dropped


def run_news(shows: dict, client, fetch, today: date):
    tracked = shows["tracked"]
    if not tracked:
        return None
    prompt = llm.news_prompt(
        tracked, shows.get("recent_news", []), today, config.NEWS_WINDOW_DAYS
    )
    result = llm.run(client, prompt, "news", llm.NEWS_SCHEMA, effort=config.NEWS_EFFORT)
    tracked_ids = {s["tmdb_id"] for s in tracked}
    kept, dropped = validate.validate_news(
        result.data["news"],
        result.sources,
        tracked_ids,
        fetch,
        today,
        config.NEWS_WINDOW_DAYS,
    )
    return result, kept, dropped


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
            print(f"    TVmaze next: {upcoming['airstamp'] if upcoming else None}")
        except Exception as error:  # noqa: BLE001 — spec: log and skip the show
            print(f"- {show['name']}: FAILED ({error!r})")


def print_usage(result: llm.LlmResult) -> None:
    print(
        f"  [tokens in/out {result.input_tokens}/{result.output_tokens}, web searches {result.searches}]"
    )


def print_dropped(dropped: list[str]) -> None:
    for reason in dropped:
        print(f"  dropped: {reason}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="job")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shows", type=Path, default=Path("shows.example.json"))
    parser.add_argument(
        "--skip", action="append", choices=["facts", "suggestions", "news"], default=[]
    )
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error("only --dry-run exists until the Sheet is wired up (Plan 2)")

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


if __name__ == "__main__":
    main()

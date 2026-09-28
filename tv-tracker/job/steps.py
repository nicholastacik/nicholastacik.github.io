from datetime import date

from job import config, llm, validate


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
    known |= set(shows.get("other_known_ids", []))
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

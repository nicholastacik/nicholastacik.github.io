# TV Tracker — Design

**Date:** 2026-09-27
**Status:** Approved in conversation, pending written-spec review

## Overview

A private, two-user (Nick + wife) TV tracker plus a public blog post about
building it. A daily job gathers facts about tracked shows from TV APIs and
asks an LLM for suggestions and news, writing everything to a Google Sheet.
A static web app reads the Sheet, shows cards and a weekly schedule, and
writes the user's decisions straight back. Readers of the blog only see
screenshots; the app requires one of two Google logins.

## Key decisions (with rationale)

| Decision | Rationale |
|---|---|
| Hybrid: APIs for facts, LLM for taste | Episode titles, dates, times, links and images must be exact — TMDB/TVmaze have them. Web-search LLMs hallucinate specifics but are good at "you might like" and spotting news. |
| LLM proposes, deterministic system confirms | The LLM never supplies an ID, URL or image. Suggestions are resolved against TMDB; unresolvable ones are dropped. |
| Google Sheet is the only datastore and the only interface between job and app | Inspectable/editable by hand, no backend, and the two halves can be built/tested independently. |
| Fully shared state | One tracked list, one feed. Either user's dismissal applies to both. |
| Shows added via TMDB search in the app | Guarantees correct IDs; avoids free-text name ambiguity. |
| News scoped to tracked shows only | Narrow, relevant, dedupable per show. |
| Job: Python on a GitHub Actions cron | Testable with pytest, prompt iteration locally via `--dry-run`, code lives in git for the post. |
| App: static HTML/CSS/JS, no framework, no build step | Three views and a handful of API calls don't justify tooling. |
| Auth: Google Identity Services + OAuth app in "Testing" mode with two test users + Sheet shared with the same two accounts | Two Google-enforced locks, zero backend. |
| Code lives in this repo (`tv-tracker/`, app under `posts/tv_tracker/app/`) | Mirrors `jeopardy/`, `chess/`, `codenames/`. |
| Out of scope: where-to-watch, torrents, per-user state | Explicitly deferred/declined in design discussion. |

## Layout

```
tv-tracker/                        # root-level pipeline (mirrors jeopardy/)
  job/                             # run from tv-tracker/: `uv run python -m job [--dry-run]`
    __main__.py                    # orchestrates the daily run
    config.py                      # env vars, constants (TZ, caps, windows)
    sheet.py                       # read/append/rewrite tabs via service account
    tmdb.py                        # TMDB client (show, season, external_ids, search)
    tvmaze.py                      # TVmaze client (lookup by IMDb, episodes)
    cards.py                       # pure: API JSON -> card rows / schedule rows
    llm.py                         # OpenAI Responses calls (suggestions, news) + validation
    prompts/suggestions.md
    prompts/news.md
  tests/                           # pytest; saved API responses under tests/fixtures/
posts/tv_tracker/
  index.qmd                        # blog post; draft: true until promoted
  notes/BUILD_NOTES.md             # running notes feeding the post (excluded from render)
  app/                             # served as-is (added to _quarto.yml resources)
    index.html
    app.js
    sheets.js                      # GIS auth + Sheets read/update
    tmdb.js                        # search
    config.js                      # SHEET_ID, OAuth client ID, TMDB read token
    styles.css
.github/workflows/tv-tracker.yml   # daily cron + workflow_dispatch
```

The folder name `tv-tracker` has a hyphen, so it isn't importable; the job is
run with `tv-tracker/` as the working directory (`python -m job`). A new uv
dependency group `tv-tracker` holds `httpx`, `gspread`, `google-auth`,
`openai`, `pytest`.

## Sheet schema (the contract)

One spreadsheet, three tabs.

### `Tracked` — state; written by the app, read by the job

| tmdb_id | tvmaze_id | name | poster_url | added_at | source |
|---|---|---|---|---|---|

- `source`: `search` or `suggestion`.
- `tvmaze_id` may be blank; the job fills it in.
- Untrack = delete the row (app).

### `Cards` — state; job appends, app updates `status` / `updated_at` only

| card_id | type | tmdb_id | show_name | headline | date | link | image_url | source_url | created_at | status | updated_at |
|---|---|---|---|---|---|---|---|---|---|---|---|

- `type`: `episode` · `season` · `suggestion` · `news`
- `status`: `new` → `noted` (episode/season/news) or `tracked` / `ignored` (suggestion)
- `headline` holds the episode title / season text / show name / news headline;
  for suggestions the LLM's one-line reason goes in `headline` alongside the
  show name (app renders `show_name` as title, `headline` as subtitle).
- `card_id` is the dedupe key; the job never appends an existing id:
  - `ep:{tmdb}:S{ss}E{ee}`
  - `season:{tmdb}:{n}:{air_date}` — a changed air date yields a new card
  - `sugg:{tmdb}` — once ignored, never suggested again
  - `news:{tmdb}:{sha1(normalized headline)[:8]}` — backstop to prompt-level dedupe
- The job never deletes or rewrites `Cards` rows, so row indices stay stable
  for the app's in-place updates.

### `Schedule` — derived; job rewrites the whole tab daily, app reads only

| airstamp | tmdb_id | show_name | episode_label | network | image_url |
|---|---|---|---|---|---|

- `airstamp` is ISO 8601 in America/Toronto; date-only when TVmaze has no time
  (common for streaming).

## Daily job

GitHub Actions cron `0 10 * * *` (6 am Eastern) plus `workflow_dispatch`.
Secrets: `TMDB_TOKEN`, `OPENAI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`,
`SHEET_ID`. Config: `OPENAI_MODEL` (chosen at implementation time),
`TZ=America/Toronto`, `NEWS_WINDOW_DAYS=7`, `NEWS_MEMORY_DAYS=30`,
`MAX_PENDING_SUGGESTIONS=3`.

Steps, in order:

1. **Load** `Tracked` and the set of existing `card_id`s (with type/status).
2. **Backfill `tvmaze_id`**: TMDB `external_ids` → IMDb id → TVmaze
   `/lookup/shows?imdb=`.
3. **Episode cards**: TMDB `/tv/{id}` + current season's episodes. Emit a card
   for each episode with `added_at ≤ air_date ≤ today` not already carded.
   Link = episode IMDb page (from episode `external_ids`), fallback show IMDb
   page. Image = episode still, fallback poster.
4. **Season cards**: seasons with `season_number > 0` and known
   `air_date ≥ today`.
5. **Schedule**: TVmaze `/shows/{id}/episodes`, keep this Mon–Sun by
   `airstamp` converted to Eastern; rewrite `Schedule`.
6. **Suggestions (LLM)**: only if pending (`status=new`) suggestion cards
   `< MAX_PENDING_SUGGESTIONS`; request `k = cap − pending`.
7. **News (LLM)**: one call across all tracked shows.
8. **Write**: append new cards; write back backfilled `tvmaze_id`s.

### LLM calls

OpenAI Responses API with the `web_search` tool and JSON-schema structured
output.

**Suggestions** — inputs: tracked (name, year), ignored (`sugg:` rows with
`status=ignored`), pending suggestions. Asks for `k` shows with exact title,
first-air year and a one-sentence reason referencing a specific tracked show;
prefer currently airing / last 2 years, one older gem allowed; search to
confirm existence. Output: `[{title, year, reason}]`.

**News** — inputs: tracked (name, year, tmdb_id), headlines of news cards
from the last `NEWS_MEMORY_DAYS`. Significant = renewal, cancellation,
premiere/release date announced or changed, trailer/teaser, major casting.
Ignore reviews, recaps, rankings, theories. "An empty list is a good answer."
Every item cites its source. Output:
`[{tmdb_id, headline, summary, source_url, published_date}]`.

Draft prompt text lives in `job/prompts/`; refining it is the first
implementation milestone (see Build order).

### Validation

- Suggestions: TMDB search by title + year; drop if no match, or already
  tracked / ignored / pending. TMDB supplies id, poster, link.
- News: drop if `tmdb_id` not tracked, `source_url` not http(s), or
  `published_date` older than `NEWS_WINDOW_DAYS`.

### Error handling

- Per-show API failures: log and skip that show.
- LLM steps run last and independently; a failure never blocks fact cards.
- Non-zero exit only if the Sheet read or write fails (GitHub emails on
  failure).

## App

Static page at `posts/tv_tracker/app/`, mobile-first, bottom tab bar.

- **Auth**: GIS token client, `spreadsheets` scope. OAuth consent screen in
  Testing mode with the two accounts as test users. Token expiry → silent
  re-request.
- **Feed**: `Cards` with `status=new`, newest first. Card = image left;
  title, subtitle, date, link right; buttons `Noted`, or `Track` / `Ignore`
  for suggestions. News shows a source link.
- **This Week**: `Schedule` grouped by day, time + network, today highlighted.
- **Shows**: TMDB search (tap → Track) above the tracked list (Untrack).
- **Writes**: on load, read `Cards` once and map `card_id → row`. A click
  removes the card optimistically, then updates `status` + `updated_at` in
  that row; on failure the card is restored with a "couldn't save" toast.
  Concurrent identical clicks are idempotent. `Track` on a suggestion also
  appends to `Tracked` (`source=suggestion`); its episodes/schedule appear on
  the next job run (or a manual `workflow_dispatch`).

## Testing

- Job: pytest on `cards.py` and `llm.py` validation using saved TMDB/TVmaze
  responses and canned LLM outputs; no network in tests. Add to `test.yml`.
- Prompts: `--dry-run` against the real tracked list over several days,
  checking for repeats, junk and misses.
- App: `node --test` for pure helpers (filter/sort cards, group schedule);
  manual check against a seeded test Sheet, which also produces blog
  screenshots.

## Build order

1. Feasibility + prompts: TMDB/TVmaze clients and a `--dry-run` that prints
   suggestion and news output for a hand-written tracked list. Iterate prompts.
2. Sheet I/O and the full job; GitHub Actions workflow.
3. App (auth → feed → schedule → search).
4. Blog post.

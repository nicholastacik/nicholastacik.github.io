# TV Tracker — Design

**Date:** 2026-09-27
**Status:** Approved (rev 4, after third spec review)

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
| Suggestions: LLM proposes, TMDB confirms | The LLM never supplies an ID, URL or image for a suggestion. Unresolvable titles are dropped. |
| News: cited, not confirmed | News can't be confirmed against a structured source. It gets a weaker, explicit trust tier: the URL must be one the search tool actually returned, the date is checked from the page where possible, and the card always shows the source domain. |
| Google Sheet is the only datastore and the only interface between job and app | Inspectable, no backend, and the two halves can be built/tested independently. |
| Rows are never deleted or reordered | Both job and app address rows by index after reading; stable indices make that safe. Removal is a flag. |
| Fully shared state | One tracked list, one feed. Either user's dismissal applies to both. |
| Shows added via TMDB search in the app | Guarantees correct IDs; avoids free-text name ambiguity. |
| News scoped to tracked shows only | Narrow, relevant, dedupable per show. |
| Job: Python on a GitHub Actions cron | Testable with pytest, prompt iteration locally via `--dry-run`, code lives in git for the post. |
| App: static HTML/CSS/JS, no framework, no build step | Three views and a handful of API calls don't justify tooling. |
| Auth: GIS token model; OAuth app **published to Production, unverified**; Sheet shared with only the two accounts | Testing mode forces re-consent every 7 days. Production-unverified (sensitive scope, <100 users) shows a one-time "unverified app" warning and no expiry. The Sheet's sharing is the access control. |
| Code lives in this repo (`tv-tracker/`, app under `posts/tv_tracker/app/`) | Mirrors `jeopardy/`, `chess/`, `codenames/`. |
| Out of scope: where-to-watch, torrents, per-user state | Explicitly deferred/declined in design discussion. |

## Layout

```
tv-tracker/                        # root-level pipeline (mirrors jeopardy/)
  job/                             # run from tv-tracker/: `uv run python -m job [--dry-run]`
    __main__.py                    # orchestrates the daily run
    config.py                      # env vars, constants (TZ, caps, windows)
    sheet.py                       # read/append/update tabs via service account
    tmdb.py                        # TMDB client (show+seasons, external_ids, search)
    tvmaze.py                      # TVmaze client (lookup by IMDb, episodes)
    cards.py                       # pure: API JSON -> card rows / schedule rows
    reconcile.py                   # pure: existing rows + fresh facts -> appends/updates
    llm.py                         # OpenAI Responses calls (suggestions, news) + validation
    prompts/suggestions.md
    prompts/news.md
  tests/                           # pytest; saved API responses + in-memory fake sheet
posts/tv_tracker/
  index.qmd                        # blog post; draft: true until promoted
  notes/BUILD_NOTES.md             # running notes feeding the post (excluded from render)
  app/                             # served as-is (added to _quarto.yml resources)
    index.html
    app.js
    state.js                       # pure: filtering, grouping, track/untrack planning
    sheets.js                      # GIS auth + Sheets read/batchUpdate
    tmdb.js                        # search
    config.js                      # SHEET_ID, OAuth client ID, TMDB read token (public!)
    styles.css
.github/workflows/tv-tracker.yml   # daily cron + workflow_dispatch
```

The folder name `tv-tracker` has a hyphen, so it isn't importable; the job is
run with `tv-tracker/` as the working directory (`python -m job`). A new uv
dependency group `tv-tracker` holds `httpx`, `gspread`, `google-auth`,
`openai`, `pytest`.

`config.js` is served publicly, so the TMDB read token in it is downloadable
by anyone. Accepted: it's a free, read-only, revocable key. The OAuth client
ID and Sheet ID are not secrets.

## Sheet schema (the contract)

One spreadsheet, four tabs. **Rows are never deleted or reordered** — not by
the job, not by the app, not by hand. Manual browsing uses filter views,
which don't reorder the underlying rows. Every row carries its key in column
A; before writing to a cached row index, writers treat a key mismatch as a
stale read and re-read (see Writes).

### `Tracked` — app owns `active`; job owns `tvmaze_id`

| tmdb_id | tvmaze_id | name | first_air_year | poster_url | added_at | source | active | updated_at |
|---|---|---|---|---|---|---|---|---|

- `source`: `search` or `suggestion`. `added_at`: date in America/Toronto
  (`YYYY-MM-DD`).
- `active`: `TRUE`/`FALSE`. Untrack sets `FALSE`; re-tracking an inactive show
  sets it back to `TRUE` and resets `added_at` to today (no backlog from the
  gap).
- **Duplicates are tolerated, not prevented.** Readers collapse rows by
  `tmdb_id`: the show is tracked if any row for it is active; its `added_at`
  is the earliest active row's. Writers (Track/Untrack) apply to every row
  with that `tmdb_id`.
- `first_air_year` comes from TMDB at add time; it feeds the LLM prompts.

### `Cards` — job owns content columns; app owns `status`

| card_id | type | tmdb_id | show_name | headline | body | date | link | image_url | source_url | created_at | current | status | updated_at |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

- `type`: `episode` · `season` · `suggestion` · `news`
- `headline`: episode title / "Season N premieres" / show name / news headline.
- `body`: blank for episode/season; the LLM's reason for suggestions; the
  news summary for news.
- `status`: `new` → `noted` (episode/season/news) or `tracked` / `ignored`
  (suggestion). **Written only by the app.** The job writes `new` when it
  appends a row and never touches `status` again.
- `current`: `TRUE`/`FALSE`, **written only by the job**. Always `TRUE`
  except season cards whose announcement is obsolete (see Season cards).
- `card_id` (dedupe key):
  - `ep:{tmdb}:S{ss}E{ee}`
  - `season:{tmdb}:{n}:{air_date}`
  - `sugg:{tmdb}` — once ignored, never suggested again
  - `news:{tmdb}:{sha1(normalized source_url)[:8]}`
- **Column ownership:** after appending a row, the job may update only
  content columns (`show_name`, `headline`, `date`, `link`, `image_url`) on
  episode rows when TMDB data changes (e.g. "Episode 5" → real title), and
  `current` on season rows. The app only writes `status` + `updated_at`.
  The two writers never touch the same cell, so a Noted click landing between
  the job's read and write can't be overwritten.
- **Visibility:** the feed shows cards with `status = new` **and**
  `current = TRUE`, except episode, season and news cards whose show is not
  active (Untrack hides them immediately, client-side; they reappear if
  re-tracked). Suggestion cards are unaffected.

### `Schedule` — derived, per-show

| tmdb_id | airstamp | show_name | episode_label | network | image_url | refreshed_at |
|---|---|---|---|---|---|---|

- `airstamp`: ISO 8601 in America/Toronto; date-only when TVmaze has no time.
- Rewritten wholesale each run (the app never writes here, so index stability
  doesn't matter for this tab), **but per-show rows are carried forward** when
  that show's refresh fails (see Schedule).
- The app hides rows for inactive shows.

### `Meta` — job run status

| key | value |
|---|---|
| last_run_at | ISO timestamp |
| last_run_ok | `TRUE`/`FALSE` |
| schedule_week | `YYYY-MM-DD` (Monday) |
| failed_shows | comma-separated show names, or blank |
| failed_steps | e.g. `news`, `suggestions`, or blank |

## Daily job

GitHub Actions cron `0 10 * * *` (6 am Eastern) plus `workflow_dispatch`.
All runs share one fixed concurrency group (`concurrency: {group:
tv-tracker-sheet, cancel-in-progress: false}`), so a manual run started
during the cron run waits instead of overlapping (overlapping runs would read
the same existing ids and append duplicate cards).
Secrets: `TMDB_TOKEN`, `OPENAI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`,
`SHEET_ID`. Config: `OPENAI_MODEL` (chosen at implementation time),
`TZ=America/Toronto`, `NEWS_WINDOW_DAYS=7`, `NEWS_MEMORY_DAYS=30`,
`MAX_PENDING_SUGGESTIONS=3`. HTTP clients retry transient errors (3 tries,
backoff) before a show counts as failed.

Steps, in order. Only active tracked shows are processed.

1. **Load** all four tabs.
2. **Backfill `tvmaze_id`**: TMDB `external_ids` → IMDb id → TVmaze
   `/lookup/shows?imdb=`. Written by key: re-read column A of `Tracked`
   immediately before writing and write to every row whose `tmdb_id` matches.
   (Safe because rows are never deleted or reordered; the re-read is a guard
   against hand edits.)
3. **Episode cards** (stateless, so a missed run self-heals):
   - From `/tv/{id}`, pick seasons (`season_number > 0`) whose `air_date` is
     set and `≤ today`, starting from the **latest season that had premiered
     on or before `added_at`** (or the first season if none had). Fetch them
     in one call via `append_to_response=season/N,season/M,…` (TMDB allows
     up to 20).
   - Emit an episode card for each episode with
     `added_at ≤ air_date ≤ today` (both plain dates, Eastern) whose
     `card_id` doesn't exist.
   - For existing episode cards, compare content columns with the fresh data
     and queue an update if different.
   - Link = episode IMDb page (episode `external_ids`), fallback show IMDb
     page. Image = episode still, fallback poster.
4. **Season cards**: reconcile every season (`season_number > 0`) that
   either hasn't premiered in TMDB (air date unknown or `≥ today`) **or
   already has season cards**, whatever its date, and including a season
   TMDB no longer lists:
   - **Target id** = `season:{tmdb}:{n}:{air_date}` if TMDB has a date (past
     or future), else none.
   - **Append** the target only if it's missing **and** its date is
     `≥ today`. No new announcements for dates already past.
   - **Set `current`** on every card of that season: `TRUE` for the target
     id, `FALSE` for all others.
   - Examples: A → B hides A, shows B. B → A shows A again (unless you
     already noted it, since `status` is untouched). A date withdrawn or a
     season removed hides every card for it. A Sept 30 card corrected to
     Sept 26 during the Sept 27 run: the Sept 26 id isn't appended (past),
     and the Sept 30 card goes `current = FALSE`. A season that premiered on
     its announced date keeps its card current; episode cards take over from
     there.
5. **Schedule**: TVmaze `/shows/{id}/episodes`, keep this Mon–Sun by
   `airstamp` in Eastern. For a show whose fetch fails, carry forward its
   existing `Schedule` rows (they keep their old `refreshed_at`). If the
   week has rolled over, drop carried rows outside the new week. Rewrite the
   tab.
6. **Suggestions (LLM)**: only if pending (`status = new`) suggestion cards
   `< MAX_PENDING_SUGGESTIONS`; request `k = cap − pending`.
7. **News (LLM)**: one call across all active tracked shows.
8. **Write**: one Sheets `batchUpdate` for card appends + content updates +
   `current` flags; then `Schedule`; then `Meta`.
9. **Exit** non-zero if anything failed (any show, any step), *after*
   writing everything that succeeded. GitHub emails on failure; `Meta` tells
   the app.

### LLM calls

OpenAI Responses API with the `web_search` tool and JSON-schema structured
output. Schemas have an **object root** (Structured Outputs requires it):
`{"suggestions": [...]}` and `{"news": [...]}`. Sources are requested with
`include: ["web_search_call.action.sources"]`.

**Suggestions** — inputs: active tracked shows (`name (first_air_year)`),
ignored (`sugg:` rows with `status = ignored`: `show_name` + year from TMDB
at card creation, stored in `date`), pending suggestions. Asks for `k` shows
with exact title, first-air year and a one-sentence reason referencing a
specific tracked show; prefer currently airing / last 2 years, one older gem
allowed. Output: `{"suggestions": [{title, year, reason}]}`.

**News** — inputs: active tracked shows (`name (first_air_year) [tmdb_id]`),
headlines of news cards from the last `NEWS_MEMORY_DAYS`. Significant =
renewal, cancellation, premiere/release date announced or changed,
trailer/teaser, major casting. Ignore reviews, recaps, rankings, theories.
"An empty list is a good answer." Every item cites its source. Output:
`{"news": [{tmdb_id, headline, summary, source_url, published_date}]}`.

Draft prompt text lives in `job/prompts/`; refining it is the first
implementation milestone (see Build order).

### Validation

**Suggestions (confirmed):** TMDB search by title + year; drop if no match,
or already tracked (active or not), ignored, or pending. TMDB supplies id,
poster, link and year.

**News (cited, not confirmed):**
1. `tmdb_id` must be an active tracked show.
2. `source_url` must match (after normalizing scheme, `www.`, trailing slash,
   fragment and tracking parameters like `utm_*`; meaningful query
   parameters are kept) a URL in the web search call's returned sources or
   the response's `url_citation` annotations. Otherwise drop.
3. Fetch the page (5 s timeout, one try). If it fails or returns non-2xx,
   drop. If it exposes a publish date (`article:published_time`, JSON-LD
   `datePublished`, `<time datetime>`), that date replaces the model's; drop
   if older than `NEWS_WINDOW_DAYS`. If no date is found, fall back to the
   model's `published_date` with the same window check.
4. Dedupe against existing `news:` card ids (by source URL hash).

The app renders news cards with the source domain visible, so the reader
judges the source.

## App

Static page at `posts/tv_tracker/app/`, mobile-first, bottom tab bar.

### Auth

- GIS token model, `spreadsheets` scope. Tokens last about an hour.
- On load and whenever there's no valid token, the app shows a **"Connect
  Google"** button; requesting a token happens only from that click (Google
  requires a user gesture for the popup).
- If a Sheets call returns 401 or the token has expired, the pending action
  is kept in memory and the button reappears as **"Reconnect Google"**.
  After reconnecting, the pending action retries automatically.
- If the first Sheet read after sign-in returns 403 (account not shared on
  the Sheet), the app shows "This app is private" and nothing else. No email
  scope is requested; Google's own permission check does the job.
- Accepted: a quick reconnect tap roughly once per session after an hour
  idle. No 7-day re-consent because the OAuth app is in Production.

### Security requirements

Production-unverified lets any Google account complete sign-in, so the data
is protected by these, all required:
- The Sheet's general access is **Restricted**, shared only with the two
  accounts and the job's service account. Never "anyone with the link".
- The app loads **no third-party scripts** except Google Identity Services.
  The `spreadsheets` scope covers all of the signed-in user's spreadsheets;
  only the app's own code (in this repo) confines it to `SHEET_ID`.
- The service account is shared on this Sheet only. Its key lives only in
  GitHub Secrets.

### Views

- **Feed**: visible cards (see Cards → Visibility), newest first. Card =
  image left; title, subtitle (`body` for suggestions), date, link right;
  buttons `Noted`, or `Track` / `Ignore` for suggestions. News cards show the
  source domain and link.
- **This Week**: `Schedule` grouped by day, time + network, today
  highlighted. The app computes the current Toronto week (Monday date) and
  **only displays rows whose `airstamp` falls in it**. Header states, checked
  in order:
  1. `Meta.schedule_week` ≠ current week → "This week hasn't refreshed yet"
     (e.g. Monday before 6 am; last week's rows are filtered out).
  2. `last_run_ok` false or `last_run_at` older than 36 h → "Couldn't
     refresh: Severance, The Bear — showing last known times".
  3. Otherwise → "Updated 6:02 am"; an empty week here says "Nothing airing
     this week".
- **Shows**: TMDB search (tap → Track) above the active tracked list
  (Untrack).

### Writes

- On load, read all tabs once and map keys to row numbers.
- Every write is a single `spreadsheets.batchUpdate` (atomic across tabs).
  Before writing, the app re-reads column A of each target tab in the same
  round trip (`values.batchGet`) and aborts + reloads if a cached row's key no
  longer matches.
- **Noted / Ignore**: set `status` + `updated_at` on the card row.
- **Track (from suggestion or search)**: fresh-read `Tracked`, then one
  batchUpdate that
  - sets the suggestion card (if any) to `tracked`, and
  - if rows for `tmdb_id` exist: sets them all `active = TRUE` (and resets
    `added_at` if they were inactive); otherwise appends one row.
  Two people tapping Track at once can each append a row; readers collapse
  duplicates by `tmdb_id`, so the result is still correct. Retrying a Track
  is harmless for the same reason.
- **Untrack**: fresh-read column A of `Tracked` and set `active = FALSE` on
  every row with that `tmdb_id` **in the fresh read** (so duplicate rows
  another device appended after page load are included). Track builds its
  target rows from the fresh read the same way.
- The UI removes the card optimistically; if the write fails for a
  non-auth reason, the card is restored with a "couldn't save" toast.

## Testing

Job (pytest, no network; saved TMDB/TVmaze responses, canned LLM outputs,
in-memory fake sheet):
- `cards.py`: episode/season/schedule rows from fixtures.
- Season-boundary catch-up: show tracked in season 2, last successful run
  before season 2 ended, next run after season 3 premiered → cards for the
  missed season 2 finale and new season 3 episodes, none for earlier ones.
- `added_at` equal to an air date → that episode is included.
- Episode metadata correction → content columns updated, `status`
  untouched.
- Season date change → new card; old card `current = FALSE`; no card's
  `status` changes.
- Season date A → B → A → A `current = TRUE`, B `current = FALSE`.
- Season date withdrawn (unknown or season removed) → all its cards
  `current = FALSE`.
- Season date corrected into the past → no new card; old card
  `current = FALSE`.
- Noted click between the job's read and write → `status = noted` survives
  the job's write (job's batch contains no `status` cells).
- Partial schedule failure → failed show's rows carried forward with old
  `refreshed_at`; `Meta.failed_shows` set; exit code non-zero.
- Total outage → schedule unchanged (all carried), `last_run_ok = FALSE`.
- Backfill with a hand-inserted row mid-table → `tvmaze_id` lands on the
  row with the matching `tmdb_id`.
- Duplicate `Tracked` rows → collapsed correctly for processing.
- News validation: URL not in sources dropped; page date overrides model
  date; stale page dropped; unreachable page dropped.
- Suggestion validation: unresolvable, tracked, ignored and pending titles
  dropped.

App (`node --test` on `state.js` with a fake Sheets client):
- Two simultaneous Tracks from stale reads → two `Tracked` rows, collapsed
  to one active show; suggestion card `tracked`.
- Track of an inactive show → reactivated, `added_at` reset, no append.
- Untrack with duplicate rows, including one appended after page load → all
  rows inactive; show's cards hidden.
- First Sheet read returns 403 → "This app is private".
- This Week on a new Monday before the job runs → last week's rows hidden,
  "hasn't refreshed yet" shown.
- Expired auth during a write → pending action kept, "Reconnect" shown,
  retried after reconnect.
- Cached row key mismatch → write aborted, reload triggered.
- Schedule freshness states: healthy-empty, stale, partial failure.

Manual: a seeded test Sheet, which also produces the blog screenshots.

## Build order

1. Feasibility + prompts: TMDB/TVmaze clients and a `--dry-run` that prints
   validated suggestion and news output for a hand-written tracked list.
   Iterate prompts.
2. Sheet I/O, reconcile logic and the full job; GitHub Actions workflow.
3. App (auth → feed → schedule → search).
4. Blog post.

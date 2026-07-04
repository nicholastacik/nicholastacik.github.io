# Sub-project A: j-archive Scraper + Storage — Design

**Date:** 2026-07-04
**Status:** Approved (pending spec review)
**Part of:** the larger "Jeopardy data science" effort, which is phased into three
independently-built sub-projects:

- **A — Scraper + storage** (this doc): produce a committed, analysis-ready dataset.
- **B — Analysis toolkit**: date/game-type filtering, category clustering (Steps 3–4),
  general DS questions (Step 5). *Not designed yet.*
- **C — Quarto blog post**: interactive, reproducible narrative over the dataset.
  *Not designed yet.*

## Goal

Produce a compact, committed, analysis-ready dataset of all Jeopardy clues
(~500k rows) from [j-archive.com](https://j-archive.com), via a polite one-time
offline crawl. Downstream sub-projects (B, C) start from this frozen dataset and
never touch the network.

## Core principle: separate the non-reproducible step from the reproducible one

Scraping is slow, network-dependent, and rude to repeat. Rendering the blog post
in CI must be fast and reproducible. The **committed Parquet file is the
reproducibility boundary**: the raw crawl lives only on the author's machine; the
compact derived artifact travels with the repo, so anyone who clones (including
CI) gets the data without re-scraping.

A second separation applies *within* the scraper: **fetching** (slow,
network-bound, must not be repeated) is isolated from **parsing** (fast,
CPU-bound, will be iterated on). Raw HTML is cached on disk on first fetch, so the
network cost is paid exactly once and the parser can be re-run freely against the
cache.

## Architecture: three-stage offline pipeline, one CLI front door

```
jeopardy/                     # offline pipeline — repo root, OUTSIDE posts/
  main.py                     # click CLI: the single entry point
  fetch.py                    # network + local HTML cache (slow, polite)
  parse.py                    # raw HTML → clue records (pure, iterable)
  crawl.py                    # resumable orchestration over all games
  build_parquet.py            # games.jsonl → clues.parquet
  data/                       # ALL gitignored (local-only, heavy)
    html_cache/               #   raw fetched pages
    games.jsonl               #   faithful append-only archive

posts/jeopardy_ds/
  clues.parquet               # ← committed dataset artifact (~20–40 MB)
  index.qmd                   # the eventual blog post (Sub-project C)
```

### Stages

1. **fetch** (`fetch.py`) — `fetch(url) -> html`. Sequential, ~1 request/second
   with random jitter (~1–1.5s), a descriptive User-Agent identifying it as a
   personal research scraper (not impersonating a browser). Every fetched page is
   written to `data/html_cache/` keyed by URL/game_id; a cached page short-circuits
   the network.
2. **parse** (`parse.py`) — `parse(html) -> list[clue records]`. Pure function, no
   network. Re-runnable against the cache as the parser is refined.
3. **crawl** (`crawl.py`) — resumable orchestration: enumerate seasons → games,
   skip `game_id`s already present in `games.jsonl`, append one JSON object per
   game. The JSONL append-log doubles as the crawl checkpoint.
4. **build** (`build_parquet.py`) — normalize `games.jsonl` into one row per clue
   and write a zstd-compressed `clues.parquet` into `posts/jeopardy_ds/`.

## Scope

Scrape **every game** j-archive has, including special games (Tournament of
Champions, Teen/College, Celebrity, Masters, etc.). Each game is **tagged** with a
`game_type` so downstream filtering is a one-liner. Nothing is discarded at scrape
time; the analyst decides later what to include.

## Schema (one row per clue, in `clues.parquet`)

| Field | Example | Purpose |
|---|---|---|
| `game_id` | 7812 | j-archive game number; join key |
| `air_date` | 2020-01-06 | time-series analyses |
| `season` | 36 | grouping / era analysis |
| `game_type` | regular / toc / celebrity / … | filter dimension (B & C) |
| `round` | Jeopardy / Double Jeopardy / Final | difficulty tiers, final-J analysis |
| `category` | "WORLD CAPITALS" | category clustering (Step 3), common answers (Step 4) |
| `clue_value` | 400 | raw historical value; difficulty proxy; DD analysis |
| `row` | 1–5 | era-stable difficulty tier within a round (Step 5) |
| `column` | 1–6 | category slot; needed for DD-location heatmaps (Step 5) |
| `is_daily_double` | true/false | Step 5 |
| `dd_wager` | 2000 (null if not a DD) | how contestants bet, if shown |
| `clue` | "This planet is named for the Roman god of war" | displayed text (embeddings) |
| `answer` | "Mars" | correct response (Step 4) |

### Schema notes / gotchas

- **Jeopardy's "question/answer" is inverted.** The displayed *clue* is a statement
  ("This planet…"); the contestant responds as a question ("What is Mars?"). Fields
  are named `clue` (displayed) and `answer` (correct response) to stay unambiguous;
  they map to the informal "question"/"answer".
- **Dollar values doubled in Nov 2001** ($500 → $1000 top clue). `clue_value` is
  therefore not comparable across eras on its own. `row` (1–5) is kept as the
  era-stable difficulty tier — the honest "how hard is this level" signal.

## Storage

- `data/html_cache/` and `data/games.jsonl` — **gitignored** (local, heavy).
- `posts/jeopardy_ds/clues.parquet` — **committed** (~20–40 MB after zstd; text
  compresses ~4x, keeping it under GitHub's 100 MB limit without Git LFS).

Parquet chosen over SQLite (would exceed GitHub's limit uncompressed → forces LFS)
and over raw JSON (no columnar querying, awkward for pandas at scale). Parquet reads
straight into pandas via `pd.read_parquet()`.

## Entry point (click CLI)

`jeopardy/main.py` exposes a `@click.group()`:

```bash
python -m jeopardy crawl      # resumable fetch of all games → data/games.jsonl (+ html_cache/)
python -m jeopardy build      # data/games.jsonl → posts/jeopardy_ds/clues.parquet
python -m jeopardy all        # crawl, then build
# later (Sub-project B): python -m jeopardy analyze ...
```

The entry point orchestrates only; each subcommand is a thin wrapper over its
focused module. Analysis subcommands slot in here later without disturbing the
pipeline code.

## Dependencies (uv-managed)

Added via uv into a dedicated `scraper` dependency group so CI's
`uv sync --frozen` (render-only) stays lean and skips them:

```bash
uv add --group scraper httpx beautifulsoup4 lxml click
```

- `httpx` — HTTP client (fetch)
- `beautifulsoup4` + `lxml` — HTML parsing (parse)
- `click` — CLI (main). The CLI runs offline only, so `click` belongs in this group.

## Testing

Parser unit tests against a small set of saved fixture HTML pages, chosen to cover
the format edge cases that actually bite:

- a modern game (post-2001 values, standard board),
- a pre-2001 game (halved values),
- a tournament game (game_type tagging),
- a game with a missing/unrevealed clue (triple stumper / blank cell).

Fetching and crawling are thin and network-bound; the parser is where correctness
risk concentrates, so that's where tests focus.

## Explicitly out of scope (YAGNI)

- Contestant-level data (who rang in, right/wrong, running scores). On the page but
  needed by none of Steps 3–5; roughly doubles parser complexity. Add in a later
  scrape only if a contestant question arises.
- Any analysis code (Sub-project B).
- The blog post (Sub-project C).

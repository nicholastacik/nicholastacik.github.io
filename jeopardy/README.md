# jeopardy — offline j-archive scraper

Produces the committed dataset `posts/jeopardy_ds/clues.parquet` (one row per
Jeopardy clue) from an offline crawl of [j-archive.com](https://www.j-archive.com).
This is dev tooling — it is **not** executed when Quarto renders the site.

## Running

The scraper's runtime deps (`httpx`, `beautifulsoup4`, `lxml`, `click`, `pytest`)
live in the `scraper` uv dependency group, which is kept out of CI's
`uv sync --frozen`. So every command must pull that group in with
`--group scraper`, run **from the repo root**:

```bash
uv run --group scraper python -m jeopardy crawl   # fetch all games → data/games.jsonl (+ html_cache/)
uv run --group scraper python -m jeopardy build   # data/games.jsonl → posts/jeopardy_ds/clues.parquet
uv run --group scraper python -m jeopardy all     # crawl, then build
```

Tests:

```bash
uv run --group scraper pytest jeopardy/tests -v
```

The full `all` run takes ~2.5–4 hours (polite, ~1 req/s). It is **resumable**:
if interrupted, rerun and it skips games already in `data/games.jsonl`, and
re-parsing is free from the cached HTML in `data/html_cache/`.

## Layout

| File | Responsibility |
|---|---|
| `fetch.py` | Polite, on-disk-cached HTTP — network cost paid once |
| `parse.py` | `parse_game(html)` → metadata + board clues + Final Jeopardy |
| `crawl.py` | Resumable orchestration: seasons → games → `data/games.jsonl` |
| `build_parquet.py` | Curates JSONL → committed zstd `clues.parquet` |
| `main.py` | `click` CLI (`crawl` / `build` / `all`) |
| `data/` | gitignored raw layer: `html_cache/` + `games.jsonl` |

The `data/` layer is the faithful archive (local only); `clues.parquet` is the
compact, curated artifact that travels with the repo — the reproducibility
boundary. See `docs/superpowers/specs/2026-07-04-jeopardy-scraper-design.md`.

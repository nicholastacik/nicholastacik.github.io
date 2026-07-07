# Sub-project C · Phase 2 — Interactive Research Tool — Design

**Date:** 2026-07-07
**Status:** Approved (pending spec review)
**Part of:** the "Jeopardy data science" effort. Prior committed work: the scraper
(`clues.parquet`), clustering (`category_clusters.parquet`, `cluster_summary.parquet`,
`cluster_labels.csv`), the token analysis (`category_tokens.parquet` — top proper-noun
entities per cluster-type + an `n_qualifying_phrases` applicability signal), and the blog
post (`posts/jeopardy_ds/index.qmd`), which links to this tool at `research/`.

## Goal

A study page: pick a category **type**, see its most common **entities** ranked, and click
one to read its Wikipedia facts inline. It turns the token analysis into an actionable
"what do I actually study for this type of category" tool.

## Architecture

A new `python -m jeopardy research` CLI command reads the committed `category_tokens.parquet`
and `cluster_labels.csv`, embeds the per-type entity data as JSON into a **self-contained
HTML** file (inline CSS + vanilla JS, no build tooling, no external assets), and writes the
committed `posts/jeopardy_ds/research/index.html`. The blog post links to `research/`. Quarto
copies the `.html` as a static resource — the site's `_quarto.yml` `render` list only renders
`.qmd`, so this file ships as-is (served at `/posts/jeopardy_ds/research/`). Regenerating is
deterministic from committed data.

## Data embedded

One entry per cluster-type (all 50), sorted by `n_qualifying_phrases` descending:
`{cluster_id, name, applicability (= n_qualifying_phrases), entities: [{phrase, count}, ...]}`.
Entities come from `category_tokens.parquet` (already top-25 per cluster by rank); placeholder
rows (`phrase is None`, for zero-qualifying clusters) are dropped, so a non-studyable type has
an empty `entities` list.

## Layout (master-detail)

- **Left — type list:** the 50 types sorted by studyability (`applicability` desc). Low-
  applicability wordplay/grab-bag types (empty or tiny entity lists) sink to the bottom and are
  visually marked/dimmed ("not really studyable").
- **Main — entity list:** the selected type's ranked entities (phrase + occurrence count).
- **Detail — facts panel:** clicking an entity loads its Wikipedia summary **live** inline
  (lead extract + optional thumbnail + a link out to the full article).

## Wikipedia enrichment (client-side, live)

Vanilla JS in the page fetches on click — no build-time crawl, no embedded facts blob:
- Primary: the Wikipedia REST summary endpoint
  `https://en.wikipedia.org/api/rest_v1/page/summary/{title}` (CORS-enabled), with the entity
  phrase URL-encoded as the title.
- Fallback on 404 / disambiguation: the search/opensearch API to resolve the best-matching
  article title, then re-fetch the summary.
- Graceful degradation: if offline, unresolved, or the API errors, show just a Wikipedia
  search link for the phrase (no crash, no blank panel).
- Known limitation (accepted): ambiguous entities ("Mercury", "Richard III") may land on a
  disambiguation page or the wrong sense; acceptable for a personal study tool.

## Build code

New `jeopardy/analysis/research.py`:
- `build_research_data(tokens_df, labels) -> list[dict]` — pure, unit-testable: produces the
  50 per-type entries sorted by applicability desc, top entities per type, placeholder rows
  dropped.
- `render_html(data) -> str` — inject the JSON + the static HTML/CSS/JS template into one
  self-contained document.
- `run_research()` — read `config.CATEGORY_TOKENS_PATH` + `config.CLUSTER_LABELS_PATH`, write
  `config.RESEARCH_HTML_PATH` (`= _POST_DIR / "research" / "index.html"`), creating the dir.

New CLI command `research` (deferred import, alongside the others). New config path
`RESEARCH_HTML_PATH`. **No new dependencies** (pandas + stdlib; the JS is inline and runs in
the browser).

## Frontend quality + expected iteration

This is the one reader-facing UI in the project. Implementation will use the `frontend-design`
skill for the HTML/CSS/interaction quality. **Visual iteration after the first render is
anticipated** — the initial build produces a working, clean tool; the author will view it and
we expect one or more rounds of refinement (layout, styling, interaction feel) before it's
final. The plan should treat "generate a working, correct tool" and "polish how it looks" as
distinct steps.

## Testing / verification

- Unit-test `build_research_data` against the committed `category_tokens.parquet` +
  `cluster_labels.csv`: 50 entries, sorted by applicability desc, top entities present,
  placeholder (`phrase is None`) rows excluded so non-studyable types have empty entity lists.
- The page itself is client-side JS → verified by opening `research/index.html` in a browser:
  a type selects, its entities list, and clicking an entity fetches a real Wikipedia summary
  (with a graceful fallback when a title doesn't resolve). This is a browser check, not a unit
  test.

## Out of scope (YAGNI)

- Global entity search across types (chose the type-browser model).
- Build-time Wikipedia fact caching / offline facts (live client-side fetch instead).
- B2 Step-5 statistics (daily-double location, difficulty over time, Final-J mix).

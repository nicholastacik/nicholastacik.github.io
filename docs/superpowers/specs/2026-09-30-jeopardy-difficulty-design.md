# Jeopardy Difficulty Analysis — Design Spec

**Date:** 2026-09-30  
**Status:** Approved

## Overview

A new blog post (`posts/jeopardy_difficulty/`) that scores every Jeopardy clue on a 1–10 difficulty scale using Jev (TypeSafe AI's structured-output model), augments the dataset with per-clue player correctness data re-scraped from J-Archive, analyzes how difficulty relates to dollar value, round, era, game type, daily double, and category cluster, and embeds an interactive clue sampler filtered by difficulty and category.

The key credibility check: Jev difficulty vs actual player correctness rate. If LLM-scored difficulty explains correctness better than dollar value does, that's the headline result.

## Data Pipeline

Three stages, each producing a parquet:

### Stage 1 — Correctness scrape

Script: `posts/jeopardy_difficulty/pipeline/scrape_correctness.py`

- Walks every `game_id` in `posts/jeopardy_ds/clues.parquet`
- Fetches cached game HTML from the existing jeopardy_ds fetch cache (no new network requests for already-cached games)
- Parses contestant response rows: which player buzzed in, right or wrong
- Output: `posts/jeopardy_difficulty/pipeline/correctness.parquet`
  - Columns: `game_id`, `row`, `column`, `n_attempts`, `n_correct`
  - Join key: `(game_id, row, column)` — matches `clues.parquet`

### Stage 2 — Jev prompt spike

Script: `posts/jeopardy_difficulty/pipeline/spike_prompt.py` (throwaway)

- Samples ~500 clues stratified by dollar value and round to cover the full difficulty range
- Runs 2–3 prompt variants through Jev, requesting `difficulty` (int 1–10) and `confidence` (float)
- Outputs scored samples for manual review
- Winning prompt gets hardcoded into `score_jev.py`

### Stage 3 — Batch scoring + merge

Script: `posts/jeopardy_difficulty/pipeline/score_jev.py`

- Sends all 563k clues to Jev: input is `(clue, category, answer)`, output schema `{difficulty: int, confidence: float}`
- Estimated cost: ~$2–3 at $0.042/M input tokens, output free
- Merges with `correctness.parquet` and original `clues.parquet`
- Output: `posts/jeopardy_difficulty/clues_scored.parquet`
  - Original 14 columns + `difficulty`, `jev_confidence`, `n_attempts`, `n_correct`, `correctness_rate`

### Stage 4 — App data export

Script: `posts/jeopardy_difficulty/pipeline/build_app_data.py`

- Joins `../jeopardy_ds/category_clusters.parquet` + `cluster_labels.csv` to add `cluster_name` per clue
- Samples 2,000 clues per difficulty bucket (1–10), stratified by round and game type → ~20k clues total
- Exports compressed JSON: `posts/jeopardy_difficulty/app/data/clues.json`
- Columns kept: `clue`, `answer`, `category`, `cluster_name`, `difficulty`, `jev_confidence`, `round`, `game_type`, `air_date`

## Post Structure

File: `posts/jeopardy_difficulty/index.qmd`

### 1. Introduction

What makes a Jeopardy clue hard? Dollar value is the obvious answer — but is it actually the best predictor? We scored every clue with an LLM and found out.

### 2. Prompt Development

Short section on the spike: candidate prompts, where they disagreed on edge cases, illustrative examples of the easiest and hardest clues surfaced. Establishes trust in the scoring approach before the analysis.

### 3. Analysis

One chart per dimension, building toward a unified picture:

| Section | X-axis | Y-axis |
|---|---|---|
| Dollar value | Clue value ($200–$2000) | Mean Jev difficulty |
| Round | Jeopardy / Double Jeopardy / Final | Difficulty distribution |
| Daily double | DD vs non-DD | Difficulty distribution |
| Era | Year (1984–2026) | Mean difficulty over time |
| Game type | Regular / TOC / Celebrity / Masters / etc. | Difficulty distribution |
| Category cluster | Cluster name (from jeopardy_ds) | Mean difficulty per cluster |
| Validation | Player correctness rate | Jev difficulty (scatter) |

The validation chart is the key result: if Jev difficulty correlates with correctness rate more tightly than dollar value does, that's the headline.

### 4. Interactive Tool

Embedded iframe at the end of the post. See Interactive Tool section below.

## Interactive Tool

Location: `posts/jeopardy_difficulty/app/`  
Pattern: same as `posts/chess/app/` and `posts/codenames/app/` — registered as a resource in `_quarto.yml`, embedded via iframe.

### UI

- **Difficulty range slider** (1–10, range selection e.g. 5–7)
- **Filters:** Round (Jeopardy / Double Jeopardy / Final), Game type, Year range, Category cluster (dropdown of cluster names)
- **Clue card:** category name → clue text → "Reveal Answer" button → answer + Jev difficulty score
- **"Next Clue" button** — samples another clue from the filtered pool

### Data

- Loaded from `app/data/clues.json` at page load (~20k rows, well under 1MB compressed)
- Filtering and sampling done client-side in JS
- No backend required

## File Layout

```
posts/jeopardy_difficulty/
├── index.qmd
├── thumbnail.png
├── clues_scored.parquet          # built by pipeline
├── pipeline/
│   ├── scrape_correctness.py
│   ├── spike_prompt.py           # throwaway spike script
│   ├── score_jev.py
│   └── build_app_data.py
└── app/
    ├── index.html
    ├── app.js
    └── data/
        └── clues.json            # built by build_app_data.py
```

## _quarto.yml additions

```yaml
resources:
  - "posts/jeopardy_difficulty/app/**"
```

## Dependencies

- Jev API (TypeSafe AI) — early access; API key needed before Stage 3
- Existing jeopardy_ds fetch cache for Stage 1 (no re-fetching)
- `posts/jeopardy_ds/category_clusters.parquet` + `cluster_labels.csv` for Stage 4 and the tool

## Open Questions

- Jev API client library / auth pattern — needs verification once early access is confirmed
- J-Archive correctness HTML structure — needs a spot-check of a cached game page before writing the scraper

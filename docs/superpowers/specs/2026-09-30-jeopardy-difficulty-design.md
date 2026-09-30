# Jeopardy Difficulty Analysis — Design Spec

**Date:** 2026-09-30  
**Status:** Approved (revised)

## Overview

A new blog post (`posts/jeopardy_difficulty/`) that scores Jeopardy clues on a 1–10 difficulty scale using Jev (TypeSafe AI's structured-output model), augments the dataset with per-clue player response counts re-scraped from J-Archive, and analyzes how difficulty relates to dollar value, round, era, game type, daily double, and category cluster. An interactive clue sampler embedded at the end lets readers explore by difficulty and category.

**Headline question:** Can an AI predict which clues stump contestants better than the dollar value does?

**Lead with examples:** cheap clues that stumped everyone, expensive clues everyone found easy, and clues Jev badly misjudged. Those are more compelling than seven equally weighted charts. The prompt development section moves behind the main findings.

**Scope:** text-only clues from regular-game board rounds only for the initial analysis and sampler. Media clues (39,108 rows where `media=True`) are excluded — without the image/audio, Jev is scoring an incomplete clue. Daily Doubles and Final Jeopardy are analyzed separately since only one contestant responds.

**Phased approach:** validate the scoring signal on a few thousand clues before committing to full-corpus scoring.

## Data Pipeline

### Stage 1 — Correctness scrape

Script: `posts/jeopardy_difficulty/pipeline/scrape_correctness.py`

- Walks every `game_id` in `posts/jeopardy_ds/clues.parquet`
- Fetches cached game HTML from the existing jeopardy_ds fetch cache (no new network requests)
- Parses contestant response rows: for each clue cell, counts correct and incorrect responses
- **Triple Stumpers** are marked `class="wrong"` in J-Archive HTML without a contestant name — these count as incorrect responses, not as "no attempt." The scraper must distinguish this case from a missing record.
- **Final Jeopardy** and **Daily Doubles** are flagged separately; their response structure differs from regular board clues
- Output: `posts/jeopardy_difficulty/pipeline/correctness.parquet`
  - Columns: `game_id`, `round`, `row`, `column`, `n_right`, `n_wrong`, `clue_type`
  - `clue_type`: `board` | `daily_double` | `final`
  - `row` and `column` are null for Final Jeopardy; handled explicitly, not joined on null keys
  - **Join key: `(game_id, round, row, column)`** — round is required to disambiguate Jeopardy vs Double Jeopardy cells that share the same row/column coordinates
  - A one-to-one join assertion runs after the merge; any duplicates abort with a clear error

### Stage 2 — Jev prompt spike (validation phase)

Script: `posts/jeopardy_difficulty/pipeline/spike_prompt.py` (throwaway)

- Samples ~2,000 text-only, regular-game board clues stratified by dollar value and round
- These clues are held out from Stage 3's scoring: prompt development must not touch the test set
- Runs 2–3 prompt variants through Jev, requesting `difficulty` (int 1–10) and `confidence` (float)
- Outputs scored samples for manual review; winning prompt is hardcoded into `score_jev.py`
- Validates signal: check that Jev difficulty correlates with `n_right / (n_right + n_wrong)` on this sample before proceeding to full-corpus scoring

### Stage 3 — Batch scoring

Script: `posts/jeopardy_difficulty/pipeline/score_jev.py`

- Scores text-only clues (`media=False`) only — ~524k clues
- Input to Jev: `(clue, category, answer)`, output schema `{difficulty: int, confidence: float}`
- Estimated cost: ~$2–3 at $0.042/M input tokens, output free
- Spike clues are scored with the same prompt so they're included in the final dataset

### Stage 4 — Merge

Script: `posts/jeopardy_difficulty/pipeline/merge.py`

- Left-joins `clues.parquet` + `correctness.parquet` on `(game_id, round, row, column)`
- Asserts one-to-one join; logs any unmatched rows
- Joins Jev scores from Stage 3
- Output: `posts/jeopardy_difficulty/clues_scored.parquet`
  - Original 14 columns + `difficulty`, `jev_confidence`, `n_right`, `n_wrong`, `clue_type`
  - `correctness_rate` is **not** pre-computed — aggregations are done at analysis time in the post so the definition stays explicit and flexible

### Stage 5 — App data export

Script: `posts/jeopardy_difficulty/pipeline/build_app_data.py`

- Filters to text-only, regular-game board clues with at least one response recorded
- Joins `../jeopardy_ds/category_clusters.parquet` + `cluster_labels.csv` to add `cluster_name`
- Samples 2,000 clues per difficulty bucket (1–10), stratified by round and game type → ~20k clues total
- Exports compressed JSON: `posts/jeopardy_difficulty/app/data/clues.json`
- Columns: `clue`, `answer`, `category`, `cluster_name`, `difficulty`, `jev_confidence`, `round`, `game_type`, `air_date`

## Post Structure

File: `posts/jeopardy_difficulty/index.qmd`

### 1. Introduction

Can an AI predict which Jeopardy clues stump contestants better than the dollar value does? We scored every text clue with an LLM and found out. Lead with three vivid examples: a $200 clue nobody got right, a $2000 clue everyone answered, and one where Jev was confidently wrong.

### 2. Analysis

One chart per dimension. Analysis is restricted to regular-game board clues (`media=False`, `round != Final`, `is_daily_double == False`) unless noted.

| Section | Notes |
|---|---|
| Dollar value vs correctness | Baseline: does board position actually predict who gets it right? |
| Jev difficulty vs dollar value | How well does LLM difficulty track the board position? |
| **Validation: Jev vs correctness** | Split by game (held-out). Compare Brier score of dollar-value-only baseline vs baseline + Jev difficulty. This is the headline result. Account for era (post-2001 dollar doubling) and round. |
| Era | Mean Jev difficulty by year — has the show gotten harder? |
| Game type | Regular / TOC / Celebrity / Masters distributions |
| Category cluster | Mean difficulty per cluster (linked to jeopardy_ds clusters) |
| Daily Double & Final | Analyzed separately: correctness rate and Jev difficulty for DDs; Final stumper rate by year |

**Validation methodology:** split the dataset by game (train/test split at the game level, not the clue level, to avoid leakage). Prompt development happens entirely outside the test set. Report Brier score with uncertainty. Dollar value baseline uses era-adjusted values (pre/post 2001 doubling).

### 3. Prompt Development

Short section after the main findings: candidate prompts, edge case disagreements, examples of clues where prompts diverged. This comes after the headline so readers trust the result before seeing how the sausage was made.

### 4. Interactive Tool

Embedded iframe. See Interactive Tool section.

## Interactive Tool

Location: `posts/jeopardy_difficulty/app/`  
Pattern: same as `posts/chess/app/` and `posts/codenames/app/` — registered as a resource in `_quarto.yml`, embedded via iframe.

**Scope:** text-only, regular-game board clues only (consistent with the analysis scope).

### UI

- **Difficulty range slider** (1–10, range selection e.g. 5–7)
- **Filters:** Round, Year range, Category cluster (dropdown of cluster names)
- **Clue card:** category name → clue text → "Reveal Answer" button → answer + Jev difficulty score
- **"Next Clue" button** — samples another from the filtered pool client-side

### Data

- Loaded from `app/data/clues.json` at page load (~20k rows, well under 1MB compressed)
- All filtering and sampling in JS; no backend

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
│   ├── merge.py
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
- Existing jeopardy_ds fetch cache for Stage 1
- `posts/jeopardy_ds/category_clusters.parquet` + `cluster_labels.csv` for Stage 5 and the tool

## Open Questions

- Jev API client library / auth pattern — needs verification once early access confirmed
- J-Archive correctness HTML structure for Triple Stumpers and contestant response rows — spot-check a cached game page before writing the scraper
- Era adjustment cutoff for dollar value baseline: 2001 is the standard but worth verifying against the data

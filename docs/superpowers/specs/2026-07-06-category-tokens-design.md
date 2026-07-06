# Most Common Tokens per Category-Type — Design

**Date:** 2026-07-06
**Status:** Approved (pending spec review)
**Part of:** the "Jeopardy data science" effort. Prior work: Sub-project A (scraper →
`clues.parquet`, 563k clues) and Sub-project B Phase 1 (category clustering → 50 named
cluster-types in `category_clusters.parquet` / `cluster_summary.parquet` /
`cluster_labels.csv`). This is the next analytical step; after it comes **Sub-project C**
(the Quarto blog post + a linked interactive research-tool HTML page), designed separately.

## Goal

For each of the 50 cluster-types, surface the most common **and distinctive** entities
worth studying — mined from clue **and** answer text — plus an automatic signal for which
types this analysis is even meaningful for ("not applicable to all").

## Why not just the answers

The correct response often isn't the studyable entity: "What year was Richard III born?"
has answer *1452*, but the thing to know is **Richard III**, which lives in the clue. So
tokens must be mined from **clues + answers together**, not answers alone. And plain
lowercased word/n-gram TF-IDF reintroduces the problem in reverse — the word "Richard"
dominates and "Richard III" is lost. The fix is entity-aware tokenization.

## Unit

The 50 cluster-types from `category_clusters.parquet`. (Chosen over raw category names,
which are too sparse in the long tail; raw-name lookup can be added to the research tool
later.)

## Token = capitalized proper-noun phrase

A maximal-munch regex extracts runs of Capitalized words — allowing regnal numerals and
lowercase connectors — as single phrase tokens: `Richard III`, `Elizabeth I`,
`World War II`, `United States of America`, `Supreme Court`. This is a transparent,
deterministic "poor man's NER" (no model): Jeopardy clue prose is normal mixed-case
English, so proper nouns are already marked by capitalization.

- Regex intent: `[A-Z][a-z]+` head, then zero-or-more of ` [A-Z][a-z]+`, ` [IVX]+`
  (regnal/era numerals), or a small connector set (` of`, ` the`, ` and`) followed by a
  capitalized word.
- A small **stoplist** drops single-word capitalized tokens that are sentence-initial or
  pronominal clue-starters (`This, These, That, The, A, An, He, She, It, In, On, Of,
  His, Her, Its, You, We, They, …`) so the first word of a clue isn't mistaken for an
  entity. (Multi-word phrases are kept; the stoplist applies to single-token candidates.)

## Ranking: c-TF-IDF with a minimum-frequency floor

Per cluster, rank the extracted phrases by **c-TF-IDF** (treat each cluster as one
document; score phrases by how distinctive they are to that cluster vs the other 49),
subject to a **minimum-frequency floor**: a phrase must appear ≥ `min_freq` (default 5)
times within the cluster to qualify. This yields phrases that are both **common** and
**characteristic**, not rare-but-distinctive noise. Keep the top `top_n` (default 25)
per cluster.

## Applicability signal (measured, not hand-decided)

Each cluster gets `n_qualifying_phrases` = how many distinct phrases clear the frequency
floor. Entity-heavy types (U.S. Presidents, World Geography) score high; wordplay and
grab-bag types (4-LETTER WORDS, HOMOPHONES, POTPOURRI) score near zero because their
answers/clues don't repeat entities. So "which categories is this applicable to" is a
computed number the post can rank by — a finding in itself.

## Data flow

`category_clusters.parquet` (instance → cluster_id) ⋈ `clues.parquet`
(on `game_id, round, category`) → all clue+answer text per cluster → `extract_phrases`
→ c-TF-IDF rank with min-freq floor. No re-embedding; reuses committed artifacts only.

## Artifact (committed)

`posts/jeopardy_ds/category_tokens.parquet` — one row per (cluster, ranked phrase):
`cluster_id (int), rank (int), phrase (str), count (int), tfidf_weight (float),
n_qualifying_phrases (int)` (the last repeated per cluster for convenience). Top-N rows
per cluster. Small; read by the post and research tool with pandas only.

## Code

New `jeopardy/analysis/tokens.py`:
- `extract_phrases(text: str) -> list[str]` — regex proper-noun phrase extraction +
  stoplist.
- `cluster_top_phrases(clusters_df, clues_df, min_freq=5, top_n=25) -> pd.DataFrame` —
  join, per-cluster phrase counts, c-TF-IDF rank with floor, plus `n_qualifying_phrases`.
- `run_tokens()` — read `config.CATEGORY_CLUSTERS_PATH` + `config.PARQUET_PATH`, write
  `config.CATEGORY_TOKENS_PATH`.

New CLI command: `uv run --group analysis python -m jeopardy tokens`.
New config path: `CATEGORY_TOKENS_PATH = _POST_DIR / "category_tokens.parquet"`.

No new dependencies (reuses `scikit-learn` / `pandas` already present; regex is stdlib).

## Testing

- `extract_phrases`: grabs "Richard III" as one phrase; keeps "World War II"; handles a
  connector ("United States of America"); drops a sentence-initial "This"/"The"; returns
  nothing entity-like from a wordplay sentence.
- `cluster_top_phrases`: on toy clusters, an entity cluster (repeated "Abraham Lincoln")
  yields a high `n_qualifying_phrases` and ranks that phrase top; a wordplay-like toy
  cluster (all distinct words) yields `n_qualifying_phrases == 0`.

## Out of scope (YAGNI)

- The blog post and interactive research tool (Sub-project C, next).
- NER models (explicitly rejected — capitalization heuristic instead).
- Per-raw-category-name lookup (may be added to the research tool later).

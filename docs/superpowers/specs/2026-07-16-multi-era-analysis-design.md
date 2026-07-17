# Multi-Era Filterable Study Tool + Entity Dedup — Design

**Date:** 2026-07-16
**Status:** Approved (pending spec review)
**Part of:** the "Jeopardy data science" effort. A revision of the shipped analysis after
first-look feedback on the research tool. Builds on the committed stable taxonomy
(`category_clusters.parquet`, `cluster_labels.csv` — 50 named types) and reworks the token
analysis, the research tool, and one post fix.

## Goals

1. Make the analysis **filterable by era** — recompute what's common for clues since 1980 /
   1990 / 2000 / 2010 / 2020, over the *same* 50 types, so you can watch what to study shift
   over time on a stable spine.
2. **Deduplicate entities** so variants collapse (Emmy/Emmys; Bohr / Niels / Niels Bohr;
   Niels / Neils).
3. **Sort entities by frequency** (most common first) in the tool.
4. **Fix the Chrome failure** of the post's cluster scatter.

## Non-goals

- Re-embedding or re-clustering per era (the taxonomy stays fixed — a filter is only
  meaningful within a fixed frame). `category_clusters.parquet` and `cluster_labels.csv` are
  unchanged.
- Re-scoping the blog post to a single era (it keeps its all-time 1984–2026 narrative).

## Era model

Five **cumulative** cutoffs, each = clues with `air_date >= YYYY-01-01`:
`ERA_CUTOFFS = [1980, 1990, 2000, 2010, 2020]`. 1980 ≈ all-time (data starts 1984). "Since"
matches the study framing ("what recurs if I care about play from year X onward").

## Pipeline changes (`jeopardy/analysis/tokens.py`)

### Entity dedup (Moderate) — applied per cluster, before ranking

Canonicalize the extracted phrases within each cluster, summing counts and keeping the
dominant (highest-count) surface form:
1. **Plurals:** merge `X` with `X+"s"`/`X+"es"` (case-insensitive comparison).
2. **Partial ↔ full names:** merge a shorter phrase into a longer one in the same cluster
   when the shorter's tokens are a contiguous subsequence of the longer's (so `Bohr` and
   `Niels` fold into `Niels Bohr`). Merge into the longest containing form.
3. **Misspellings:** merge two phrases with Levenshtein distance ≤ 1 within a cluster
   (`Niels`/`Neils`). Implemented with a small stdlib helper (no new dependency).

The `tokens` command emits a **merge report** (`X + Y → Z`, per cluster) to a review file
(`posts/jeopardy_ds/notes/dedup-merges.md`, which is render-excluded). **Gate:** the author
reviews this report on real data before the regenerated artifacts are committed; the merge
rules/threshold are tuned from what the report shows.

### Per-era recomputation

For each era cutoff, filter the merged `category_clusters ⋈ clues` rows to
`air_date >= cutoff`, then run phrase extraction → dedup → c-TF-IDF (min-freq floor) exactly
as today, but **rank entities by `count` descending** (tiebreak: tfidf_weight desc, then
phrase), keeping `top_n` per (era, cluster). c-TF-IDF is still computed (idf within that era's
cluster set) and drives the applicability signal, but no longer the visible order.

### Artifacts (regenerated, committed)

- `posts/jeopardy_ds/category_tokens.parquet` — now long-format with an `era` column:
  `era (int cutoff), cluster_id, rank, phrase, count, tfidf_weight`. Top-N per (era, cluster),
  count-sorted, deduped.
- `posts/jeopardy_ds/category_eras.parquet` — per (era, cluster) stats:
  `era, cluster_id, size (category-instances in that era assigned to the cluster),
  share (size / total era instances), n_qualifying_phrases (applicability)`.
- `cluster_labels.csv`, `category_clusters.parquet` — **unchanged** (stable taxonomy).

New config: `ERA_CUTOFFS = [1980, 1990, 2000, 2010, 2020]`;
`CATEGORY_ERAS_PATH = _POST_DIR / "category_eras.parquet"`;
`DEDUP_MERGES_PATH = _POST_DIR / "notes" / "dedup-merges.md"`.

## Research tool changes (`jeopardy/analysis/research.py`)

- `build_research_data` produces **per-era** data: for each era, the 50 types with
  `{cluster_id, name, applicability, prevalence (share), entities: [{phrase, count}] count-desc}`.
  Embed all five eras: `DATA = {eras: [...], byEra: {"<cutoff>": [ ...types sorted by
  applicability desc... ]}}`.
- The page gains an **era selector** (segmented control: Since 1980 → 2020), defaulting to
  **2010** (modern, good sample). Changing it re-sorts the type list by that era's studyability,
  swaps each type's entity list (count-sorted, deduped) for that era, and shows a **prevalence
  indicator** per type. The 50 types stay fixed so entities/prevalence visibly shift as the era
  slides. All filtering is instant, client-side. Live Wikipedia fetch unchanged.
- Fold in the deferred nits: `write_text(..., encoding="utf-8")`; tighten the two structural
  tests to assert the dim/marking behavior and drop the operator-precedence quirk.

## Post change (`posts/jeopardy_ds/index.qmd`)

- **Chrome fix:** switch the `fig-clusters` scatter from plotly WebGL (`render_mode="webgl"`)
  to SVG (`render_mode="svg"`) with a smaller stratified sample (~4,500 points) so it loads in
  Chrome and Firefox. Static/interactive otherwise unchanged.
- The post reads `category_tokens.parquet`, which now has an `era` column — its all-time tables
  (§6) filter `era == 1980`. `category_eras.parquet`'s all-time row supplies applicability.
- Add one sentence in §7 noting the tool is now filterable by era.
- Keep the all-time narrative and numbers.

## Data flow

`category_clusters.parquet` (instance→cluster, stable) ⋈ `clues.parquet` (air_date, clue,
answer) → per era: filter by date → extract phrases → dedup → count-sort + c-TF-IDF → write
`category_tokens.parquet` (+ merge report) and `category_eras.parquet`. The research generator
+ post read these committed artifacts. No embeddings/UMAP recompute.

## Testing

- **Dedup:** unit-test each rule — plural merge (Emmy+Emmys→Emmy), component merge
  (Bohr+Niels→Niels Bohr), fuzzy merge (Niels+Neils, distance ≤1), and a *negative* case
  (two distinct short names that must NOT merge).
- **Per-era tokens:** on a small fixture with clues spanning eras, assert rows exist per era,
  are count-sorted, deduped, and a recent-era view differs from all-time.
- **Prevalence:** `category_eras.parquet` shares per era sum to ~1 across clusters.
- **build_research_data:** per-era structure, prevalence present, entities count-sorted,
  50 types per era.
- **Merge report review** (human gate) and **browser check** of the tool (era selector,
  count-sorted entities, prevalence) + the post scatter loading in Chrome.

## Out of scope (YAGNI)

- Decade *buckets* (chose cumulative "since"). Independent per-era clustering (chose stable
  taxonomy). B2 Step-5 statistics.

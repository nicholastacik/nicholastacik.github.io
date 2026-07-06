# Sub-project B · Phase 1 — Category Clustering (Step 3) — Design

**Date:** 2026-07-05
**Status:** Approved (pending spec review)
**Part of:** the "Jeopardy data science" effort. Sub-project A (scraper) is done and
produced the committed `posts/jeopardy_ds/clues.parquet` (563,266 clues). Sub-project B
(analysis) is split into phases:

- **B · Phase 1 — Category clustering** (this doc): discover the most common *types*
  of categories. Done first because what it reveals about the data's semantic
  structure will inform the later phases.
- **B · Phase 2 — Pandas analysis toolkit** (Steps 4–5: common answers, daily-double
  location, difficulty over time, Final-J categories, game-type comparisons). *Not
  designed yet.*
- **C — Quarto blog post**: interactive, reproducible narrative. *Not designed yet.*

## Goal

Discover the most common **types** of Jeopardy categories — to guide what to study —
by embedding every category instance and clustering the embeddings. Deliver committed,
analysis-ready artifacts (cluster assignments, 2D coordinates, per-cluster labels) that
the eventual blog post reads directly.

## Core principle: offline compute, committed artifacts (same boundary as the scraper)

Embedding ~123k documents needs `torch` + a downloaded model, and clustering is heavy
and only semi-deterministic. None of that belongs in CI or the rendered post. So the
compute runs offline on the author's machine and commits small derived artifacts; the
post reads those with pandas only. `torch`/`umap`/`sklearn` never touch CI.

A second boundary mirrors fetch/parse: **embedding** (slow, heavy) is separated from
**clustering** (fast, re-tunable). The embedding matrix is cached to disk, so `k` and
UMAP can be re-run freely without re-encoding.

## The unit: category instances

One document per **category instance** = one `(game_id, round, category)` group. All
~123k instances are clustered (not deduped by name): because the goal is the *most
common* types, letting a perennial category type recur across thousands of games
naturally frequency-weights the clusters — cluster size then reads directly as "how
common this type is."

## Document construction

For each instance, build one text document:

```
CATEGORY NAME. <clue → answer>; <clue → answer>; ... (clue→answer pairs shuffled)
```

- **Category name first** as the anchor (it is the category's title/label).
- The **clue→answer pairs are shuffled** per document, driven by a **fixed global seed
  plus a stable per-instance index** — so ordering is non-systematic across the corpus
  (no position consistently carries a role, removing positional bias) yet fully
  **reproducible** (same seed → identical documents → identical embeddings → identical
  clusters).
- No front-loading needed for truncation insurance: the 512-token model (below) fits
  essentially every instance (~200–380 tokens worst case).

## Embedding

- Model: **`BAAI/bge-small-en-v1.5`** via `sentence-transformers` — local, free, no API
  key, deterministic on CPU. 512-token window (covers full category documents without
  truncation), 384-dim output (compact for storage/clustering/UMAP).
- Chosen over `all-MiniLM-L6-v2` (256-token limit would truncate longer categories) and
  over an embeddings API (cost + external dependency; no quality need at this scale) and
  over TF-IDF (bag-of-words misses semantics like PENNE/RIGATONI → pasta).
- The ~123k × 384 embedding matrix is **cached** to `jeopardy/data/` (gitignored,
  ~190 MB, regenerable) alongside a small instance-index parquet, so clustering re-runs
  skip re-encoding.

## Clustering + visualization

- **KMeans** (fixed seed) on the full 384-dim embeddings → a `cluster_id` for every
  instance. Every instance is assigned (no noise bucket), so cluster sizes partition the
  corpus and rank cleanly as "most common types." `k` (default ~50) is chosen by a quick
  size/silhouette sweep plus eyeballing the auto-labels; deliberately over-segmenting is
  fine (big clusters surface perennial types; fine splits stay interpretable).
- Chosen over UMAP→HDBSCAN (auto-discovers count but produces a large, awkward "noise"
  bucket and is harder to rank) and hierarchical (full linkage on 123k points is
  memory-prohibitive).
- **UMAP** (seeded) reduces embeddings to 2D **only for visualization** (a scatter plot
  in the eventual post) — not for the clustering itself.

## Cluster labeling (three-part deterministic fingerprint)

Each cluster gets a self-describing, free, deterministic fingerprint:
1. **Top category names** — most frequent actual category names in the cluster (e.g.
   `U.S. PRESIDENTS (312), THE PRESIDENCY (188), …`).
2. **Centroid exemplars** — the instances nearest the cluster center (most typical
   members), shown with a clue or two.
3. **Top distinctive terms** via **c-TF-IDF** — terms common inside the cluster but rare
   across the corpus (surfaces `inauguration` over `the`).

## Optional LLM naming (enrichment layer, not pipeline)

Human-friendly cluster names are an **optional enrichment** layered on top of the
deterministic core — they do not change the reproducible pipeline.

- `cluster` emits **`cluster_naming_prompt.md`**: every cluster's fingerprint formatted
  ready to paste into an LLM.
- `name-clusters` (optional CLI) reads the fingerprints and calls the **OpenAI API**
  (default `gpt-4o-mini`, one batched call, est. one-time cost ~$0.01–0.30) to write
  **`cluster_labels.csv`** (`cluster_id, name`). Requires `OPENAI_API_KEY` in the env.
  Naming can equivalently be done for free by pasting `cluster_naming_prompt.md` into the
  ChatGPT web app and filling `cluster_labels.csv` by hand — the script is a convenience.
- The summary artifact and the eventual post read `cluster_labels.csv` **if present**,
  falling back to the auto-fingerprint label otherwise.

`cluster_labels.csv` is a **committed, human/LLM-curated artifact** (like a hand-edited
label file), deliberately outside the deterministic pipeline: re-running `name-clusters`
may yield different names, and that is fine.

## Artifacts

**Committed** (in `posts/jeopardy_ds/`):
- `category_clusters.parquet` — one row per instance: `game_id, round, category,
  cluster_id, umap_x, umap_y` (~123k rows, a few MB).
- `cluster_summary.parquet` — one row per cluster: `cluster_id, size,
  top_category_names, top_terms, exemplars`.
- `cluster_naming_prompt.md` — generated paste-ready naming prompt.
- `cluster_labels.csv` — optional curated `cluster_id → name` map.

**Gitignored** (`jeopardy/data/`): the embedding matrix cache (`embeddings.npy`) and the
instance-index parquet; the downloaded model (in the HF cache).

## Code layout

A new `jeopardy/analysis/` subpackage (the flat top-level package stays for the scraper):

```
jeopardy/
  analysis/
    __init__.py
    documents.py      # build_documents(): clues.parquet -> instance docs (seeded shuffle)
    embed.py          # encode with bge-small-en-v1.5, cache the matrix
    cluster.py        # KMeans + UMAP
    label.py          # three-part fingerprint, cluster_summary, naming-prompt
    name_clusters.py  # optional OpenAI naming -> cluster_labels.csv
  config.py           # + analysis constants (model, seeds, k, paths, OpenAI model)
  main.py             # + embed / cluster / name-clusters commands
  data/               # gitignored: embeddings cache + instance index
```

## CLI

```bash
uv run --group analysis python -m jeopardy embed              # docs + embed -> cached matrix
uv run --group analysis python -m jeopardy cluster --k 50     # cluster + umap + label -> committed artifacts + naming prompt
uv run --group analysis python -m jeopardy name-clusters      # optional: OpenAI -> cluster_labels.csv (needs OPENAI_API_KEY)
```

## Dependencies (uv-managed)

A new offline **`analysis`** dependency group, kept out of CI's `uv sync --frozen`:

```bash
uv add --group analysis sentence-transformers scikit-learn umap-learn openai
```

- `sentence-transformers` (pulls `torch`) — embedding
- `scikit-learn` — KMeans, TfidfVectorizer (c-TF-IDF)
- `umap-learn` — 2D projection
- `openai` — optional cluster naming

`pandas`/`pyarrow` are already main deps; the eventual post reads the artifacts with
pandas only — no `torch`/`umap`/`sklearn`/`openai` in CI.

## Reproducibility

Fixed seeds for the document shuffle, KMeans, and UMAP; pinned model name
(`bge-small-en-v1.5`); pinned deps via `uv.lock`. Same inputs → identical clusters. The
only non-deterministic piece is optional LLM naming, isolated in the committed
`cluster_labels.csv` curated artifact.

## Testing

- **documents:** unit-test document construction and seeded-shuffle determinism on a
  tiny in-memory fixture (name first; same seed → identical order; different instances →
  different orders).
- **label:** unit-test c-TF-IDF term selection, top-category-name counting, and exemplar
  selection on toy data (deterministic, no model).
- **cluster:** unit-test the KMeans+UMAP pipeline *shape* on a small synthetic embedding
  matrix (assert output schema, `cluster_id` range, 2D coords) — the real model is not
  run in tests.
- **embed:** test the cache behavior of the encode wrapper (cached matrix short-circuits
  re-encoding); the real `bge` model is **not** loaded in tests (too heavy).
- **name-clusters:** test parsing/CSV-writing against a stubbed OpenAI response (no real
  API call).

## Out of scope (YAGNI)

- HDBSCAN, hierarchical clustering, per-clue mean-pool embedding.
- Making LLM naming part of the deterministic pipeline (it stays an optional enrichment).
- Steps 4–5 (Sub-project B Phase 2) and the blog post (Sub-project C).

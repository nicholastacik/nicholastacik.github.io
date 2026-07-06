# Category Clustering (Sub-project B, Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cluster all ~123k Jeopardy category instances into semantic "types" and emit committed artifacts (cluster assignments + 2D coords + per-cluster fingerprints) the eventual blog post reads.

**Architecture:** Offline compute pipeline behind the existing `click` CLI, in a new `jeopardy/analysis/` subpackage. `documents` builds one text doc per category instance (seeded shuffle); `embed` encodes them with a local sentence-transformer and caches the matrix; `cluster` runs KMeans + UMAP; `label` builds three-part fingerprints and a naming prompt; `name_clusters` optionally calls the OpenAI API. Heavy deps stay in an offline `analysis` uv group; the post reads the committed parquet/csv artifacts with pandas only.

**Tech Stack:** Python 3.12+, `sentence-transformers` (embedding), `scikit-learn` (KMeans + TF-IDF), `umap-learn` (2D projection), `openai` (optional naming), `pandas`/`pyarrow` (artifacts), `pytest`. All via `uv`.

## Global Constraints

- Python `>=3.12`.
- Analysis deps (`sentence-transformers`, `scikit-learn`, `umap-learn`, `openai`) live in a new **`analysis` uv dependency group**, kept out of CI's `uv sync --frozen`. `pandas`/`pyarrow` are already main deps. No `torch`/`umap`/`sklearn`/`openai` in CI or the rendered post.
- Embedding model: **`BAAI/bge-small-en-v1.5`** (512-token window, 384-dim output).
- Fixed seed **`RANDOM_SEED = 42`** for the document shuffle, KMeans, and UMAP — deterministic re-runs.
- Unit of analysis: the **category instance** = one `(game_id, round, category)` group. Cluster **all** instances (not deduped).
- Document text: `CATEGORY NAME.` first (anchor), then the `clue -> answer` pairs **shuffled per-document with a seeded RNG** (`RANDOM_SEED + instance_id`). Pairs are sorted before shuffling so input order is deterministic.
- Clustering: **KMeans** (every instance assigned, `n_init=10`). **UMAP** to 2D is for **visualization only**, not clustering. Default `k = 50`.
- Cluster labels: three-part deterministic fingerprint — top actual category names, centroid exemplars, c-TF-IDF distinctive terms.
- Optional LLM naming (`gpt-4o-mini`, needs `OPENAI_API_KEY`) writes a **committed, curated** `cluster_labels.csv` — deliberately outside the deterministic pipeline.
- Committed artifacts in `posts/jeopardy_ds/`: `category_clusters.parquet`, `cluster_summary.parquet`, `cluster_naming_prompt.md`, and optional `cluster_labels.csv`. The embedding-matrix cache (`embeddings.npy`) and instance index (`instances.parquet`) live in the gitignored `jeopardy/data/`.
- Run from **repo root**. Tests: `uv run --all-groups pytest jeopardy/tests -v` (the suite spans the `scraper` group — which holds `pytest` — and the new `analysis` group). CLI: `uv run --group analysis python -m jeopardy <cmd>`.

---

## Data contracts

**Instance index** (`jeopardy/data/instances.parquet`, gitignored) — produced by `embed`, consumed by `cluster`:
`instance_id (int), game_id (int), round (str), category (str), document (str)`. Row `i` corresponds to row `i` of `embeddings.npy` (an `(N, 384)` float array).

**`category_clusters.parquet`** (committed) — one row per instance:
`instance_id, game_id, round, category, cluster_id (int), umap_x (float), umap_y (float)`.

**`cluster_summary.parquet`** (committed) — one row per cluster, sorted by `size` desc:
`cluster_id (int), size (int), top_category_names (list[str]), top_terms (list[str]), exemplars (list[str])`.

**`cluster_labels.csv`** (committed, optional) — `cluster_id, name`.

## File structure

```
jeopardy/
  analysis/
    __init__.py            # empty (marks subpackage)
    documents.py           # build_documents(): clues.parquet -> instance docs (seeded shuffle)
    embed.py               # get_model / embed_documents / run_embed (cached)
    label.py               # three-part fingerprint, cluster_summary, naming prompt
    cluster.py             # cluster_embeddings / project_2d / run_cluster (wires label)
    name_clusters.py       # optional OpenAI naming -> cluster_labels.csv
  config.py                # + analysis constants (Modify)
  main.py                  # + embed / cluster / name-clusters commands (Modify)
  tests/
    test_documents.py
    test_embed.py
    test_label.py
    test_cluster.py
    test_name_clusters.py
    test_analysis_pipeline.py
```

---

## Task 1: Scaffold analysis subpackage, deps, config, CLI

**Files:**
- Create: `jeopardy/analysis/__init__.py`
- Modify: `jeopardy/config.py`, `jeopardy/main.py`, `pyproject.toml` (via uv)
- Test: `jeopardy/tests/test_cli.py` (extend)

**Interfaces:**
- Produces: `jeopardy.config` gains `EMBED_MODEL`, `RANDOM_SEED`, `DEFAULT_K`, `OPENAI_MODEL`, and paths `EMBEDDINGS_PATH`, `INSTANCES_PATH`, `CATEGORY_CLUSTERS_PATH`, `CLUSTER_SUMMARY_PATH`, `NAMING_PROMPT_PATH`, `CLUSTER_LABELS_PATH`. `jeopardy.main.cli` gains commands `embed`, `cluster`, `name-clusters`.

- [ ] **Step 1: Add the analysis dependency group**

Run (from repo root):
```bash
uv add --group analysis sentence-transformers scikit-learn umap-learn openai
```
Expected: `pyproject.toml` gains `[dependency-groups] analysis = [...]`; `uv.lock` updates.

- [ ] **Step 2: Create `jeopardy/analysis/__init__.py` (empty)**

Empty file.

- [ ] **Step 3: Append analysis constants to `jeopardy/config.py`**

Add at the end of the file:
```python
# --- analysis: category clustering ---
EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # 512-token window, 384-dim
RANDOM_SEED = 42                          # shuffle + KMeans + UMAP
DEFAULT_K = 50                            # KMeans clusters
OPENAI_MODEL = "gpt-4o-mini"              # optional cluster naming

EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"       # gitignored cache
INSTANCES_PATH = DATA_DIR / "instances.parquet"     # gitignored instance index
_POST_DIR = REPO_ROOT / "posts" / "jeopardy_ds"
CATEGORY_CLUSTERS_PATH = _POST_DIR / "category_clusters.parquet"
CLUSTER_SUMMARY_PATH = _POST_DIR / "cluster_summary.parquet"
NAMING_PROMPT_PATH = _POST_DIR / "cluster_naming_prompt.md"
CLUSTER_LABELS_PATH = _POST_DIR / "cluster_labels.csv"
```

- [ ] **Step 4: Add the three CLI commands to `jeopardy/main.py`**

Append inside the module (after the existing `all_` command):
```python
@cli.command()
@click.option("--force", is_flag=True, help="Re-embed even if the cache exists.")
@click.option("--limit", default=None, type=int, help="Embed only the first N instances (for smoke tests).")
def embed(force, limit):
    """Build category documents and embed them (cached to data/)."""
    from jeopardy.analysis.embed import run_embed
    run_embed(force=force, limit=limit)


@cli.command()
@click.option("--k", default=None, type=int, help="Number of KMeans clusters (default from config).")
def cluster(k):
    """Cluster embeddings, project to 2D, and write cluster artifacts."""
    from jeopardy import config
    from jeopardy.analysis.cluster import run_cluster
    run_cluster(k if k is not None else config.DEFAULT_K)


@cli.command(name="name-clusters")
def name_clusters():
    """Optional: name clusters via OpenAI -> cluster_labels.csv (needs OPENAI_API_KEY)."""
    from jeopardy.analysis.name_clusters import run_name_clusters
    run_name_clusters()
```

- [ ] **Step 5: Extend the CLI test**

Replace the command tuple in `jeopardy/tests/test_cli.py`'s `test_cli_exposes_commands` so it reads:
```python
def test_cli_exposes_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("crawl", "build", "all", "embed", "cluster", "name-clusters"):
        assert cmd in result.output
```

- [ ] **Step 6: Run the test**

Run: `uv run --all-groups pytest jeopardy/tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add jeopardy/analysis/__init__.py jeopardy/config.py jeopardy/main.py jeopardy/tests/test_cli.py pyproject.toml uv.lock
git commit -m "feat(analysis): scaffold clustering subpackage, deps, CLI commands"
```

---

## Task 2: Build category-instance documents

**Files:**
- Create: `jeopardy/analysis/documents.py`
- Test: `jeopardy/tests/test_documents.py`

**Interfaces:**
- Consumes: `jeopardy.config.RANDOM_SEED`; a clues DataFrame with columns `game_id, round, category, clue, answer`.
- Produces:
  - `make_document(category: str, pairs: list[tuple[str, str]], rng) -> str` — `"CATEGORY. c -> a; c -> a"`, pairs applied in `rng.permutation` order.
  - `build_documents(clues_df) -> pd.DataFrame` with columns `instance_id, game_id, round, category, document`, one row per `(game_id, round, category)` group, in sorted-key order (so `instance_id` is stable).

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/test_documents.py`:
```python
import numpy as np
import pandas as pd
from jeopardy.analysis.documents import build_documents, make_document


def _clues():
    return pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy", "category": "PASTA",
         "clue": "a tube shape", "answer": "penne"},
        {"game_id": 1, "round": "Jeopardy", "category": "PASTA",
         "clue": "a ribbon shape", "answer": "linguine"},
        {"game_id": 1, "round": "Final", "category": "AUTHORS",
         "clue": "beloved novelist", "answer": "Toni Morrison"},
    ])


def test_build_documents_shape_and_name_first():
    df = build_documents(_clues())
    assert list(df.columns) == ["instance_id", "game_id", "round", "category", "document"]
    assert len(df) == 2  # (1, Jeopardy, PASTA) and (1, Final, AUTHORS)
    pasta = df.loc[df["category"] == "PASTA", "document"].iloc[0]
    assert pasta.startswith("PASTA.")
    assert "penne" in pasta and "linguine" in pasta


def test_build_documents_deterministic():
    pd.testing.assert_frame_equal(build_documents(_clues()), build_documents(_clues()))


def test_instance_ids_are_contiguous():
    df = build_documents(_clues())
    assert df["instance_id"].tolist() == [0, 1]


def test_make_document_shuffle_is_seed_reproducible():
    pairs = [("a", "1"), ("b", "2"), ("c", "3")]
    d1 = make_document("X", pairs, np.random.default_rng(7))
    d2 = make_document("X", pairs, np.random.default_rng(7))
    assert d1 == d2
    assert d1.startswith("X.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_documents.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.documents`).

- [ ] **Step 3: Implement `jeopardy/analysis/documents.py`**

```python
"""Build one text document per Jeopardy category instance."""
import numpy as np
import pandas as pd

from jeopardy import config


def make_document(category, pairs, rng):
    """`"CATEGORY. clue -> answer; clue -> answer"`, pairs in rng-permuted order."""
    order = rng.permutation(len(pairs))
    body = "; ".join(f"{pairs[i][0]} -> {pairs[i][1]}" for i in order)
    return f"{category}. {body}" if body else f"{category}."


def build_documents(clues_df):
    """One document per (game_id, round, category); stable instance_id per sorted key."""
    rows = []
    grouped = clues_df.groupby(["game_id", "round", "category"], sort=True)
    for instance_id, ((game_id, round_, category), group) in enumerate(grouped):
        pairs = [
            (str(c) if c is not None else "", str(a) if a is not None else "")
            for c, a in zip(group["clue"], group["answer"])
        ]
        pairs.sort()  # deterministic input order before the seeded shuffle
        rng = np.random.default_rng(config.RANDOM_SEED + instance_id)
        rows.append({
            "instance_id": instance_id,
            "game_id": game_id,
            "round": round_,
            "category": category,
            "document": make_document(category, pairs, rng),
        })
    return pd.DataFrame(rows, columns=["instance_id", "game_id", "round", "category", "document"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_documents.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/documents.py jeopardy/tests/test_documents.py
git commit -m "feat(analysis): build category-instance documents with seeded shuffle"
```

---

## Task 3: Embed documents (cached)

**Files:**
- Create: `jeopardy/analysis/embed.py`
- Test: `jeopardy/tests/test_embed.py`

**Interfaces:**
- Consumes: `build_documents`; `jeopardy.config` (`PARQUET_PATH`, `DATA_DIR`, `EMBEDDINGS_PATH`, `INSTANCES_PATH`, `EMBED_MODEL`).
- Produces:
  - `get_model()` — lazily loads and caches the `SentenceTransformer`.
  - `embed_documents(documents) -> np.ndarray` — `(N, 384)` float array.
  - `run_embed(force=False, limit=None)` — reads `clues.parquet`, builds documents, embeds, writes `EMBEDDINGS_PATH` (npy) + `INSTANCES_PATH` (parquet). Skips if both exist and not `force`.

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/test_embed.py`:
```python
import numpy as np
import pandas as pd
from jeopardy.analysis import embed as embed_mod


class FakeModel:
    def __init__(self):
        self.calls = 0

    def encode(self, docs, **kwargs):
        self.calls += 1
        return np.ones((len(list(docs)), 4), dtype="float32")


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(embed_mod.config, "PARQUET_PATH", tmp_path / "clues.parquet")
    monkeypatch.setattr(embed_mod.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(embed_mod.config, "EMBEDDINGS_PATH", tmp_path / "embeddings.npy")
    monkeypatch.setattr(embed_mod.config, "INSTANCES_PATH", tmp_path / "instances.parquet")
    pd.DataFrame([
        {"game_id": 1, "round": "Final", "category": "X", "clue": "c", "answer": "a"},
        {"game_id": 2, "round": "Final", "category": "Y", "clue": "d", "answer": "b"},
    ]).to_parquet(tmp_path / "clues.parquet")


def test_run_embed_writes_cache(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fake = FakeModel()
    monkeypatch.setattr(embed_mod, "get_model", lambda: fake)
    embed_mod.run_embed()
    assert (tmp_path / "embeddings.npy").exists()
    assert (tmp_path / "instances.parquet").exists()
    assert fake.calls == 1
    assert np.load(tmp_path / "embeddings.npy").shape[0] == 2


def test_run_embed_cache_skips_encode(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    (tmp_path / "embeddings.npy").write_bytes(b"x")
    (tmp_path / "instances.parquet").write_bytes(b"x")

    def boom():
        raise AssertionError("get_model called on a cache hit")

    monkeypatch.setattr(embed_mod, "get_model", boom)
    embed_mod.run_embed()  # should return early, not encode


def test_run_embed_limit(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fake = FakeModel()
    monkeypatch.setattr(embed_mod, "get_model", lambda: fake)
    embed_mod.run_embed(limit=1)
    assert np.load(tmp_path / "embeddings.npy").shape[0] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_embed.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.embed`).

- [ ] **Step 3: Implement `jeopardy/analysis/embed.py`**

```python
"""Encode category documents with a local sentence-transformer (cached)."""
import numpy as np
import pandas as pd

from jeopardy import config
from jeopardy.analysis.documents import build_documents

_model = None


def get_model():
    """Lazily load and cache the SentenceTransformer (heavy import kept local)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(config.EMBED_MODEL)
    return _model


def embed_documents(documents):
    """Encode an iterable of strings into an (N, dim) float array."""
    model = get_model()
    return model.encode(
        list(documents),
        batch_size=64,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


def run_embed(force=False, limit=None):
    """Build documents, embed them, and cache the matrix + instance index."""
    if config.EMBEDDINGS_PATH.exists() and config.INSTANCES_PATH.exists() and not force:
        print("Embeddings cache present; skipping (use --force to re-embed).")
        return
    clues = pd.read_parquet(config.PARQUET_PATH)
    instances = build_documents(clues)
    if limit is not None:
        instances = instances.head(limit).reset_index(drop=True)
    embeddings = embed_documents(instances["document"])
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.save(config.EMBEDDINGS_PATH, embeddings)
    instances.to_parquet(config.INSTANCES_PATH, index=False)
    print(f"Embedded {len(instances):,} instances -> {config.EMBEDDINGS_PATH}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_embed.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/embed.py jeopardy/tests/test_embed.py
git commit -m "feat(analysis): cached sentence-transformer embedding"
```

---

## Task 4: Cluster labels — three-part fingerprint

**Files:**
- Create: `jeopardy/analysis/label.py`
- Test: `jeopardy/tests/test_label.py`

**Interfaces:**
- Consumes: an instances DataFrame (`category`, `document` columns), an `(N, dim)` embeddings array, a length-`N` `labels` array, and a `(k, dim)` `centers` array.
- Produces:
  - `top_category_names(categories, n=10) -> list[str]` — `["NAME (count)", ...]` by frequency.
  - `ctfidf_terms(cluster_docs, n=10) -> list[list[str]]` — per-cluster distinctive terms via TF-IDF over concatenated cluster documents.
  - `nearest_exemplars(embeddings, centroid, cluster_idx, categories, n=5) -> list[str]` — category names of the instances nearest the centroid.
  - `build_cluster_summary(instances, embeddings, labels, centers) -> pd.DataFrame` with columns `cluster_id, size, top_category_names, top_terms, exemplars`, sorted by `size` desc.
  - `write_naming_prompt(summary, path)` — writes a paste-ready markdown naming prompt.

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/test_label.py`:
```python
import numpy as np
import pandas as pd
from jeopardy.analysis.label import (
    top_category_names, ctfidf_terms, nearest_exemplars,
    build_cluster_summary, write_naming_prompt,
)


def test_top_category_names_counts_and_orders():
    out = top_category_names(["PASTA", "PASTA", "OPERA"])
    assert out[0] == "PASTA (2)"
    assert "OPERA (1)" in out


def test_ctfidf_surfaces_distinctive_terms():
    docs = [
        "president elected inauguration president term",
        "pasta penne rigatoni pasta noodle",
    ]
    terms = ctfidf_terms(docs, n=3)
    assert any("president" in t for t in terms[0])
    assert any("pasta" in t or "penne" in t for t in terms[1])


def test_nearest_exemplars_returns_closest():
    emb = np.array([[0.0, 0.0], [1.0, 1.0], [0.1, 0.1]])
    centroid = np.array([0.0, 0.0])
    cats = np.array(["A", "B", "C"])
    out = nearest_exemplars(emb, centroid, np.array([0, 1, 2]), cats, n=2)
    assert out == ["A", "C"]


def _instances(cats):
    return pd.DataFrame({
        "category": cats,
        "document": [f"{c}. clue -> ans" for c in cats],
    })


def test_build_cluster_summary_shape_and_sort():
    cats = ["PASTA", "PASTA", "PASTA", "OPERA"]
    emb = np.array([[0.0, 0.0], [0.1, 0.0], [0.0, 0.1], [9.0, 9.0]])
    labels = np.array([0, 0, 0, 1])
    centers = np.array([[0.03, 0.03], [9.0, 9.0]])
    summary = build_cluster_summary(_instances(cats), emb, labels, centers)
    assert list(summary.columns) == ["cluster_id", "size", "top_category_names", "top_terms", "exemplars"]
    assert summary.iloc[0]["size"] == 3        # sorted by size desc → PASTA cluster first
    assert summary["size"].sum() == 4


def test_write_naming_prompt(tmp_path):
    summary = pd.DataFrame([{
        "cluster_id": 0, "size": 3,
        "top_category_names": ["PASTA (3)"], "top_terms": ["penne"], "exemplars": ["PASTA"],
    }])
    p = tmp_path / "prompt.md"
    write_naming_prompt(summary, p)
    text = p.read_text()
    assert "Cluster 0" in text and "PASTA" in text and "penne" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_label.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.label`).

- [ ] **Step 3: Implement `jeopardy/analysis/label.py`**

```python
"""Three-part deterministic fingerprints for clusters + a naming prompt."""
from collections import Counter

import numpy as np
import pandas as pd


def top_category_names(categories, n=10):
    return [f"{name} ({count})" for name, count in Counter(categories).most_common(n)]


def ctfidf_terms(cluster_docs, n=10):
    """Per-cluster distinctive terms: TF-IDF over one concatenated doc per cluster."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(
        stop_words="english", max_features=5000,
        token_pattern=r"[A-Za-z][A-Za-z'\-]+",
    )
    matrix = vec.fit_transform(cluster_docs)
    terms = np.array(vec.get_feature_names_out())
    out = []
    for i in range(matrix.shape[0]):
        row = matrix.getrow(i).toarray().ravel()
        top = row.argsort()[::-1][:n]
        out.append([terms[j] for j in top if row[j] > 0])
    return out


def nearest_exemplars(embeddings, centroid, cluster_idx, categories, n=5):
    """Category names of the `n` instances nearest the cluster centroid."""
    distances = np.linalg.norm(embeddings[cluster_idx] - centroid, axis=1)
    order = np.argsort(distances)[:n]
    return [categories[cluster_idx[j]] for j in order]


def build_cluster_summary(instances, embeddings, labels, centers):
    categories = instances["category"].to_numpy()
    documents = instances["document"].to_numpy()
    k = centers.shape[0]
    cluster_docs = [" ".join(documents[np.where(labels == cid)[0]]) for cid in range(k)]
    terms = ctfidf_terms(cluster_docs)
    rows = []
    for cid in range(k):
        idx = np.where(labels == cid)[0]
        rows.append({
            "cluster_id": cid,
            "size": int(len(idx)),
            "top_category_names": top_category_names(categories[idx].tolist()),
            "top_terms": terms[cid],
            "exemplars": nearest_exemplars(embeddings, centers[cid], idx, categories),
        })
    return pd.DataFrame(rows).sort_values("size", ascending=False).reset_index(drop=True)


def write_naming_prompt(summary, path):
    lines = [
        "# Cluster naming prompt",
        "",
        "For each cluster, reply with JSON mapping the cluster id (as a string key) to a",
        "short 2-4 word human-readable category-type name, e.g. {\"0\": \"U.S. Presidents\"}.",
        "",
    ]
    for _, r in summary.iterrows():
        lines.append(f"## Cluster {r['cluster_id']} (size {r['size']})")
        lines.append(f"- Top categories: {', '.join(r['top_category_names'])}")
        lines.append(f"- Distinctive terms: {', '.join(r['top_terms'])}")
        lines.append(f"- Exemplars: {', '.join(r['exemplars'])}")
        lines.append("")
    path.write_text("\n".join(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_label.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/label.py jeopardy/tests/test_label.py
git commit -m "feat(analysis): three-part cluster fingerprints + naming prompt"
```

---

## Task 5: Cluster + project to 2D

**Files:**
- Create: `jeopardy/analysis/cluster.py`
- Test: `jeopardy/tests/test_cluster.py`

**Interfaces:**
- Consumes: `jeopardy.config` (`INSTANCES_PATH`, `EMBEDDINGS_PATH`, `RANDOM_SEED`, `CATEGORY_CLUSTERS_PATH`, `CLUSTER_SUMMARY_PATH`, `NAMING_PROMPT_PATH`); `build_cluster_summary`, `write_naming_prompt` from `label`.
- Produces:
  - `cluster_embeddings(embeddings, k, seed) -> (labels: np.ndarray, centers: np.ndarray)` via KMeans (`n_init=10`).
  - `project_2d(embeddings, seed) -> np.ndarray` — `(N, 2)` UMAP coords.
  - `run_cluster(k)` — loads cache, clusters, projects, writes `category_clusters.parquet`, `cluster_summary.parquet`, and the naming prompt.

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/test_cluster.py`:
```python
import numpy as np
from jeopardy.analysis.cluster import cluster_embeddings, project_2d


def test_cluster_embeddings_shape_and_separation():
    rng = np.random.default_rng(0)
    emb = np.vstack([
        rng.normal(0, 0.05, (20, 8)) + 5.0,
        rng.normal(0, 0.05, (20, 8)),
    ])
    labels, centers = cluster_embeddings(emb, k=2, seed=42)
    assert labels.shape == (40,)
    assert centers.shape == (2, 8)
    # the two blobs land in different clusters
    assert labels[0] != labels[-1]


def test_project_2d_shape():
    rng = np.random.default_rng(0)
    emb = rng.normal(size=(30, 8))
    coords = project_2d(emb, seed=42)
    assert coords.shape == (30, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_cluster.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.cluster`).

- [ ] **Step 3: Implement `jeopardy/analysis/cluster.py`**

```python
"""KMeans clustering + UMAP 2D projection over category embeddings."""
import numpy as np
import pandas as pd

from jeopardy import config
from jeopardy.analysis.label import build_cluster_summary, write_naming_prompt


def cluster_embeddings(embeddings, k, seed):
    """KMeans → (labels, centers)."""
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = km.fit_predict(embeddings)
    return labels, km.cluster_centers_


def project_2d(embeddings, seed):
    """UMAP → (N, 2) coordinates, for visualization only."""
    import umap
    reducer = umap.UMAP(n_components=2, random_state=seed)
    return reducer.fit_transform(embeddings)


def run_cluster(k):
    instances = pd.read_parquet(config.INSTANCES_PATH)
    embeddings = np.load(config.EMBEDDINGS_PATH)
    labels, centers = cluster_embeddings(embeddings, k, config.RANDOM_SEED)
    coords = project_2d(embeddings, config.RANDOM_SEED)

    out = instances[["instance_id", "game_id", "round", "category"]].copy()
    out["cluster_id"] = labels
    out["umap_x"] = coords[:, 0]
    out["umap_y"] = coords[:, 1]
    config.CATEGORY_CLUSTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(config.CATEGORY_CLUSTERS_PATH, index=False)

    summary = build_cluster_summary(instances, embeddings, labels, centers)
    summary.to_parquet(config.CLUSTER_SUMMARY_PATH, index=False)
    write_naming_prompt(summary, config.NAMING_PROMPT_PATH)
    print(f"Clustered {len(out):,} instances into {k} clusters -> {config.CATEGORY_CLUSTERS_PATH}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_cluster.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/cluster.py jeopardy/tests/test_cluster.py
git commit -m "feat(analysis): KMeans clustering + UMAP projection + artifacts"
```

---

## Task 6: Optional OpenAI cluster naming

**Files:**
- Create: `jeopardy/analysis/name_clusters.py`
- Test: `jeopardy/tests/test_name_clusters.py`

**Interfaces:**
- Consumes: `jeopardy.config` (`CLUSTER_SUMMARY_PATH`, `CLUSTER_LABELS_PATH`, `OPENAI_MODEL`); a cluster summary DataFrame.
- Produces:
  - `build_prompt(summary) -> str` — one prompt string listing every cluster's fingerprint, asking for a JSON `{id: name}` reply.
  - `parse_response(text) -> dict[int, str]` — parse the JSON reply into `{cluster_id: name}`.
  - `write_labels(names, path)` — write `cluster_id,name` CSV sorted by id.
  - `run_name_clusters()` — read summary, call OpenAI, write `cluster_labels.csv`.

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/test_name_clusters.py`:
```python
import pandas as pd
from jeopardy.analysis import name_clusters as nc


def test_parse_response():
    assert nc.parse_response('{"0": "U.S. Presidents", "1": "Pasta"}') == {0: "U.S. Presidents", 1: "Pasta"}


def test_write_labels_sorted(tmp_path):
    p = tmp_path / "labels.csv"
    nc.write_labels({1: "Beta", 0: "Alpha"}, p)
    lines = p.read_text().splitlines()
    assert lines[0] == "cluster_id,name"
    assert lines[1] == "0,Alpha"
    assert lines[2] == "1,Beta"


def test_build_prompt_includes_fingerprints():
    summary = pd.DataFrame([{
        "cluster_id": 0, "size": 10,
        "top_category_names": ["PASTA (5)"], "top_terms": ["penne"], "exemplars": ["PASTA"],
    }])
    prompt = nc.build_prompt(summary)
    assert "Cluster 0" in prompt and "PASTA" in prompt and "penne" in prompt


def test_run_name_clusters_stubbed(tmp_path, monkeypatch):
    summary = pd.DataFrame([{
        "cluster_id": 0, "size": 5,
        "top_category_names": ["PASTA (5)"], "top_terms": ["penne"], "exemplars": ["PASTA"],
    }])
    summary.to_parquet(tmp_path / "summary.parquet")
    monkeypatch.setattr(nc.config, "CLUSTER_SUMMARY_PATH", tmp_path / "summary.parquet")
    monkeypatch.setattr(nc.config, "CLUSTER_LABELS_PATH", tmp_path / "labels.csv")
    monkeypatch.setattr(nc, "_complete", lambda prompt: '{"0": "Pasta"}')
    nc.run_name_clusters()
    assert (tmp_path / "labels.csv").read_text().splitlines()[1] == "0,Pasta"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_name_clusters.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.name_clusters`).

- [ ] **Step 3: Implement `jeopardy/analysis/name_clusters.py`**

```python
"""Optional: name clusters via the OpenAI API -> committed cluster_labels.csv."""
import csv
import json

import pandas as pd

from jeopardy import config


def build_prompt(summary):
    lines = [
        "You are naming clusters of Jeopardy categories. For each cluster below, reply",
        "with a JSON object mapping the cluster id (string key) to a short 2-4 word",
        'category-type name, e.g. {"0": "U.S. Presidents"}. Reply with JSON only.',
        "",
    ]
    for _, r in summary.iterrows():
        lines.append(f"Cluster {r['cluster_id']} (size {r['size']})")
        lines.append(f"  top categories: {', '.join(r['top_category_names'])}")
        lines.append(f"  distinctive terms: {', '.join(r['top_terms'])}")
        lines.append(f"  exemplars: {', '.join(r['exemplars'])}")
        lines.append("")
    return "\n".join(lines)


def parse_response(text):
    return {int(k): str(v) for k, v in json.loads(text).items()}


def write_labels(names, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["cluster_id", "name"])
        for cid in sorted(names):
            writer.writerow([cid, names[cid]])


def _complete(prompt):
    """Send the prompt to OpenAI and return the raw text reply."""
    from openai import OpenAI
    client = OpenAI()  # reads OPENAI_API_KEY from the environment
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def run_name_clusters():
    summary = pd.read_parquet(config.CLUSTER_SUMMARY_PATH)
    names = parse_response(_complete(build_prompt(summary)))
    write_labels(names, config.CLUSTER_LABELS_PATH)
    print(f"Wrote {len(names)} cluster names -> {config.CLUSTER_LABELS_PATH}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_name_clusters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/name_clusters.py jeopardy/tests/test_name_clusters.py
git commit -m "feat(analysis): optional OpenAI cluster naming"
```

---

## Task 7: End-to-end validation

**Files:**
- Create: `jeopardy/tests/test_analysis_pipeline.py`

**Interfaces:**
- Consumes: everything above. No new production code — proves the pieces compose.

- [ ] **Step 1: Write the integration test (documents → cluster → summary, fake embeddings)**

Create `jeopardy/tests/test_analysis_pipeline.py`:
```python
import numpy as np
import pandas as pd
from jeopardy.analysis.documents import build_documents
from jeopardy.analysis.cluster import cluster_embeddings
from jeopardy.analysis.label import build_cluster_summary


def _clues():
    rows = []
    for g in range(6):  # 6 pasta-ish + 6 opera-ish category instances
        rows.append({"game_id": g, "round": "Jeopardy", "category": "PASTA",
                     "clue": "shape of pasta", "answer": "penne"})
        rows.append({"game_id": g, "round": "Double Jeopardy", "category": "OPERA",
                     "clue": "work by Verdi", "answer": "Aida"})
    return pd.DataFrame(rows)


def test_pipeline_composes():
    instances = build_documents(_clues())
    assert len(instances) == 12
    # deterministic fake embeddings: two separated blobs keyed by category
    rng = np.random.default_rng(0)
    emb = np.array([
        (rng.normal(0, 0.01, 8) + (5.0 if c == "PASTA" else 0.0))
        for c in instances["category"]
    ])
    labels, centers = cluster_embeddings(emb, k=2, seed=42)
    summary = build_cluster_summary(instances, emb, labels, centers)
    assert summary["size"].sum() == 12
    assert set(summary.columns) == {"cluster_id", "size", "top_category_names", "top_terms", "exemplars"}
    # each cluster is a pure category type
    joined = " ".join(summary.iloc[0]["top_category_names"] + summary.iloc[1]["top_category_names"])
    assert "PASTA" in joined and "OPERA" in joined
```

- [ ] **Step 2: Run the full suite**

Run: `uv run --all-groups pytest jeopardy/tests -v`
Expected: PASS (scraper tests + all analysis tests).

- [ ] **Step 3: Real smoke run on a small slice**

Validate the real embedding model + clustering end-to-end on a small slice (fast — a few hundred instances), from the repo root:
```bash
uv run --group analysis python -m jeopardy embed --limit 500
uv run --group analysis python -m jeopardy cluster --k 8
```
Expected: `embed` downloads the model on first run and writes `jeopardy/data/embeddings.npy` + `instances.parquet` (500 rows); `cluster` writes `posts/jeopardy_ds/category_clusters.parquet`, `cluster_summary.parquet`, and `cluster_naming_prompt.md`.

- [ ] **Step 4: Inspect the slice artifacts**

```bash
uv run --group analysis python -c "
import pandas as pd
cl = pd.read_parquet('posts/jeopardy_ds/category_clusters.parquet')
su = pd.read_parquet('posts/jeopardy_ds/cluster_summary.parquet')
print('clusters rows:', cl.shape, 'cols:', list(cl.columns))
print('summary rows:', su.shape)
print(su[['cluster_id','size','top_category_names','top_terms']].head(8).to_string())
"
```
Expected: `category_clusters.parquet` has the 500 rows with `cluster_id`/`umap_x`/`umap_y`; the summary shows plausible fingerprints.

- [ ] **Step 5: Clean up slice artifacts and commit only the test**

The slice artifacts are not the real dataset — remove them so they aren't committed prematurely.
```bash
rm -f posts/jeopardy_ds/category_clusters.parquet posts/jeopardy_ds/cluster_summary.parquet posts/jeopardy_ds/cluster_naming_prompt.md
rm -rf jeopardy/data
git add jeopardy/tests/test_analysis_pipeline.py
git commit -m "test(analysis): end-to-end clustering pipeline validation"
```

- [ ] **Step 6: Full run (manual, run by Nick when ready)**

The real run embeds all ~123k instances (~5–15 min, first run also downloads the model), then clusters. Iterate on `k` as desired (re-`cluster` reuses the cached embeddings):
```bash
uv run --group analysis python -m jeopardy embed
uv run --group analysis python -m jeopardy cluster --k 50
# optional naming (needs OPENAI_API_KEY): uv run --group analysis python -m jeopardy name-clusters
```
Then commit the artifacts:
```bash
git add posts/jeopardy_ds/category_clusters.parquet posts/jeopardy_ds/cluster_summary.parquet posts/jeopardy_ds/cluster_naming_prompt.md
# and posts/jeopardy_ds/cluster_labels.csv if naming was run
git commit -m "data(analysis): category clusters from full embedding run"
```

---

## Self-Review

**Spec coverage:**
- Offline compute → committed artifacts, torch out of CI → `analysis` group (Task 1), artifacts in `posts/jeopardy_ds/` (Task 5). ✓
- Unit = all category instances → `build_documents` groups `(game_id, round, category)` (Task 2). ✓
- Document = name-first + seeded shuffle of clue→answer pairs → Task 2. ✓
- `bge-small-en-v1.5`, 512-token, cached matrix, embed/cluster split → Tasks 1, 3. ✓
- KMeans (all assigned) + UMAP 2D viz only → Task 5. ✓
- Three-part fingerprint (top names, exemplars, c-TF-IDF) → Task 4. ✓
- Optional OpenAI naming → committed `cluster_labels.csv`, outside deterministic pipeline → Task 6. ✓
- Fixed seeds (shuffle, KMeans, UMAP) → Tasks 2, 5. ✓
- Committed vs gitignored artifacts → Tasks 3 (cache in data/), 5 (artifacts in post dir). ✓
- Naming prompt emitted → Tasks 4, 5. ✓
- Testing per the spec (documents/label/cluster shape/embed cache/name-clusters stub) → Tasks 2–7. ✓

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `build_documents` output columns (`instance_id, game_id, round, category, document`) are consumed unchanged by `run_embed` (writes `instances.parquet`) and `run_cluster` (reads them). `cluster_embeddings` returns `(labels, centers)` consumed by `build_cluster_summary(instances, embeddings, labels, centers)`. `build_cluster_summary` columns (`cluster_id, size, top_category_names, top_terms, exemplars`) are consumed by `write_naming_prompt` and `build_prompt`. `parse_response`/`write_labels` share the `{cluster_id: name}` dict. Consistent. ✓

**Known limitation (accepted per spec):** the real embedding run and the full clustering are the manual heavy step (Task 7 step 6); the automated tasks validate correctness on synthetic data + a small real slice.

# Most Common Tokens per Category-Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For each of the 50 cluster-types, extract the most common + distinctive capitalized proper-noun phrases from clue+answer text and write a committed `category_tokens.parquet`.

**Architecture:** A new `jeopardy/analysis/tokens.py` that reads the committed `category_clusters.parquet` + `clues.parquet` (no re-embedding), extracts proper-noun phrases via a transparent regex, and ranks them per cluster by c-TF-IDF with a minimum-frequency floor. Behind a new `tokens` CLI command.

**Tech Stack:** Python 3.12+, `pandas` (main dep), stdlib `re`/`math`/`collections`. No new dependencies.

## Global Constraints

- Python `>=3.12`.
- No new dependencies — uses `pandas` (already main) + stdlib only.
- Token = capitalized proper-noun phrase, extracted from **clue + answer text combined**.
- Ranking = c-TF-IDF (each cluster is one document) with a **minimum-frequency floor** (`min_freq`, default 5); keep top `top_n` (default 25) per cluster.
- `n_qualifying_phrases` per cluster = count of distinct phrases clearing the floor (the "applicability" signal). Every one of the 50 clusters must be represented in the output (clusters with zero qualifying phrases get one placeholder row).
- Committed artifact: `posts/jeopardy_ds/category_tokens.parquet`. Reuses `category_clusters.parquet` + `clues.parquet`; writes nothing to the gitignored `jeopardy/data/`.
- Unit = the 50 cluster-types (join instance→cluster on `game_id, round, category`).
- Run from **repo root**. Tests: `uv run --all-groups pytest jeopardy/tests -v`. CLI: `uv run --group analysis python -m jeopardy tokens`.

---

## Data contract

**`category_tokens.parquet`** (committed) — one row per (cluster, ranked phrase):
`cluster_id (int), rank (int), phrase (str|None), count (int), tfidf_weight (float), n_qualifying_phrases (int)`.
Rows ordered by `cluster_id` then `rank`. A cluster with no qualifying phrases has a single row: `rank=0, phrase=None, count=0, tfidf_weight=0.0, n_qualifying_phrases=0`.

## File structure

```
jeopardy/
  analysis/
    tokens.py              # extract_phrases / cluster_top_phrases / run_tokens
  config.py                # + CATEGORY_TOKENS_PATH (Modify)
  main.py                  # + tokens command (Modify)
  tests/
    test_tokens.py
```

---

## Task 1: Config path, CLI command, and phrase extraction

**Files:**
- Create: `jeopardy/analysis/tokens.py`
- Modify: `jeopardy/config.py`, `jeopardy/main.py`
- Test: `jeopardy/tests/test_tokens.py`

**Interfaces:**
- Produces: `jeopardy.config.CATEGORY_TOKENS_PATH`; `jeopardy.main.cli` gains a `tokens` command; `jeopardy.analysis.tokens.extract_phrases(text: str) -> list[str]` (all proper-noun phrase matches, dups included, leading stopwords stripped, single-stopword phrases dropped).

- [ ] **Step 1: Add the config path**

Append to `jeopardy/config.py`:
```python
CATEGORY_TOKENS_PATH = _POST_DIR / "category_tokens.parquet"
```

- [ ] **Step 2: Add the `tokens` CLI command**

Append inside `jeopardy/main.py` (after the existing commands):
```python
@cli.command()
@click.option("--min-freq", default=5, type=int, help="Min phrase count within a cluster to qualify.")
@click.option("--top-n", default=25, type=int, help="Max ranked phrases kept per cluster.")
def tokens(min_freq, top_n):
    """Extract most-common proper-noun phrases per cluster -> category_tokens.parquet."""
    from jeopardy.analysis.tokens import run_tokens
    run_tokens(min_freq=min_freq, top_n=top_n)
```

- [ ] **Step 3: Write the failing tests for `extract_phrases`**

Create `jeopardy/tests/test_tokens.py`:
```python
from jeopardy.analysis.tokens import extract_phrases


def test_extracts_regnal_entity():
    out = extract_phrases("In 1483 Richard III seized the throne of England")
    assert "Richard III" in out
    assert "England" in out


def test_extracts_multiword_war():
    out = extract_phrases("World War II began in Europe")
    assert "World War II" in out
    assert "Europe" in out


def test_connectors_join_entity():
    out = extract_phrases("The United States of America declared independence")
    assert "United States of America" in out
    # sentence-initial "The" must not glue onto the entity
    assert "The United States of America" not in out


def test_sentence_initial_pronoun_dropped():
    # a wordplay-style clue yields no proper-noun entities
    assert extract_phrases("This four-letter word means to leap") == []


def test_word_boundary_and_dedup_counting():
    # returns each occurrence (dups kept) so callers can count
    out = extract_phrases("Napoleon met Napoleon again")
    assert out.count("Napoleon") == 2
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.tokens`).

- [ ] **Step 5: Implement `extract_phrases` in `jeopardy/analysis/tokens.py`**

```python
"""Most-common proper-noun phrases per cluster-type."""
import re

# Single-token capitalized words that are sentence-initial/pronominal, not entities.
_STOPWORDS = {
    "This", "These", "That", "Those", "The", "A", "An", "He", "She", "It",
    "In", "On", "At", "Of", "To", "For", "His", "Her", "Its", "Their", "They",
    "You", "We", "I", "When", "What", "Where", "Who", "Why", "How", "As", "By",
    "From", "With", "One", "Now", "Here", "There", "Like", "Also", "But", "And",
    "Or", "If", "Then", "Both", "Each", "Some", "Many", "Most", "All", "No",
}

_WORD = r"[A-Z][a-z]+"
_NUM = r"(?:[IVX]+|\d+)"
_CONNECT = r"(?:of|the|and|de|la|von|van)"
# Head cap-word, then continuations: cap-words / numerals, optionally preceded by
# lowercase connector words ("of the"). Maximal munch keeps "Richard III" whole.
_PHRASE_RE = re.compile(
    rf"\b{_WORD}(?:\s+(?:{_CONNECT}\s+)*(?:{_WORD}|{_NUM}))*"
)


def _strip_leading_stopwords(phrase):
    tokens = phrase.split()
    while tokens and tokens[0] in _STOPWORDS:
        tokens.pop(0)
    return " ".join(tokens)


def extract_phrases(text):
    """All proper-noun phrases in `text` (dups kept), leading stopwords stripped."""
    out = []
    for m in _PHRASE_RE.finditer(text or ""):
        phrase = _strip_leading_stopwords(m.group(0).strip())
        if phrase:
            out.append(phrase)
    return out
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add jeopardy/analysis/tokens.py jeopardy/config.py jeopardy/main.py jeopardy/tests/test_tokens.py
git commit -m "feat(analysis): proper-noun phrase extraction + tokens CLI scaffold"
```

---

## Task 2: Per-cluster c-TF-IDF ranking + artifact writer

**Files:**
- Modify: `jeopardy/analysis/tokens.py`
- Test: `jeopardy/tests/test_tokens.py`

**Interfaces:**
- Consumes: `extract_phrases`; `jeopardy.config` (`CATEGORY_CLUSTERS_PATH`, `PARQUET_PATH`, `CATEGORY_TOKENS_PATH`); a clusters DataFrame (`game_id, round, category, cluster_id`) and a clues DataFrame (`game_id, round, category, clue, answer`).
- Produces:
  - `cluster_top_phrases(clusters_df, clues_df, min_freq=5, top_n=25) -> pd.DataFrame` with columns `cluster_id, rank, phrase, count, tfidf_weight, n_qualifying_phrases`; every cluster represented (placeholder row when none qualify).
  - `run_tokens(min_freq=5, top_n=25)` — read artifacts, write `CATEGORY_TOKENS_PATH`.

- [ ] **Step 1: Write the failing tests**

Append to `jeopardy/tests/test_tokens.py`:
```python
import pandas as pd
from jeopardy.analysis.tokens import cluster_top_phrases


def _clusters():
    # cluster 0 = entity-heavy (Lincoln repeats), cluster 1 = wordplay (all distinct)
    rows = []
    for i in range(8):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "PRESIDENTS", "cluster_id": 0})
        rows.append({"game_id": i, "round": "Jeopardy", "category": "4-LETTER WORDS", "cluster_id": 1})
    return pd.DataFrame(rows)


def _clues():
    rows = []
    for i in range(8):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "PRESIDENTS",
                     "clue": "This president led during the Civil War", "answer": "Abraham Lincoln"})
        rows.append({"game_id": i, "round": "Jeopardy", "category": "4-LETTER WORDS",
                     "clue": f"a four letter word number {i}", "answer": f"wordx{i}"})
    return pd.DataFrame(rows)


def test_entity_cluster_ranks_repeated_entity():
    df = cluster_top_phrases(_clusters(), _clues(), min_freq=5, top_n=25)
    c0 = df[df["cluster_id"] == 0]
    assert c0.iloc[0]["phrase"] == "Abraham Lincoln"
    assert c0.iloc[0]["count"] == 8
    assert c0.iloc[0]["rank"] == 1
    assert (c0["n_qualifying_phrases"] > 0).all()


def test_wordplay_cluster_has_no_qualifying_phrases():
    df = cluster_top_phrases(_clusters(), _clues(), min_freq=5, top_n=25)
    c1 = df[df["cluster_id"] == 1]
    assert len(c1) == 1
    assert c1.iloc[0]["n_qualifying_phrases"] == 0
    assert pd.isna(c1.iloc[0]["phrase"])


def test_all_clusters_represented_and_columns():
    df = cluster_top_phrases(_clusters(), _clues(), min_freq=5, top_n=25)
    assert set(df["cluster_id"]) == {0, 1}
    assert list(df.columns) == ["cluster_id", "rank", "phrase", "count", "tfidf_weight", "n_qualifying_phrases"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py -v`
Expected: FAIL (`cannot import name 'cluster_top_phrases'`).

- [ ] **Step 3: Implement the ranking + writer**

Append to `jeopardy/analysis/tokens.py`:
```python
import math
from collections import Counter

import pandas as pd

from jeopardy import config


def cluster_top_phrases(clusters_df, clues_df, min_freq=5, top_n=25):
    keys = ["game_id", "round", "category"]
    merged = clues_df.merge(clusters_df[keys + ["cluster_id"]], on=keys, how="inner")
    text = (merged["clue"].fillna("") + " " + merged["answer"].fillna("")).tolist()
    cids = merged["cluster_id"].tolist()

    counts = {}  # cluster_id -> Counter(phrase -> count)
    for cid, t in zip(cids, text):
        counts.setdefault(cid, Counter()).update(extract_phrases(t))

    n_clusters = len(counts)
    doc_freq = Counter()  # phrase -> number of clusters containing it
    for counter in counts.values():
        doc_freq.update(counter.keys())

    rows = []
    for cid in sorted(counts):
        qualifying = {p: n for p, n in counts[cid].items() if n >= min_freq}
        n_qual = len(qualifying)
        if not qualifying:
            rows.append({"cluster_id": cid, "rank": 0, "phrase": None, "count": 0,
                         "tfidf_weight": 0.0, "n_qualifying_phrases": 0})
            continue
        scored = []
        for phrase, n in qualifying.items():
            idf = math.log(n_clusters / (1 + doc_freq[phrase])) + 1.0
            scored.append((phrase, n, n * idf))
        scored.sort(key=lambda x: (-x[2], -x[1], x[0]))
        for rank, (phrase, n, weight) in enumerate(scored[:top_n], start=1):
            rows.append({"cluster_id": cid, "rank": rank, "phrase": phrase, "count": n,
                         "tfidf_weight": weight, "n_qualifying_phrases": n_qual})
    return pd.DataFrame(
        rows, columns=["cluster_id", "rank", "phrase", "count", "tfidf_weight", "n_qualifying_phrases"]
    )


def run_tokens(min_freq=5, top_n=25):
    clusters = pd.read_parquet(config.CATEGORY_CLUSTERS_PATH)
    clues = pd.read_parquet(config.PARQUET_PATH)
    df = cluster_top_phrases(clusters, clues, min_freq=min_freq, top_n=top_n)
    config.CATEGORY_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.CATEGORY_TOKENS_PATH, index=False)
    applicable = df[df["n_qualifying_phrases"] > 0]["cluster_id"].nunique()
    print(f"Wrote {len(df):,} rows for {df['cluster_id'].nunique()} clusters "
          f"({applicable} with qualifying phrases) -> {config.CATEGORY_TOKENS_PATH}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/tokens.py jeopardy/tests/test_tokens.py
git commit -m "feat(analysis): per-cluster c-TF-IDF phrase ranking + artifact writer"
```

---

## Task 3: End-to-end validation + real run

**Files:**
- Test: `jeopardy/tests/test_tokens.py` (add an integration test)

**Interfaces:**
- Consumes: everything above. Produces the real committed `category_tokens.parquet`.

- [ ] **Step 1: Write an integration test (extract → rank, realistic mini-corpus)**

Append to `jeopardy/tests/test_tokens.py`:
```python
def test_pipeline_entity_beats_common_word():
    # "Lincoln" distinctive to cluster 0; "President" common to both -> Lincoln ranks above
    clusters = pd.DataFrame(
        [{"game_id": i, "round": "Jeopardy", "category": "PRES", "cluster_id": 0} for i in range(6)]
        + [{"game_id": i, "round": "Jeopardy", "category": "GOV", "cluster_id": 1} for i in range(6)]
    )
    clues = pd.DataFrame(
        [{"game_id": i, "round": "Jeopardy", "category": "PRES",
          "clue": "President Abraham Lincoln", "answer": "Abraham Lincoln"} for i in range(6)]
        + [{"game_id": i, "round": "Jeopardy", "category": "GOV",
            "clue": "President George Washington", "answer": "George Washington"} for i in range(6)]
    )
    df = cluster_top_phrases(clusters, clues, min_freq=5, top_n=25)
    c0 = df[df["cluster_id"] == 0].set_index("phrase")
    # "Abraham Lincoln" (distinctive) outranks "President" (in both clusters)
    assert c0.loc["Abraham Lincoln", "rank"] < c0.loc["President", "rank"]
```

- [ ] **Step 2: Run the full suite**

Run: `uv run --all-groups pytest jeopardy/tests -v`
Expected: PASS (all prior tests + the new token tests).

- [ ] **Step 3: Real run over the 50 clusters**

Run (fast — no embedding, reads committed artifacts):
```bash
uv run --group analysis python -m jeopardy tokens
```
Expected: writes `posts/jeopardy_ds/category_tokens.parquet`; prints how many of the 50 clusters have qualifying phrases.

- [ ] **Step 4: Inspect the output**

```bash
uv run --group analysis python -c "
import pandas as pd
t = pd.read_parquet('posts/jeopardy_ds/category_tokens.parquet')
lb = pd.read_csv('posts/jeopardy_ds/cluster_labels.csv')
print('rows:', t.shape)
stats = t.groupby('cluster_id')['n_qualifying_phrases'].first().reset_index().merge(lb, on='cluster_id')
print('--- most studyable types ---')
print(stats.sort_values('n_qualifying_phrases', ascending=False).head(8).to_string(index=False))
print('--- least (applicability ~0) ---')
print(stats.sort_values('n_qualifying_phrases').head(5).to_string(index=False))
print('--- sample: top phrases for the most studyable cluster ---')
top_cid = stats.sort_values('n_qualifying_phrases', ascending=False).iloc[0]['cluster_id']
print(t[t.cluster_id==top_cid][['rank','phrase','count']].head(12).to_string(index=False))
"
```
Expected: entity types (presidents, geography, history) top the applicability ranking; wordplay/grab-bag types near zero; the sample phrases are real entities.

- [ ] **Step 5: Commit the integration test and the real artifact**

```bash
git add jeopardy/tests/test_tokens.py posts/jeopardy_ds/category_tokens.parquet
git commit -m "test(analysis): token pipeline validation + committed category_tokens.parquet"
```

---

## Self-Review

**Spec coverage:**
- Unit = 50 cluster-types via join on (game_id, round, category) → Task 2 (`cluster_top_phrases` merge). ✓
- Token = capitalized proper-noun phrase from clue+answer → Task 1 (`extract_phrases`), Task 2 (combined text). ✓
- Regnal numerals / connectors / sentence-initial stoplist → Task 1 regex + `_strip_leading_stopwords` + tests. ✓
- c-TF-IDF with min-frequency floor, top-N → Task 2. ✓
- `n_qualifying_phrases` applicability, every cluster represented → Task 2 (placeholder rows). ✓
- Committed `category_tokens.parquet` with exact columns → Tasks 2, 3; data contract. ✓
- No new deps → uses pandas + stdlib only. ✓
- CLI `tokens` command → Task 1. ✓
- Testing (extract_phrases entity/connector/stopword/wordplay; ranking entity-vs-wordplay; integration distinctiveness) → Tasks 1–3. ✓

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `extract_phrases(text) -> list[str]` consumed by `cluster_top_phrases` (via Counter.update). `cluster_top_phrases` output columns `[cluster_id, rank, phrase, count, tfidf_weight, n_qualifying_phrases]` match the data contract and `run_tokens`'s writer and the inspection script. Join keys `[game_id, round, category]` present in both `category_clusters.parquet` (from Phase 1) and `clues.parquet` (from Sub-project A). ✓

**Known limitation (accepted):** the connector regex captures common "X of Y" titles but multi-connector titles ("War of the Roses") are captured via the `(?:connector\s+)*` run; genuinely ambiguous capitalization (all-caps cl-ues, sentence-initial proper nouns) is down-weighted by the frequency floor + c-TF-IDF rather than perfectly parsed.

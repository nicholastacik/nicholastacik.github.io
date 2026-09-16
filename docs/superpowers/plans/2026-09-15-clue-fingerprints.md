# Clue Fingerprints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For each recurring entity, show its "fingerprint" — the distinctive terms Jeopardy keeps using to clue it (with evidence counts) plus example clues with J-Archive links — rendered instantly in the detail pane, independent of Wikipedia.

**Architecture:** One offline `fingerprints` build produces (a) `clues_store.parquet` — each distinct clue once, keyed by a stable `clue_id`, intrinsic fields only; (b) `category_quiz_refs.parquet` — per `(cluster_id, phrase)` and per-cluster general, the quiz's clue-ID selections (replacing `category_sample_clues.parquet`); (c) `category_fingerprints.parquet` — per `(cluster_id, phrase)`, TF-IDF `cues` (with distinct-clue support) and `example_clue_ids`. The research build embeds only the *union of referenced* clue IDs. The tool looks up clue text by ID; the quiz and fingerprint keep separate selection rules.

**Tech Stack:** Python 3.12, pandas, scikit-learn `TfidfVectorizer`, pytest, `uv --group analysis`; self-contained HTML/JS research page; Quarto (post unaffected).

## Global Constraints

- Package manager `uv`; run tests `uv run --group analysis python -m pytest` from repo root (tests in `jeopardy/tests/`, no top-level `tests/`).
- Committed artifacts live under `posts/jeopardy_ds/`; offline steps may read `jeopardy/data/*` (gitignored) but committed artifacts must be readable without them. The `fingerprints` build reads only committed parquet + `clues.parquet`.
- `clue_id` = `"{game_id}:{round}:{row}:{column}"`, with null `row`/`column` (Final Jeopardy) as `0`. Stable and unique per physical clue.
- `cluster_id`/`phrase` must NOT be columns on `clues_store.parquet` (a clue belongs to its original cluster AND Misc); membership lives only on the refs.
- Cues: TF-IDF `TfidfVectorizer(stop_words="english", ngram_range=(1,2), token_pattern=r"[A-Za-z][A-Za-z'\-]+")`; each cue carries `support` (distinct clues containing it) and `total`; require `support >= 2`; at most 6; allow fewer/zero; drop a unigram fully subsumed by a kept bigram; drop the entity's own name tokens.
- `example_clue_ids` = the entity's single newest clue PLUS up to 3 more ranked by cue coverage, deduplicated.
- Embedded page carries ONLY the union of referenced clue IDs (fingerprint examples + quiz refs) — never the full pool. Target ≤ ~3.5 MB.
- One clue is never a "recurring cue": a single-clue entity yields zero cue chips regardless of repeated words.
- Fingerprint renders immediately from local data and stays usable if the Wikipedia fetch fails/hangs; Wikipedia loads below, async.
- J-Archive link: `https://www.j-archive.com/showgame.php?game_id={game_id}`.
- No docstrings/comments/type-hints on untouched code (repo-owner preference). Commit after each task. Work on `main` (user consented).

---

### Task 1: Clue store + quiz refs (provenance core)

**Files:**
- Create: `jeopardy/analysis/fingerprints.py`
- Modify: `jeopardy/config.py` (add paths + J-Archive URL)
- Test: `jeopardy/tests/test_fingerprints.py`

**Interfaces:**
- Consumes: `sample_clues._cluster_resolution`, `sample_clues._sample`; `tokens._cluster_phrase_counts`, `tokens.build_surface_counts`, `tokens.extract_phrases`, `tokens.load_entity_decisions`; `misc_pool.misc_membership`; `config.ERA_CUTOFFS`, `config.MISC_ID`, `config.MISC_FRACTION`.
- Produces: `clue_ids(clues_df) -> Series` (vectorized `"{game_id}:{round}:{row}:{col}"`); `build_clue_index(clusters_df, clues_df, decisions, quiz_k=2, quiz_general_n=12, min_freq=5) -> (store_df, entity_clues, quiz_refs)` where `store_df` columns are `["clue_id","clue","answer","year","category","game_id","round","row","column"]` (deduped by `clue_id`), `entity_clues` is `{(int cid, str phrase): [ {"clue_id","year","clue"} ... full pool ]}`, and `quiz_refs` is `{int cid: {phrase_or_None: [clue_id,...]}}`.

- [ ] **Step 1: Write the failing test**

Create `jeopardy/tests/test_fingerprints.py`:

```python
import pandas as pd
from jeopardy.analysis.fingerprints import clue_ids, build_clue_index

_D = pd.Timestamp("2005-06-01")


def _clusters():
    return pd.DataFrame([
        {"game_id": i, "round": "Jeopardy", "category": "ART", "cluster_id": 0} for i in range(8)
    ])


def _clues():
    rows = []
    for i in range(2):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "ART", "row": 1.0, "column": 1.0,
                     "air_date": _D, "clue": f"He cut off his ear, case {i}", "answer": "van Gogh"})
    for i in range(2, 8):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "ART", "row": 1.0, "column": 1.0,
                     "air_date": _D, "clue": "Dutch post-impressionist painter", "answer": "Vincent van Gogh"})
    return pd.DataFrame(rows)


def test_clue_ids_stable_and_unique():
    ids = clue_ids(_clues())
    assert ids.iloc[0] == "0:Jeopardy:1:1"
    assert ids.nunique() == len(ids)  # each (game,round,row,col) distinct here


def test_store_has_intrinsic_fields_only_and_deduped():
    store, entity_clues, quiz_refs = build_clue_index(_clusters(), _clues(), decisions={}, min_freq=5)
    assert list(store.columns) == ["clue_id", "clue", "answer", "year", "category",
                                   "game_id", "round", "row", "column"]
    assert "cluster_id" not in store.columns and "phrase" not in store.columns
    assert store["clue_id"].is_unique


def test_quiz_refs_map_merged_answer_to_canonical_and_keep_general():
    store, entity_clues, quiz_refs = build_clue_index(_clusters(), _clues(), decisions={}, min_freq=5)
    refs = quiz_refs[0]
    assert "Vincent van Gogh" in refs           # van Gogh answers resolve to the canonical entity
    assert None in refs                          # general pool present
    ids = set(store["clue_id"])
    assert all(cid in ids for cid in refs["Vincent van Gogh"])   # refs point into the store
    assert ("Vincent van Gogh") in {p for (c, p) in entity_clues}  # full pool captured for cues
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group analysis python -m pytest jeopardy/tests/test_fingerprints.py -q`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.fingerprints`).

- [ ] **Step 3: Add config paths**

In `jeopardy/config.py`, after `ENTITY_DECISIONS_PATH` / `CATEGORY_SAMPLE_CLUES_PATH`, add:

```python
CLUES_STORE_PATH = _POST_DIR / "clues_store.parquet"
CATEGORY_QUIZ_REFS_PATH = _POST_DIR / "category_quiz_refs.parquet"
CATEGORY_FINGERPRINTS_PATH = _POST_DIR / "category_fingerprints.parquet"
JARCHIVE_GAME_URL = "https://www.j-archive.com/showgame.php?game_id={game_id}"
```

- [ ] **Step 4: Implement the store + refs**

Create `jeopardy/analysis/fingerprints.py`:

```python
"""Clue fingerprints: a shared clue store, quiz refs, and per-entity TF-IDF cues."""
import pandas as pd

from jeopardy import config
from jeopardy.analysis.misc_pool import misc_membership
from jeopardy.analysis.sample_clues import _cluster_resolution, _sample
from jeopardy.analysis.tokens import (
    build_surface_counts,
    extract_phrases,
    load_entity_decisions,
    _cluster_phrase_counts,
)

_STORE_COLS = ["clue_id", "clue", "answer", "year", "category", "game_id", "round", "row", "column"]


def clue_ids(clues_df):
    r = clues_df["row"].fillna(0).astype(int).astype(str)
    c = clues_df["column"].fillna(0).astype(int).astype(str)
    return (clues_df["game_id"].astype(int).astype(str) + ":" + clues_df["round"].astype(str)
            + ":" + r + ":" + c)


def build_clue_index(clusters_df, clues_df, decisions, quiz_k=2, quiz_general_n=12, min_freq=5):
    clues_df = clues_df.copy()
    clues_df["year"] = pd.to_datetime(clues_df["air_date"]).dt.year
    clues_df = clues_df[clues_df["year"].notna()]
    clues_df["year"] = clues_df["year"].astype(int)
    clues_df["clue_id"] = clue_ids(clues_df)
    store = clues_df.drop_duplicates("clue_id")[_STORE_COLS].reset_index(drop=True)

    keys = ["game_id", "round", "category"]
    merged = clues_df.merge(clusters_df[keys + ["cluster_id"]], on=keys, how="inner")
    base_rows = merged[merged["cluster_id"] != config.MISC_ID]
    surface = build_surface_counts(
        list(base_rows["clue"].fillna("")) + list(base_rows["answer"].fillna(""))
    )
    entity_clues, quiz_refs = {}, {}
    for cid, sub in merged.groupby("cluster_id"):
        cdec = decisions.get(int(cid), {})
        resolution = {}
        for cutoff in config.ERA_CUTOFFS:
            era_sub = sub[sub["year"] >= cutoff]
            if era_sub.empty:
                continue
            resolution.update(_cluster_resolution(_cluster_phrase_counts(era_sub, surface), cdec, min_freq))
        by_entity, general = {}, []
        for row in sub.sort_values("year").itertuples():
            answer = row.answer if isinstance(row.answer, str) else ""
            entity = None
            for phrase in extract_phrases(answer):
                if phrase in resolution:
                    entity = resolution[phrase]
                    break
            rec = {"clue_id": row.clue_id, "year": int(row.year), "clue": row.clue}
            if entity is not None:
                by_entity.setdefault(entity, []).append(rec)
            general.append(rec)
        refs, seen = {}, set()
        for entity, recs in by_entity.items():
            entity_clues[(int(cid), entity)] = recs
            picks = _sample(recs, quiz_k)
            refs[entity] = [r["clue_id"] for r in picks]
            seen.update(refs[entity])
        pool = [r for r in general if r["clue_id"] not in seen]
        refs[None] = [r["clue_id"] for r in _sample(pool, quiz_general_n)]
        quiz_refs[int(cid)] = refs
    return store, entity_clues, quiz_refs
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run --group analysis python -m pytest jeopardy/tests/test_fingerprints.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add jeopardy/analysis/fingerprints.py jeopardy/config.py jeopardy/tests/test_fingerprints.py
git commit -m "feat(analysis): clue store + quiz refs (fingerprints provenance core)"
```

---

### Task 2: TF-IDF cues + example selection

**Files:**
- Modify: `jeopardy/analysis/fingerprints.py` (add `build_cues`)
- Test: `jeopardy/tests/test_fingerprints.py`

**Interfaces:**
- Consumes: `entity_clues` from Task 1 (`{(cid, phrase): [{"clue_id","year","clue"}]}`).
- Produces: `build_cues(entity_clues, n_cues=6, n_examples=4) -> {(cid, phrase): {"cues": [{"term","support","total"}], "example_clue_ids": [clue_id,...]}}`.

- [ ] **Step 1: Write the failing test**

Add to `jeopardy/tests/test_fingerprints.py`:

```python
from jeopardy.analysis.fingerprints import build_cues


def _mk(cid, phrase, clues):
    return {(cid, phrase): [{"clue_id": f"{cid}:{phrase}:{i}", "year": 2000 + i, "clue": c}
                            for i, c in enumerate(clues)]}


def test_cue_needs_two_distinct_clues_with_support_counts():
    # "Hannibal" recurs across 3 of Mark Twain's 4 clues; a one-off word does not qualify.
    ec = _mk(0, "Mark Twain", [
        "Born in Hannibal Missouri", "This Hannibal native", "The Hannibal author", "A riverboat pilot",
    ])
    ec.update(_mk(0, "Other", ["totally unrelated widget gadget"]))  # corpus contrast
    fp = build_cues(ec, n_cues=6, n_examples=4)[(0, "Mark Twain")]
    hann = [c for c in fp["cues"] if c["term"] == "hannibal"]
    assert hann and hann[0]["support"] == 3 and hann[0]["total"] == 4
    assert all(c["support"] >= 2 for c in fp["cues"])
    assert "twain" not in [c["term"] for c in fp["cues"]]   # entity's own name excluded


def test_single_clue_entity_has_no_cues():
    ec = _mk(0, "Solo", ["the same the same the same word word"])
    ec.update(_mk(0, "Filler", ["different other text here"]))
    fp = build_cues(ec)[(0, "Solo")]
    assert fp["cues"] == []                       # one clue -> never a recurring cue
    assert fp["example_clue_ids"] == ["0:Solo:0"]  # the one clue is the example


def test_example_ids_reserve_the_newest_even_with_low_coverage():
    # 3 old clues heavy with cue terms, 1 newest clue with none: newest must still be an example.
    ec = _mk(0, "Ex", [
        "cue cue cue alpha", "cue cue beta", "cue cue gamma", "totally different newest",
    ])
    ec.update(_mk(0, "Filler2", ["xxxx yyyy zzzz"]))
    fp = build_cues(ec, n_cues=6, n_examples=4)[(0, "Ex")]
    assert "0:Ex:3" in fp["example_clue_ids"]      # newest (index 3) reserved
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group analysis python -m pytest jeopardy/tests/test_fingerprints.py -k cue -q`
Expected: FAIL (`build_cues` undefined).

- [ ] **Step 3: Implement `build_cues`**

Add to `jeopardy/analysis/fingerprints.py`:

```python
import re

import numpy as np

_CUE_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_FILLER = {"clue", "crew", "this", "these", "one"}


def _contains(term, text):
    toks = _CUE_TOKEN.findall((text or "").lower())
    parts = term.split()
    if len(parts) == 1:
        return parts[0] in toks
    joined = " ".join(toks)
    return term in joined


def _dedup_ngrams(cues):
    bigram_words = set()
    for c in cues:
        if " " in c["term"]:
            bigram_words.update(c["term"].split())
    out = []
    for c in cues:
        if " " not in c["term"] and c["term"] in bigram_words:
            continue  # unigram fully covered by a kept bigram
        out.append(c)
    return out


def build_cues(entity_clues, n_cues=6, n_examples=4):
    from sklearn.feature_extraction.text import TfidfVectorizer
    keys = list(entity_clues)
    docs = [" ".join(r["clue"] or "" for r in entity_clues[k]) for k in keys]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=20000,
                          token_pattern=r"[A-Za-z][A-Za-z'\-]+")
    matrix = vec.fit_transform(docs)
    terms = np.array(vec.get_feature_names_out())
    out = {}
    for i, k in enumerate(keys):
        cid, phrase = k
        recs = entity_clues[k]
        total = len(recs)
        name_toks = {t.lower() for t in phrase.split()}
        row = matrix.getrow(i).toarray().ravel()
        cues = []
        for j in row.argsort()[::-1]:
            if row[j] <= 0 or len(cues) >= n_cues * 3:
                break
            term = terms[j]
            tparts = term.split()
            if any(t in name_toks for t in tparts) or any(t in _FILLER for t in tparts):
                continue
            support = sum(1 for r in recs if _contains(term, r["clue"]))
            if support < 2:
                continue
            cues.append({"term": term, "support": int(support), "total": int(total)})
        cues = _dedup_ngrams(cues)[:n_cues]
        cue_terms = [c["term"] for c in cues]
        newest = max(recs, key=lambda r: r["year"])
        by_cov = sorted(recs, key=lambda r: -sum(1 for t in cue_terms if _contains(t, r["clue"])))
        picks, seen = [newest["clue_id"]], {newest["clue_id"]}
        for r in by_cov:
            if len(picks) >= n_examples:
                break
            if r["clue_id"] not in seen:
                picks.append(r["clue_id"]); seen.add(r["clue_id"])
        out[k] = {"cues": cues, "example_clue_ids": picks}
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group analysis python -m pytest jeopardy/tests/test_fingerprints.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/fingerprints.py jeopardy/tests/test_fingerprints.py
git commit -m "feat(analysis): TF-IDF cues with support counts + newest-reserved examples"
```

---

### Task 3: `run_fingerprints` + CLI, retire `sample-clues`

**Files:**
- Modify: `jeopardy/analysis/fingerprints.py` (add `run_fingerprints`)
- Modify: `jeopardy/main.py` (add `fingerprints` command; remove `sample-clues` command)
- Modify: `jeopardy/analysis/sample_clues.py` (remove `build_sample_clues`/`run_sample_clues`; keep `_cluster_resolution`/`_sample`/`_spread`)
- Delete: `posts/jeopardy_ds/category_sample_clues.parquet`; remove `jeopardy/tests/test_sample_clues.py` tests that call the removed builder (keep any that test `_cluster_resolution` if present — none currently)
- Regenerate (committed): `clues_store.parquet`, `category_quiz_refs.parquet`, `category_fingerprints.parquet`

**Interfaces:**
- Produces: `run_fingerprints(min_freq=5)` writes the three artifacts. `category_quiz_refs.parquet` columns: `cluster_id, phrase (nullable), clue_ids (list[str])`. `category_fingerprints.parquet` columns: `cluster_id, phrase, cues (list[struct]), example_clue_ids (list[str])`.

- [ ] **Step 1: Implement `run_fingerprints`**

Add to `jeopardy/analysis/fingerprints.py`:

```python
def run_fingerprints(min_freq=5):
    clusters = pd.read_parquet(config.CATEGORY_CLUSTERS_PATH)
    clues = pd.read_parquet(config.PARQUET_PATH)
    misc = misc_membership(clusters, config.MISC_FRACTION, config.MISC_ID)
    clusters = pd.concat([clusters, misc], ignore_index=True)
    decisions = load_entity_decisions(config.ENTITY_DECISIONS_PATH)
    store, entity_clues, quiz_refs = build_clue_index(clusters, clues, decisions, min_freq=min_freq)
    cues = build_cues(entity_clues)

    quiz_rows = [{"cluster_id": cid, "phrase": ph, "clue_ids": ids}
                 for cid, refs in quiz_refs.items() for ph, ids in refs.items()]
    fp_rows = [{"cluster_id": cid, "phrase": ph, "cues": v["cues"],
                "example_clue_ids": v["example_clue_ids"]} for (cid, ph), v in cues.items()]

    config.CLUES_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    store.to_parquet(config.CLUES_STORE_PATH, index=False)
    pd.DataFrame(quiz_rows).to_parquet(config.CATEGORY_QUIZ_REFS_PATH, index=False)
    pd.DataFrame(fp_rows).to_parquet(config.CATEGORY_FINGERPRINTS_PATH, index=False)
    print(f"Wrote {len(store):,} clues, {len(quiz_rows):,} quiz refs, {len(fp_rows):,} fingerprints")
```

- [ ] **Step 2: Wire the CLI; remove `sample-clues`**

In `jeopardy/main.py`, replace the `sample-clues` command with:

```python
@cli.command()
def fingerprints():
    """Build the shared clue store, quiz refs, and per-entity TF-IDF fingerprints."""
    from jeopardy.analysis.fingerprints import run_fingerprints
    run_fingerprints()
```

In `jeopardy/analysis/sample_clues.py`, delete `build_sample_clues` and `run_sample_clues` (keep `_spread`, `_sample`, `_cluster_resolution`). Delete `jeopardy/tests/test_sample_clues.py` (its tests target the removed builder; provenance is now covered by `test_fingerprints.py`).

- [ ] **Step 3: Run the offline build (precondition: committed parquet exist)**

```bash
uv run --group analysis python -m jeopardy fingerprints
git rm --cached posts/jeopardy_ds/category_sample_clues.parquet 2>/dev/null; rm -f posts/jeopardy_ds/category_sample_clues.parquet
```

- [ ] **Step 4: Verify artifacts**

```bash
uv run --group analysis python - <<'PY'
import pandas as pd
from jeopardy import config
store = pd.read_parquet(config.CLUES_STORE_PATH)
fp = pd.read_parquet(config.CATEGORY_FINGERPRINTS_PATH)
qr = pd.read_parquet(config.CATEGORY_QUIZ_REFS_PATH)
assert store["clue_id"].is_unique and "cluster_id" not in store.columns
allids = set(store["clue_id"])
ref_ids = set(i for ids in qr["clue_ids"] for i in ids) | set(i for ids in fp["example_clue_ids"] for i in ids)
assert ref_ids <= allids, "referenced clue ids missing from store"
print("clues", len(store), "| fingerprints", len(fp), "| referenced", len(ref_ids))
row = fp[fp.phrase == "Mark Twain"]
if len(row): print("Mark Twain cues:", [(c["term"], c["support"], c["total"]) for c in row.iloc[0]["cues"]][:6])
PY
```

- [ ] **Step 5: Run the suite + commit**

Run: `uv run --group analysis python -m pytest -q` — expected all pass (sample-clue tests removed).

```bash
git add jeopardy/analysis/fingerprints.py jeopardy/analysis/sample_clues.py jeopardy/main.py \
        posts/jeopardy_ds/clues_store.parquet posts/jeopardy_ds/category_quiz_refs.parquet \
        posts/jeopardy_ds/category_fingerprints.parquet
git rm posts/jeopardy_ds/category_sample_clues.parquet
git add jeopardy/tests/test_sample_clues.py
git commit -m "feat(analysis): fingerprints CLI + artifacts; retire category_sample_clues"
```

---

### Task 4: Research build — embed pruned clues + fingerprints + quiz refs

**Files:**
- Modify: `jeopardy/analysis/research.py` (`build_research_data`, `run_research`)
- Test: `jeopardy/tests/test_research.py`

**Interfaces:**
- Consumes: the three artifacts from Task 3.
- Produces: `build_research_data(tokens_df, eras_df, labels, fingerprints_df=None, quiz_refs_df=None, clues_df=None)` returns extra keys: `"clues"` (id → `{clue,answer,year,category,game_id}`, ONLY referenced ids), `"fingerprints"` (`{str cid: {phrase: {cues, exampleClueIds}}}`), `"quiz"` (`{str cid: {phrase_or_"": [clue_id]}}`). `byEra`/`sampleClues` removed.

- [ ] **Step 1: Write the failing test**

Add to `jeopardy/tests/test_research.py`:

```python
def _fp_df():
    return pd.DataFrame([{"cluster_id": 0, "phrase": "Mark Twain",
                          "cues": [{"term": "hannibal", "support": 3, "total": 4}],
                          "example_clue_ids": ["1:Jeopardy:1:1"]}])

def _quiz_df():
    return pd.DataFrame([{"cluster_id": 0, "phrase": "Mark Twain", "clue_ids": ["1:Jeopardy:1:1"]},
                         {"cluster_id": 0, "phrase": None, "clue_ids": ["9:Jeopardy:2:2"]}])

def _clues_store_df():
    return pd.DataFrame([
        {"clue_id": "1:Jeopardy:1:1", "clue": "This Hannibal native", "answer": "Mark Twain",
         "year": 1994, "category": "AUTHORS", "game_id": 1, "round": "Jeopardy", "row": 1, "column": 1},
        {"clue_id": "9:Jeopardy:2:2", "clue": "unreferenced-by-nobody? no, general refs it", "answer": "x",
         "year": 2001, "category": "MISC", "game_id": 9, "round": "Jeopardy", "row": 2, "column": 2},
        {"clue_id": "7:Jeopardy:3:3", "clue": "NEVER REFERENCED", "answer": "y",
         "year": 2000, "category": "X", "game_id": 7, "round": "Jeopardy", "row": 3, "column": 3},
    ])


def test_build_embeds_only_referenced_clues():
    data = build_research_data(_tokens_df(), _eras_df(), _labels(), _fp_df(), _quiz_df(), _clues_store_df())
    assert set(data["clues"].keys()) == {"1:Jeopardy:1:1", "9:Jeopardy:2:2"}  # unreferenced pruned
    assert "NEVER REFERENCED" not in json_dumps(data)
    assert data["fingerprints"]["0"]["Mark Twain"]["cues"][0]["term"] == "hannibal"
    assert data["quiz"]["0"][""] == ["9:Jeopardy:2:2"]  # general pool keyed by ""


def json_dumps(d):
    import json
    return json.dumps(d)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group analysis python -m pytest jeopardy/tests/test_research.py -k referenced -q`
Expected: FAIL (signature/keys).

- [ ] **Step 3: Implement**

In `jeopardy/analysis/research.py`, change `build_research_data` signature and replace the `sample_map` block with the referenced-union logic (keep the `byEra` entity list construction intact — the left/main panes still use it):

```python
def build_research_data(tokens_df, eras_df, labels, fingerprints_df=None, quiz_refs_df=None, clues_df=None):
```

At the end, before `return`, replace the old `sample_map` code with:

```python
    fingerprints = {}
    if fingerprints_df is not None:
        for _, r in fingerprints_df.iterrows():
            fingerprints.setdefault(str(int(r["cluster_id"])), {})[r["phrase"]] = {
                "cues": list(r["cues"]), "exampleClueIds": list(r["example_clue_ids"])}
    quiz = {}
    if quiz_refs_df is not None:
        for _, r in quiz_refs_df.iterrows():
            key = "" if (r["phrase"] is None or pd.isna(r["phrase"])) else r["phrase"]
            quiz.setdefault(str(int(r["cluster_id"])), {})[key] = list(r["clue_ids"])
    referenced = set()
    for byphrase in fingerprints.values():
        for v in byphrase.values():
            referenced.update(v["exampleClueIds"])
    for byphrase in quiz.values():
        for ids in byphrase.values():
            referenced.update(ids)
    clues = {}
    if clues_df is not None:
        for _, r in clues_df[clues_df["clue_id"].isin(referenced)].iterrows():
            clues[r["clue_id"]] = {"clue": r["clue"], "answer": r["answer"], "year": int(r["year"]),
                                   "category": r["category"], "game_id": int(r["game_id"])}
    return {"eras": [int(e) for e in eras], "byEra": by_era,
            "fingerprints": fingerprints, "quiz": quiz, "clues": clues,
            "jarchive": config.JARCHIVE_GAME_URL}
```

Update `run_research` to load the three artifacts and pass them (guard each with `.exists()`):

```python
    fp = pd.read_parquet(config.CATEGORY_FINGERPRINTS_PATH) if config.CATEGORY_FINGERPRINTS_PATH.exists() else None
    qr = pd.read_parquet(config.CATEGORY_QUIZ_REFS_PATH) if config.CATEGORY_QUIZ_REFS_PATH.exists() else None
    cs = pd.read_parquet(config.CLUES_STORE_PATH) if config.CLUES_STORE_PATH.exists() else None
    data = build_research_data(tokens, eras, labels, fp, qr, cs)
```

Delete the old `sample = pd.read_parquet(config.CATEGORY_SAMPLE_CLUES_PATH)...` line.

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group analysis python -m pytest jeopardy/tests/test_research.py -q`
Expected: PASS. (Update any pre-existing sample-clue payload test to the new `quiz`/`clues` shape; the byEra/render/era-selector tests stay.)

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/research.py jeopardy/tests/test_research.py
git commit -m "feat(research): embed pruned clue store + fingerprints + quiz refs"
```

---

### Task 5: Detail-pane UI — instant fingerprint + ref-based quiz

**Files:**
- Modify: `jeopardy/analysis/research.py` (`_HTML_TEMPLATE` CSS/JS)
- Test: `jeopardy/tests/test_research.py`

**Interfaces:** consumes `DATA.clues`, `DATA.fingerprints`, `DATA.quiz`.

- [ ] **Step 1: Write the failing test**

Add to `jeopardy/tests/test_research.py`:

```python
def test_render_html_has_fingerprint_and_ref_quiz():
    data = build_research_data(_tokens_df(), _eras_df(), _labels(), _fp_df(), _quiz_df(), _clues_store_df())
    html = render_html(data)
    for marker in ["renderFingerprint", "cue-chip", "j-archive", "DATA.clues", "DATA.quiz", "DATA.fingerprints"]:
        assert marker in html
```

- [ ] **Step 2: Run to verify failure** — `uv run --group analysis python -m pytest jeopardy/tests/test_research.py -k fingerprint -q` → FAIL.

- [ ] **Step 3: Implement the JS/CSS**

In `_HTML_TEMPLATE`, add CSS near `.sample-card`:

```css
  .fingerprint { margin: 0 0 18px; }
  .fingerprint .eyebrow { color: var(--gold); }
  .cue-chip { display: inline-block; font-family: var(--mono); font-size: 11px; background: var(--panel-2);
    border: 1px solid var(--line); border-radius: var(--radius); padding: 3px 8px; margin: 0 6px 6px 0; }
  .cue-chip .support { color: var(--ash); }
  .fp-clue { border-left: 3px solid var(--gold); padding: 8px 12px; margin: 8px 0; background: var(--panel); }
  .fp-clue .meta { font-family: var(--mono); font-size: 11px; color: var(--ash); }
```

Replace `eligibleClues`/`rollSampleClue` to resolve IDs through `DATA.clues` and `DATA.quiz` (general key `""`), keeping the same scoped/fellBack/recency behavior:

```javascript
      function clueById(id) { return DATA.clues && DATA.clues[id]; }

      function eligibleClues(clusterId) {
        const refs = (DATA.quiz && DATA.quiz[String(clusterId)]) || {};
        const toClues = ids => (ids || []).map(clueById).filter(Boolean);
        if (selectedEntity) {
          const scoped = toClues(refs[selectedEntity.phrase]).filter(c => c.year >= currentEra);
          if (scoped.length) return { clues: scoped, scoped: true, fellBack: false };
          return { clues: toClues(refs[""]).filter(c => c.year >= currentEra), scoped: false, fellBack: true };
        }
        return { clues: toClues(refs[""]).filter(c => c.year >= currentEra), scoped: false, fellBack: false };
      }
```

(`rollSampleClue` is unchanged except it now receives clue objects that also have `game_id`; leave its body as-is.)

Also update `renderMain`'s sample-button guard (the old `DATA.sampleClues` is gone): replace
`const hasSamples = ((DATA.sampleClues && DATA.sampleClues[String(d.cluster_id)]) || []).length > 0;`
with `const hasSamples = !!(DATA.quiz && DATA.quiz[String(d.cluster_id)]);`.

Add a fingerprint renderer and call it FIRST in `selectEntity`, before the Wikipedia fetch (the
`"jarchive"` key is already in the `build_research_data` return from Task 4):

```javascript
      function renderFingerprint(entity) {
        const byPhrase = (DATA.fingerprints && DATA.fingerprints[String(selectedTypeId)]) || {};
        const fp = byPhrase[entity.phrase];
        let html = '<p class="eyebrow">The answer</p>' + `<h3>${escapeHtml(entity.phrase)}</h3>`;
        if (fp) {
          html += '<div class="fingerprint"><p class="eyebrow">How Jeopardy clues it</p>';
          if (fp.cues && fp.cues.length) {
            html += fp.cues.map(c => `<span class="cue-chip">${escapeHtml(c.term)}` +
              ` <span class="support">&middot; ${c.support} of ${c.total}</span></span>`).join('');
          }
          const examples = (fp.exampleClueIds || []).map(clueById).filter(Boolean)
            .filter(c => c.year >= currentEra);
          const shown = examples.length ? examples
            : (fp.exampleClueIds || []).map(clueById).filter(Boolean).slice(-1);
          shown.slice(0, 3).forEach(c => {
            const url = DATA.jarchive.replace('{game_id}', c.game_id);
            html += `<div class="fp-clue"><p class="clue-text">${escapeHtml(c.clue)}</p>` +
              `<p class="meta">${escapeHtml(c.answer)} &middot; ${escapeHtml(c.category)} &middot; ${c.year} ` +
              `&middot; <a class="j-archive" href="${url}" target="_blank" rel="noopener">J-Archive &#8599;</a></p></div>`;
          });
          html += '</div>';
        }
        html += '<div id="wiki-slot"><p class="pulse">Asking Wikipedia&hellip;</p></div>';
        detailPanel.innerHTML = html;
      }
```

Add `DATA.jarchive` to the payload: in `build_research_data`'s return add `"jarchive": config.JARCHIVE_GAME_URL`. Rewrite `selectEntity` so the fingerprint paints immediately and Wikipedia fills `#wiki-slot` async (surviving failure):

```javascript
      async function selectEntity(entity) {
        if (selectedEntity === entity) {
          selectedEntity = null; renderMain(); renderDetailEmpty(); return;
        }
        selectedEntity = entity;
        renderMain();
        renderFingerprint(entity);
        if (window.matchMedia('(max-width: 980px)').matches) detailPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        let summary = wikiCache.has(entity.phrase) ? wikiCache.get(entity.phrase) : await fetchWiki(entity.phrase);
        wikiCache.set(entity.phrase, summary);
        if (selectedEntity !== entity) return;
        const slot = document.getElementById('wiki-slot');
        if (!slot) return;
        if (summary && summary.extract) {
          const thumb = summary.thumbnail && summary.thumbnail.source;
          const url = summary.content_urls && summary.content_urls.desktop && summary.content_urls.desktop.page;
          slot.innerHTML = (thumb ? `<img src="${escapeHtml(thumb)}" alt="${escapeHtml(entity.phrase)}">` : '') +
            `<p class="extract">${escapeHtml(summary.extract)}</p>` +
            (url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">Read the full article on Wikipedia &#8599;</a>` : '');
        } else {
          const s = 'https://en.wikipedia.org/w/index.php?search=' + encodeURIComponent(entity.phrase);
          slot.innerHTML = `<p class="fallback">No Wikipedia summary. <a href="${escapeHtml(s)}" target="_blank" rel="noopener">Search &#8599;</a></p>`;
        }
      }
```

Remove the now-unused `renderDetailLoading`/`renderDetail`. Keep `renderDetailEmpty`.

- [ ] **Step 4: Run tests + smoke render**

Run: `uv run --group analysis python -m pytest jeopardy/tests/test_research.py -q` — expected PASS.
Then `uv run --group analysis python -m jeopardy research` and confirm "Wrote ..." with no error.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/research.py jeopardy/tests/test_research.py
git commit -m "feat(research): instant clue-fingerprint detail pane + ref-based quiz"
```

---

### Task 6: Regenerate + size + post beat

**Files:** Modify `posts/jeopardy_ds/index.qmd` (one story line); regenerate `research/index.html`, `_freeze/...`.

- [ ] **Step 1: Regenerate the tool**

```bash
uv run --group analysis python -m jeopardy research
echo "HTML MB: $(echo "scale=2; $(wc -c < posts/jeopardy_ds/research/index.html)/1000000" | bc)"
```
If > ~3.5 MB, lower `quiz_k`/`quiz_general_n`/`n_examples` in `run_fingerprints`/`build_cues`, rerun `jeopardy fingerprints` + `research`, and note it.

- [ ] **Step 2: Add a post line** — in `posts/jeopardy_ds/index.qmd`'s "A study tool" section, after the sample-clue sentence, add:

```markdown
Each answer now also carries a **clue fingerprint** — the handful of terms Jeopardy keeps using to
ask about it (with how often), and real example clues linked back to J-Archive — so you can study
the *angle*, not just the name.
```

- [ ] **Step 3: Render + full suite**

```bash
uv run quarto render posts/jeopardy_ds/index.qmd
uv run --group analysis python -m pytest -q
```
Both must succeed ("Output created"; all tests pass).

- [ ] **Step 4: Commit**

```bash
git add posts/jeopardy_ds/research/index.html posts/jeopardy_ds/index.qmd _freeze/posts/jeopardy_ds
git commit -m "content: regenerate tool with clue fingerprints; add story line"
```

---

### Task 7: Browser verification (HUMAN)

- [ ] Serve (`! uv run quarto preview`) and check in `posts/jeopardy_ds/research/`:
  - Click a known entity (e.g. Mark Twain): fingerprint chips read sensibly with "N of M" counts; example clues show category + year + a working **J-Archive** link to the right game; the fingerprint appears **immediately** (before Wikipedia).
  - **Offline check:** block network (DevTools offline) and click an entity — the fingerprint still renders and is usable; only the Wikipedia slot degrades.
  - Quiz "Sample clue" still works (scoped/broaden/era), now via references; era filter respected; recent windows have examples.
  - Mobile (≤980px): detail scrolls into view; layout intact.

---

## Notes for the executor
- Order matters: T1 (store/refs) → T2 (cues) → T3 (build/CLI) → T4 (embed) → T5 (UI). T3 regenerates the artifacts T4/T5 read.
- The offline `fingerprints` build needs the committed `category_clusters.parquet`, `cluster_labels.csv`, `entity_decisions.csv`, and `clues.parquet` — all present in the repo (no gitignored caches required).

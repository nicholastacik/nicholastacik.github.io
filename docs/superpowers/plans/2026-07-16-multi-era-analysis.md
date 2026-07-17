# Multi-Era Filterable Study Tool + Entity Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recompute the token analysis per era (since 1980/90/2000/2010/2020) over the stable 50-type taxonomy, with entity deduplication and count-sorting, and make the research tool filterable by era; fix the post's Chrome scatter.

**Architecture:** A deduplication module (pure, tested) feeds a per-era token pipeline that writes long-format `category_tokens.parquet` (+ `category_eras.parquet` + a merge report). A human merge-review checkpoint gates artifact regeneration. The research tool embeds all eras and filters client-side; the post switches its scatter to SVG.

**Tech Stack:** Python 3.12+, pandas, stdlib (`re`, `collections`, edit-distance helper). Vanilla HTML/CSS/JS (tool). No new dependencies.

## Global Constraints

- Python `>=3.12`. **No new dependencies.**
- Stable taxonomy: `category_clusters.parquet` and `cluster_labels.csv` are **unchanged** (no re-embed/re-cluster/re-UMAP).
- Eras = cumulative cutoffs `ERA_CUTOFFS = [1980, 1990, 2000, 2010, 2020]` (each = clues with `air_date >= YYYY-01-01`; 1980 ≈ all-time).
- Entity dedup = Moderate: plurals + unambiguous partial↔full component merge + fuzzy misspelling (edit distance ≤1, single-token, min length 5). Keep the fuller name for component merges; the dominant-count form otherwise; sum counts. Emit a merge report reviewed by the author before artifacts are committed.
- Entities ranked by **count desc** (tiebreak tfidf_weight desc, then phrase); `top_n=25` per (era, cluster). c-TF-IDF still computed for the applicability signal.
- Artifacts (regenerated, committed under `posts/jeopardy_ds/`): `category_tokens.parquet` (`era, cluster_id, rank, phrase, count, tfidf_weight`), `category_eras.parquet` (`era, cluster_id, size, share, n_qualifying_phrases`).
- Research tool: era selector defaulting to **2010**; count-sorted deduped entities; per-type prevalence; all eras embedded, filtered client-side; live Wikipedia fetch unchanged.
- Post keeps the all-time narrative; only the Chrome scatter fix (WebGL→SVG, ~4,500 pts) + era-column filtering (`era==1980`) in its token cells + one pointer sentence.
- Run from repo root. Tests: `uv run --all-groups pytest jeopardy/tests -v`. Pipeline: `uv run --group analysis python -m jeopardy tokens`.
- Don't touch unrelated files (incl. `posts/montreal_events/`).

---

## Task 1: Entity dedup module

**Files:**
- Create: `jeopardy/analysis/dedup.py`
- Test: `jeopardy/tests/test_dedup.py`

**Interfaces:**
- Produces: `canonicalize(counts: dict[str,int]) -> tuple[dict[str,int], list[tuple[str,str]]]` — collapses variant phrases within ONE cluster, returning `(merged_counts, merges)` where each merge is `(loser, winner)`.

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/test_dedup.py`:
```python
from jeopardy.analysis.dedup import canonicalize, edit_distance_le_1


def test_edit_distance_le_1():
    assert edit_distance_le_1("niels", "neils")      # transposition-ish substitution
    assert edit_distance_le_1("emmy", "emmys")       # one insertion
    assert not edit_distance_le_1("mars", "venus")


def test_plural_merges_to_dominant():
    out, merges = canonicalize({"Emmy": 50, "Emmys": 30})
    assert out == {"Emmy": 80}
    assert ("Emmys", "Emmy") in merges


def test_component_merges_to_fuller_name():
    out, _ = canonicalize({"Bohr": 169, "Niels": 40, "Niels Bohr": 111})
    assert out == {"Niels Bohr": 320}


def test_fuzzy_merges_misspelling():
    out, _ = canonicalize({"Niels": 40, "Neils": 10})
    assert out == {"Niels": 50}


def test_ambiguous_surname_not_over_merged():
    # "Adams" is a component of BOTH -> ambiguous -> not merged; the two Johns stay distinct
    out, _ = canonicalize({"John Adams": 30, "John Quincy Adams": 20, "Adams": 15})
    assert "John Adams" in out and "John Quincy Adams" in out
    assert out["John Adams"] == 30 and out["John Quincy Adams"] == 20


def test_short_distinct_words_not_fuzzy_merged():
    # length < 5 -> no fuzzy merge (Mars the planet vs Marx the person)
    out, _ = canonicalize({"Mars": 50, "Marx": 20})
    assert out == {"Mars": 50, "Marx": 20}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_dedup.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.dedup`).

- [ ] **Step 3: Implement `jeopardy/analysis/dedup.py`**

```python
"""Collapse variant entity phrases within a cluster (plurals, partial/full, misspellings)."""


def edit_distance_le_1(a, b):
    """True if the Levenshtein distance between a and b is <= 1."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:  # one substitution
        return sum(x != y for x, y in zip(a, b)) == 1
    if la > lb:   # make a the shorter
        a, b, la, lb = b, a, lb, la
    i = j = diff = 0  # one insertion/deletion
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            diff += 1
            j += 1
            if diff > 1:
                return False
    return True


def _contiguous(short, long_):
    n, m = len(short), len(long_)
    if n == 0 or n >= m:
        return False
    return any(long_[i:i + n] == short for i in range(m - n + 1))


def _plural(a, b):  # a, b already lowercased
    return b in (a + "s", a + "es") or a in (b + "s", b + "es")


def canonicalize(counts):
    """Return (merged_counts, merges) for one cluster's phrase->count mapping."""
    phrases = list(counts)
    toks = {p: [t.lower() for t in p.split()] for p in phrases}
    low = {p: p.lower() for p in phrases}
    parent = {p: p for p in phrases}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        parent[find(a)] = find(b)

    # Rule 1: unambiguous component merge (shorter is a contiguous token subseq of exactly one longer)
    for a in phrases:
        containers = [b for b in phrases
                      if b != a and len(toks[b]) > len(toks[a]) and _contiguous(toks[a], toks[b])]
        if len(containers) == 1:
            union(a, containers[0])
    # Rule 2 (plurals) + Rule 3 (single-token fuzzy, min length 5)
    for i, a in enumerate(phrases):
        for b in phrases[i + 1:]:
            if _plural(low[a], low[b]) or (
                len(toks[a]) == 1 and len(toks[b]) == 1
                and len(low[a]) >= 5 and len(low[b]) >= 5
                and edit_distance_le_1(low[a], low[b])
            ):
                union(a, b)

    groups = {}
    for p in phrases:
        groups.setdefault(find(p), []).append(p)
    result, merges = {}, []
    for members in groups.values():
        canon = max(members, key=lambda p: (len(toks[p]), counts[p], p))
        result[canon] = sum(counts[m] for m in members)
        merges.extend((m, canon) for m in members if m != canon)
    return result, merges
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_dedup.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/dedup.py jeopardy/tests/test_dedup.py
git commit -m "feat(analysis): entity dedup (plurals, partial/full, fuzzy) with over-merge guards"
```

---

## Task 2: Per-era token pipeline + artifacts

**Files:**
- Modify: `jeopardy/analysis/tokens.py`, `jeopardy/config.py`
- Test: `jeopardy/tests/test_tokens.py`

**Interfaces:**
- Consumes: `extract_phrases`, `build_surface_counts` (existing in tokens.py); `canonicalize` (Task 1); `config.ERA_CUTOFFS`, `config.CATEGORY_TOKENS_PATH`, `config.CATEGORY_ERAS_PATH`, `config.DEDUP_MERGES_PATH`.
- Produces:
  - `era_tokens(clusters_df, clues_df, cutoffs, min_freq=5, top_n=25) -> (tokens_df, eras_df, merges)` — long-format per (era, cluster).
  - `run_tokens(min_freq=5, top_n=25)` — writes both parquets + the merge report.

- [ ] **Step 1: Add config**

Append to `jeopardy/config.py`:
```python
ERA_CUTOFFS = [1980, 1990, 2000, 2010, 2020]
CATEGORY_ERAS_PATH = _POST_DIR / "category_eras.parquet"
DEDUP_MERGES_PATH = _POST_DIR / "notes" / "dedup-merges.md"
```

- [ ] **Step 2: Write the failing tests**

Append to `jeopardy/tests/test_tokens.py`:
```python
from jeopardy.analysis.tokens import era_tokens


def _era_clusters():
    return pd.DataFrame([
        {"game_id": g, "round": "Jeopardy", "category": "SCIENTISTS", "cluster_id": 0}
        for g in range(12)
    ])


def _era_clues():
    rows = []
    for g in range(12):
        yr = 1995 if g < 6 else 2015  # half old, half recent
        rows.append({"game_id": g, "round": "Jeopardy", "category": "SCIENTISTS",
                     "air_date": pd.Timestamp(f"{yr}-01-01"),
                     "clue": "This physicist Niels Bohr and also Bohr", "answer": "Niels Bohr"})
    return pd.DataFrame(rows)


def test_era_tokens_long_format_and_dedup():
    tokens_df, eras_df, merges = era_tokens(_era_clusters(), _era_clues(), [1980, 2010], min_freq=2, top_n=25)
    assert set(tokens_df["era"]) == {1980, 2010}
    # Bohr/Niels folded into Niels Bohr by dedup
    phrases_1980 = set(tokens_df[tokens_df["era"] == 1980]["phrase"])
    assert "Niels Bohr" in phrases_1980
    assert "Bohr" not in phrases_1980
    # eras_df has one row per (era, cluster)
    assert set(eras_df.columns) == {"era", "cluster_id", "size", "share", "n_qualifying_phrases"}


def test_era_tokens_count_sorted():
    tokens_df, _, _ = era_tokens(_era_clusters(), _era_clues(), [1980], min_freq=2, top_n=25)
    counts = tokens_df[tokens_df["era"] == 1980].sort_values("rank")["count"].tolist()
    assert counts == sorted(counts, reverse=True)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py::test_era_tokens_long_format_and_dedup -v`
Expected: FAIL (`cannot import name 'era_tokens'`).

- [ ] **Step 4: Implement `era_tokens` + rework `run_tokens` in `jeopardy/analysis/tokens.py`**

Add (keeping the existing `extract_phrases`, `build_surface_counts`, and cap-dominance helpers; `era_tokens` replaces the single-shot `cluster_top_phrases` role):
```python
import math
from collections import Counter

import pandas as pd

from jeopardy import config
from jeopardy.analysis.dedup import canonicalize

DEDUP_CANDIDATE_K = 150  # dedup the top-K by count per (era, cluster) before selecting top_n


def _cluster_phrase_counts(sub, surface):
    """sub: rows for one cluster (clue/answer). Returns Counter(phrase->count) after cap-dominance filter."""
    c = Counter()
    for clue, ans in zip(sub["clue"], sub["answer"]):
        c.update(extract_phrases(clue))
        c.update(extract_phrases(ans))
    return Counter({p: n for p, n in c.items() if _keep_single_word(p, surface)})  # existing cap-dominance rule


def era_tokens(clusters_df, clues_df, cutoffs, min_freq=5, top_n=25):
    keys = ["game_id", "round", "category"]
    merged = clues_df.merge(clusters_df[keys + ["cluster_id"]], on=keys, how="inner")
    merged["year"] = pd.to_datetime(merged["air_date"]).dt.year
    token_rows, era_rows, all_merges = [], [], []

    for cutoff in cutoffs:
        era = merged[merged["year"] >= cutoff]
        surface = build_surface_counts(
            list(era["clue"].fillna("")) + list(era["answer"].fillna(""))
        )
        total_instances = era.groupby(["game_id", "round", "category"]).ngroups or 1
        # per-cluster
        per_cluster_counts = {}
        for cid, sub in era.groupby("cluster_id"):
            raw = _cluster_phrase_counts(sub, surface)
            # dedup the top-K candidates by count, then keep >= min_freq
            topk = dict(sorted(raw.items(), key=lambda kv: -kv[1])[:DEDUP_CANDIDATE_K])
            merged_counts, merges = canonicalize(topk)
            all_merges.extend((cutoff, cid, lo, hi) for lo, hi in merges)
            per_cluster_counts[cid] = {p: n for p, n in merged_counts.items() if n >= min_freq}
        # c-TF-IDF idf within this era's cluster set
        doc_freq = Counter()
        for c in per_cluster_counts.values():
            doc_freq.update(c.keys())
        n_clusters = len(per_cluster_counts)
        # instances per cluster (for prevalence)
        sizes = era.groupby("cluster_id").apply(
            lambda g: g.groupby(["game_id", "round", "category"]).ngroups
        )
        for cid, counts in per_cluster_counts.items():
            n_qual = len(counts)
            era_rows.append({"era": cutoff, "cluster_id": int(cid),
                             "size": int(sizes.get(cid, 0)),
                             "share": float(sizes.get(cid, 0)) / total_instances,
                             "n_qualifying_phrases": n_qual})
            scored = []
            for phrase, n in counts.items():
                idf = math.log(n_clusters / doc_freq[phrase]) if doc_freq[phrase] else 0.0
                scored.append((phrase, n, n * idf))
            scored.sort(key=lambda x: (-x[1], -x[2], x[0]))  # COUNT desc, then tfidf, then phrase
            for rank, (phrase, n, w) in enumerate(scored[:top_n], start=1):
                token_rows.append({"era": cutoff, "cluster_id": int(cid), "rank": rank,
                                   "phrase": phrase, "count": int(n), "tfidf_weight": float(w)})

    tokens_df = pd.DataFrame(token_rows, columns=["era", "cluster_id", "rank", "phrase", "count", "tfidf_weight"])
    eras_df = pd.DataFrame(era_rows, columns=["era", "cluster_id", "size", "share", "n_qualifying_phrases"])
    return tokens_df, eras_df, all_merges


def _write_merge_report(merges, path):
    lines = ["---", "draft: true", "---", "", "# Entity dedup merges", ""]
    by_key = {}
    for era, cid, lo, hi in merges:
        by_key.setdefault((era, cid), []).append((lo, hi))
    for (era, cid), pairs in sorted(by_key.items()):
        lines.append(f"## era {era}, cluster {cid}")
        for lo, hi in pairs:
            lines.append(f"- `{lo}` + → `{hi}`")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_tokens(min_freq=5, top_n=25):
    clusters = pd.read_parquet(config.CATEGORY_CLUSTERS_PATH)
    clues = pd.read_parquet(config.PARQUET_PATH)
    tokens_df, eras_df, merges = era_tokens(clusters, clues, config.ERA_CUTOFFS, min_freq, top_n)
    tokens_df.to_parquet(config.CATEGORY_TOKENS_PATH, index=False)
    eras_df.to_parquet(config.CATEGORY_ERAS_PATH, index=False)
    _write_merge_report(merges, config.DEDUP_MERGES_PATH)
    print(f"Wrote {len(tokens_df):,} token rows across {len(config.ERA_CUTOFFS)} eras; "
          f"{len(merges):,} merges -> {config.DEDUP_MERGES_PATH}")
```
(If the existing cap-dominance helper is named differently than `_keep_single_word`/`build_surface_counts`, reuse the actual names from the current `tokens.py` — do not invent new ones; the intent is: keep the existing single-word cap-dominance filter, just apply it inside the per-era loop.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py -v`
Expected: PASS (new era tests + the existing token tests that still apply; update any existing test that referenced the old single-era `cluster_top_phrases` signature to the new `era_tokens`, keeping its intent).

- [ ] **Step 6: Commit**

```bash
git add jeopardy/analysis/tokens.py jeopardy/config.py jeopardy/tests/test_tokens.py
git commit -m "feat(analysis): per-era token pipeline with dedup, count-sort, prevalence"
```

---

## Task 3: Merge-review checkpoint + regenerate artifacts (controller/human gate)

**Files:**
- Regenerate: `posts/jeopardy_ds/category_tokens.parquet`, `posts/jeopardy_ds/category_eras.parquet`, `posts/jeopardy_ds/notes/dedup-merges.md`

This is a human gate, not an automated build.

- [ ] **Step 1: Run the real pipeline**

Run: `uv run --group analysis python -m jeopardy tokens`
Expected: writes the two parquets + `posts/jeopardy_ds/notes/dedup-merges.md`; prints token-row and merge counts.

- [ ] **Step 2: Review the merge report with the author**

Present `posts/jeopardy_ds/notes/dedup-merges.md` (and a sample of top entities per type per era) to the author. Look for over-merges (distinct entities collapsed). If any rule is too eager, tune `dedup.py` (e.g., raise the fuzzy min-length, tighten the component guard), re-run Task 2's tests, and regenerate. Repeat until the author approves the merges.

- [ ] **Step 3: Commit the regenerated artifacts**

```bash
git add posts/jeopardy_ds/category_tokens.parquet posts/jeopardy_ds/category_eras.parquet posts/jeopardy_ds/notes/dedup-merges.md
git commit -m "data(analysis): per-era deduped token artifacts"
```

---

## Task 4: Research tool — per-era data + era selector

**Files:**
- Modify: `jeopardy/analysis/research.py`, `jeopardy/tests/test_research.py`
- Regenerate: `posts/jeopardy_ds/research/index.html`

**Interfaces:**
- Consumes: `config.CATEGORY_TOKENS_PATH` (now with `era`), `config.CATEGORY_ERAS_PATH`, `config.CLUSTER_LABELS_PATH`, `config.ERA_CUTOFFS`.
- Produces: `build_research_data(tokens_df, eras_df, labels) -> dict` (`{"eras": [...], "byEra": {"<cutoff>": [ {cluster_id, name, applicability, prevalence, entities:[{phrase,count}]} sorted by applicability desc ]}}`).

- [ ] **Step 1: Rework `build_research_data` (per-era) + tests**

Update the signature to take `eras_df` and produce the per-era structure (entities count-sorted — the tokens are already count-sorted by rank; carry `share` as `prevalence`). Update `jeopardy/tests/test_research.py`'s fixtures to the new `(tokens_df, eras_df, labels)` shape and assert: `data["eras"] == config.ERA_CUTOFFS`; each era lists all types sorted by applicability desc; entities are count-desc; prevalence present. Fold in the deferred nit: assert the non-studyable dim marking properly (check the `dim` class / label string in `render_html`, not just the name).

```python
def build_research_data(tokens_df, eras_df, labels):
    by_era = {}
    eras = sorted(eras_df["era"].unique())
    for era in eras:
        et = tokens_df[tokens_df["era"] == era]
        ee = eras_df[eras_df["era"] == era].set_index("cluster_id")
        entries = []
        for cid, name in labels.items():
            rows = et[et["cluster_id"] == cid].sort_values("rank")
            stat = ee.loc[cid] if cid in ee.index else None
            entries.append({
                "cluster_id": int(cid), "name": name,
                "applicability": int(stat["n_qualifying_phrases"]) if stat is not None else 0,
                "prevalence": float(stat["share"]) if stat is not None else 0.0,
                "entities": [{"phrase": r["phrase"], "count": int(r["count"])}
                             for _, r in rows.iterrows() if r["phrase"] is not None and pd.notna(r["phrase"])],
            })
        entries.sort(key=lambda d: d["applicability"], reverse=True)
        by_era[str(int(era))] = entries
    return {"eras": [int(e) for e in eras], "byEra": by_era}
```

- [ ] **Step 2: Update `render_html` + `run_research` (frontend-design)**

Invoke the **frontend-design** skill. Extend the existing self-contained page:
- Add an **era selector** (segmented control) for `DATA.eras`, defaulting to `2010`.
- On era change: read `DATA.byEra[era]`, re-render the type list (sorted by that era's applicability) with a **prevalence** indicator per type, and the selected type's entities (already count-sorted). Keep the type selection stable across era changes when possible.
- Entities render count-desc (as given). Live Wikipedia fetch unchanged.
- `run_research` now reads both parquets: `tokens = pd.read_parquet(config.CATEGORY_TOKENS_PATH); eras = pd.read_parquet(config.CATEGORY_ERAS_PATH); labels = ...; data = build_research_data(tokens, eras, labels)`. Write with `encoding="utf-8"`.

- [ ] **Step 3: Run tests + generate**

Run: `uv run --all-groups pytest jeopardy/tests/test_research.py -v` (PASS), then `uv run --group analysis python -m jeopardy research`.
Expected: page regenerated; embeds all 5 eras; structural one-liner confirms `DATA.eras == [1980,1990,2000,2010,2020]` and each era has 50 types.

- [ ] **Step 4: Commit**

```bash
git add jeopardy/analysis/research.py jeopardy/tests/test_research.py posts/jeopardy_ds/research/index.html
git commit -m "feat(research): era selector, count-sorted entities, prevalence"
```

---

## Task 5: Post — Chrome scatter fix + era-column filtering

**Files:**
- Modify: `posts/jeopardy_ds/index.qmd`
- Regenerate: `_freeze/posts/jeopardy_ds/...`

- [ ] **Step 1: Fix the scatter (WebGL→SVG) and the era-column reads**

In `index.qmd`:
- `fig-clusters` cell: change `render_mode="webgl"` to `render_mode="svg"` and the sample cap from `10000` to `4500` (so it loads in Chrome; SVG at ~4.5k points is smooth enough).
- The token cells (`tbl-types`, `fig-applicability`, `tbl-entities`) now read a long-format `category_tokens.parquet` with an `era` column and applicability from `category_eras.parquet`. Filter to all-time: add `tokens = tokens[tokens["era"] == 1980]` after loading, and load `eras = pd.read_parquet("category_eras.parquet"); eras = eras[eras["era"] == 1980]` for the applicability bar (`n_qualifying_phrases` now comes from `eras`, joined on `cluster_id`). Keep the prose/numbers all-time.
- §7 "A study tool": add one sentence that the tool is now filterable by era (1980→2020).

- [ ] **Step 2: Render + verify (incl. Chrome)**

Run: `uv run quarto render posts/jeopardy_ds/index.qmd`
Expected: clean render; the token tables/applicability bar still populate (all-time). Then open `_site/posts/jeopardy_ds/index.html` **in Chrome** and confirm Figure 2 (the cluster scatter) now loads.

- [ ] **Step 3: Commit**

```bash
git add posts/jeopardy_ds/index.qmd _freeze/posts/jeopardy_ds
git commit -m "post(jeopardy): SVG scatter for Chrome + era-column token reads + tool pointer"
```

---

## Task 6: Browser verification (controller/human checkpoint)

- [ ] **Step 1: Exercise the tool**

Restart `quarto preview` (or open the file) and verify at `posts/jeopardy_ds/research/`:
- The era selector switches between 1980→2020; the type order + entities + prevalence update.
- Entities are count-sorted; deduped variants (Emmy/Emmys, Niels Bohr) are collapsed.
- Sliding to recent eras (2010/2020) shows plausibly different top entities than all-time.
- Live Wikipedia fetch still works; graceful fallback intact.

- [ ] **Step 2: Confirm Chrome scatter**

Confirm the post's Figure 2 loads in Chrome (the WebGL→SVG fix).

- [ ] **Step 3: Any polish** — iterate the tool via frontend-design per author feedback; regenerate + re-commit as needed.

---

## Self-Review

**Spec coverage:**
- Cumulative eras 1980–2020 → Task 2 (`ERA_CUTOFFS`, `era_tokens`). ✓
- Stable taxonomy unchanged → no changes to category_clusters/cluster_labels. ✓
- Moderate dedup (plurals, unambiguous component, fuzzy≤1 min-len-5) + over-merge guards → Task 1 + tests (incl. Adams + Mars negatives). ✓
- Merge report + human review gate → Task 2 (`_write_merge_report`), Task 3 (checkpoint). ✓
- Count-sort → Task 2 (`scored.sort` count-first). ✓
- Artifacts (`category_tokens` w/ era, `category_eras`) → Task 2. ✓
- Research tool per-era + selector + prevalence + count-sort + nits → Task 4. ✓
- Post Chrome SVG fix + era filtering + pointer → Task 5. ✓
- Browser verification → Task 6. ✓
- No new deps → dedup is stdlib. ✓

**Placeholder scan:** Task 2 Step 4 flags that the existing cap-dominance helper names must be reused verbatim from the current `tokens.py` (rather than the illustrative `_keep_single_word`/`build_surface_counts`) — the implementer reads the current file for the real names; this is a real instruction, not a TODO. Task 4 Step 2 delegates visuals to frontend-design with a concrete data contract + behavior. No other placeholders.

**Type consistency:** `canonicalize(dict) -> (dict, merges)` consumed by `era_tokens`, which emits `tokens_df` (era, cluster_id, rank, phrase, count, tfidf_weight) + `eras_df` (era, cluster_id, size, share, n_qualifying_phrases) — consumed by `build_research_data(tokens_df, eras_df, labels)` and the post cells. `run_tokens`/`run_research` read the config paths defined in Task 2. ✓

**Known risks (call out during execution):**
- Task 2 must reuse the *actual* existing helper names in `tokens.py` (cap-dominance filter, surface counts) — read the file; don't invent.
- Dedup over-merge is expected to need tuning; that's what Task 3's human gate is for.
- Interactive era selector + Chrome scatter are browser-verified (Tasks 5–6), not unit-tested.

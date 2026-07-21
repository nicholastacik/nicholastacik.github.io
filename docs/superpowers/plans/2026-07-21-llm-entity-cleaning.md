# LLM Entity-Cleaning Pass (Token Quality v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean the token lists via a deterministic pre-filter + an in-session LLM validity/canonical pass, applied deterministically from a committed `entity_decisions.csv`.

**Architecture:** Two pure, tested code units — a mechanical pre-filter and an apply-decisions step — plug into the existing `era_tokens` pipeline. The LLM classification is an offline controller-orchestrated authoring step (like cluster naming) that produces the committed CSV; the pipeline only reads it. Iteration is cheap (edit CSV → regenerate; no re-embed).

**Tech Stack:** Python 3.12+, pandas, stdlib (`csv`). No new runtime dependency.

## Global Constraints

- Python `>=3.12`. No new runtime dependency (the LLM pass is offline authoring).
- `entity_decisions.csv` columns: `cluster_id, phrase, keep, canonical, source` (`source ∈ {llm, manual}`). Committed at `posts/jeopardy_ds/entity_decisions.csv`. `config.ENTITY_DECISIONS_PATH`.
- Deterministic pre-filter drops ONLY unambiguous noise: phrases containing "clue crew" (case-insensitive) and exact single-token interjections `{Oh, Hi, Ah, Hey}`. Months / nationalities / vague names are the LLM's job — NOT the pre-filter's (May/March are name-ambiguous).
- Apply order in `era_tokens`: raw counts (cap-dominance filter + pre-filter) → top-150 → `canonicalize` (dedup) → **apply entity decisions** → `>= min_freq` → count-sort → top_n. Decisions keyed per `(cluster_id, phrase)`, applied every era. Absent phrase → default keep. Applying only affects the DISPLAY path (the applicability metric stays on raw counts, which the pre-filter already cleans).
- LLM classification is in-session (controller-orchestrated subagents), reviewed with the author before commit. Hand-fixes carry `source=manual` and are never overwritten by an LLM re-run.
- Stable taxonomy untouched (`category_clusters.parquet`, `cluster_labels.csv`). No re-embed/re-cluster.
- Run from repo root. Tests: `uv run --all-groups pytest jeopardy/tests -v`.
- Don't touch unrelated files (incl. `posts/montreal_events/`).

## File structure

```
jeopardy/analysis/tokens.py    # + is_mechanical_noise, load_entity_decisions, apply_entity_decisions; wire into era_tokens
jeopardy/config.py             # + ENTITY_DECISIONS_PATH
jeopardy/tests/test_tokens.py  # + tests
posts/jeopardy_ds/entity_decisions.csv   # committed LLM/curated decisions (Task 3)
posts/jeopardy_ds/index.qmd    # + methodology beat (Task 5)
```

---

## Task 1: Deterministic pre-filter

**Files:**
- Modify: `jeopardy/analysis/tokens.py`
- Test: `jeopardy/tests/test_tokens.py`

**Interfaces:**
- Produces: `is_mechanical_noise(phrase: str) -> bool`. Wired into `era_tokens`'s raw-count filter (alongside the existing cap-dominance `_is_generic_single_word`), so mechanical noise is dropped from raw counts.

- [ ] **Step 1: Write the failing tests**

Append to `jeopardy/tests/test_tokens.py`:
```python
from jeopardy.analysis.tokens import is_mechanical_noise


def test_mechanical_noise_drops_clue_crew_and_interjections():
    assert is_mechanical_noise("Sarah of the Clue Crew")
    assert is_mechanical_noise("Jimmy of the Clue Crew")
    assert is_mechanical_noise("Oh")
    assert is_mechanical_noise("Hi")


def test_mechanical_noise_keeps_real_and_ambiguous():
    # real entities, and the ambiguous ones the LLM (not the pre-filter) must judge
    for p in ["Isaac Newton", "May", "April", "March", "English", "Oh Brother"]:
        assert not is_mechanical_noise(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py::test_mechanical_noise_drops_clue_crew_and_interjections -v`
Expected: FAIL (`cannot import name 'is_mechanical_noise'`).

- [ ] **Step 3: Implement `is_mechanical_noise` + wire into the raw filter**

Add to `jeopardy/analysis/tokens.py`:
```python
_INTERJECTIONS = {"Oh", "Hi", "Ah", "Hey"}


def is_mechanical_noise(phrase):
    """Unambiguous non-entity noise: Clue Crew presenter metadata + bare interjections."""
    if "clue crew" in phrase.lower():
        return True
    return phrase in _INTERJECTIONS
```
Then, in `era_tokens` where the per-cluster raw counts are built with the cap-dominance filter (the comprehension using `_is_generic_single_word`), add `and not is_mechanical_noise(phrase)` so mechanical noise is excluded from `raw` (this also keeps it out of the applicability count). Read the current filter expression and extend it in place — do not duplicate the counting logic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py -v`
Expected: PASS (new + existing token tests).

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/tokens.py jeopardy/tests/test_tokens.py
git commit -m "feat(analysis): deterministic pre-filter for Clue Crew + interjection noise"
```

---

## Task 2: Apply entity decisions

**Files:**
- Modify: `jeopardy/analysis/tokens.py`, `jeopardy/config.py`
- Test: `jeopardy/tests/test_tokens.py`

**Interfaces:**
- Consumes: `config.ENTITY_DECISIONS_PATH`.
- Produces:
  - `load_entity_decisions(path) -> dict[int, dict[str, tuple[bool, str]]]` — `{cluster_id: {phrase: (keep, canonical)}}`; `{}` if the file is missing.
  - `apply_entity_decisions(counts: dict[str, int], cluster_decisions: dict[str, tuple[bool, str]]) -> dict[str, int]` — drops `keep=False`, remaps `canonical != phrase` (summing counts), default-keeps phrases absent from the decisions.
  - Wired into `era_tokens` after `canonicalize`, before the `min_freq` floor.

- [ ] **Step 1: Add config**

Append to `jeopardy/config.py`:
```python
ENTITY_DECISIONS_PATH = _POST_DIR / "entity_decisions.csv"
```

- [ ] **Step 2: Write the failing tests**

Append to `jeopardy/tests/test_tokens.py`:
```python
from jeopardy.analysis.tokens import apply_entity_decisions, load_entity_decisions


def test_apply_drops_remaps_and_default_keeps():
    counts = {"John": 40, "Grey": 20, "Anatomy": 15, "Isaac Newton": 30}
    decisions = {
        "John": (False, ""),               # drop (vague)
        "Grey": (True, "Grey's Anatomy"),  # merge into fuller
        "Anatomy": (True, "Grey's Anatomy"),
        # "Isaac Newton" absent -> default keep
    }
    out = apply_entity_decisions(counts, decisions)
    assert "John" not in out
    assert out["Grey's Anatomy"] == 35   # 20 + 15 summed
    assert out["Isaac Newton"] == 30     # default keep
    assert "Grey" not in out and "Anatomy" not in out


def test_load_entity_decisions_missing_file(tmp_path):
    assert load_entity_decisions(tmp_path / "nope.csv") == {}


def test_load_entity_decisions_parses(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("cluster_id,phrase,keep,canonical,source\n"
                 "3,John,false,,llm\n"
                 "3,Grey,true,Grey's Anatomy,llm\n")
    d = load_entity_decisions(p)
    assert d[3]["John"] == (False, "")
    assert d[3]["Grey"] == (True, "Grey's Anatomy")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py -k "apply or load_entity" -v`
Expected: FAIL (import errors).

- [ ] **Step 4: Implement + wire in**

Add to `jeopardy/analysis/tokens.py`:
```python
import csv


def load_entity_decisions(path):
    """{cluster_id: {phrase: (keep, canonical)}} from the CSV; {} if the file is absent."""
    out = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            keep = row["keep"].strip().lower() in ("true", "1", "yes")
            out.setdefault(int(row["cluster_id"]), {})[row["phrase"]] = (keep, row["canonical"])
    return out


def apply_entity_decisions(counts, cluster_decisions):
    """Drop keep=False; remap canonical!=phrase (summing); default-keep absent phrases."""
    out = {}
    for phrase, n in counts.items():
        decision = cluster_decisions.get(phrase)
        if decision is None:
            out[phrase] = out.get(phrase, 0) + n
            continue
        keep, canonical = decision
        if not keep:
            continue
        target = canonical if (canonical and canonical.strip()) else phrase
        out[target] = out.get(target, 0) + n
    return out
```
Wire into `era_tokens`: near the top, load once `decisions = load_entity_decisions(config.ENTITY_DECISIONS_PATH)`. In the per-cluster loop, after `merged_counts, merges = canonicalize(topk)`, insert
`merged_counts = apply_entity_decisions(merged_counts, decisions.get(int(cid), {}))`
BEFORE the `>= min_freq` filter that builds the display counts. (Applicability / `n_qualifying_phrases` is computed from the raw counts as before — do NOT route it through `apply_entity_decisions`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_tokens.py -v`
Expected: PASS. (With no `entity_decisions.csv` present yet, `load_entity_decisions` returns `{}` → default-keep → pipeline behavior unchanged.)

- [ ] **Step 6: Commit**

```bash
git add jeopardy/analysis/tokens.py jeopardy/config.py jeopardy/tests/test_tokens.py
git commit -m "feat(analysis): apply committed entity decisions in the token pipeline"
```

---

## Task 3: In-session LLM classification + review gate (CONTROLLER + LLM, human-gated)

This is not a code task — it is a controller-orchestrated authoring step that produces the committed `entity_decisions.csv`, with a human review gate. No production code changes.

- [ ] **Step 1: Derive the candidate set**

From the current committed `posts/jeopardy_ds/category_tokens.parquet`, for each `cluster_id` collect the union of distinct displayed `phrase`s across all eras, with each phrase's max count (for context). This is the shortlist to judge (~a few thousand `(cluster_id, phrase)` pairs).

- [ ] **Step 2: Run the in-session LLM pass (fanned across subagents)**

For each cluster (batch several clusters per subagent to bound dispatch count), give a subagent: the cluster's name (from `cluster_labels.csv`) + its candidate phrases with counts, and this rubric — return, per phrase, `keep` and `canonical`:
- **drop** (`keep=false`): vague bare first names ("John", "James", "Michael"), stray interjections/filler ("Oh", "Hi"), calendar months used as months, nationality/adjective tokens ("English", "French", "British", "Spanish", "Canadian" as standalones), and any remaining production/metadata junk.
- **merge** (`keep=true, canonical=<fuller/joined form>`): broken possessives ("Grey"+"Anatomy" → "Grey's Anatomy"), noun/adjective country pairs ("Canadian" → "Canada"), and partial↔full names the rules missed.
- **keep** (`keep=true, canonical=<phrase>`): genuine studyable entities.
Assemble all returned rows into `posts/jeopardy_ds/entity_decisions.csv` (`cluster_id, phrase, keep, canonical, source=llm`).

- [ ] **Step 3: Review gate with the author**

Present the drop and merge decisions (a summary: counts by action + the full drop list + all merges, per cluster) to the author. Apply hand-fixes by editing rows and setting `source=manual`. Tune the rubric and re-run specific clusters if needed (an LLM re-run replaces only `source=llm` rows; `manual` rows are preserved). Repeat until approved.

- [ ] **Step 4: Commit the decisions**

```bash
git add posts/jeopardy_ds/entity_decisions.csv
git commit -m "data(analysis): LLM entity-cleaning decisions (curated)"
```

---

## Task 4: Regenerate the cascade + verify (CONTROLLER)

- [ ] **Step 1: Regenerate artifacts + tool**

Run:
```bash
uv run --group analysis python -m jeopardy tokens
uv run --group analysis python -m jeopardy research
```
Expected: `era_tokens` now applies `entity_decisions.csv`; artifacts + research page regenerate.

- [ ] **Step 2: Verify the cleaning worked**

Spot-check the regenerated `category_tokens.parquet` / research page: the flagged noise is gone (no bare "John"/"Michael" in Books&Authors/Movies/Television; no "Clue Crew" anywhere; no standalone nationalities where dropped) and merges took ("Grey's Anatomy" present, "Grey"/"Anatomy" gone). Confirm entities are still count-sorted and every cluster still has entities.

- [ ] **Step 3: Commit regenerated artifacts**

```bash
git add posts/jeopardy_ds/category_tokens.parquet posts/jeopardy_ds/category_eras.parquet posts/jeopardy_ds/research/index.html posts/jeopardy_ds/notes/dedup-merges.md
git commit -m "data(analysis): regenerate tokens + tool with LLM entity cleaning"
```

---

## Task 5: Post methodology beat

**Files:**
- Modify: `posts/jeopardy_ds/index.qmd`

- [ ] **Step 1: Add the "why rules weren't enough" section**

In `index.qmd`, in the findings/tool area (after the entity-tables discussion, before §7's tool link), add a short prose subsection (no new code cell needed) telling the methodology story: the proper-noun + dedup rules got most of the way, but couldn't judge *studyability* — "John" vs "John Adams", "Grey"/"Anatomy" vs "Grey's Anatomy", or Jeopardy's "Clue Crew" presenter names that aren't answers at all. So an LLM took a second pass over the candidate entities, marking keep/drop and merging variants, and the resulting decisions are applied deterministically. Use 2–3 concrete before/after examples. Keep it a few sentences; match the post's voice. Do not overclaim (it's a curated pass, not fully automated).

- [ ] **Step 2: Render to verify**

Run: `uv run quarto render posts/jeopardy_ds/index.qmd`
Expected: clean render; the new prose appears; no cell errors (this is prose-only, so no data dependency).

- [ ] **Step 3: Commit**

```bash
git add posts/jeopardy_ds/index.qmd _freeze/posts/jeopardy_ds
git commit -m "post(jeopardy): methodology beat on LLM entity cleaning"
```

---

## Task 6: Browser verification (HUMAN checkpoint)

- [ ] **Step 1:** Restart `quarto preview`; open the research tool. Confirm the flagged noise is gone across the clusters the author cited (Books & Authors, Pop Music, Movies, Television, World Geography, Notable People, Oscars, Museums, Royalty, American History, Sports, Explorers), merges look right, and the era selector + live Wikipedia still work.
- [ ] **Step 2:** Iterate per the Iteration workflow in the spec (edit CSV rows → `tokens`+`research` → re-view; or ask for a scoped LLM re-judge of a cluster). `source=manual` edits persist.

---

## Self-Review

**Spec coverage:**
- Deterministic pre-filter (Clue Crew + interjections only; months/nationalities → LLM) → Task 1 + tests (keeps May/April/English). ✓
- LLM per-cluster keep/drop + canonical → Task 3; committed `entity_decisions.csv` (with `source`) → Tasks 2 (schema/load), 3 (author). ✓
- Apply deterministically after dedup, all eras, default-keep, display-only (not applicability) → Task 2 + wiring. ✓
- Review gate + `source=manual` protection + iteration → Tasks 3, 6. ✓
- Regenerate cascade + verify → Task 4. ✓
- Post methodology beat → Task 5. ✓
- No new runtime dep, stable taxonomy untouched, config path → Global Constraints + Tasks 1–2. ✓
- Out of scope (Oscars/Movies clustering; applicability metric change) → not implemented. ✓

**Placeholder scan:** Task 1 Step 3 instructs reusing the actual raw-filter expression in the current `tokens.py` (not duplicating) — a real instruction. Task 3/5 are authoring/prose steps with concrete rubric + examples, not code placeholders. No TODOs.

**Type consistency:** `load_entity_decisions -> {int: {str:(bool,str)}}` consumed by `apply_entity_decisions(counts, cluster_decisions)` in `era_tokens`; CSV columns `cluster_id,phrase,keep,canonical,source` match the loader and Task 3's writer. `is_mechanical_noise(str)->bool` used in the raw filter. ✓

**Known risks (call out during execution):**
- Task 1 must extend the *existing* cap-dominance filter expression in `era_tokens` (read the file for the exact comprehension) — don't reimplement counting.
- Task 3 is a large fan-out (50 clusters); batch clusters per subagent and expect a review/tune loop (that's the point).
- Applying decisions is display-only by design; applicability stays raw (pre-filter-cleaned). If the author later wants applicability cleaned too, that's a follow-up.

# Interactive Research Tool (Sub-project C, Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-contained interactive study page (type browser → ranked entities → live Wikipedia facts on click), generated from the committed token data and served at `posts/jeopardy_ds/research/`.

**Architecture:** A `python -m jeopardy research` command reads `category_tokens.parquet` + `cluster_labels.csv`, builds a per-type entity structure (pure, testable), embeds it as JSON in a self-contained HTML file (inline CSS/JS, live client-side Wikipedia fetch), and writes the committed `posts/jeopardy_ds/research/index.html`.

**Tech Stack:** Python 3.12+, pandas (data), vanilla HTML/CSS/JS (the page, no build tooling, no external assets). Frontend built with the frontend-design skill.

## Global Constraints

- Python `>=3.12`. **No new dependencies** (pandas + stdlib; the page's JS is inline and runs in the browser).
- The page is a **single self-contained HTML file** — inline CSS + JS, no external stylesheets/scripts/CDN, data embedded as JSON. Committed at `posts/jeopardy_ds/research/index.html`.
- The site's `_quarto.yml` `render` list renders only `.qmd`; this `.html` ships as a copied static asset (served at `/posts/jeopardy_ds/research/`). Do not add it to the render list.
- Facts are fetched **live, client-side** from Wikipedia: primary `https://en.wikipedia.org/api/rest_v1/page/summary/{title}` (CORS-enabled); fallback to the search API (`.../w/api.php?...&origin=*`) on 404/disambiguation; graceful degradation to a search link on any failure/offline.
- Inputs (committed): `posts/jeopardy_ds/category_tokens.parquet` (`cluster_id, rank, phrase, count, tfidf_weight, n_qualifying_phrases`; `phrase` is None for zero-qualifying clusters' placeholder row) and `posts/jeopardy_ds/cluster_labels.csv` (`cluster_id, name`).
- Types sorted by studyability (`n_qualifying_phrases` desc); non-studyable types (empty entity list) shown but visually de-emphasized.
- The frontend uses the **frontend-design** skill for HTML/CSS/interaction quality. **Visual iteration after first render is expected** (Task 3) — "build a working, correct tool" (Tasks 1–2) is distinct from "polish how it looks" (Task 3).
- Run from repo root. Tests: `uv run --all-groups pytest jeopardy/tests -v`. Generate: `uv run --group analysis python -m jeopardy research` (works with plain `uv run` too — only pandas needed).
- Don't touch unrelated pre-existing files.

---

## Data contract

`build_research_data(tokens_df, labels) -> list[dict]`, one entry per cluster-type, sorted by `applicability` descending:
```json
{"cluster_id": 26, "name": "Books & Authors", "applicability": 3125,
 "entities": [{"phrase": "Agatha Christie", "count": 111}, ...]}
```
Placeholder rows (`phrase is None`) are dropped, so a non-studyable type has `"entities": []`.

## File structure

```
jeopardy/
  analysis/
    research.py            # build_research_data / render_html / run_research
  config.py                # + RESEARCH_HTML_PATH (Modify)
  main.py                  # + research command (Modify)
  tests/
    test_research.py
posts/jeopardy_ds/research/
  index.html               # generated, committed
```

---

## Task 1: Data layer — config, CLI, `build_research_data`

**Files:**
- Create: `jeopardy/analysis/research.py` (partial — `build_research_data` only)
- Modify: `jeopardy/config.py`, `jeopardy/main.py`
- Test: `jeopardy/tests/test_research.py`

**Interfaces:**
- Produces: `jeopardy.config.RESEARCH_HTML_PATH`; `jeopardy.main.cli` gains a `research` command (deferred import); `jeopardy.analysis.research.build_research_data(tokens_df, labels: dict) -> list[dict]` (per the data contract).

- [ ] **Step 1: Add the config path**

Append to `jeopardy/config.py`:
```python
RESEARCH_HTML_PATH = _POST_DIR / "research" / "index.html"
```

- [ ] **Step 2: Add the `research` CLI command**

Append inside `jeopardy/main.py` (after the existing commands):
```python
@cli.command()
def research():
    """Generate the interactive research tool -> posts/jeopardy_ds/research/index.html."""
    from jeopardy.analysis.research import run_research
    run_research()
```

- [ ] **Step 3: Write the failing tests**

Create `jeopardy/tests/test_research.py`:
```python
import pandas as pd
from jeopardy.analysis.research import build_research_data


def _tokens():
    return pd.DataFrame([
        {"cluster_id": 1, "rank": 1, "phrase": "Agatha Christie", "count": 111,
         "tfidf_weight": 9.0, "n_qualifying_phrases": 2},
        {"cluster_id": 1, "rank": 2, "phrase": "Toni Morrison", "count": 65,
         "tfidf_weight": 8.0, "n_qualifying_phrases": 2},
        {"cluster_id": 2, "rank": 0, "phrase": None, "count": 0,
         "tfidf_weight": 0.0, "n_qualifying_phrases": 0},  # non-studyable placeholder
    ])


def _labels():
    return {1: "Books & Authors", 2: "Wordplay & Vocabulary"}


def test_shape_and_sort():
    data = build_research_data(_tokens(), _labels())
    assert [d["name"] for d in data] == ["Books & Authors", "Wordplay & Vocabulary"]  # sorted by applicability desc
    assert data[0]["applicability"] == 2
    assert data[0]["entities"] == [
        {"phrase": "Agatha Christie", "count": 111},
        {"phrase": "Toni Morrison", "count": 65},
    ]


def test_placeholder_type_has_empty_entities():
    data = build_research_data(_tokens(), _labels())
    wordplay = next(d for d in data if d["name"] == "Wordplay & Vocabulary")
    assert wordplay["applicability"] == 0
    assert wordplay["entities"] == []


def test_all_types_present():
    data = build_research_data(_tokens(), _labels())
    assert {d["cluster_id"] for d in data} == {1, 2}
    assert all(set(d) == {"cluster_id", "name", "applicability", "entities"} for d in data)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run --all-groups pytest jeopardy/tests/test_research.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.analysis.research`).

- [ ] **Step 5: Implement `build_research_data` in `jeopardy/analysis/research.py`**

```python
"""Generate the interactive research tool (type -> entities -> live Wikipedia facts)."""
import pandas as pd


def build_research_data(tokens_df, labels):
    """Per-type entity data for the research page, sorted by applicability desc."""
    out = []
    for cluster_id, name in labels.items():
        rows = tokens_df[tokens_df["cluster_id"] == cluster_id]
        applicability = int(rows["n_qualifying_phrases"].iloc[0]) if len(rows) else 0
        entities = [
            {"phrase": r["phrase"], "count": int(r["count"])}
            for _, r in rows.iterrows()
            if r["phrase"] is not None and pd.notna(r["phrase"])
        ]
        out.append({
            "cluster_id": int(cluster_id),
            "name": name,
            "applicability": applicability,
            "entities": entities,
        })
    out.sort(key=lambda d: d["applicability"], reverse=True)
    return out
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --all-groups pytest jeopardy/tests/test_research.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add jeopardy/analysis/research.py jeopardy/config.py jeopardy/main.py jeopardy/tests/test_research.py
git commit -m "feat(research): data layer + CLI command for the study tool"
```

---

## Task 2: The page — `render_html` + `run_research` (frontend-design)

**Files:**
- Modify: `jeopardy/analysis/research.py` (add `render_html`, `run_research`)
- Test: `jeopardy/tests/test_research.py` (add structural tests)
- Create: `posts/jeopardy_ds/research/index.html` (generated)

**Interfaces:**
- Consumes: `build_research_data`; `jeopardy.config` (`CATEGORY_TOKENS_PATH`, `CLUSTER_LABELS_PATH`, `RESEARCH_HTML_PATH`).
- Produces: `render_html(data: list[dict]) -> str` (a complete self-contained HTML document with `data` embedded as JSON); `run_research()` (reads inputs, writes `RESEARCH_HTML_PATH`).

- [ ] **Step 1: Build the self-contained HTML template with the frontend-design skill**

Invoke the **frontend-design** skill to produce the page markup/style. The deliverable is a `render_html(data)` Python function that returns ONE complete self-contained HTML document (no external assets, no CDN) with these REQUIREMENTS:

- Embed the data exactly once: `const DATA = <json>;` where `<json>` is `json.dumps(data)` (use `json.dumps(..., ensure_ascii=False)`).
- **Master-detail layout:** a left column listing every type (name + a small "N entities" / applicability badge), sorted as given (already applicability-desc); types with `entities.length === 0` are visually de-emphasized (dimmed) and labeled "not really studyable." Selecting a type shows its ranked entities (phrase + count) in the main column.
- **Entity click → live Wikipedia facts** in a detail panel, using this exact fetch logic (the functional core — implement verbatim; style the surrounding panel freely):

```javascript
async function fetchWiki(phrase) {
  const REST = t => `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(t)}?redirect=true`;
  try {
    let r = await fetch(REST(phrase));
    if (r.ok) {
      const j = await r.json();
      if (j.type !== 'disambiguation' && j.extract) return j;
    }
    const s = await fetch(`https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(phrase)}&format=json&origin=*`);
    if (s.ok) {
      const hit = (await s.json())?.query?.search?.[0];
      if (hit) {
        const r2 = await fetch(REST(hit.title));
        if (r2.ok) { const j2 = await r2.json(); if (j2.extract) return j2; }
      }
    }
  } catch (e) { /* fall through to null */ }
  return null;
}
```
- Render on success: `summary.extract`, optional `summary.thumbnail?.source`, and a link to `summary.content_urls?.desktop?.page`. On `null` (unresolved/offline/error): show a graceful fallback link to `https://en.wikipedia.org/w/index.php?search=<phrase>` (no crash, no blank panel).
- Self-contained, theme-neutral-but-clean, readable at desktop widths; no console errors on load.

Add the `render_html` function to `jeopardy/analysis/research.py` (it may build the HTML via a template string; the JSON is injected with `json.dumps`). It must be a COMPLETE working document — no TODOs/placeholders.

- [ ] **Step 2: Add `run_research` to `jeopardy/analysis/research.py`**

```python
import json
from jeopardy import config


def run_research():
    tokens = pd.read_parquet(config.CATEGORY_TOKENS_PATH)
    labels = pd.read_csv(config.CLUSTER_LABELS_PATH).set_index("cluster_id")["name"].to_dict()
    data = build_research_data(tokens, labels)
    html = render_html(data)
    config.RESEARCH_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.RESEARCH_HTML_PATH.write_text(html)
    studyable = sum(1 for d in data if d["entities"])
    print(f"Wrote {config.RESEARCH_HTML_PATH} ({len(data)} types, {studyable} studyable)")
```

- [ ] **Step 3: Add structural tests for `render_html`**

Append to `jeopardy/tests/test_research.py`:
```python
import json
from jeopardy.analysis.research import render_html


def test_render_html_is_self_contained_and_embeds_data():
    data = build_research_data(_tokens(), _labels())
    html = render_html(data)
    assert html.strip().lower().startswith("<!doctype html")
    assert "const DATA" in html
    # data embedded as JSON and parseable back
    assert "Agatha Christie" in html and "Books &amp; Authors" in html or "Books & Authors" in html
    # no external asset references
    assert "cdn." not in html and "<script src=" not in html and "<link " not in html
    # the live-fetch endpoint + fallback are present
    assert "api/rest_v1/page/summary" in html
    assert "list=search" in html


def test_render_html_marks_non_studyable():
    data = build_research_data(_tokens(), _labels())
    html = render_html(data)
    # both type names appear (studyable + non-studyable)
    assert "Wordplay &amp; Vocabulary" in html or "Wordplay & Vocabulary" in html
```

- [ ] **Step 4: Run tests**

Run: `uv run --all-groups pytest jeopardy/tests/test_research.py -v`
Expected: PASS (data + structural tests).

- [ ] **Step 5: Generate the real page**

Run: `uv run --group analysis python -m jeopardy research`
Expected: writes `posts/jeopardy_ds/research/index.html`; prints `50 types, N studyable`.

- [ ] **Step 6: Structural sanity of the generated file**

Run:
```bash
uv run python -c "
import re, pathlib, json
h = pathlib.Path('posts/jeopardy_ds/research/index.html').read_text()
m = re.search(r'const DATA\s*=\s*(\[.*?\]);', h, re.S)
data = json.loads(m.group(1))
print('types:', len(data))
print('studyable:', sum(1 for d in data if d['entities']))
print('top type:', data[0]['name'], '->', [e['phrase'] for e in data[0]['entities'][:3]])
print('sorted desc:', all(data[i]['applicability'] >= data[i+1]['applicability'] for i in range(len(data)-1)))
"
```
Expected: 50 types, sorted desc, top type is entity-dense (e.g. Books & Authors) with real entities.

- [ ] **Step 7: Commit code + generated page**

```bash
git add jeopardy/analysis/research.py jeopardy/tests/test_research.py posts/jeopardy_ds/research/index.html
git commit -m "feat(research): self-contained study page with live Wikipedia facts"
```

---

## Task 3: Browser verification + visual iteration (checkpoint)

**Files:**
- Modify (as iteration requires): `jeopardy/analysis/research.py` (template), then regenerate `posts/jeopardy_ds/research/index.html`

**Interfaces:**
- Consumes: the generated page. No new production interfaces.

This task is a human/controller checkpoint, not an automated build — the interactive behavior (live Wikipedia fetch, layout feel) can only be judged in a browser.

- [ ] **Step 1: Open and exercise the page**

Open `posts/jeopardy_ds/research/index.html` in a browser (or serve the site: `uv run quarto preview`). Verify:
- The 50 types list, sorted by studyability; non-studyable types dimmed/marked.
- Selecting a type shows its ranked entities with counts.
- Clicking an entity loads a real Wikipedia summary inline (extract + link; thumbnail when present).
- A deliberately ambiguous entity still resolves via the search fallback, and a nonsense/offline case degrades to a search link (no crash, no blank panel, no console errors).

- [ ] **Step 2: Visual iteration**

Present the rendered page to the author. Using the frontend-design skill, iterate on layout, styling, and interaction feel per feedback. After each change, regenerate (`uv run --group analysis python -m jeopardy research`) and re-open. Repeat until approved.

- [ ] **Step 3: Commit the polished page**

```bash
git add jeopardy/analysis/research.py posts/jeopardy_ds/research/index.html
git commit -m "feat(research): visual polish"
```

- [ ] **Step 4: (Optional) verify the post link resolves**

The post links to `research/`. Render the site (`uv run quarto render`) and confirm `_site/posts/jeopardy_ds/research/index.html` exists (the `.html` is copied as a static asset). Expected: file present under `_site`.

---

## Self-Review

**Spec coverage:**
- `python -m jeopardy research` generates self-contained HTML from committed data → Tasks 1 (CLI/data), 2 (render/write). ✓
- Data contract (per-type, sorted by applicability, placeholder dropped) → Task 1 `build_research_data` + tests. ✓
- Master-detail layout, non-studyable de-emphasized → Task 2 requirements + Task 3. ✓
- Live client-side Wikipedia fetch (REST + search fallback + graceful degrade) → Task 2 `fetchWiki` (verbatim) + structural tests. ✓
- Self-contained (no external assets), committed at research/index.html, shipped as static asset → Task 2 + Global Constraints. ✓
- No new deps → pandas + stdlib + inline JS. ✓
- frontend-design + visual iteration → Tasks 2 (build), 3 (iterate). ✓
- Testing: build_research_data unit tests + render_html structural tests + browser verification → Tasks 1–3. ✓

**Placeholder scan:** Task 2 Step 1 delegates the *visual* template to the frontend-design skill but pins the data contract, the exact `fetchWiki` logic, and concrete structural requirements + tests; the deliverable is explicitly a complete file with no TODOs. All Python (`build_research_data`, `run_research`) and the JS fetch core are given verbatim. No other placeholders.

**Type consistency:** `build_research_data` returns `[{cluster_id, name, applicability, entities:[{phrase,count}]}]` — consumed by `render_html(data)` (embeds JSON) and the JS (`DATA`), and asserted by tests. `run_research` reads `config.CATEGORY_TOKENS_PATH`/`CLUSTER_LABELS_PATH`, writes `config.RESEARCH_HTML_PATH` — all defined in Task 1. ✓

**Known risks:**
- Interactive behavior (live fetch) isn't unit-testable; Task 3 is a genuine browser/human checkpoint — call out that automated tests cover only data + HTML structure.
- Wikipedia entity resolution is best-effort (disambiguation) — accepted per spec; the graceful-fallback path is required and structurally testable (endpoints present) but its runtime behavior is verified in the browser.

# Jeopardy Difficulty Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Jeopardy difficulty post that scores ~524k text-only clues with Jev, validates against scraped player correctness data, and embeds an interactive difficulty sampler.

**Architecture:** Five Python pipeline scripts (scraper → spike → scorer → merger → app exporter) produce parquet/JSON artifacts; a Quarto post reads the parquets for analysis; a standalone HTML/JS app in `posts/jeopardy_difficulty/app/` consumes the JSON for the interactive sampler. The new post lives entirely in `posts/jeopardy_difficulty/` and reads (never writes) from `jeopardy/data/html_cache/` and `posts/jeopardy_ds/`.

**Tech Stack:** Python ≥ 3.12, pandas/pyarrow, BeautifulSoup4/lxml, httpx, pytest, Quarto, Plotly, vanilla JS

**Spec:** `docs/superpowers/specs/2026-09-30-jeopardy-difficulty-design.md`

## Global Constraints

- Run scripts with `uv run python posts/jeopardy_difficulty/pipeline/<script>.py`
- Run tests with `uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/ -v`
- Correctness join key: `(game_id, round, row, column)` — `round` is the full name ("Jeopardy", "Double Jeopardy", "Final"); Final rows carry `row=NaN, column=NaN` — fill with sentinel -1 before joining (pandas does match NaN keys in merges, but the sentinel avoids silent type issues with float NaN equality)
- `Triple Stumper` appears as a single `<td class="wrong">Triple Stumper</td>` cell — is_triple_stumper=True, n_right=0, n_wrong=0
- `any_correct = n_right > 0` is the single outcome used throughout: for computing the training target, for chart axes, and as `y_true` in the Brier score — never mix `correctness_rate` for training with `n_right > 0` for evaluation
- Score all game types (not just regular) so the game-type chart has real data; media=True exclusion still applies
- Spike samples 2,000 clues stratified by **round and row** from the non-test 80% of games; saves `spike_game_ids.txt` (unique game_ids from the spike sample); `merge.py` adds `in_spike_game: bool` — test set excludes all spike game IDs, not just spike clues
- Category cluster joins use key `(game_id, round, category)` — unique in `category_clusters.parquet`; do not deduplicate by mode
- Brier score implemented with numpy (`np.mean((y_pred - y_true)**2)`); no sklearn or statsmodels imports in the post; remove `trendline="ols"` from scatter charts
- Use era-adjusted row (1–5) as the dollar-value baseline feature, not raw dollar value — dollar values doubled on 2001-11-26 (`jeopardy.config.VALUE_DOUBLING_DATE`); include round in both baseline and full model

## Review Focus

1. **Final Jeopardy join on NaN keys** — `clues.parquet` and `correctness.parquet` both have row=NaN, column=NaN for Final; a naive pandas merge produces no matches. The -1 sentinel fill must happen in both dataframes before the merge and be verified by the 1:1 join assertion in `merge.py`. Test: add a Final row to the merge fixture and assert it appears in the output.
2. **Triple Stumper inflates n_wrong** — `<td class="wrong">Triple Stumper</td>` must set is_triple_stumper=True and contribute 0 to n_wrong. Test: Task 1 includes an explicit test asserting n_wrong==0 for a known Triple Stumper clue.
3. **Spike games leak into test set** — excluding individual spike clue IDs leaves other clues from the same 348 spike games eligible for the test set. `spike_prompt.py` saves `spike_game_ids.txt` (game-level); `merge.py` adds `in_spike_game: bool`; the post samples test games only from `~in_spike_game` games.
4. **App bucket underflow** — difficulty buckets 1 and 10 may have far fewer than 2,000 qualifying clues; `build_app_data.py` must not raise on small buckets. Test: pass a dataframe with only 5 rows in bucket 1 and assert the output contains those 5 rows.
5. **round name mismatch at join** — `parse.py` stores round as "J"/"DJ"/"Final"; `build_parquet.py` converts to "Jeopardy"/"Double Jeopardy"/"Final"; `scrape_correctness.py` must output the full names to match `clues.parquet`. Test: assert the round values in correctness output are in {"Jeopardy", "Double Jeopardy", "Final"}.

---

## Task 1: Scaffold + Correctness Scraper

**Files:**
- Create: `posts/jeopardy_difficulty/pipeline/__init__.py`
- Create: `posts/jeopardy_difficulty/pipeline/scrape_correctness.py`
- Create: `posts/jeopardy_difficulty/pipeline/tests/__init__.py`
- Create: `posts/jeopardy_difficulty/pipeline/tests/fixtures/` (directory)
- Create: `posts/jeopardy_difficulty/pipeline/tests/test_scrape_correctness.py`

**Interfaces:**
- Produces: `parse_game_correctness(html: str, game_id: int) -> list[dict]`
  - Each dict: `{"game_id": int, "round": str, "row": float, "column": float, "n_right": int, "n_wrong": int, "is_triple_stumper": bool}`
  - `round` values: "Jeopardy", "Double Jeopardy", "Final"
  - `row` and `column` are `float("nan")` for Final Jeopardy
- Produces: `run_scrape(cache_dir: Path, clues_parquet: Path, out_path: Path) -> None`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p posts/jeopardy_difficulty/pipeline/tests/fixtures
touch posts/jeopardy_difficulty/pipeline/__init__.py
touch posts/jeopardy_difficulty/pipeline/tests/__init__.py
```

- [ ] **Step 2: Copy a real game HTML file as test fixture**

```bash
cp jeopardy/data/html_cache/game_9489.html \
   posts/jeopardy_difficulty/pipeline/tests/fixtures/game_9489.html
```

This game is known to contain:
- `clue_J_1_1`: Caleb wrong, Amber right → n_right=1, n_wrong=1, is_triple_stumper=False
- `clue_J_2_2`: Triple Stumper → n_right=0, n_wrong=0, is_triple_stumper=True
- Final Jeopardy: all three contestants wrong → n_right=0, n_wrong=3, is_triple_stumper=False

- [ ] **Step 3: Write failing tests**

```python
# posts/jeopardy_difficulty/pipeline/tests/test_scrape_correctness.py
import math
from pathlib import Path
from pipeline.scrape_correctness import parse_game_correctness

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return (FIXTURES / name).read_text()


def _find(rows, round_, row, col):
    for r in rows:
        row_match = (math.isnan(r["row"]) and row is None) or r["row"] == row
        col_match = (math.isnan(r["column"]) and col is None) or r["column"] == col
        if r["round"] == round_ and row_match and col_match:
            return r
    raise AssertionError(f"no row for {round_} row={row} col={col}")


def test_normal_clue_right_and_wrong():
    rows = parse_game_correctness(_load("game_9489.html"), game_id=9489)
    clue = _find(rows, "Jeopardy", row=1, col=1)
    assert clue["n_right"] == 1
    assert clue["n_wrong"] == 1
    assert clue["is_triple_stumper"] is False
    assert clue["game_id"] == 9489


def test_triple_stumper_not_counted_as_wrong():
    rows = parse_game_correctness(_load("game_9489.html"), game_id=9489)
    clue = _find(rows, "Jeopardy", row=2, col=2)
    assert clue["n_right"] == 0
    assert clue["n_wrong"] == 0
    assert clue["is_triple_stumper"] is True


def test_final_jeopardy_null_coordinates():
    rows = parse_game_correctness(_load("game_9489.html"), game_id=9489)
    fj = _find(rows, "Final", row=None, col=None)
    assert math.isnan(fj["row"])
    assert math.isnan(fj["column"])
    assert fj["n_wrong"] == 3
    assert fj["n_right"] == 0
    assert fj["is_triple_stumper"] is False


def test_round_names_are_full():
    rows = parse_game_correctness(_load("game_9489.html"), game_id=9489)
    rounds = {r["round"] for r in rows}
    assert rounds <= {"Jeopardy", "Double Jeopardy", "Final"}
```

- [ ] **Step 4: Run tests to confirm they fail**

```bash
uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/test_scrape_correctness.py -v
```

Expected: ImportError or ModuleNotFoundError (file doesn't exist yet)

- [ ] **Step 5: Write `scrape_correctness.py`**

```python
# posts/jeopardy_difficulty/pipeline/scrape_correctness.py
"""Parse J-Archive game HTML to extract per-clue contestant response counts."""
import math
import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

_CID_RE = re.compile(r"clue_(J|DJ)_(\d+)_(\d+)$")
_ROUND_FULL = {"J": "Jeopardy", "DJ": "Double Jeopardy"}
_TRIPLE_STUMPER = "Triple Stumper"


def _parse_response(rtd):
    """Return (n_right, n_wrong, is_triple_stumper) from a response <td>."""
    right_cells = rtd.find_all("td", class_="right")
    wrong_cells = rtd.find_all("td", class_="wrong")
    wrong_names = [td.get_text(strip=True) for td in wrong_cells]
    is_triple_stumper = _TRIPLE_STUMPER in wrong_names
    n_right = len(right_cells)
    n_wrong = sum(1 for name in wrong_names if name != _TRIPLE_STUMPER)
    return n_right, n_wrong, is_triple_stumper


def parse_game_correctness(html: str, game_id: int) -> list[dict]:
    """Return one response-count row per revealed clue in this game HTML."""
    soup = BeautifulSoup(html, "lxml")
    rows = []

    # Board clues (Jeopardy + Double Jeopardy)
    for prefix, div_id in [("J", "jeopardy_round"), ("DJ", "double_jeopardy_round")]:
        round_div = soup.find("div", id=div_id)
        if round_div is None:
            continue
        for cell in round_div.find_all("td", class_="clue"):
            ctd = cell.find("td", class_="clue_text", id=_CID_RE)
            if ctd is None:
                continue
            m = _CID_RE.search(ctd["id"])
            col, row = int(m.group(2)), int(m.group(3))
            rtd = cell.find("td", id=ctd["id"] + "_r")
            if rtd is None:
                continue
            n_right, n_wrong, is_ts = _parse_response(rtd)
            rows.append({
                "game_id": game_id,
                "round": _ROUND_FULL[prefix],
                "row": float(row),
                "column": float(col),
                "n_right": n_right,
                "n_wrong": n_wrong,
                "is_triple_stumper": is_ts,
            })

    # Final Jeopardy
    fj_div = soup.find("div", id="final_jeopardy_round")
    if fj_div is not None:
        rtd = fj_div.find("td", id="clue_FJ_r")
        if rtd is not None:
            n_right, n_wrong, is_ts = _parse_response(rtd)
            rows.append({
                "game_id": game_id,
                "round": "Final",
                "row": float("nan"),
                "column": float("nan"),
                "n_right": n_right,
                "n_wrong": n_wrong,
                "is_triple_stumper": is_ts,
            })

    return rows


def run_scrape(cache_dir: Path, clues_parquet: Path, out_path: Path) -> None:
    clues = pd.read_parquet(clues_parquet, columns=["game_id"])
    game_ids = clues["game_id"].unique()
    print(f"Scraping correctness for {len(game_ids):,} games...")

    all_rows = []
    for i, game_id in enumerate(sorted(game_ids)):
        cache_file = cache_dir / f"game_{game_id}.html"
        if not cache_file.exists():
            continue
        html = cache_file.read_text()
        all_rows.extend(parse_game_correctness(html, int(game_id)))
        if (i + 1) % 500 == 0:
            print(f"  {i+1:,}/{len(game_ids):,}")

    df = pd.DataFrame(all_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, compression="zstd", index=False)
    print(f"Wrote {len(df):,} rows to {out_path}")


if __name__ == "__main__":
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[3]
    run_scrape(
        cache_dir=ROOT / "jeopardy" / "data" / "html_cache",
        clues_parquet=ROOT / "posts" / "jeopardy_ds" / "clues.parquet",
        out_path=Path(__file__).parent.parent / "correctness.parquet",
    )
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/test_scrape_correctness.py -v
```

Expected: 4 tests PASS

- [ ] **Step 7: Run the scraper**

```bash
uv run python posts/jeopardy_difficulty/pipeline/scrape_correctness.py
```

Expected: writes `posts/jeopardy_difficulty/correctness.parquet`. Spot-check:
```bash
uv run python -c "
import pandas as pd
df = pd.read_parquet('posts/jeopardy_difficulty/correctness.parquet')
print(df.shape, df.dtypes)
print(df[df['is_triple_stumper']].head(3))
"
```

- [ ] **Step 8: Commit**

```bash
git add posts/jeopardy_difficulty/pipeline/ posts/jeopardy_difficulty/correctness.parquet
git commit -m "feat(jeopardy-difficulty): add correctness scraper with tests"
```

---

## Task 2: Jev Prompt Spike

**Files:**
- Create: `posts/jeopardy_difficulty/pipeline/spike_prompt.py` (throwaway — not committed long-term)
- Create: `posts/jeopardy_difficulty/pipeline/prompt.txt` (committed — the winning prompt)

**Interfaces:**
- Consumes: `posts/jeopardy_ds/clues.parquet`
- Produces: manual review output; winning prompt written to `pipeline/prompt.txt`
- Produces: `posts/jeopardy_difficulty/spike_ids.txt` — one `game_id,round,row,column` per line, the 2,000 spike clues excluded from the validation test set

**Note:** The Jev API details are confirmed at this step. The API key goes in `JEVAI_API_KEY` env var. Update `score_jev.py` in Task 3 once the exact API client is known.

- [ ] **Step 1: Write `spike_prompt.py`**

```python
# posts/jeopardy_difficulty/pipeline/spike_prompt.py
"""Sample 2k clues for prompt development. Throwaway — not kept after Task 3."""
import os
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
CLUES = ROOT / "posts" / "jeopardy_ds" / "clues.parquet"
CORRECTNESS = Path(__file__).parent.parent / "correctness.parquet"
OUT = Path(__file__).parent.parent / "spike_sample.jsonl"
SPIKE_GAME_IDS = Path(__file__).parent.parent / "spike_game_ids.txt"

PROMPTS = {
    "v1": (
        "Rate the difficulty of this Jeopardy clue on a scale of 1 (very easy) to 10 (very hard). "
        "Consider how much specialized knowledge is needed to answer it correctly. "
        "Category: {category}. Clue: {clue}. Answer: {answer}. "
        "Return JSON: {{\"difficulty\": <int 1-10>, \"confidence\": <float 0-1>}}"
    ),
    "v2": (
        "You are an expert Jeopardy analyst. Rate how difficult this clue is for a typical contestant "
        "on a scale of 1 (almost anyone would know it) to 10 (only a specialist would know it). "
        "Category: {category}. Clue: {clue}. Correct answer: {answer}. "
        "Return JSON only: {{\"difficulty\": <int 1-10>, \"confidence\": <float 0-1>}}"
    ),
    "v3": (
        "Rate this Jeopardy clue's difficulty 1-10. "
        "1=common knowledge, 5=needs some study, 10=expert specialist only. "
        "Category: {category}\nClue: {clue}\nAnswer: {answer}\n"
        "JSON only: {{\"difficulty\": <int>, \"confidence\": <float>}}"
    ),
}


def sample_clues(n=2000, exclude_game_ids: set = None):
    """Sample n clues stratified by round and row, excluding test games."""
    df = pd.read_parquet(CLUES)
    df = df[
        (df["media"] == False) &
        (df["round"].isin(["Jeopardy", "Double Jeopardy"])) &
        df["row"].notna()
    ].dropna(subset=["clue", "answer", "category"])
    if exclude_game_ids:
        df = df[~df["game_id"].isin(exclude_game_ids)]
    # Stratify by round × row (10 buckets: 2 rounds × 5 rows)
    df["stratum"] = df["round"] + "_" + df["row"].astype(int).astype(str)
    n_strata = df["stratum"].nunique()
    sampled = (
        df.groupby("stratum", group_keys=False)
        .apply(lambda g: g.sample(min(len(g), n // n_strata), random_state=42))
    )
    return sampled.head(n)


def score_with_jev(prompt_text: str, api_key: str) -> dict:
    """Replace with actual Jev client call once API is confirmed."""
    import httpx
    # TODO: update endpoint and request format once Jev API details are confirmed
    resp = httpx.post(
        "https://api.typesafe.ai/v1/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"prompt": prompt_text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    api_key = os.environ["JEVAI_API_KEY"]
    # Pre-select 20% of games as the held-out test set; sample spike from the rest
    all_game_ids = pd.read_parquet(CLUES, columns=["game_id"])["game_id"].unique()
    rng = __import__("numpy").random.default_rng(42)
    test_game_ids = set(rng.choice(all_game_ids, size=int(len(all_game_ids) * 0.2), replace=False))
    sample = sample_clues(2000, exclude_game_ids=test_game_ids)

    # Save spike game IDs (for merge.py to tag in_spike_game)
    spike_game_ids = set(sample["game_id"].unique())
    SPIKE_GAME_IDS.write_text("\n".join(str(g) for g in sorted(spike_game_ids)))
    # Also save test game IDs so merge.py can tag in_test_game
    (Path(__file__).parent.parent / "test_game_ids.txt").write_text(
        "\n".join(str(g) for g in sorted(test_game_ids))
    )
    print(f"Spike: {len(sample)} clues from {len(spike_game_ids)} games; "
          f"test set: {len(test_game_ids)} games")

    # Score all 2k clues with each prompt variant for manual comparison
    results = []
    for prompt_name, prompt_template in PROMPTS.items():
        print(f"Scoring with {prompt_name}...")
        for _, row in sample.iterrows():
            prompt_text = prompt_template.format(
                category=row["category"], clue=row["clue"], answer=row["answer"]
            )
            try:
                result = score_with_jev(prompt_text, api_key)
                results.append({"prompt": prompt_name, "game_id": int(row["game_id"]),
                                 "round": row["round"], "row": row["row"], "column": row["column"],
                                 "clue": row["clue"], "result": result})
            except Exception as e:
                print(f"Error on clue {row['game_id']}: {e}")
    OUT.write_text("\n".join(json.dumps(r) for r in results))
    print(f"Wrote {len(results)} spike results to {OUT}")

    # Validate signal: for each prompt variant, join against correctness and print correlation
    if CORRECTNESS.exists():
        import numpy as np
        corr = pd.read_parquet(CORRECTNESS)
        for variant_name in PROMPTS:
            scored_df = pd.DataFrame([
                {**r, "difficulty": r["result"].get("difficulty")}
                for r in results if r["prompt"] == variant_name
                and r["result"].get("difficulty") is not None
            ])
            if scored_df.empty:
                print(f"\n{variant_name}: no successful scores — skipping signal check")
                continue
            merged = scored_df.merge(corr, on=["game_id", "round", "row", "column"], how="inner")
            # Include triple stumpers (they ARE observed outcomes: everyone got it wrong)
            has_response = (merged["n_right"] > 0) | (merged["n_wrong"] > 0) | merged["is_triple_stumper"]
            merged = merged[has_response]
            merged["any_correct"] = (merged["n_right"] > 0).astype(float)
            corr_val = np.corrcoef(merged["difficulty"], merged["any_correct"])[0, 1]
            print(f"\nSpike signal check ({variant_name}): difficulty vs any_correct corr = {corr_val:.3f}")
        print("Expected: negative (harder clues → fewer correct). If |corr| < 0.05, the prompt is not capturing difficulty.")
```

- [ ] **Step 2: Confirm Jev API access and update `score_with_jev`**

Get API key from TypeSafe AI console. Update the `score_with_jev` function in `spike_prompt.py` with the confirmed endpoint and request/response format.

- [ ] **Step 3: Run the spike**

```bash
JEVAI_API_KEY=<your-key> uv run python posts/jeopardy_difficulty/pipeline/spike_prompt.py
```

Review `spike_sample.jsonl` manually. Compare the three prompts across several clues — look for:
- Obvious mislabelings (trivial clues scored 9+, expert clues scored 1-2)
- Confidence calibration (does high confidence track accurate ratings?)
- Disagreements on edge cases (Daily Double clues, wordplay clues)

- [ ] **Step 4: Write winning prompt to `prompt.txt` and commit game ID files**

Write the full winning prompt text (with `{category}`, `{clue}`, `{answer}` placeholders) to:
`posts/jeopardy_difficulty/pipeline/prompt.txt`

```bash
git add posts/jeopardy_difficulty/pipeline/prompt.txt \
        posts/jeopardy_difficulty/spike_game_ids.txt \
        posts/jeopardy_difficulty/test_game_ids.txt
git commit -m "feat(jeopardy-difficulty): add prompt spike results and game splits"
```

---

## Task 3: Batch Jev Scoring

**Files:**
- Create: `posts/jeopardy_difficulty/pipeline/score_jev.py`
- Create: `posts/jeopardy_difficulty/pipeline/tests/test_score_jev.py`

**Interfaces:**
- Consumes: `posts/jeopardy_ds/clues.parquet`, `pipeline/prompt.txt`
- Produces: `posts/jeopardy_difficulty/jev_scores.parquet`
  - Columns: `game_id: int64`, `round: str`, `row: float64`, `column: float64`, `difficulty: int64`, `jev_confidence: float64`

- [ ] **Step 1: Write failing tests**

```python
# posts/jeopardy_difficulty/pipeline/tests/test_score_jev.py
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from pipeline.score_jev import score_clue, build_prompt, filter_scoreable


def test_build_prompt_fills_placeholders():
    template = "Category: {category}. Clue: {clue}. Answer: {answer}."
    result = build_prompt(template, category="SCIENCE", clue="It orbits Earth", answer="the Moon")
    assert "SCIENCE" in result
    assert "It orbits Earth" in result
    assert "the Moon" in result


def test_filter_scoreable_excludes_media():
    # game_type is no longer filtered — all game types are scored
    df = pd.DataFrame({
        "media": [True, False, False],
        "game_type": ["regular", "regular", "toc"],
        "round": ["Jeopardy", "Jeopardy", "Jeopardy"],
        "clue": ["a", "b", "c"],
        "answer": ["x", "y", "z"],
        "category": ["A", "B", "C"],
    })
    result = filter_scoreable(df)
    assert len(result) == 2  # both non-media clues kept regardless of game_type
    assert set(result["clue"]) == {"b", "c"}


def test_score_clue_returns_difficulty_and_confidence():
    mock_client = MagicMock()
    mock_client.return_value = {"difficulty": 7, "confidence": 0.85}
    result = score_clue(mock_client, "some prompt text")
    assert result["difficulty"] == 7
    assert result["jev_confidence"] == 0.85


def test_score_clue_clamps_difficulty_range():
    mock_client = MagicMock()
    mock_client.return_value = {"difficulty": 15, "confidence": 0.5}
    result = score_clue(mock_client, "some prompt")
    assert 1 <= result["difficulty"] <= 10
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/test_score_jev.py -v
```

- [ ] **Step 3: Write `score_jev.py`**

```python
# posts/jeopardy_difficulty/pipeline/score_jev.py
"""Batch Jev scoring for text-only regular-game board clues."""
import os
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
CLUES_PATH = ROOT / "posts" / "jeopardy_ds" / "clues.parquet"
PROMPT_PATH = Path(__file__).parent / "prompt.txt"
OUT_PATH = Path(__file__).parent.parent / "jev_scores.parquet"

def filter_scoreable(df: pd.DataFrame) -> pd.DataFrame:
    """Text-only clues across all game types and rounds."""
    return df[
        (df["media"] == False) &
        df["clue"].notna() &
        df["answer"].notna() &
        df["category"].notna()
    ].copy()


def build_prompt(template: str, category: str, clue: str, answer: str) -> str:
    return template.format(category=category, clue=clue, answer=answer)


def score_clue(jev_client, prompt_text: str) -> dict:
    """Call Jev and return {difficulty: int, jev_confidence: float}."""
    result = jev_client(prompt_text)
    difficulty = max(1, min(10, int(result["difficulty"])))
    return {"difficulty": difficulty, "jev_confidence": float(result["confidence"])}


def make_jev_client(api_key: str):
    """Return a callable that sends one prompt to Jev and returns parsed JSON."""
    import httpx
    # Update endpoint/payload format to match confirmed Jev API
    def call(prompt_text: str) -> dict:
        resp = httpx.post(
            "https://api.typesafe.ai/v1/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"prompt": prompt_text},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()
    return call


def _clue_key(row) -> tuple:
    # Normalize NaN coordinates to -1 so Final Jeopardy keys are hashable and comparable
    import math as _math
    r = row["row"]; c = row["column"]
    return (int(row["game_id"]), str(row["round"]),
            -1.0 if (r is None or (isinstance(r, float) and _math.isnan(r))) else float(r),
            -1.0 if (c is None or (isinstance(c, float) and _math.isnan(c))) else float(c))


def run_scoring(api_key: str) -> None:
    import hashlib
    template = PROMPT_PATH.read_text().strip()
    prompt_hash = hashlib.sha256(template.encode()).hexdigest()[:16]

    df = filter_scoreable(pd.read_parquet(CLUES_PATH))
    print(f"Scoring {len(df):,} clues...")

    checkpoint = OUT_PATH.with_suffix(".checkpoint.parquet")
    hash_file = OUT_PATH.with_suffix(".prompt_hash")
    done_keys: set = set()  # only successfully scored keys
    rows = []

    if checkpoint.exists():
        saved_hash = hash_file.read_text().strip() if hash_file.exists() else ""
        if saved_hash != prompt_hash:
            print("Prompt changed — discarding checkpoint and starting fresh")
            checkpoint.unlink()
            hash_file.unlink(missing_ok=True)
        else:
            prev = pd.read_parquet(checkpoint)
            all_prev = prev.to_dict(orient="records")
            # Only keep successful rows; failed (null difficulty) will be retried
            rows = [r for r in all_prev if r.get("difficulty") is not None]
            done_keys = {_clue_key(r) for r in rows}
            n_failed = len(all_prev) - len(rows)
            print(f"Resuming: {len(done_keys):,} successful, {n_failed:,} failed rows will retry")
    else:
        # Fresh run: record which prompt was used so resume can validate
        hash_file.write_text(prompt_hash)

    client = make_jev_client(api_key)
    for i, (_, row) in enumerate(df.iterrows()):
        key = _clue_key(row)
        if key in done_keys:
            continue
        prompt = build_prompt(template, row["category"], row["clue"], row["answer"])
        # Bounded retry: 3 attempts with exponential backoff
        for attempt in range(3):
            try:
                scored = score_clue(client, prompt)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"Giving up on clue {key}: {e}")
                    scored = {"difficulty": None, "jev_confidence": None}
                else:
                    time.sleep(2 ** attempt)
        rows.append({"game_id": row["game_id"], "round": row["round"],
                     "row": row["row"], "column": row["column"], **scored})
        # Only mark as done if scoring succeeded; null-difficulty rows remain retryable
        if scored["difficulty"] is not None:
            done_keys.add(key)
        if len(rows) % 1000 == 0:
            print(f"  {len(rows):,}/{len(df):,}")
            pd.DataFrame(rows).to_parquet(checkpoint, compression="zstd", index=False)

    out = pd.DataFrame(rows)
    out.to_parquet(OUT_PATH, compression="zstd", index=False)
    checkpoint.unlink(missing_ok=True)
    print(f"Wrote {len(out):,} rows to {OUT_PATH}")


if __name__ == "__main__":
    api_key = os.environ["JEVAI_API_KEY"]
    run_scoring(api_key)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/test_score_jev.py -v
```

- [ ] **Step 5: Run the scorer**

```bash
JEVAI_API_KEY=<your-key> uv run python posts/jeopardy_difficulty/pipeline/score_jev.py
```

Spot-check output:
```bash
uv run python -c "
import pandas as pd
df = pd.read_parquet('posts/jeopardy_difficulty/jev_scores.parquet')
print(df.shape)
print(df['difficulty'].value_counts().sort_index())
print(df['jev_confidence'].describe())
"
```

- [ ] **Step 6: Commit**

```bash
git add posts/jeopardy_difficulty/pipeline/score_jev.py \
        posts/jeopardy_difficulty/pipeline/tests/test_score_jev.py \
        posts/jeopardy_difficulty/jev_scores.parquet
git commit -m "feat(jeopardy-difficulty): add Jev batch scoring"
```

---

## Task 4: Merge Pipeline

**Files:**
- Create: `posts/jeopardy_difficulty/pipeline/merge.py`
- Create: `posts/jeopardy_difficulty/pipeline/tests/test_merge.py`

**Interfaces:**
- Consumes:
  - `posts/jeopardy_ds/clues.parquet` (14 original columns)
  - `posts/jeopardy_difficulty/correctness.parquet` (from Task 1)
  - `posts/jeopardy_difficulty/jev_scores.parquet` (from Task 3)
  - `posts/jeopardy_difficulty/spike_ids.txt` (from Task 2)
- Produces: `posts/jeopardy_difficulty/clues_scored.parquet`
  - All 14 original columns + `n_right`, `n_wrong`, `is_triple_stumper`, `difficulty`, `jev_confidence`, `in_spike: bool`

- [ ] **Step 1: Write failing tests**

```python
# posts/jeopardy_difficulty/pipeline/tests/test_merge.py
import math
import pandas as pd
import pytest
from pipeline.merge import merge_datasets, _fill_nan_keys, _assert_one_to_one


def _make_clues():
    return pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy",       "row": 1.0, "column": 1.0, "clue": "Q1", "answer": "A1", "media": False},
        {"game_id": 1, "round": "Double Jeopardy", "row": 1.0, "column": 1.0, "clue": "Q2", "answer": "A2", "media": False},
        {"game_id": 1, "round": "Final",            "row": float("nan"), "column": float("nan"), "clue": "FJ", "answer": "FA", "media": False},
    ])


def _make_correctness():
    return pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy",       "row": 1.0, "column": 1.0, "n_right": 2, "n_wrong": 0, "is_triple_stumper": False},
        {"game_id": 1, "round": "Double Jeopardy", "row": 1.0, "column": 1.0, "n_right": 0, "n_wrong": 1, "is_triple_stumper": False},
        {"game_id": 1, "round": "Final",            "row": float("nan"), "column": float("nan"), "n_right": 1, "n_wrong": 2, "is_triple_stumper": False},
    ])


def _make_scores():
    return pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy",       "row": 1.0, "column": 1.0, "difficulty": 4, "jev_confidence": 0.9},
        {"game_id": 1, "round": "Double Jeopardy", "row": 1.0, "column": 1.0, "difficulty": 7, "jev_confidence": 0.8},
        {"game_id": 1, "round": "Final",            "row": float("nan"), "column": float("nan"), "difficulty": 9, "jev_confidence": 0.7},
    ])


def test_final_jeopardy_joins_correctly():
    result = merge_datasets(_make_clues(), _make_correctness(), _make_scores(),
                            spike_game_ids=set(), test_game_ids=set())
    fj = result[result["round"] == "Final"]
    assert len(fj) == 1
    assert fj.iloc[0]["n_right"] == 1
    assert fj.iloc[0]["difficulty"] == 9
    assert math.isnan(fj.iloc[0]["row"])


def test_round_specific_join_no_collision():
    result = merge_datasets(_make_clues(), _make_correctness(), _make_scores(),
                            spike_game_ids=set(), test_game_ids=set())
    j_row = result[result["round"] == "Jeopardy"].iloc[0]
    dj_row = result[result["round"] == "Double Jeopardy"].iloc[0]
    assert j_row["n_right"] == 2
    assert dj_row["n_wrong"] == 1


def test_spike_game_flag():
    # game_id=1 is the spike game; all its clues should be flagged
    result = merge_datasets(_make_clues(), _make_correctness(), _make_scores(),
                            spike_game_ids={1}, test_game_ids={2})
    j_row = result[result["round"] == "Jeopardy"].iloc[0]
    assert j_row["in_spike_game"]       # truthy assert — numpy bool, never `is True`
    assert not j_row["in_test_game"]    # same: not `is False`


def test_test_game_flag():
    result = merge_datasets(_make_clues(), _make_correctness(), _make_scores(),
                            spike_game_ids=set(), test_game_ids={1})
    j_row = result[result["round"] == "Jeopardy"].iloc[0]
    assert j_row["in_test_game"]


def test_one_to_one_violation_raises():
    dup_correctness = pd.concat([_make_correctness(), _make_correctness()])
    with pytest.raises(AssertionError, match="one-to-one"):
        merge_datasets(_make_clues(), dup_correctness, _make_scores(),
                       spike_game_ids=set(), test_game_ids=set())
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/test_merge.py -v
```

- [ ] **Step 3: Write `merge.py`**

```python
# posts/jeopardy_difficulty/pipeline/merge.py
"""Join clues.parquet + correctness.parquet + jev_scores.parquet."""
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
_POST = ROOT / "posts" / "jeopardy_difficulty"
_JOIN_COLS = ["game_id", "round", "row", "column"]
_SENTINEL = -1.0  # replaces NaN in row/column during join


def _fill_nan_keys(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["row"] = df["row"].fillna(_SENTINEL)
    df["column"] = df["column"].fillna(_SENTINEL)
    return df


def _restore_nan_keys(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["row"] = df["row"].replace(_SENTINEL, float("nan"))
    df["column"] = df["column"].replace(_SENTINEL, float("nan"))
    return df


def _assert_one_to_one(left: pd.DataFrame, right: pd.DataFrame, key: list[str]) -> None:
    dupes = right.duplicated(subset=key, keep=False)
    if dupes.any():
        raise AssertionError(f"one-to-one join violated: {right[dupes][key].head()}")


def _load_game_ids(path: Path) -> set:
    if not path.exists():
        return set()
    return {int(line.strip()) for line in path.read_text().splitlines() if line.strip()}


def merge_datasets(
    clues: pd.DataFrame,
    correctness: pd.DataFrame,
    scores: pd.DataFrame,
    spike_game_ids: set,
    test_game_ids: set,
) -> pd.DataFrame:
    _assert_one_to_one(clues, correctness, _JOIN_COLS)
    _assert_one_to_one(clues, scores, _JOIN_COLS)

    clues_f = _fill_nan_keys(clues)
    corr_f = _fill_nan_keys(correctness)
    scores_f = _fill_nan_keys(scores)

    merged = clues_f.merge(corr_f, on=_JOIN_COLS, how="left")
    merged = merged.merge(scores_f, on=_JOIN_COLS, how="left")
    merged = _restore_nan_keys(merged)

    merged["in_spike_game"] = merged["game_id"].isin(spike_game_ids)
    merged["in_test_game"] = merged["game_id"].isin(test_game_ids)
    return merged


def run_merge() -> None:
    clues = pd.read_parquet(ROOT / "posts" / "jeopardy_ds" / "clues.parquet")
    correctness = pd.read_parquet(_POST / "correctness.parquet")
    scores = pd.read_parquet(_POST / "jev_scores.parquet")
    spike_game_ids = _load_game_ids(_POST / "spike_game_ids.txt")
    test_game_ids = _load_game_ids(_POST / "test_game_ids.txt")

    result = merge_datasets(clues, correctness, scores, spike_game_ids, test_game_ids)
    out = _POST / "clues_scored.parquet"
    result.to_parquet(out, compression="zstd", index=False)
    print(f"Wrote {len(result):,} rows to {out}")
    print(f"Columns: {list(result.columns)}")
    unmatched = result["difficulty"].isna().sum()
    print(f"Unmatched (no Jev score): {unmatched:,}")


if __name__ == "__main__":
    run_merge()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/test_merge.py -v
```

- [ ] **Step 5: Run the merge**

```bash
uv run python posts/jeopardy_difficulty/pipeline/merge.py
```

- [ ] **Step 6: Commit**

```bash
git add posts/jeopardy_difficulty/pipeline/merge.py \
        posts/jeopardy_difficulty/pipeline/tests/test_merge.py \
        posts/jeopardy_difficulty/clues_scored.parquet
git commit -m "feat(jeopardy-difficulty): add merge pipeline"
```

---

## Task 5: App Data Export + Interactive Tool

**Files:**
- Create: `posts/jeopardy_difficulty/pipeline/build_app_data.py`
- Create: `posts/jeopardy_difficulty/pipeline/tests/test_build_app_data.py`
- Create: `posts/jeopardy_difficulty/app/index.html`
- Modify: `_quarto.yml` (add resource entry)

**Interfaces:**
- Consumes: `clues_scored.parquet`, `posts/jeopardy_ds/category_clusters.parquet`, `posts/jeopardy_ds/cluster_labels.csv`
- Produces: `posts/jeopardy_difficulty/app/data/clues.json`

- [ ] **Step 1: Write failing tests**

```python
# posts/jeopardy_difficulty/pipeline/tests/test_build_app_data.py
import pandas as pd
from pipeline.build_app_data import build_app_data, filter_app_clues


def _make_scored(n=10):
    import random
    rows = []
    for i in range(n):
        rows.append({
            "game_id": i, "round": "Jeopardy", "row": 1.0, "column": float(i % 6 + 1),
            "clue": f"Clue {i}", "answer": f"Answer {i}", "category": f"CAT{i % 3}",
            "media": False, "game_type": "regular", "is_daily_double": False,
            "difficulty": (i % 10) + 1, "jev_confidence": 0.8,
            "n_right": 1, "n_wrong": 0, "is_triple_stumper": False,
            "air_date": pd.Timestamp("2020-01-01"), "in_spike": False,
        })
    return pd.DataFrame(rows)


def _make_clusters(n=10):
    # Must include game_id and round to match (game_id, round, category) join key
    return pd.DataFrame([
        {"game_id": i, "round": "Jeopardy", "category": f"CAT{i % 3}", "cluster_id": i % 3}
        for i in range(n)
    ])


def _make_labels():
    return {0: "Science", 1: "History", 2: "Arts"}


def test_filter_app_clues_excludes_media():
    df = _make_scored(5)
    df.loc[0, "media"] = True
    result = filter_app_clues(df)
    assert len(result) == 4


def test_filter_requires_response_data():
    df = _make_scored(5)
    df.loc[0, "n_right"] = 0
    df.loc[0, "n_wrong"] = 0
    df.loc[0, "is_triple_stumper"] = False
    # zero responses but not triple stumper = no response data → exclude
    result = filter_app_clues(df)
    assert len(result) == 4


def test_bucket_underflow_takes_all():
    # Only 3 rows in bucket 1 — should return all 3, not error
    df = _make_scored(3)
    df["difficulty"] = 1
    clusters = _make_clusters(3)
    labels = _make_labels()
    result = build_app_data(df, clusters, labels, per_bucket=2000)
    assert len(result) == 3


def test_output_has_required_keys():
    df = _make_scored(10)
    clusters = _make_clusters(10)
    labels = _make_labels()
    result = build_app_data(df, clusters, labels, per_bucket=2000)
    required = {"clue", "answer", "category", "cluster_name", "difficulty",
                "jev_confidence", "round", "game_type", "air_date"}
    assert required <= set(result[0].keys())
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/test_build_app_data.py -v
```

- [ ] **Step 3: Write `build_app_data.py`**

```python
# posts/jeopardy_difficulty/pipeline/build_app_data.py
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
_POST = ROOT / "posts" / "jeopardy_difficulty"
_DS = ROOT / "posts" / "jeopardy_ds"
_APP_DATA = _POST / "app" / "data" / "clues.json"

_APP_COLS = ["clue", "answer", "category", "cluster_name", "difficulty",
             "jev_confidence", "round", "game_type", "air_date"]


def filter_app_clues(df: pd.DataFrame) -> pd.DataFrame:
    """Text-only, regular-game board clues with at least one recorded response."""
    has_response = (df["n_right"] > 0) | (df["n_wrong"] > 0) | df["is_triple_stumper"]
    return df[
        (df["media"] == False) &
        (df["game_type"] == "regular") &
        (df["round"].isin(["Jeopardy", "Double Jeopardy"])) &
        (df["is_daily_double"] == False) &
        df["difficulty"].notna() &
        has_response
    ].copy()


def build_app_data(
    scored: pd.DataFrame,
    clusters: pd.DataFrame,
    labels: dict,
    per_bucket: int = 2000,
) -> list[dict]:
    df = filter_app_clues(scored)
    # (game_id, round, category) is unique in category_clusters — join directly
    df = df.merge(clusters[["game_id", "round", "category", "cluster_id"]],
                  on=["game_id", "round", "category"], how="left")
    df["cluster_name"] = df["cluster_id"].map(labels).fillna("Uncategorized")

    rows = []
    for bucket in range(1, 11):
        bucket_df = df[df["difficulty"] == bucket]
        sample = bucket_df.sample(min(len(bucket_df), per_bucket), random_state=42)
        rows.extend(sample[_APP_COLS].to_dict(orient="records"))

    # Serialize air_date (Timestamp → ISO string)
    for r in rows:
        if hasattr(r["air_date"], "isoformat"):
            r["air_date"] = r["air_date"].isoformat()[:10]
    return rows


def run_build() -> None:
    scored = pd.read_parquet(_POST / "clues_scored.parquet")
    clusters = pd.read_parquet(_DS / "category_clusters.parquet")
    labels = pd.read_csv(_DS / "cluster_labels.csv").set_index("cluster_id")["name"].to_dict()

    data = build_app_data(scored, clusters, labels)
    _APP_DATA.parent.mkdir(parents=True, exist_ok=True)
    _APP_DATA.write_text(json.dumps(data))
    print(f"Wrote {len(data):,} clues to {_APP_DATA}")


if __name__ == "__main__":
    run_build()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run --group scraper pytest posts/jeopardy_difficulty/pipeline/tests/test_build_app_data.py -v
```

- [ ] **Step 5: Run app data export**

```bash
uv run python posts/jeopardy_difficulty/pipeline/build_app_data.py
```

- [ ] **Step 6: Write `app/index.html`**

```html
<!-- posts/jeopardy_difficulty/app/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Jeopardy Difficulty Sampler</title>
  <style>
    :root {
      --bg: #0a0a2e;
      --card-bg: #1a1a5e;
      --accent: #f5c518;
      --text: #ffffff;
      --muted: #aaaacc;
      --radius: 8px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif;
           min-height: 100vh; display: flex; flex-direction: column; align-items: center;
           padding: 24px 16px; }
    h1 { color: var(--accent); font-size: 1.4rem; margin-bottom: 20px; }
    .controls { width: 100%; max-width: 640px; display: flex; flex-direction: column; gap: 12px; }
    .control-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    label { color: var(--muted); font-size: 0.85rem; min-width: 90px; }
    input[type=range] { flex: 1; accent-color: var(--accent); }
    select { background: var(--card-bg); color: var(--text); border: 1px solid var(--accent);
             border-radius: var(--radius); padding: 4px 8px; }
    .range-display { color: var(--accent); font-weight: bold; min-width: 40px; }
    .card { background: var(--card-bg); border-radius: var(--radius); padding: 24px;
            width: 100%; max-width: 640px; margin-top: 24px; }
    .category { color: var(--accent); font-size: 1rem; font-weight: bold;
                text-transform: uppercase; letter-spacing: 2px; margin-bottom: 16px; }
    .clue-text { font-size: 1.1rem; line-height: 1.6; margin-bottom: 20px; }
    .answer-box { background: #0a0a2e; border-radius: var(--radius); padding: 16px;
                  margin-bottom: 16px; display: none; }
    .answer-box .answer { color: var(--accent); font-size: 1.2rem; font-weight: bold; }
    .meta { color: var(--muted); font-size: 0.8rem; margin-top: 8px; }
    .btn { background: var(--accent); color: #000; border: none; border-radius: var(--radius);
           padding: 10px 20px; font-weight: bold; cursor: pointer; font-size: 0.95rem; }
    .btn:hover { opacity: 0.85; }
    .btn-outline { background: transparent; color: var(--accent);
                   border: 2px solid var(--accent); margin-left: 8px; }
    #status { color: var(--muted); margin-top: 16px; font-size: 0.85rem; }
  </style>
</head>
<body>
  <h1>Jeopardy Difficulty Sampler</h1>
  <div class="controls">
    <div class="control-row">
      <label>Min difficulty</label>
      <input type="range" id="min-diff" min="1" max="10" value="1">
      <span class="range-display" id="min-val">1</span>
    </div>
    <div class="control-row">
      <label>Max difficulty</label>
      <input type="range" id="max-diff" min="1" max="10" value="10">
      <span class="range-display" id="max-val">10</span>
    </div>
    <div class="control-row">
      <label>Round</label>
      <select id="round-filter">
        <option value="">Any</option>
        <option value="Jeopardy">Jeopardy</option>
        <option value="Double Jeopardy">Double Jeopardy</option>
      </select>
    </div>
    <div class="control-row">
      <label>Category</label>
      <select id="cluster-filter"><option value="">Any</option></select>
    </div>
  </div>
  <div class="card" id="card" style="display:none">
    <div class="category" id="card-category"></div>
    <div class="clue-text" id="card-clue"></div>
    <div class="answer-box" id="answer-box">
      <div class="answer" id="card-answer"></div>
      <div class="meta" id="card-meta"></div>
    </div>
    <button class="btn" id="reveal-btn" onclick="reveal()">Reveal Answer</button>
    <button class="btn btn-outline" onclick="nextClue()">Next Clue</button>
  </div>
  <div id="status">Loading clues...</div>

  <script>
    let allClues = [], filtered = [], current = null;

    fetch("data/clues.json")
      .then(r => r.json())
      .then(data => {
        allClues = data;
        populateClusters();
        applyFilters();
        document.getElementById("status").textContent = "";
      });

    function populateClusters() {
      const clusters = [...new Set(allClues.map(c => c.cluster_name))].sort();
      const sel = document.getElementById("cluster-filter");
      clusters.forEach(name => {
        const opt = document.createElement("option");
        opt.value = name; opt.textContent = name;
        sel.appendChild(opt);
      });
    }

    function applyFilters() {
      const minD = +document.getElementById("min-diff").value;
      const maxD = +document.getElementById("max-diff").value;
      const round = document.getElementById("round-filter").value;
      const cluster = document.getElementById("cluster-filter").value;
      filtered = allClues.filter(c =>
        c.difficulty >= minD && c.difficulty <= maxD &&
        (!round || c.round === round) &&
        (!cluster || c.cluster_name === cluster)
      );
      document.getElementById("status").textContent =
        filtered.length === 0 ? "No clues match these filters." : "";
      nextClue();
    }

    function nextClue() {
      if (filtered.length === 0) {
        document.getElementById("card").style.display = "none";
        return;
      }
      current = filtered[Math.floor(Math.random() * filtered.length)];
      document.getElementById("card-category").textContent = current.category;
      document.getElementById("card-clue").textContent = current.clue;
      document.getElementById("answer-box").style.display = "none";
      document.getElementById("reveal-btn").style.display = "inline-block";
      document.getElementById("card").style.display = "block";
    }

    function reveal() {
      document.getElementById("card-answer").textContent =
        "What is: " + current.answer + "?";
      document.getElementById("card-meta").textContent =
        `Difficulty: ${current.difficulty}/10 · ${current.round} · ${current.air_date}`;
      document.getElementById("answer-box").style.display = "block";
      document.getElementById("reveal-btn").style.display = "none";
    }

    document.getElementById("min-diff").addEventListener("input", function() {
      document.getElementById("min-val").textContent = this.value;
      if (+this.value > +document.getElementById("max-diff").value)
        document.getElementById("max-diff").value = this.value;
      document.getElementById("max-val").textContent =
        document.getElementById("max-diff").value;
      applyFilters();
    });
    document.getElementById("max-diff").addEventListener("input", function() {
      document.getElementById("max-val").textContent = this.value;
      if (+this.value < +document.getElementById("min-diff").value)
        document.getElementById("min-diff").value = this.value;
      document.getElementById("min-val").textContent =
        document.getElementById("min-diff").value;
      applyFilters();
    });
    document.getElementById("round-filter").addEventListener("change", applyFilters);
    document.getElementById("cluster-filter").addEventListener("change", applyFilters);
  </script>
</body>
</html>
```

- [ ] **Step 7: Register app resource in `_quarto.yml`**

Add to the `resources:` list in `_quarto.yml`:
```yaml
    - "posts/jeopardy_difficulty/app/**"
```

- [ ] **Step 8: Commit**

```bash
git add posts/jeopardy_difficulty/pipeline/build_app_data.py \
        posts/jeopardy_difficulty/pipeline/tests/test_build_app_data.py \
        posts/jeopardy_difficulty/app/ \
        posts/jeopardy_difficulty/correctness.parquet \
        _quarto.yml
git commit -m "feat(jeopardy-difficulty): add app data export and interactive sampler"
```

---

## Task 6: Post (index.qmd)

**Files:**
- Create: `posts/jeopardy_difficulty/index.qmd`
- Create: `posts/jeopardy_difficulty/thumbnail.png` (generate from first chart)

**Interfaces:**
- Consumes: `posts/jeopardy_difficulty/clues_scored.parquet` (all pipeline outputs merged)
- Consumes: `posts/jeopardy_ds/cluster_labels.csv`

**Note:** This task is the analysis narrative. The exact chart values depend on the scored data, so specific numbers are illustrative — fill them in from the actual output. The post structure mirrors the spec exactly.

- [ ] **Step 1: Add `numpy` to the main dependency group in `pyproject.toml`**

The post uses `numpy` directly. Check if it's already a transitive dependency — if not, add it:

```bash
uv add numpy
```

The post does NOT use `sklearn` or `statsmodels` — Brier score is computed with numpy, and scatter trendlines use `np.polyfit`. Do not add either.

- [ ] **Step 2: Write `index.qmd` setup block**

```python
# {python} setup block (include: false)
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

ROOT = Path(".").resolve()  # posts/jeopardy_difficulty/ when rendered by Quarto
scored = pd.read_parquet(ROOT / "clues_scored.parquet")
labels = pd.read_csv(ROOT.parent / "jeopardy_ds" / "cluster_labels.csv") \
           .set_index("cluster_id")["name"].to_dict()

# Working subset: text-only, regular-game board clues with Jev score and response data
board = scored[
    (scored["media"] == False) &
    (scored["game_type"] == "regular") &
    (scored["round"].isin(["Jeopardy", "Double Jeopardy"])) &
    (scored["is_daily_double"] == False) &
    scored["difficulty"].notna() &
    ((scored["n_right"] > 0) | (scored["n_wrong"] > 0) | scored["is_triple_stumper"])
].copy()

board["any_correct"] = (board["n_right"] > 0).astype(float)   # single outcome used everywhere
board["year"] = board["air_date"].dt.year
board["adj_row"] = board["row"]   # 1-5, era-consistent (dollar value doubled in 2001 but row didn't)
board["round_num"] = board["round"].map({"Jeopardy": 0, "Double Jeopardy": 1})

# Validation split: test set = in_test_game games; training = non-test, non-spike-game
train = board[~board["in_test_game"] & ~board["in_spike_game"]]
test = board[board["in_test_game"]]
```

- [ ] **Step 3: Write the six analysis chart blocks and validation section**

Include the following charts in order — each as a named `{python}` chunk with a `fig-cap`:

**Chart 1: Dollar value (row) vs mean correctness rate** — baseline comparison
```python
baseline = board.groupby("adj_row")["any_correct"].mean().reset_index()
fig = px.bar(baseline, x="adj_row", y="any_correct",
             labels={"adj_row": "Row (1=cheapest, 5=most expensive)", "any_correct": "Fraction correct"},
             title="Dollar value predicts correctness — but imperfectly")
fig.show()
```

**Chart 2: Jev difficulty vs fraction correct** — the headline scatter
```python
import numpy as np
bucket_corr = board.groupby("difficulty")["any_correct"].mean().reset_index()
# Manual linear trendline (no statsmodels)
m, b = np.polyfit(bucket_corr["difficulty"], bucket_corr["any_correct"], 1)
bucket_corr["trend"] = m * bucket_corr["difficulty"] + b
fig = go.Figure()
fig.add_trace(go.Scatter(x=bucket_corr["difficulty"], y=bucket_corr["any_correct"],
                         mode="markers", name="Mean fraction correct"))
fig.add_trace(go.Scatter(x=bucket_corr["difficulty"], y=bucket_corr["trend"],
                         mode="lines", name="Trend"))
fig.update_layout(title="Jev difficulty vs fraction of clues answered correctly",
                  xaxis_title="Jev difficulty (1–10)", yaxis_title="Fraction correct")
fig.show()
```

**Chart 3: Validation — Brier score comparison** (text + bar chart)

Both models use `any_correct` as the outcome. Baseline uses `adj_row + round_num`; full model adds `difficulty`. Uncertainty via bootstrap resampling by game.

```python
import numpy as np

# Baseline: predict P(any_correct) from adj_row + round in train set
train_means = train.groupby(["adj_row", "round_num"])["any_correct"].mean()
def predict_baseline(df):
    return df.set_index(["adj_row", "round_num"]).index.map(
        lambda k: train_means.get(k, train_means.mean())
    )
# Full model: also include difficulty
train_means_full = train.groupby(["adj_row", "round_num", "difficulty"])["any_correct"].mean()
def predict_full(df):
    return df.set_index(["adj_row", "round_num", "difficulty"]).index.map(
        lambda k: train_means_full.get(k, train_means.get(k[:2], train_means.mean()))
    )

y_true = test["any_correct"].values
baseline_pred = np.array(predict_baseline(test[["adj_row", "round_num"]]))
full_pred = np.array(predict_full(test[["adj_row", "round_num", "difficulty"]]))

def brier(y, yhat): return np.mean((yhat - y) ** 2)

# Bootstrap by game for uncertainty — preserve multiplicity when a game is drawn twice
from collections import defaultdict
rng = np.random.default_rng(0)
game_ids = test["game_id"].unique()
game_to_idx = defaultdict(list)
for pos, gid in enumerate(test["game_id"]):
    game_to_idx[gid].append(pos)
boot_diff = []
for _ in range(500):
    sampled_games = rng.choice(game_ids, size=len(game_ids), replace=True)
    boot_idx = np.concatenate([game_to_idx[gid] for gid in sampled_games])
    boot_diff.append(brier(y_true[boot_idx], baseline_pred[boot_idx]) -
                     brier(y_true[boot_idx], full_pred[boot_idx]))
improvement = brier(y_true, baseline_pred) - brier(y_true, full_pred)
ci_lo, ci_hi = np.percentile(boot_diff, [2.5, 97.5])
print(f"Brier improvement (baseline → +Jev): {improvement:.4f} "
      f"[95% CI: {ci_lo:.4f}, {ci_hi:.4f}]")

fig = px.bar(
    x=["Baseline (row + round)", "Baseline + Jev difficulty"],
    y=[brier(y_true, baseline_pred), brier(y_true, full_pred)],
    labels={"x": "", "y": "Brier score (lower = better)"},
    title="Adding Jev difficulty on top of board position"
)
fig.show()
```

**Chart 4: Difficulty by year** — has the show gotten harder?
```python
yearly = board.groupby("year")["difficulty"].mean().reset_index()
fig = px.line(yearly, x="year", y="difficulty", title="Mean Jev difficulty over time")
fig.show()
```

**Chart 5: Difficulty by game type**
```python
fig = px.violin(scored[scored["difficulty"].notna()], x="game_type", y="difficulty",
                title="Difficulty distribution by game type")
fig.show()
```

**Chart 6: Difficulty by category cluster** (top 20 clusters by clue count)
```python
clusters_raw = pd.read_parquet(ROOT.parent / "jeopardy_ds" / "category_clusters.parquet")
# Join on (game_id, round, category) — unique key, no deduplication needed
board_with_cluster = board.merge(
    clusters_raw[["game_id", "round", "category", "cluster_id"]],
    on=["game_id", "round", "category"], how="left"
)
board_with_cluster["cluster_name"] = board_with_cluster["cluster_id"].map(labels).fillna("Misc")
cluster_diff = (board_with_cluster.groupby("cluster_name")["difficulty"]
                .agg(["mean", "count"]).reset_index()
                .sort_values("count", ascending=False).head(20)
                .sort_values("mean"))
fig = px.bar(cluster_diff, x="mean", y="cluster_name", orientation="h",
             title="Mean difficulty by category cluster")
fig.show()
```

- [ ] **Step 4: Write the interactive tool embed**

Add to the bottom of `index.qmd`:

```markdown
## Try it yourself

<iframe src="app/index.html" width="100%" height="640px" frameborder="0"
        style="border-radius:8px;"></iframe>
```

- [ ] **Step 5: Write the full post narrative**

The post structure (intro → analysis → prompt dev) follows the spec. Write prose for each section. Lead the intro with three specific examples pulled from the actual data:

```python
# Find vivid examples for the intro
cheap_stumpers = board[(board["clue_value"] <= 400) & board["is_triple_stumper"]].nlargest(3, "difficulty")
easy_expensive = board[(board["clue_value"] >= 1600) & (board["n_right"] > 0)].nsmallest(3, "difficulty")
jev_wrong = board[(board["difficulty"] <= 3) & board["is_triple_stumper"]].head(3)
```

- [ ] **Step 6: Render and check**

```bash
cd /Users/nick/Work/nicholastacik.github.io
uv run quarto render posts/jeopardy_difficulty/index.qmd --to html
open _site/posts/jeopardy_difficulty/index.html
```

Fix any rendering errors. Verify the iframe loads and the filters work.

- [ ] **Step 7: Commit**

```bash
git add posts/jeopardy_difficulty/index.qmd posts/jeopardy_difficulty/thumbnail.png
git commit -m "feat(jeopardy-difficulty): add post with analysis and embedded sampler"
```

"""Batch Jev scoring for text-only clues across all game types and rounds."""
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
CLUES_PATH = ROOT / "posts" / "jeopardy_ds" / "clues.parquet"
PROMPT_PATH = Path(__file__).parent / "prompt.txt"
OUT_PATH = Path(__file__).parent.parent / "jev_scores.parquet"

CLUE_FORMAT = "Category: {category}. Clue: {clue}. Correct answer: {answer}."

# 10 rubric levels (0–9); +1 maps to difficulty 1–10 in output.
# Percentile-anchored: spike corr=-0.227, median=5.0 (best of 3 variants tested).
DIFFICULTY_CRITERIA = [
    "~90%+ of contestants answer correctly",
    "~80% of contestants answer correctly",
    "~70% of contestants answer correctly",
    "~55% of contestants answer correctly",
    "~45% of contestants answer correctly — median Jeopardy clue",
    "~35% of contestants answer correctly",
    "~25% of contestants answer correctly",
    "~15% of contestants answer correctly",
    "~8% of contestants answer correctly",
    "~2% of contestants answer correctly",
]


def filter_scoreable(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (df["media"] == False) &
        df["clue"].notna() &
        df["answer"].notna() &
        df["category"].notna()
    ].copy()


def build_prompt(category: str, clue: str, answer: str) -> str:
    return CLUE_FORMAT.format(category=category, clue=clue, answer=answer)


def score_clue(jev_client, clue_state: str) -> dict:
    result = jev_client(clue_state)
    difficulty = max(1, min(10, int(result["difficulty"])))
    return {"difficulty": difficulty, "jev_confidence": float(result["confidence"])}


def make_jev_client(instructions: str):
    from typesafe_sdk import TypeSafeClient, Score

    client = TypeSafeClient()

    def call(clue_state: str) -> dict:
        resp = client.system_one(
            state=clue_state,
            questions={
                "difficulty": Score(
                    instructions=instructions,
                    criteria=DIFFICULTY_CRITERIA,
                ),
            },
        )
        ans = resp.scores["difficulty"]
        raw_score = ans.score  # float 0–9
        difficulty = max(1, min(10, int(round(raw_score)) + 1))
        return {"difficulty": difficulty, "confidence": ans.confidence}
    return call


def _clue_key(row) -> tuple:
    import math as _math
    r = row["row"]; c = row["column"]
    return (int(row["game_id"]), str(row["round"]),
            -1.0 if (r is None or (isinstance(r, float) and _math.isnan(r))) else float(r),
            -1.0 if (c is None or (isinstance(c, float) and _math.isnan(c))) else float(c))


def _load_checkpoint(checkpoint: Path, hash_file: Path, prompt_hash: str) -> tuple:
    """Load a scoring checkpoint. Returns (rows, done_keys, n_failed_from_checkpoint)."""
    if not checkpoint.exists():
        hash_file.write_text(prompt_hash)
        return [], set(), 0
    saved_hash = hash_file.read_text().strip() if hash_file.exists() else ""
    if saved_hash != prompt_hash:
        print("Prompt changed — discarding checkpoint and starting fresh")
        checkpoint.unlink()
        hash_file.unlink(missing_ok=True)
        hash_file.write_text(prompt_hash)
        return [], set(), 0
    prev = pd.read_parquet(checkpoint)
    all_prev = prev.to_dict(orient="records")
    rows = [r for r in all_prev if pd.notna(r.get("difficulty"))]
    done_keys = {_clue_key(r) for r in rows}
    n_failed = len(all_prev) - len(rows)
    print(f"Resuming: {len(done_keys):,} successful, {n_failed:,} failed rows will retry")
    return rows, done_keys, n_failed


def _cleanup_checkpoint(checkpoint: Path, n_failed: int) -> None:
    if n_failed == 0:
        checkpoint.unlink(missing_ok=True)
    else:
        print(f"  {n_failed:,} clues exhausted retries — checkpoint kept for next run")


def run_scoring() -> None:
    import hashlib
    instructions = PROMPT_PATH.read_text().strip()
    prompt_hash = hashlib.sha256(instructions.encode()).hexdigest()[:16]

    df = filter_scoreable(pd.read_parquet(CLUES_PATH))
    print(f"Scoring {len(df):,} clues...")

    checkpoint = OUT_PATH.with_suffix(".checkpoint.parquet")
    hash_file = OUT_PATH.with_suffix(".prompt_hash")
    rows, done_keys, _ = _load_checkpoint(checkpoint, hash_file, prompt_hash)

    client = make_jev_client(instructions)
    n_failed = 0
    for i, (_, row) in enumerate(df.iterrows()):
        key = _clue_key(row)
        if key in done_keys:
            continue
        clue_state = build_prompt(row["category"], row["clue"], row["answer"])
        for attempt in range(3):
            try:
                scored = score_clue(client, clue_state)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"Giving up on clue {key}: {e}")
                    scored = {"difficulty": None, "jev_confidence": None}
                    n_failed += 1
                else:
                    time.sleep(2 ** attempt)
        rows.append({"game_id": row["game_id"], "round": row["round"],
                     "row": row["row"], "column": row["column"], **scored})
        if pd.notna(scored["difficulty"]):
            done_keys.add(key)
        if len(rows) % 1000 == 0:
            print(f"  {len(rows):,}/{len(df):,}")
            pd.DataFrame(rows).to_parquet(checkpoint, compression="zstd", index=False)

    out = pd.DataFrame(rows)
    out.to_parquet(OUT_PATH, compression="zstd", index=False)
    _cleanup_checkpoint(checkpoint, n_failed)
    print(f"Wrote {len(out):,} rows to {OUT_PATH}")


if __name__ == "__main__":
    run_scoring()

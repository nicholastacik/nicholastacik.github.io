"""Join clues.parquet + correctness.parquet + jev_scores.parquet."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
_POST = ROOT / "posts" / "jeopardy_difficulty"
_JOIN_COLS = ["game_id", "round", "row", "column"]
_SENTINEL = -1.0


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


def _assert_one_to_one(left: pd.DataFrame, right: pd.DataFrame, key: list) -> None:
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

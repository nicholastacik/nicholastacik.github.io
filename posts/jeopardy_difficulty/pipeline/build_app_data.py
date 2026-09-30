"""Export sampled clues for the interactive difficulty sampler app."""
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
    df = df.merge(clusters[["game_id", "round", "category", "cluster_id"]],
                  on=["game_id", "round", "category"], how="left")
    df["cluster_name"] = df["cluster_id"].map(labels).fillna("Uncategorized")

    rows = []
    for bucket in range(1, 11):
        bucket_df = df[df["difficulty"] == bucket]
        sample = bucket_df.sample(min(len(bucket_df), per_bucket), random_state=42)
        rows.extend(sample[_APP_COLS].to_dict(orient="records"))

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

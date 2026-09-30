"""Spike: compare 3 Score-rubric criteria formulations on 2k clues."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from typesafe_sdk import TypeSafeClient, Score

ROOT = Path(__file__).resolve().parents[3]
CLUES = ROOT / "posts" / "jeopardy_ds" / "clues.parquet"
CORRECTNESS = Path(__file__).parent.parent / "correctness.parquet"
OUT = Path(__file__).parent.parent / "spike_sample.jsonl"
SPIKE_GAME_IDS = Path(__file__).parent.parent / "spike_game_ids.txt"

INSTRUCTIONS = (Path(__file__).parent / "prompt.txt").read_text().strip()

# 3 criteria formulations to compare (10 levels each, 0=easiest → 9=hardest → +1 → 1–10)
CRITERIA = {
    "descriptive": [
        "Almost anyone would know this — everyday knowledge or ubiquitous pop culture",
        "Easy — broad general knowledge that most adults pick up without effort",
        "Somewhat easy — covered in school or by casual media consumption",
        "Below average difficulty — requires a specific interest or hobby",
        "Median Jeopardy difficulty — a strong contestant would likely get this",
        "Slightly above average — needs solid reading or cultural breadth",
        "Hard — only enthusiasts or students in this area would know it",
        "Very hard — specialist knowledge required, most players would guess",
        "Expert level — only those with deep domain expertise know it reliably",
        "Near-impossible — obscure even to specialists in this domain",
    ],
    "percentile": [
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
    ],
    "concise": [
        "Trivially easy — a child could answer",
        "Easy — common general knowledge",
        "Fairly easy — school or pop culture recall",
        "Below average — hobby-level knowledge",
        "Median — typical for a Jeopardy contestant",
        "Above average — requires dedicated reading",
        "Hard — enthusiast-level knowledge",
        "Very hard — specialist knowledge needed",
        "Expert — deep domain mastery required",
        "Near-impossible — obscure even to experts",
    ],
}


def sample_clues(n=2000, exclude_game_ids: set = None):
    df = pd.read_parquet(CLUES)
    df = df[
        (df["media"] == False) &
        (df["round"].isin(["Jeopardy", "Double Jeopardy"])) &
        df["row"].notna()
    ].dropna(subset=["clue", "answer", "category"])
    if exclude_game_ids:
        df = df[~df["game_id"].isin(exclude_game_ids)]
    df["stratum"] = df["round"] + "_" + df["row"].astype(int).astype(str)
    n_strata = df["stratum"].nunique()
    sampled = (
        df.groupby("stratum", group_keys=False)
        .apply(lambda g: g.sample(min(len(g), n // n_strata), random_state=42))
    )
    return sampled.head(n)


if __name__ == "__main__":
    all_game_ids = pd.read_parquet(CLUES, columns=["game_id"])["game_id"].unique()
    rng = np.random.default_rng(42)
    test_game_ids = set(rng.choice(all_game_ids, size=int(len(all_game_ids) * 0.2), replace=False))
    sample = sample_clues(2000, exclude_game_ids=test_game_ids)

    spike_game_ids = set(sample["game_id"].unique())
    SPIKE_GAME_IDS.write_text("\n".join(str(g) for g in sorted(spike_game_ids)))
    (Path(__file__).parent.parent / "test_game_ids.txt").write_text(
        "\n".join(str(g) for g in sorted(test_game_ids))
    )
    print(f"Spike: {len(sample)} clues from {len(spike_game_ids)} games; "
          f"test set: {len(test_game_ids)} games")

    client = TypeSafeClient()
    results = []
    for variant_name, criteria_list in CRITERIA.items():
        print(f"Scoring with {variant_name}...")
        for _, row in sample.iterrows():
            clue_state = (
                f"Category: {row['category']}. "
                f"Clue: {row['clue']}. "
                f"Correct answer: {row['answer']}."
            )
            try:
                resp = client.system_one(
                    state=clue_state,
                    questions={"difficulty": Score(instructions=INSTRUCTIONS, criteria=criteria_list)},
                )
                ans = resp.scores["difficulty"]
                raw_score = ans.score  # float 0–9
                difficulty = max(1, min(10, int(round(raw_score)) + 1))  # 1–10
                results.append({
                    "criteria": variant_name,
                    "game_id": int(row["game_id"]),
                    "round": row["round"],
                    "row": row["row"],
                    "column": row["column"],
                    "clue": row["clue"],
                    "result": {"difficulty": difficulty, "confidence": ans.confidence},
                })
            except Exception as e:
                print(f"Error on clue {row['game_id']}: {e}")

    OUT.write_text("\n".join(json.dumps(r) for r in results))
    print(f"Wrote {len(results)} spike results to {OUT}")

    if CORRECTNESS.exists():
        corr_df = pd.read_parquet(CORRECTNESS)
        print("\nSelection criteria: most negative corr AND median close to 5\n")
        for variant_name in CRITERIA:
            scored_df = pd.DataFrame([
                {**r, "difficulty": r["result"]["difficulty"]}
                for r in results if r["criteria"] == variant_name
            ])
            if scored_df.empty:
                print(f"{variant_name}: no successful scores — skipping")
                continue
            merged = scored_df.merge(corr_df, on=["game_id", "round", "row", "column"], how="inner")
            has_response = (merged["n_right"] > 0) | (merged["n_wrong"] > 0) | merged["is_triple_stumper"]
            merged = merged[has_response]
            merged["any_correct"] = (merged["n_right"] > 0).astype(float)
            corr_val = np.corrcoef(merged["difficulty"], merged["any_correct"])[0, 1]
            median_val = merged["difficulty"].median()
            dist = merged["difficulty"].value_counts().sort_index().to_dict()
            print(f"{variant_name}: corr={corr_val:.3f}, median={median_val:.1f}, dist={dist}")

"""Sample 2k clues for prompt development. Throwaway — not kept after Task 3."""
import json
from pathlib import Path
import pandas as pd
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.typesafe import TypeSafeModel

ROOT = Path(__file__).resolve().parents[3]
CLUES = ROOT / "posts" / "jeopardy_ds" / "clues.parquet"
CORRECTNESS = Path(__file__).parent.parent / "correctness.parquet"
OUT = Path(__file__).parent.parent / "spike_sample.jsonl"
SPIKE_GAME_IDS = Path(__file__).parent.parent / "spike_game_ids.txt"

PROMPTS = {
    "v1": (
        "Rate the difficulty of this Jeopardy clue on a scale of 1 (very easy) to 10 (very hard). "
        "Consider how much specialized knowledge is needed to answer it correctly. "
        "Category: {category}. Clue: {clue}. Answer: {answer}."
    ),
    "v2": (
        "You are an expert Jeopardy analyst. Rate how difficult this clue is for a typical contestant "
        "on a scale of 1 (almost anyone would know it) to 10 (only a specialist would know it). "
        "Category: {category}. Clue: {clue}. Correct answer: {answer}."
    ),
    "v3": (
        "Rate this Jeopardy clue's difficulty 1-10. "
        "1=common knowledge, 5=needs some study, 10=expert specialist only. "
        "Category: {category}. Clue: {clue}. Answer: {answer}."
    ),
}


class DifficultyScore(BaseModel):
    difficulty: int
    confidence: float


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
    rng = __import__("numpy").random.default_rng(42)
    test_game_ids = set(rng.choice(all_game_ids, size=int(len(all_game_ids) * 0.2), replace=False))
    sample = sample_clues(2000, exclude_game_ids=test_game_ids)

    spike_game_ids = set(sample["game_id"].unique())
    SPIKE_GAME_IDS.write_text("\n".join(str(g) for g in sorted(spike_game_ids)))
    (Path(__file__).parent.parent / "test_game_ids.txt").write_text(
        "\n".join(str(g) for g in sorted(test_game_ids))
    )
    print(f"Spike: {len(sample)} clues from {len(spike_game_ids)} games; "
          f"test set: {len(test_game_ids)} games")

    results = []
    for prompt_name, prompt_template in PROMPTS.items():
        print(f"Scoring with {prompt_name}...")
        agent = Agent(TypeSafeModel("jev-latest"), output_type=DifficultyScore)
        for _, row in sample.iterrows():
            prompt_text = prompt_template.format(
                category=row["category"], clue=row["clue"], answer=row["answer"]
            )
            try:
                out = agent.run_sync(prompt_text)
                results.append({"prompt": prompt_name, "game_id": int(row["game_id"]),
                                 "round": row["round"], "row": row["row"], "column": row["column"],
                                 "clue": row["clue"],
                                 "result": {"difficulty": out.output.difficulty,
                                            "confidence": float(out.output.confidence)}})
            except Exception as e:
                print(f"Error on clue {row['game_id']}: {e}")
    OUT.write_text("\n".join(json.dumps(r) for r in results))
    print(f"Wrote {len(results)} spike results to {OUT}")

    if CORRECTNESS.exists():
        import numpy as np
        corr = pd.read_parquet(CORRECTNESS)
        for variant_name in PROMPTS:
            scored_df = pd.DataFrame([
                {**r, "difficulty": r["result"]["difficulty"]}
                for r in results if r["prompt"] == variant_name
            ])
            if scored_df.empty:
                print(f"\n{variant_name}: no successful scores — skipping signal check")
                continue
            merged = scored_df.merge(corr, on=["game_id", "round", "row", "column"], how="inner")
            has_response = (merged["n_right"] > 0) | (merged["n_wrong"] > 0) | merged["is_triple_stumper"]
            merged = merged[has_response]
            merged["any_correct"] = (merged["n_right"] > 0).astype(float)
            corr_val = np.corrcoef(merged["difficulty"], merged["any_correct"])[0, 1]
            print(f"\nSpike signal check ({variant_name}): difficulty vs any_correct corr = {corr_val:.3f}")
        print("Expected: negative (harder clues → fewer correct). If |corr| < 0.05, the prompt is not capturing difficulty.")

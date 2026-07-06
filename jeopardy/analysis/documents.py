"""Build one text document per Jeopardy category instance."""
import numpy as np
import pandas as pd

from jeopardy import config


def make_document(category, pairs, rng):
    """`"CATEGORY. clue -> answer; clue -> answer"`, pairs in rng-permuted order."""
    order = rng.permutation(len(pairs))
    body = "; ".join(f"{pairs[i][0]} -> {pairs[i][1]}" for i in order)
    return f"{category}. {body}" if body else f"{category}."


def build_documents(clues_df):
    """One document per (game_id, round, category); stable instance_id per sorted key."""
    rows = []
    grouped = clues_df.groupby(["game_id", "round", "category"], sort=True)
    for instance_id, ((game_id, round_, category), group) in enumerate(grouped):
        pairs = [
            (str(c) if not pd.isna(c) else "", str(a) if not pd.isna(a) else "")
            for c, a in zip(group["clue"], group["answer"])
        ]
        pairs.sort()  # deterministic input order before the seeded shuffle
        rng = np.random.default_rng(config.RANDOM_SEED + instance_id)
        rows.append({
            "instance_id": instance_id,
            "game_id": game_id,
            "round": round_,
            "category": category,
            "document": make_document(category, pairs, rng),
        })
    return pd.DataFrame(rows, columns=["instance_id", "game_id", "round", "category", "document"])

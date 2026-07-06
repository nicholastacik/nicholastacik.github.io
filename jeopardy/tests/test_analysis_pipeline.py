import numpy as np
import pandas as pd
from jeopardy.analysis.documents import build_documents
from jeopardy.analysis.cluster import cluster_embeddings
from jeopardy.analysis.label import build_cluster_summary


def _clues():
    rows = []
    for g in range(6):  # 6 pasta-ish + 6 opera-ish category instances
        rows.append({"game_id": g, "round": "Jeopardy", "category": "PASTA",
                     "clue": "shape of pasta", "answer": "penne"})
        rows.append({"game_id": g, "round": "Double Jeopardy", "category": "OPERA",
                     "clue": "work by Verdi", "answer": "Aida"})
    return pd.DataFrame(rows)


def test_pipeline_composes():
    instances = build_documents(_clues())
    assert len(instances) == 12
    # deterministic fake embeddings: two separated blobs keyed by category
    rng = np.random.default_rng(0)
    emb = np.array([
        (rng.normal(0, 0.01, 8) + (5.0 if c == "PASTA" else 0.0))
        for c in instances["category"]
    ])
    labels, centers = cluster_embeddings(emb, k=2, seed=42)
    summary = build_cluster_summary(instances, emb, labels, centers)
    assert summary["size"].sum() == 12
    assert set(summary.columns) == {"cluster_id", "size", "top_category_names", "top_terms", "exemplars"}
    # each cluster is a pure category type: grouping the true categories by
    # assigned label must yield exactly one category per cluster, and the
    # two clusters together must cover both categories. This fails if any
    # PASTA and OPERA instances are mixed into the same cluster.
    categories_by_label = pd.Series(instances["category"].to_numpy()).groupby(labels)
    per_cluster_categories = categories_by_label.unique()
    assert all(len(cats) == 1 for cats in per_cluster_categories)
    assert {cats[0] for cats in per_cluster_categories} == {"PASTA", "OPERA"}

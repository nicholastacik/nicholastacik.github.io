import numpy as np
import pandas as pd
from jeopardy.analysis.label import (
    top_category_names, ctfidf_terms, nearest_exemplars,
    build_cluster_summary, write_naming_prompt,
)


def test_top_category_names_counts_and_orders():
    out = top_category_names(["PASTA", "PASTA", "OPERA"])
    assert out[0] == "PASTA (2)"
    assert "OPERA (1)" in out


def test_ctfidf_surfaces_distinctive_terms():
    docs = [
        "president elected inauguration president term",
        "pasta penne rigatoni pasta noodle",
    ]
    terms = ctfidf_terms(docs, n=3)
    assert any("president" in t for t in terms[0])
    assert any("pasta" in t or "penne" in t for t in terms[1])


def test_nearest_exemplars_returns_closest():
    emb = np.array([[0.0, 0.0], [1.0, 1.0], [0.1, 0.1]])
    centroid = np.array([0.0, 0.0])
    cats = np.array(["A", "B", "C"])
    out = nearest_exemplars(emb, centroid, np.array([0, 1, 2]), cats, n=2)
    assert out == ["A", "C"]


def _instances(cats):
    return pd.DataFrame({
        "category": cats,
        "document": [f"{c}. clue -> ans" for c in cats],
    })


def test_build_cluster_summary_shape_and_sort():
    cats = ["PASTA", "PASTA", "PASTA", "OPERA"]
    emb = np.array([[0.0, 0.0], [0.1, 0.0], [0.0, 0.1], [9.0, 9.0]])
    labels = np.array([0, 0, 0, 1])
    centers = np.array([[0.03, 0.03], [9.0, 9.0]])
    summary = build_cluster_summary(_instances(cats), emb, labels, centers)
    assert list(summary.columns) == ["cluster_id", "size", "top_category_names", "top_terms", "exemplars"]
    assert summary.iloc[0]["size"] == 3        # sorted by size desc → PASTA cluster first
    assert summary["size"].sum() == 4


def test_write_naming_prompt(tmp_path):
    summary = pd.DataFrame([{
        "cluster_id": 0, "size": 3,
        "top_category_names": ["PASTA (3)"], "top_terms": ["penne"], "exemplars": ["PASTA"],
    }])
    p = tmp_path / "prompt.md"
    write_naming_prompt(summary, p)
    text = p.read_text()
    assert "Cluster 0" in text and "PASTA" in text and "penne" in text

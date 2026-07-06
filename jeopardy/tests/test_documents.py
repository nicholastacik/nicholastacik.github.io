import numpy as np
import pandas as pd
from jeopardy.analysis.documents import build_documents, make_document


def _clues():
    return pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy", "category": "PASTA",
         "clue": "a tube shape", "answer": "penne"},
        {"game_id": 1, "round": "Jeopardy", "category": "PASTA",
         "clue": "a ribbon shape", "answer": "linguine"},
        {"game_id": 1, "round": "Final", "category": "AUTHORS",
         "clue": "beloved novelist", "answer": "Toni Morrison"},
    ])


def test_build_documents_shape_and_name_first():
    df = build_documents(_clues())
    assert list(df.columns) == ["instance_id", "game_id", "round", "category", "document"]
    assert len(df) == 2  # (1, Jeopardy, PASTA) and (1, Final, AUTHORS)
    pasta = df.loc[df["category"] == "PASTA", "document"].iloc[0]
    assert pasta.startswith("PASTA.")
    assert "penne" in pasta and "linguine" in pasta


def test_build_documents_deterministic():
    pd.testing.assert_frame_equal(build_documents(_clues()), build_documents(_clues()))


def test_instance_ids_are_contiguous():
    df = build_documents(_clues())
    assert df["instance_id"].tolist() == [0, 1]


def test_make_document_shuffle_is_seed_reproducible():
    pairs = [("a", "1"), ("b", "2"), ("c", "3")]
    d1 = make_document("X", pairs, np.random.default_rng(7))
    d2 = make_document("X", pairs, np.random.default_rng(7))
    assert d1 == d2
    assert d1.startswith("X.")


def test_build_documents_independent_of_row_order():
    df = _clues()
    forward = build_documents(df)
    reversed_ = build_documents(df.iloc[::-1])
    pd.testing.assert_frame_equal(forward, reversed_)


def test_build_documents_nan_clue_and_answer_become_empty_string():
    df = pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy", "category": "PASTA",
         "clue": "a tube shape", "answer": "penne"},
        {"game_id": 1, "round": "Jeopardy", "category": "PASTA",
         "clue": float("nan"), "answer": float("nan")},
    ])
    doc = build_documents(df)["document"].iloc[0]
    assert "nan" not in doc

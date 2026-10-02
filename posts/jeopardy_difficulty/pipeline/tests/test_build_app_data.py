import pandas as pd
from pipeline.build_app_data import build_app_data, filter_app_clues


def _make_scored(n=10):
    rows = []
    for i in range(n):
        rows.append({
            "game_id": i, "round": "Jeopardy", "row": 1.0, "column": float(i % 6 + 1),
            "clue": f"Clue {i}", "answer": f"Answer {i}", "category": f"CAT{i % 3}",
            "media": False, "game_type": "regular", "is_daily_double": False,
            "difficulty": (i % 10) + 1, "jev_confidence": 0.8,
            "n_right": 1, "n_wrong": 0, "is_triple_stumper": False,
            "air_date": pd.Timestamp("2020-01-01"), "in_spike_game": False,
        })
    return pd.DataFrame(rows)


def _make_clusters(n=10):
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
    result = filter_app_clues(df)
    assert len(result) == 4


def test_bucket_underflow_takes_all():
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

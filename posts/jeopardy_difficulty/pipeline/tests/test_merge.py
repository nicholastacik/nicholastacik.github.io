import math
import pandas as pd
import pytest
from pipeline.merge import merge_datasets, _fill_nan_keys, _assert_one_to_one


def _make_clues():
    return pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy",        "row": 1.0, "column": 1.0, "clue": "Q1", "answer": "A1", "media": False},
        {"game_id": 1, "round": "Double Jeopardy",  "row": 1.0, "column": 1.0, "clue": "Q2", "answer": "A2", "media": False},
        {"game_id": 1, "round": "Final",             "row": float("nan"), "column": float("nan"), "clue": "FJ", "answer": "FA", "media": False},
    ])


def _make_correctness():
    return pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy",        "row": 1.0, "column": 1.0, "n_right": 2, "n_wrong": 0, "is_triple_stumper": False},
        {"game_id": 1, "round": "Double Jeopardy",  "row": 1.0, "column": 1.0, "n_right": 0, "n_wrong": 1, "is_triple_stumper": False},
        {"game_id": 1, "round": "Final",             "row": float("nan"), "column": float("nan"), "n_right": 1, "n_wrong": 2, "is_triple_stumper": False},
    ])


def _make_scores():
    return pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy",        "row": 1.0, "column": 1.0, "difficulty": 4, "jev_confidence": 0.9},
        {"game_id": 1, "round": "Double Jeopardy",  "row": 1.0, "column": 1.0, "difficulty": 7, "jev_confidence": 0.8},
        {"game_id": 1, "round": "Final",             "row": float("nan"), "column": float("nan"), "difficulty": 9, "jev_confidence": 0.7},
    ])


def test_final_jeopardy_joins_correctly():
    result = merge_datasets(_make_clues(), _make_correctness(), _make_scores(),
                            spike_game_ids=set(), test_game_ids=set())
    fj = result[result["round"] == "Final"]
    assert len(fj) == 1
    assert fj.iloc[0]["n_right"] == 1
    assert fj.iloc[0]["difficulty"] == 9
    assert math.isnan(fj.iloc[0]["row"])


def test_round_specific_join_no_collision():
    result = merge_datasets(_make_clues(), _make_correctness(), _make_scores(),
                            spike_game_ids=set(), test_game_ids=set())
    j_row = result[result["round"] == "Jeopardy"].iloc[0]
    dj_row = result[result["round"] == "Double Jeopardy"].iloc[0]
    assert j_row["n_right"] == 2
    assert dj_row["n_wrong"] == 1


def test_spike_game_flag():
    result = merge_datasets(_make_clues(), _make_correctness(), _make_scores(),
                            spike_game_ids={1}, test_game_ids={2})
    j_row = result[result["round"] == "Jeopardy"].iloc[0]
    assert j_row["in_spike_game"]
    assert not j_row["in_test_game"]


def test_test_game_flag():
    result = merge_datasets(_make_clues(), _make_correctness(), _make_scores(),
                            spike_game_ids=set(), test_game_ids={1})
    j_row = result[result["round"] == "Jeopardy"].iloc[0]
    assert j_row["in_test_game"]


def test_one_to_one_violation_raises():
    dup_correctness = pd.concat([_make_correctness(), _make_correctness()])
    with pytest.raises(AssertionError, match="one-to-one"):
        merge_datasets(_make_clues(), dup_correctness, _make_scores(),
                       spike_game_ids=set(), test_game_ids=set())

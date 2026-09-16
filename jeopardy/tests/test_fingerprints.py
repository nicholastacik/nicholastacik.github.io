import pandas as pd
from jeopardy.analysis.fingerprints import clue_ids, build_clue_index

_D = pd.Timestamp("2005-06-01")


def _clusters():
    return pd.DataFrame([
        {"game_id": i, "round": "Jeopardy", "category": "ART", "cluster_id": 0} for i in range(8)
    ])


def _clues():
    rows = []
    for i in range(2):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "ART", "row": 1.0, "column": 1.0,
                     "air_date": _D, "clue": f"He cut off his ear, case {i}", "answer": "van Gogh"})
    for i in range(2, 8):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "ART", "row": 1.0, "column": 1.0,
                     "air_date": _D, "clue": "Dutch post-impressionist painter", "answer": "Vincent van Gogh"})
    return pd.DataFrame(rows)


def test_clue_ids_stable_and_unique():
    ids = clue_ids(_clues())
    assert ids.iloc[0] == "0:Jeopardy:1:1"
    assert ids.nunique() == len(ids)  # each (game,round,row,col) distinct here


def test_store_has_intrinsic_fields_only_and_deduped():
    store, entity_clues, quiz_refs = build_clue_index(_clusters(), _clues(), decisions={}, min_freq=5)
    assert list(store.columns) == ["clue_id", "clue", "answer", "year", "category",
                                   "game_id", "round", "row", "column"]
    assert "cluster_id" not in store.columns and "phrase" not in store.columns
    assert store["clue_id"].is_unique


def test_quiz_refs_map_merged_answer_to_canonical_and_keep_general():
    store, entity_clues, quiz_refs = build_clue_index(_clusters(), _clues(), decisions={}, min_freq=5)
    refs = quiz_refs[0]
    assert "Vincent van Gogh" in refs           # van Gogh answers resolve to the canonical entity
    assert None in refs                          # general pool present
    ids = set(store["clue_id"])
    assert all(cid in ids for cid in refs["Vincent van Gogh"])   # refs point into the store
    assert ("Vincent van Gogh") in {p for (c, p) in entity_clues}  # full pool captured for cues

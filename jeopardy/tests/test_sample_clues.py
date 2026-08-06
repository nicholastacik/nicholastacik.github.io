import pandas as pd
from jeopardy.analysis.sample_clues import build_sample_clues

_D = pd.Timestamp("2005-06-01")


def _clusters():
    return pd.DataFrame([
        {"game_id": i, "round": "Jeopardy", "category": "ART", "cluster_id": 0}
        for i in range(8)
    ])


def _clues():
    # 6 clues answered "van Gogh", 2 answered "Vincent van Gogh": under the token
    # pipeline these merge to the canonical "Vincent van Gogh". A sample clue for
    # that entity must include the "van Gogh" answers (provenance via canonicalize).
    rows = []
    for i in range(6):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "ART", "air_date": _D,
                     "clue": f"This painter cut off his ear, case {i}", "answer": "van Gogh"})
    for i in range(6, 8):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "ART", "air_date": _D,
                     "clue": "Dutch post-impressionist, full name", "answer": "Vincent van Gogh"})
    return pd.DataFrame(rows)


def test_sample_clue_maps_merged_answer_to_canonical_entity():
    df = build_sample_clues(_clusters(), _clues(), decisions={}, k=3, general_n=25, min_freq=5)
    scoped = df[(df["cluster_id"] == 0) & (df["phrase"] == "Vincent van Gogh")]
    assert len(scoped) == 3                                   # capped at k
    assert set(scoped["answer"]) <= {"van Gogh", "Vincent van Gogh"}
    assert scoped["year"].notna().all() and (scoped["year"] == 2005).all()


def test_general_pool_has_null_phrase_and_is_capped():
    df = build_sample_clues(_clusters(), _clues(), decisions={}, k=3, general_n=5, min_freq=5)
    general = df[(df["cluster_id"] == 0) & (df["phrase"].isna())]
    assert 1 <= len(general) <= 5
    assert list(df.columns) == ["cluster_id", "phrase", "clue", "answer", "year"]


def test_dropped_entity_gets_no_scoped_clues():
    # Decision drops the entity -> no scoped rows for it.
    dec = {0: {"Vincent van Gogh": (False, "Vincent van Gogh"),
               "van Gogh": (False, "van Gogh")}}
    df = build_sample_clues(_clusters(), _clues(), decisions=dec, k=3, general_n=25, min_freq=5)
    assert df[df["phrase"] == "Vincent van Gogh"].empty

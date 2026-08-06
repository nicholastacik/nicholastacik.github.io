import pandas as pd
from jeopardy.analysis.misc_pool import misc_membership


def _clusters():
    # 10 instances, centroid_dist 0.0 .. 9.0; the worst (highest) are 9,8,...
    return pd.DataFrame({
        "game_id": list(range(10)),
        "round": ["Jeopardy"] * 10,
        "category": [f"CAT{i}" for i in range(10)],
        "cluster_id": [i % 3 for i in range(10)],
        "centroid_dist": [float(i) for i in range(10)],
    })


def test_selects_worst_fraction_and_relabels():
    misc = misc_membership(_clusters(), fraction=0.2, misc_id=-1)
    assert len(misc) == 2                                   # round(10 * 0.2)
    assert set(misc["cluster_id"]) == {-1}                  # all relabeled
    assert set(misc["category"]) == {"CAT9", "CAT8"}        # the two farthest
    assert list(misc.columns) == ["game_id", "round", "category", "cluster_id"]


def test_originals_untouched_and_at_least_one():
    df = _clusters()
    misc = misc_membership(df, fraction=0.0001, misc_id=-1)
    assert len(misc) == 1                                   # floor guarded to >= 1
    assert "centroid_dist" in df.columns and len(df) == 10  # caller's frame unchanged

import pandas as pd
from jeopardy.analysis.fingerprints import (
    clue_ids, build_clue_index, build_cues, _contains, _select_cues,
)

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
    fj = pd.DataFrame([{"game_id": 5, "round": "Final", "row": None, "column": None,
                        "air_date": _D, "clue": "final", "answer": "z"}])
    assert clue_ids(fj).iloc[0] == "5:Final:0:0"   # null row/col -> 0


def test_store_has_intrinsic_fields_only_and_deduped():
    clues = _clues()
    dup = clues.iloc[[0]].copy()   # same game_id/round/row/column -> same clue_id
    clues = pd.concat([clues, dup], ignore_index=True)
    store, entity_clues, quiz_refs = build_clue_index(_clusters(), clues, decisions={}, min_freq=5)
    assert list(store.columns) == ["clue_id", "clue", "answer", "year", "category",
                                   "game_id", "round", "row", "column"]
    assert "cluster_id" not in store.columns and "phrase" not in store.columns
    assert store["clue_id"].is_unique                      # the injected duplicate collapsed
    assert (store["clue_id"] == "0:Jeopardy:1:1").sum() == 1


def test_quiz_refs_map_merged_answer_to_canonical_and_keep_general():
    store, entity_clues, quiz_refs = build_clue_index(_clusters(), _clues(), decisions={}, min_freq=5)
    refs = quiz_refs[0]
    assert "Vincent van Gogh" in refs           # van Gogh answers resolve to the canonical entity
    assert None in refs                          # general pool present
    ids = set(store["clue_id"])
    assert all(cid in ids for cid in refs["Vincent van Gogh"])   # refs point into the store
    assert ("Vincent van Gogh") in {p for (c, p) in entity_clues}  # full pool captured for cues


def _mk(cid, phrase, clues):
    return {(cid, phrase): [{"clue_id": f"{cid}:{phrase}:{i}", "year": 2000 + i, "clue": c}
                            for i, c in enumerate(clues)]}


def test_cue_needs_two_distinct_clues_with_support_counts():
    # "Hannibal" recurs across 3 of Mark Twain's 4 clues; a one-off word does not qualify.
    ec = _mk(0, "Mark Twain", [
        "Born in Hannibal Missouri", "This Hannibal native", "The Hannibal author", "A riverboat pilot",
    ])
    ec.update(_mk(0, "Other", ["totally unrelated widget gadget"]))  # corpus contrast
    fp = build_cues(ec, n_cues=6, n_examples=4)[(0, "Mark Twain")]
    hann = [c for c in fp["cues"] if c["term"] == "hannibal"]
    assert hann and hann[0]["support"] == 3 and hann[0]["total"] == 4
    assert all(c["support"] >= 2 for c in fp["cues"])
    assert "twain" not in [c["term"] for c in fp["cues"]]   # entity's own name excluded


def test_single_clue_entity_has_no_cues():
    ec = _mk(0, "Solo", ["the same the same the same word word"])
    ec.update(_mk(0, "Filler", ["different other text here"]))
    fp = build_cues(ec)[(0, "Solo")]
    assert fp["cues"] == []                       # one clue -> never a recurring cue
    assert fp["example_clue_ids"] == ["0:Solo:0"]  # the one clue is the example


def test_example_ids_reserve_the_newest_even_with_low_coverage():
    # 3 old clues heavy with cue terms, 1 newest clue with none: newest must still be an example.
    ec = _mk(0, "Ex", [
        "cue cue cue alpha", "cue cue beta", "cue cue gamma", "totally different newest",
    ])
    ec.update(_mk(0, "Filler2", ["xxxx yyyy zzzz"]))
    fp = build_cues(ec, n_cues=6, n_examples=4)[(0, "Ex")]
    assert "0:Ex:3" in fp["example_clue_ids"]      # newest (index 3) reserved


def test_bigram_kept_and_covered_unigrams_dropped():
    # "Tom" and "Sawyer" recur together as "Tom Sawyer" across 3 clues; the bigram is kept and
    # the covered unigrams are dropped.
    ec = _mk(0, "Book", ["Tom Sawyer paints", "Tom Sawyer fence", "Tom Sawyer river"])
    ec.update(_mk(0, "Filler", ["unrelated words here now"]))
    fp = build_cues(ec, n_cues=6, n_examples=4)[(0, "Book")]
    terms = [c["term"] for c in fp["cues"]]
    assert "tom sawyer" in terms
    assert "tom" not in terms and "sawyer" not in terms


def test_contains_bigram_requires_token_adjacency_not_substring():
    # Token-fusion: tokens are ["concat", "dog"] — the bigram "cat dog" must NOT match, though a
    # naive space-join substring check ("...concat dog...") would false-positive. (Bites bug 1.)
    assert _contains("cat dog", "this is concat dog food") is False
    assert _contains("great lakes", "the great lakes region") is True
    assert _contains("great lakes", "just lakes alone") is False


def test_select_cues_drops_unigram_only_for_a_surviving_bigram():
    # A high-ranked unigram must NOT be dropped by a bigram that falls outside the kept n_cues.
    # Ranked candidates: unigram "sawyer" at #2, its covering bigram "tom sawyer" at #7 (past
    # n_cues=6). Pre-fix (dedup on the full pool, then slice) dropped "sawyer" for a bigram that
    # never survived; the fix keeps "sawyer". (Bites bug 2.)
    cand = [{"term": t, "support": 2, "total": 3} for t in
            ["alpha", "sawyer", "beta", "gamma", "delta", "epsilon", "tom sawyer"]]
    kept = [c["term"] for c in _select_cues(cand, n_cues=6)]
    assert "sawyer" in kept                      # not dropped by the sliced-away bigram
    assert kept == ["alpha", "sawyer", "beta", "gamma", "delta", "epsilon"]

    # But when the covering bigram IS kept (ranked above the unigram), the unigram is dropped.
    cand2 = [{"term": "tom sawyer", "support": 3, "total": 3},
             {"term": "sawyer", "support": 3, "total": 3},
             {"term": "river", "support": 2, "total": 3}]
    kept2 = [c["term"] for c in _select_cues(cand2, n_cues=6)]
    assert kept2 == ["tom sawyer", "river"]


def test_run_fingerprints_store_is_pruned_to_referenced(tmp_path, monkeypatch):
    import jeopardy.analysis.fingerprints as fp
    clusters = _clusters()
    clusters["centroid_dist"] = 0.0
    clues = _clues()
    # one extra clue that resolves to NO displayed entity and is not in any general sample cap
    # -> must NOT appear in the written store.
    extra = pd.DataFrame([{"game_id": 999, "round": "Jeopardy", "category": "ART", "row": 5.0,
                           "column": 5.0, "air_date": _D, "clue": "orphan clue", "answer": "nobody"}])
    clues = pd.concat([clues, extra], ignore_index=True)

    monkeypatch.setattr(fp.config, "CATEGORY_CLUSTERS_PATH", tmp_path / "cl.parquet")
    monkeypatch.setattr(fp.config, "PARQUET_PATH", tmp_path / "clues.parquet")
    monkeypatch.setattr(fp.config, "ENTITY_DECISIONS_PATH", tmp_path / "dec.csv")
    monkeypatch.setattr(fp.config, "CLUES_STORE_PATH", tmp_path / "store.parquet")
    monkeypatch.setattr(fp.config, "CATEGORY_QUIZ_REFS_PATH", tmp_path / "qr.parquet")
    monkeypatch.setattr(fp.config, "CATEGORY_FINGERPRINTS_PATH", tmp_path / "fp.parquet")
    clusters.to_parquet(tmp_path / "cl.parquet")
    clues.to_parquet(tmp_path / "clues.parquet")

    fp.run_fingerprints(min_freq=5)
    store = pd.read_parquet(tmp_path / "store.parquet")
    qr = pd.read_parquet(tmp_path / "qr.parquet")
    fpr = pd.read_parquet(tmp_path / "fp.parquet")
    referenced = set(i for ids in qr["clue_ids"] for i in ids) | \
                 set(i for ids in fpr["example_clue_ids"] for i in ids)
    assert set(store["clue_id"]) == referenced          # exactly the referenced set
    assert "999:Jeopardy:5:5" not in set(store["clue_id"])  # orphan pruned


def test_run_fingerprints_pruned_to_displayed_entities(tmp_path, monkeypatch):
    import jeopardy.analysis.fingerprints as fp
    clusters = _clusters()
    clusters["centroid_dist"] = 0.0
    clues = _clues()  # resolves to "Vincent van Gogh" in cluster 0
    monkeypatch.setattr(fp.config, "CATEGORY_CLUSTERS_PATH", tmp_path / "cl.parquet")
    monkeypatch.setattr(fp.config, "PARQUET_PATH", tmp_path / "clues.parquet")
    monkeypatch.setattr(fp.config, "ENTITY_DECISIONS_PATH", tmp_path / "dec.csv")
    monkeypatch.setattr(fp.config, "CATEGORY_TOKENS_PATH", tmp_path / "tok.parquet")
    monkeypatch.setattr(fp.config, "CLUES_STORE_PATH", tmp_path / "store.parquet")
    monkeypatch.setattr(fp.config, "CATEGORY_QUIZ_REFS_PATH", tmp_path / "qr.parquet")
    monkeypatch.setattr(fp.config, "CATEGORY_FINGERPRINTS_PATH", tmp_path / "fp.parquet")
    clusters.to_parquet(tmp_path / "cl.parquet")
    clues.to_parquet(tmp_path / "clues.parquet")
    # tokens list a DIFFERENT (non-resolved) entity only -> van Gogh must be pruned out
    pd.DataFrame({"era": [1980], "cluster_id": [0], "rank": [1], "phrase": ["Someone Else"],
                  "count": [9], "tfidf_weight": [0.0]}).to_parquet(tmp_path / "tok.parquet")
    fp.run_fingerprints(min_freq=5)
    fpr = pd.read_parquet(tmp_path / "fp.parquet")
    assert "Vincent van Gogh" not in set(fpr["phrase"])   # not displayed -> no fingerprint
    qr = pd.read_parquet(tmp_path / "qr.parquet")
    per_entity = qr[qr["phrase"].notna()]
    assert "Vincent van Gogh" not in set(per_entity["phrase"])  # per-entity quiz ref pruned too
    assert qr["phrase"].isna().any()                      # general pool still present

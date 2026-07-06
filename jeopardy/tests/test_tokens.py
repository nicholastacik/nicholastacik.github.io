from jeopardy.analysis.tokens import extract_phrases


def test_extracts_regnal_entity():
    out = extract_phrases("In 1483 Richard III seized the throne of England")
    assert "Richard III" in out
    assert "England" in out


def test_extracts_multiword_war():
    out = extract_phrases("World War II began in Europe")
    assert "World War II" in out
    assert "Europe" in out


def test_connectors_join_entity():
    out = extract_phrases("The United States of America declared independence")
    assert "United States of America" in out
    # sentence-initial "The" must not glue onto the entity
    assert "The United States of America" not in out


def test_sentence_initial_pronoun_dropped():
    # a wordplay-style clue yields no proper-noun entities
    assert extract_phrases("This four-letter word means to leap") == []


def test_word_boundary_and_dedup_counting():
    # returns each occurrence (dups kept) so callers can count
    out = extract_phrases("Napoleon met Napoleon again")
    assert out.count("Napoleon") == 2


def test_year_not_glued_to_regnal_entity():
    out = extract_phrases("In 1483 Richard III seized the throne of England")
    assert "Richard III" in out
    assert "England" in out
    assert not any("1483" in phrase for phrase in out)


def test_year_dropped_but_entity_kept():
    out = extract_phrases("The 1980 Olympics were held in Moscow")
    assert "Olympics" in out
    assert "Moscow" in out
    assert not any("1980" in phrase for phrase in out)


def test_and_splits_separate_entities():
    out = extract_phrases("World War II and World War I are conflicts")
    assert "World War II" in out
    assert "World War I" in out
    assert "World War II and World War I" not in out


def test_leading_title_dropped_not_emitted():
    # a leading title is dropped like a stopword, not emitted as its own token
    assert extract_phrases("President Abraham Lincoln") == ["Abraham Lincoln"]


def test_leading_title_dropped_name_and_place_survive():
    out = extract_phrases("King Henry VIII of England")
    assert any("Henry VIII" in phrase for phrase in out)
    assert any("England" in phrase for phrase in out)
    assert not any(phrase == "King" for phrase in out)


def test_stopword_then_title_yields_nothing():
    # "The" (stopword) and "President" (title) both strip, leaving nothing
    assert extract_phrases("The President spoke") == []


import pandas as pd
from jeopardy.analysis.tokens import cluster_top_phrases


def _clusters():
    # cluster 0 = entity-heavy (Lincoln repeats), cluster 1 = wordplay (all distinct)
    rows = []
    for i in range(8):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "PRESIDENTS", "cluster_id": 0})
        rows.append({"game_id": i, "round": "Jeopardy", "category": "4-LETTER WORDS", "cluster_id": 1})
    return pd.DataFrame(rows)


def _clues():
    rows = []
    for i in range(8):
        rows.append({"game_id": i, "round": "Jeopardy", "category": "PRESIDENTS",
                     "clue": "This president led during the Civil War", "answer": "Abraham Lincoln"})
        rows.append({"game_id": i, "round": "Jeopardy", "category": "4-LETTER WORDS",
                     "clue": f"a four letter word number {i}", "answer": f"wordx{i}"})
    return pd.DataFrame(rows)


def test_entity_cluster_ranks_repeated_entity():
    df = cluster_top_phrases(_clusters(), _clues(), min_freq=5, top_n=25)
    c0 = df[df["cluster_id"] == 0]
    assert c0.iloc[0]["phrase"] == "Abraham Lincoln"
    assert c0.iloc[0]["count"] == 8
    assert c0.iloc[0]["rank"] == 1
    assert (c0["n_qualifying_phrases"] > 0).all()


def test_wordplay_cluster_has_no_qualifying_phrases():
    df = cluster_top_phrases(_clusters(), _clues(), min_freq=5, top_n=25)
    c1 = df[df["cluster_id"] == 1]
    assert len(c1) == 1
    assert c1.iloc[0]["n_qualifying_phrases"] == 0
    assert pd.isna(c1.iloc[0]["phrase"])


def test_all_clusters_represented_and_columns():
    df = cluster_top_phrases(_clusters(), _clues(), min_freq=5, top_n=25)
    assert set(df["cluster_id"]) == {0, 1}
    assert list(df.columns) == ["cluster_id", "rank", "phrase", "count", "tfidf_weight", "n_qualifying_phrases"]


def test_pipeline_entity_beats_common_word():
    # "Congress" is a common capitalized (non-title) word shared by clusters 0
    # and 1; a third, unrelated cluster keeps it from being in *every*
    # cluster (which would zero out its idf entirely and exclude it). Its
    # idf is still small relative to the names distinctive to a single
    # cluster, so "Abraham Lincoln" outranks it within cluster 0.
    clusters = pd.DataFrame(
        [{"game_id": i, "round": "Jeopardy", "category": "PRES", "cluster_id": 0} for i in range(6)]
        + [{"game_id": i, "round": "Jeopardy", "category": "GOV", "cluster_id": 1} for i in range(6)]
        + [{"game_id": i, "round": "Jeopardy", "category": "MISC", "cluster_id": 2} for i in range(6)]
    )
    clues = pd.DataFrame(
        [{"game_id": i, "round": "Jeopardy", "category": "PRES",
          "clue": "Congress honored Abraham Lincoln", "answer": "Abraham Lincoln"} for i in range(6)]
        + [{"game_id": i, "round": "Jeopardy", "category": "GOV",
            "clue": "Congress honored George Washington", "answer": "George Washington"} for i in range(6)]
        + [{"game_id": i, "round": "Jeopardy", "category": "MISC",
            "clue": "no proper nouns appear in this clue at all", "answer": "nothing notable"} for i in range(6)]
    )
    df = cluster_top_phrases(clusters, clues, min_freq=5, top_n=25)
    c0 = df[df["cluster_id"] == 0].set_index("phrase")
    # "Abraham Lincoln" (distinctive to cluster 0) outranks "Congress" (shared)
    assert c0.loc["Abraham Lincoln", "rank"] < c0.loc["Congress", "rank"]
    assert c0.loc["Congress", "tfidf_weight"] < c0.loc["Abraham Lincoln", "tfidf_weight"]

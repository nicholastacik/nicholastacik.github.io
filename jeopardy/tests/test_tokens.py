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
from jeopardy.analysis.tokens import era_tokens

_AIR_DATE = pd.Timestamp("2000-01-01")  # single fixed date; era_tokens is exercised with cutoffs=[1980]


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
        rows.append({"game_id": i, "round": "Jeopardy", "category": "PRESIDENTS", "air_date": _AIR_DATE,
                     "clue": "This president led during the Civil War", "answer": "Abraham Lincoln"})
        rows.append({"game_id": i, "round": "Jeopardy", "category": "4-LETTER WORDS", "air_date": _AIR_DATE,
                     "clue": f"a four letter word number {i}", "answer": f"wordx{i}"})
    return pd.DataFrame(rows)


def test_entity_cluster_ranks_repeated_entity():
    tokens_df, eras_df, _ = era_tokens(_clusters(), _clues(), [1980], min_freq=5, top_n=25)
    c0 = tokens_df[tokens_df["cluster_id"] == 0]
    assert c0.iloc[0]["phrase"] == "Abraham Lincoln"
    assert c0.iloc[0]["count"] == 8
    assert c0.iloc[0]["rank"] == 1
    assert (eras_df[eras_df["cluster_id"] == 0]["n_qualifying_phrases"] > 0).all()


def test_wordplay_cluster_has_no_qualifying_phrases():
    tokens_df, eras_df, _ = era_tokens(_clusters(), _clues(), [1980], min_freq=5, top_n=25)
    c1_tokens = tokens_df[tokens_df["cluster_id"] == 1]
    assert len(c1_tokens) == 0
    c1_era = eras_df[eras_df["cluster_id"] == 1].iloc[0]
    assert c1_era["n_qualifying_phrases"] == 0


def test_all_clusters_represented_and_columns():
    tokens_df, eras_df, _ = era_tokens(_clusters(), _clues(), [1980], min_freq=5, top_n=25)
    # every cluster shows up in eras_df even when it has no qualifying phrases
    assert set(eras_df["cluster_id"]) == {0, 1}
    assert list(tokens_df.columns) == ["era", "cluster_id", "rank", "phrase", "count", "tfidf_weight"]


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
        [{"game_id": i, "round": "Jeopardy", "category": "PRES", "air_date": _AIR_DATE,
          "clue": "Congress honored Abraham Lincoln", "answer": "Abraham Lincoln"} for i in range(6)]
        + [{"game_id": i, "round": "Jeopardy", "category": "GOV", "air_date": _AIR_DATE,
            "clue": "Congress honored George Washington", "answer": "George Washington"} for i in range(6)]
        + [{"game_id": i, "round": "Jeopardy", "category": "MISC", "air_date": _AIR_DATE,
            "clue": "no proper nouns appear in this clue at all", "answer": "nothing notable"} for i in range(6)]
    )
    tokens_df, _, _ = era_tokens(clusters, clues, [1980], min_freq=5, top_n=25)
    c0 = tokens_df[tokens_df["cluster_id"] == 0].set_index("phrase")
    # "Abraham Lincoln" (distinctive to cluster 0) outranks "Congress" (shared)
    assert c0.loc["Abraham Lincoln", "rank"] < c0.loc["Congress", "rank"]
    assert c0.loc["Congress", "tfidf_weight"] < c0.loc["Abraham Lincoln", "tfidf_weight"]


from jeopardy.analysis.tokens import build_surface_counts


def test_build_surface_counts_tracks_cap_vs_lower():
    texts = (
        ["species is a word"] * 5
        + ["Species classification"]
        + ["China is a country"]
        + ["china tea set"] * 2
    )
    cap_count, lower_count = build_surface_counts(texts)
    assert lower_count["species"] == 5
    assert cap_count["species"] == 1
    assert cap_count["china"] == 1
    assert lower_count["china"] == 2


def _animals_clusters_and_clues():
    rows_clusters, rows_clues = [], []
    # cluster 0: real animal-cluster clues where "Species" leaks in as a
    # sentence-initial generic noun alongside real single-word entities
    # "China" and "Taft" which are capitalized throughout the corpus.
    for i in range(10):
        rows_clusters.append({"game_id": i, "round": "Jeopardy", "category": "ANIMALS", "cluster_id": 0})
        rows_clues.append({
            "game_id": i, "round": "Jeopardy", "category": "ANIMALS", "air_date": _AIR_DATE,
            "clue": "Species like this thrive near China and were named for Taft",
            "answer": "China species",
        })
    # cluster 1: filler text that only ever uses "species" lowercase, to make
    # "species" predominantly lowercase across the whole corpus.
    for i in range(30):
        rows_clusters.append({"game_id": 100 + i, "round": "Jeopardy", "category": "FILLER", "cluster_id": 1})
        rows_clues.append({
            "game_id": 100 + i, "round": "Jeopardy", "category": "FILLER", "air_date": _AIR_DATE,
            "clue": "species require careful species study of species behavior",
            "answer": "species report",
        })
    return pd.DataFrame(rows_clusters), pd.DataFrame(rows_clues)


def test_generic_single_word_dropped_real_single_word_entities_kept():
    clusters, clues = _animals_clusters_and_clues()
    tokens_df, eras_df, _ = era_tokens(clusters, clues, [1980], min_freq=5, top_n=25)
    c0 = tokens_df[tokens_df["cluster_id"] == 0]
    phrases = set(c0["phrase"])
    assert "Species" not in phrases
    assert "China" in phrases
    assert "Taft" in phrases
    assert eras_df[eras_df["cluster_id"] == 0].iloc[0]["n_qualifying_phrases"] == 2


def test_multiword_phrase_never_dropped_by_capitalization_filter():
    # "united" and "kingdom" are individually overwhelmingly lowercase across
    # the corpus, but the multi-word phrase "United Kingdom" must survive
    # since the capitalization-dominance filter only applies to single words.
    rows_clusters, rows_clues = [], []
    for i in range(10):
        rows_clusters.append({"game_id": i, "round": "Jeopardy", "category": "GEO", "cluster_id": 0})
        rows_clues.append({
            "game_id": i, "round": "Jeopardy", "category": "GEO", "air_date": _AIR_DATE,
            "clue": "United Kingdom is a united kingdom of nations",
            "answer": "United Kingdom",
        })
    # a second, unrelated cluster so "United Kingdom" has a nonzero idf
    # (distinctive to cluster 0) instead of appearing in every cluster.
    for i in range(10):
        rows_clusters.append({"game_id": 100 + i, "round": "Jeopardy", "category": "MISC", "cluster_id": 1})
        rows_clues.append({
            "game_id": 100 + i, "round": "Jeopardy", "category": "MISC", "air_date": _AIR_DATE,
            "clue": "no proper nouns appear in this clue at all",
            "answer": "nothing notable",
        })
    clusters = pd.DataFrame(rows_clusters)
    clues = pd.DataFrame(rows_clues)
    tokens_df, _, _ = era_tokens(clusters, clues, [1980], min_freq=5, top_n=25)
    c0 = tokens_df[tokens_df["cluster_id"] == 0]
    assert "United Kingdom" in set(c0["phrase"])


def _era_clusters():
    return pd.DataFrame([
        {"game_id": g, "round": "Jeopardy", "category": "SCIENTISTS", "cluster_id": 0}
        for g in range(12)
    ])


def _era_clues():
    rows = []
    for g in range(12):
        yr = 1995 if g < 6 else 2015  # half old, half recent
        rows.append({"game_id": g, "round": "Jeopardy", "category": "SCIENTISTS",
                     "air_date": pd.Timestamp(f"{yr}-01-01"),
                     "clue": "This physicist Niels Bohr and also Bohr", "answer": "Niels Bohr"})
    return pd.DataFrame(rows)


def test_era_tokens_long_format_and_dedup():
    tokens_df, eras_df, merges = era_tokens(_era_clusters(), _era_clues(), [1980, 2010], min_freq=2, top_n=25)
    assert set(tokens_df["era"]) == {1980, 2010}
    # Bohr/Niels folded into Niels Bohr by dedup
    phrases_1980 = set(tokens_df[tokens_df["era"] == 1980]["phrase"])
    assert "Niels Bohr" in phrases_1980
    assert "Bohr" not in phrases_1980
    # eras_df has one row per (era, cluster)
    assert set(eras_df.columns) == {"era", "cluster_id", "size", "share", "n_qualifying_phrases"}


def test_era_tokens_count_sorted():
    tokens_df, _, _ = era_tokens(_era_clusters(), _era_clues(), [1980], min_freq=2, top_n=25)
    counts = tokens_df[tokens_df["era"] == 1980].sort_values("rank")["count"].tolist()
    assert counts == sorted(counts, reverse=True)


def _many_entities_clusters_and_clues():
    # cluster 0: 12 distinct two-word entities (5 occurrences each, so each
    # is >= min_freq on its own) plus a dedupable single-word pair
    # "Emmy"/"Emmys" (5 occurrences each). None of these phrases collide via
    # the contiguous-component or plural dedup rules except the Emmy pair.
    names = [
        "Meryl Streep", "Tom Hanks", "Denzel Washington", "Julia Roberts",
        "Brad Pitt", "Angelina Jolie", "Robert Downey", "Al Pacino",
        "Jack Nicholson", "Cate Blanchett", "Morgan Freeman", "Nicole Kidman",
    ]
    rows_clusters, rows_clues = [], []
    gid = 0
    for name in names:
        for _ in range(5):
            rows_clusters.append({"game_id": gid, "round": "Jeopardy", "category": "AWARDS", "cluster_id": 0})
            rows_clues.append({"game_id": gid, "round": "Jeopardy", "category": "AWARDS", "air_date": _AIR_DATE,
                                "clue": "this actor won an award for a film role", "answer": name})
            gid += 1
    for word in ("Emmy", "Emmys"):
        for _ in range(5):
            rows_clusters.append({"game_id": gid, "round": "Jeopardy", "category": "AWARDS", "cluster_id": 0})
            rows_clues.append({"game_id": gid, "round": "Jeopardy", "category": "AWARDS", "air_date": _AIR_DATE,
                                "clue": "this television award is given every year", "answer": word})
            gid += 1
    return pd.DataFrame(rows_clusters), pd.DataFrame(rows_clues)


def test_n_qualifying_phrases_uncapped_and_pre_dedup():
    # Regression test for the applicability-metric bug: n_qualifying_phrases
    # must count every distinct raw phrase >= min_freq, BEFORE the
    # DEDUP_CANDIDATE_K top-150 cap and BEFORE canonicalize() dedup - not
    # the capped/deduped count used for the displayed top-N tokens.
    clusters, clues = _many_entities_clusters_and_clues()
    tokens_df, eras_df, merges = era_tokens(clusters, clues, [1980], min_freq=5, top_n=25)

    # sanity: the display path *did* dedup Emmy/Emmys into one canonical row
    assert any(lo in ("Emmy", "Emmys") and hi in ("Emmy", "Emmys") for _, _, lo, hi in merges)
    c0_tokens = tokens_df[tokens_df["cluster_id"] == 0]
    assert "Emmy" not in set(c0_tokens["phrase"])
    assert "Emmys" in set(c0_tokens["phrase"])
    assert len(c0_tokens) == 13  # 12 actor names + 1 merged Emmy/Emmys row

    # n_qualifying_phrases must NOT be reduced by that dedup: 12 actor names
    # + Emmy + Emmys, counted separately, uncapped = 14.
    n_qual = eras_df[eras_df["cluster_id"] == 0].iloc[0]["n_qualifying_phrases"]
    assert n_qual == 14


from jeopardy.analysis.tokens import is_mechanical_noise


def test_mechanical_noise_drops_clue_crew_and_interjections():
    assert is_mechanical_noise("Sarah of the Clue Crew")
    assert is_mechanical_noise("Jimmy of the Clue Crew")
    assert is_mechanical_noise("Oh")
    assert is_mechanical_noise("Hi")


def test_mechanical_noise_keeps_real_and_ambiguous():
    # real entities, and the ambiguous ones the LLM (not the pre-filter) must judge
    for p in ["Isaac Newton", "May", "April", "March", "English", "Oh Brother"]:
        assert not is_mechanical_noise(p)


from jeopardy.analysis.tokens import apply_entity_decisions, load_entity_decisions


def test_apply_drops_remaps_and_default_keeps():
    counts = {"John": 40, "Grey": 20, "Anatomy": 15, "Isaac Newton": 30}
    decisions = {
        "John": (False, ""),               # drop (vague)
        "Grey": (True, "Grey's Anatomy"),  # merge into fuller
        "Anatomy": (True, "Grey's Anatomy"),
        # "Isaac Newton" absent -> default keep
    }
    out = apply_entity_decisions(counts, decisions)
    assert "John" not in out
    assert out["Grey's Anatomy"] == 35   # 20 + 15 summed
    assert out["Isaac Newton"] == 30     # default keep
    assert "Grey" not in out and "Anatomy" not in out


def test_load_entity_decisions_missing_file(tmp_path):
    assert load_entity_decisions(tmp_path / "nope.csv") == {}


def test_load_entity_decisions_parses(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("cluster_id,phrase,keep,canonical,source\n"
                 "3,John,false,,llm\n"
                 "3,Grey,true,Grey's Anatomy,llm\n")
    d = load_entity_decisions(p)
    assert d[3]["John"] == (False, "")
    assert d[3]["Grey"] == (True, "Grey's Anatomy")


from jeopardy.analysis.misc_pool import misc_membership


def test_misc_membership_added_produces_overflow_cluster_in_tokens():
    # Two real clusters; mark the worst-fitting instances as misc (-1) and
    # confirm era_tokens treats -1 as its own type with its own entities.
    clusters = _clusters().copy()
    clusters["centroid_dist"] = [float(i) for i in range(len(clusters))]
    misc = misc_membership(clusters, fraction=0.25, misc_id=-1)
    combined = pd.concat([clusters, misc], ignore_index=True)
    tokens_df, eras_df, _ = era_tokens(combined, _clues(), [1980], min_freq=1, top_n=25)
    assert -1 in set(eras_df["cluster_id"])
    # the misc rows are additive: cluster 0 still present and unchanged in count
    c0 = tokens_df[(tokens_df["cluster_id"] == 0) & (tokens_df["phrase"] == "Abraham Lincoln")]
    assert int(c0.iloc[0]["count"]) == 8

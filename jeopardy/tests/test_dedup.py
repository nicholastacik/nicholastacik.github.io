from jeopardy.analysis.dedup import canonicalize


def test_plural_merges_to_dominant():
    out, merges = canonicalize({"Emmy": 50, "Emmys": 30})
    assert out == {"Emmy": 80}
    assert ("Emmys", "Emmy") in merges


def test_component_merges_to_fuller_name():
    # "Bohr" (169) outnumbers "Niels Bohr" (111) -> count guard blocks it; "Niels" is a leading
    # given name (not the last word) -> last-word rule blocks it. Legit aliases are restored via
    # entity_decisions, not the automatic merge.
    out, _ = canonicalize({"Bohr": 169, "Niels": 40, "Niels Bohr": 111})
    assert out == {"Bohr": 169, "Niels": 40, "Niels Bohr": 111}


def test_count_guard_blocks_overprominent_short_phrase():
    # "London" (118) outnumbers "Jack London" (70): a standalone entity, not a fragment.
    out, _ = canonicalize({"London": 118, "Jack London": 70})
    assert out == {"London": 118, "Jack London": 70}
    # a minority short phrase that is the container's LAST word still folds in
    out2, _ = canonicalize({"Gogh": 10, "Vincent Gogh": 40})
    assert out2 == {"Vincent Gogh": 50}


def test_leading_given_name_not_merged():
    # "Jack" (20) is a minority AND the container's leading given name -> must not fold in and
    # inflate the author's count with unrelated characters named Jack.
    out, _ = canonicalize({"Jack": 20, "Jack London": 46})
    assert out == {"Jack": 20, "Jack London": 46}


def test_ambiguous_surname_not_over_merged():
    # "Adams" is a component of BOTH -> ambiguous -> not merged; the two Johns stay distinct
    out, _ = canonicalize({"John Adams": 30, "John Quincy Adams": 20, "Adams": 15})
    assert "John Adams" in out and "John Quincy Adams" in out
    assert out["John Adams"] == 30 and out["John Quincy Adams"] == 20


def test_short_distinct_words_not_fuzzy_merged():
    # length < 5 -> no fuzzy merge (Mars the planet vs Marx the person)
    out, _ = canonicalize({"Mars": 50, "Marx": 20})
    assert out == {"Mars": 50, "Marx": 20}


def test_distinct_one_edit_apart_not_merged():
    # Fuzzy rule removed: distinct entities that happen to be one edit apart
    # must NOT be merged (Gambia/Zambia, Manet/Monet are real countries/people).
    out, _ = canonicalize({"Gambia": 30, "Zambia": 20})
    assert out == {"Gambia": 30, "Zambia": 20}

    out, _ = canonicalize({"Manet": 15, "Monet": 40})
    assert out == {"Manet": 15, "Monet": 40}

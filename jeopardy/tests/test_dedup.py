from jeopardy.analysis.dedup import canonicalize, edit_distance_le_1


def test_edit_distance_le_1():
    assert edit_distance_le_1("niels", "neils")      # transposition-ish substitution
    assert edit_distance_le_1("emmy", "emmys")       # one insertion
    assert not edit_distance_le_1("mars", "venus")


def test_plural_merges_to_dominant():
    out, merges = canonicalize({"Emmy": 50, "Emmys": 30})
    assert out == {"Emmy": 80}
    assert ("Emmys", "Emmy") in merges


def test_component_merges_to_fuller_name():
    out, _ = canonicalize({"Bohr": 169, "Niels": 40, "Niels Bohr": 111})
    assert out == {"Niels Bohr": 320}


def test_fuzzy_merges_misspelling():
    out, _ = canonicalize({"Niels": 40, "Neils": 10})
    assert out == {"Niels": 50}


def test_ambiguous_surname_not_over_merged():
    # "Adams" is a component of BOTH -> ambiguous -> not merged; the two Johns stay distinct
    out, _ = canonicalize({"John Adams": 30, "John Quincy Adams": 20, "Adams": 15})
    assert "John Adams" in out and "John Quincy Adams" in out
    assert out["John Adams"] == 30 and out["John Quincy Adams"] == 20


def test_short_distinct_words_not_fuzzy_merged():
    # length < 5 -> no fuzzy merge (Mars the planet vs Marx the person)
    out, _ = canonicalize({"Mars": 50, "Marx": 20})
    assert out == {"Mars": 50, "Marx": 20}

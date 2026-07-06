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

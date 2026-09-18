from jeopardy.tests.browser.render_fixture import build_fixture_data, build_fixture_html


def test_fixture_data_has_two_topics_and_expected_clues():
    data = build_fixture_data()
    # two topics available to the picker
    assert set(data["quiz"].keys()) == {"1", "2"}
    # the out-of-era clue is kept in the store (excluded at runtime by the year filter)
    assert data["clues"]["old"]["year"] == 2005
    assert data["clues"]["a1"]["year"] == 2014
    # the twice-referenced id exists once in the store
    assert "dup" in data["clues"]
    # Topic Alpha (cluster 1) references dup in BOTH the general pool and an entity
    alpha = data["quiz"]["1"]
    dup_refs = sum(1 for ids in alpha.values() if "dup" in ids)
    assert dup_refs == 2


def test_fixture_html_is_self_contained_with_practice():
    html = build_fixture_html()
    for marker in ['id="practice-open"', 'id="practice"', "Topic Alpha", "Topic Beta",
                   "function pickSession"]:
        assert marker in html, marker

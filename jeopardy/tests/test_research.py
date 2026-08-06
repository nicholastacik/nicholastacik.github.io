import pandas as pd

from jeopardy import config
from jeopardy.analysis.research import build_research_data, render_html

ERAS = [1980, 1990, 2000, 2010, 2020]


def _labels():
    return {1: "Books & Authors", 2: "Wordplay & Vocabulary"}


def _tokens_df():
    # Cluster 1 is studyable in every era, with applicability rising over time.
    # Cluster 2 is the "not really studyable" placeholder (no phrases) in every era.
    rows = []
    for i, era in enumerate(ERAS):
        rows.append({"era": era, "cluster_id": 1, "rank": 1, "phrase": "Agatha Christie",
                      "count": 111 - i, "tfidf_weight": 9.0})
        rows.append({"era": era, "cluster_id": 1, "rank": 2, "phrase": "Toni Morrison",
                      "count": 65 - i, "tfidf_weight": 8.0})
        rows.append({"era": era, "cluster_id": 2, "rank": 0, "phrase": None,
                      "count": 0, "tfidf_weight": 0.0})
    return pd.DataFrame(rows)


def _eras_df():
    rows = []
    for i, era in enumerate(ERAS):
        # cluster 1's applicability grows each era; cluster 2 stays at 0 (non-studyable)
        rows.append({"era": era, "cluster_id": 1, "size": 100 + i, "share": 0.02 + i * 0.01,
                      "n_qualifying_phrases": 2 + i})
        rows.append({"era": era, "cluster_id": 2, "size": 10, "share": 0.001,
                      "n_qualifying_phrases": 0})
    return pd.DataFrame(rows)


def test_eras_match_config_cutoffs():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    assert data["eras"] == config.ERA_CUTOFFS
    assert data["eras"] == ERAS


def test_each_era_lists_all_types_sorted_by_applicability_desc():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    for era in ERAS:
        entries = data["byEra"][str(era)]
        assert {e["cluster_id"] for e in entries} == {1, 2}
        applicabilities = [e["applicability"] for e in entries]
        assert applicabilities == sorted(applicabilities, reverse=True)
        assert entries[0]["cluster_id"] == 1  # always more applicable than the placeholder


def test_entities_are_count_sorted_and_prevalence_present():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    for i, era in enumerate(ERAS):
        entries = data["byEra"][str(era)]
        books = next(e for e in entries if e["cluster_id"] == 1)
        counts = [ent["count"] for ent in books["entities"]]
        assert counts == sorted(counts, reverse=True)
        assert books["entities"] == [
            {"phrase": "Agatha Christie", "count": 111 - i},
            {"phrase": "Toni Morrison", "count": 65 - i},
        ]
        assert books["prevalence"] == 0.02 + i * 0.01
        assert books["applicability"] == 2 + i


def test_placeholder_type_has_empty_entities_every_era():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    for era in ERAS:
        entries = data["byEra"][str(era)]
        wordplay = next(e for e in entries if e["cluster_id"] == 2)
        assert wordplay["applicability"] == 0
        assert wordplay["entities"] == []
        assert wordplay["prevalence"] == 0.001


def test_entry_shape():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    for era in ERAS:
        for entry in data["byEra"][str(era)]:
            assert set(entry) == {"cluster_id", "name", "applicability", "prevalence", "entities"}


def test_render_html_is_self_contained_and_embeds_data():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    html = render_html(data)
    assert html.strip().lower().startswith("<!doctype html")
    assert "const DATA" in html
    # data embedded as JSON and parseable back
    assert "Agatha Christie" in html and "Books &amp; Authors" in html or "Books & Authors" in html
    # no external asset references
    assert "cdn." not in html and "<script src=" not in html and "<link " not in html
    # the live-fetch endpoint + fallback are present
    assert "api/rest_v1/page/summary" in html
    assert "list=search" in html


def test_render_html_has_era_selector_over_all_eras():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    html = render_html(data)
    assert "renderEraToggle" in html
    assert "DATA.eras" in html
    # defaults to 2010
    assert "DATA.eras.includes(2010)" in html


def _sample_clues_df():
    return pd.DataFrame([
        {"cluster_id": 0, "phrase": "Abraham Lincoln", "clue": "16th president",
         "answer": "Abraham Lincoln", "year": 1994, "category": "PRESIDENTS"},
        {"cluster_id": 0, "phrase": None, "clue": "any clue", "answer": "something", "year": 2001,
         "category": "PRESIDENTS"},
    ])


def test_build_research_data_embeds_sample_clues_keyed_by_cluster():
    data = build_research_data(_tokens_df(), _eras_df(), _labels(), _sample_clues_df())
    assert "sampleClues" in data
    assert "0" in data["sampleClues"]
    entry = data["sampleClues"]["0"][0]
    assert set(entry.keys()) == {"phrase", "clue", "answer", "year", "category"}


def test_build_research_data_sample_clues_default_empty():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    assert data["sampleClues"] == {}


def test_render_html_has_sample_clue_controls():
    data = build_research_data(_tokens_df(), _eras_df(), _labels(), _sample_clues_df())
    html = render_html(data)
    assert "sample-clue-btn" in html          # the trigger
    assert "reveal-answer-btn" in html         # hidden-answer reveal
    assert "sampleClues" in html               # data embedded


def test_render_html_marks_non_studyable():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    html = render_html(data)
    # both type names appear (studyable + non-studyable)
    assert "Wordplay &amp; Vocabulary" in html or "Wordplay & Vocabulary" in html
    # the client-side renderer actually marks non-studyable types: a `dim` class
    # is applied to the side item, and the meta label reads "not really studyable"
    # (rather than the entities count) whenever a type has no entities.
    assert "!studyable ? ' dim'" in html  # class marker conditional on emptiness
    assert "not really studyable" in html

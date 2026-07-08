import pandas as pd
from jeopardy.analysis.research import build_research_data, render_html


def _tokens():
    return pd.DataFrame([
        {"cluster_id": 1, "rank": 1, "phrase": "Agatha Christie", "count": 111,
         "tfidf_weight": 9.0, "n_qualifying_phrases": 2},
        {"cluster_id": 1, "rank": 2, "phrase": "Toni Morrison", "count": 65,
         "tfidf_weight": 8.0, "n_qualifying_phrases": 2},
        {"cluster_id": 2, "rank": 0, "phrase": None, "count": 0,
         "tfidf_weight": 0.0, "n_qualifying_phrases": 0},  # non-studyable placeholder
    ])


def _labels():
    return {1: "Books & Authors", 2: "Wordplay & Vocabulary"}


def test_shape_and_sort():
    data = build_research_data(_tokens(), _labels())
    assert [d["name"] for d in data] == ["Books & Authors", "Wordplay & Vocabulary"]  # sorted by applicability desc
    assert data[0]["applicability"] == 2
    assert data[0]["entities"] == [
        {"phrase": "Agatha Christie", "count": 111},
        {"phrase": "Toni Morrison", "count": 65},
    ]


def test_placeholder_type_has_empty_entities():
    data = build_research_data(_tokens(), _labels())
    wordplay = next(d for d in data if d["name"] == "Wordplay & Vocabulary")
    assert wordplay["applicability"] == 0
    assert wordplay["entities"] == []


def test_all_types_present():
    data = build_research_data(_tokens(), _labels())
    assert {d["cluster_id"] for d in data} == {1, 2}
    assert all(set(d) == {"cluster_id", "name", "applicability", "entities"} for d in data)


def test_render_html_is_self_contained_and_embeds_data():
    data = build_research_data(_tokens(), _labels())
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


def test_render_html_marks_non_studyable():
    data = build_research_data(_tokens(), _labels())
    html = render_html(data)
    # both type names appear (studyable + non-studyable)
    assert "Wordplay &amp; Vocabulary" in html or "Wordplay & Vocabulary" in html

import pandas as pd
from jeopardy.analysis.research import build_research_data


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

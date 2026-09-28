import json
from datetime import date
from types import SimpleNamespace as NS

import pytest
from job.__main__ import main, run_news, run_suggestions

SEVERANCE = {"tmdb_id": 95396, "name": "Severance", "first_air_year": 2022}


def client_returning(payload, calls):
    def create(**kwargs):
        calls.append(kwargs)
        return NS(
            output=[],
            output_text=json.dumps(payload),
            usage=NS(input_tokens=1, output_tokens=1),
        )

    return NS(responses=NS(create=create))


def test_requires_dry_run_flag():
    with pytest.raises(SystemExit):
        main([])


def test_news_skipped_when_nothing_tracked():
    assert (
        run_news({"tracked": []}, client=None, fetch=None, today=date(2026, 9, 27))
        is None
    )


def test_suggestions_skipped_when_queue_full():
    shows = {"tracked": [SEVERANCE], "pending": [SEVERANCE] * 3}
    assert run_suggestions(shows, client=None, search=None) is None


def test_suggestions_skipped_when_nothing_tracked():
    assert run_suggestions({"tracked": []}, client=None, search=None) is None


def test_suggestions_capped_to_remaining_slots_after_validation():
    calls = []
    shows = {
        "tracked": [SEVERANCE],
        "pending": [{"tmdb_id": 8, "name": "Y", "first_air_year": 2021}] * 2,
    }
    titles = ["A", "B", "C"]
    payload = {
        "suggestions": [{"title": t, "year": 2025, "reason": "r"} for t in titles]
    }
    results = {
        t: [{"id": i, "name": t, "first_air_date": "2025-01-01"}]
        for i, t in enumerate(titles, 100)
    }
    _, kept, dropped = run_suggestions(
        shows, client_returning(payload, calls), results.__getitem__
    )
    assert [s.name for s in kept] == ["A"]
    assert dropped == ["B (2025): over queue capacity", "C (2025): over queue capacity"]


def test_suggestions_ask_for_remaining_slots_and_treat_all_lists_as_known():
    calls = []
    shows = {
        "tracked": [SEVERANCE],
        "ignored": [{"tmdb_id": 7, "name": "X", "first_air_year": 2020}],
        "pending": [{"tmdb_id": 8, "name": "Y", "first_air_year": 2021}],
    }
    payload = {"suggestions": [{"title": "X", "year": 2020, "reason": "r"}]}
    x_result = [{"id": 7, "name": "X", "first_air_date": "2020-01-01"}]
    _, kept, dropped = run_suggestions(
        shows, client_returning(payload, calls), lambda title: x_result
    )
    assert "Suggest 2 show(s)" in calls[0]["input"]
    assert kept == []
    assert dropped == ["X (2020): already tracked, ignored or suggested"]


def test_news_validates_against_tracked_ids():
    calls = []
    payload = {
        "news": [
            {
                "tmdb_id": 1,
                "headline": "h",
                "summary": "s",
                "source_url": "https://a.com/x",
                "published_date": "2026-09-26",
            }
        ]
    }
    _, kept, dropped = run_news(
        {"tracked": [SEVERANCE]},
        client_returning(payload, calls),
        lambda url: "",
        date(2026, 9, 27),
    )
    assert kept == []
    assert dropped == ["h: not a tracked show"]


def test_news_uses_medium_effort_and_suggestions_low():
    calls = []
    run_news({"tracked": [SEVERANCE]}, client_returning({"news": []}, calls), lambda url: "", date(2026, 9, 27))
    run_suggestions({"tracked": [SEVERANCE]}, client_returning({"suggestions": []}, calls), lambda t: [])
    assert [c["reasoning"] for c in calls] == [{"effort": "medium"}, {"effort": "low"}]

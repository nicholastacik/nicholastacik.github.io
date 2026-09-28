import hashlib
from datetime import date

from job.llm_cards import llm_inputs, news_card, news_card_id, suggestion_card
from job.state import Show
from job.validate import NewsItem, Suggestion

SHOWS = [
    Show(1, "One", 2020, "p1", date(2026, 9, 1), None),
    Show(2, "Two", None, "p2", date(2026, 9, 1), None),
]


def test_suggestion_card():
    s = Suggestion(
        9, "Nine", 2025, "Because.", "https://poster", "https://www.themoviedb.org/tv/9"
    )
    card = suggestion_card(s, "T")
    assert {
        k: card[k]
        for k in (
            "card_id",
            "type",
            "tmdb_id",
            "show_name",
            "headline",
            "body",
            "date",
            "link",
            "image_url",
            "status",
        )
    } == {
        "card_id": "sugg:9",
        "type": "suggestion",
        "tmdb_id": 9,
        "show_name": "Nine",
        "headline": "Nine",
        "body": "Because.",
        "date": "2025",
        "link": "https://www.themoviedb.org/tv/9",
        "image_url": "https://poster",
        "status": "new",
    }


def test_news_card_id_uses_normalized_url_and_show():
    digest = hashlib.sha1(b"deadline.com/a").hexdigest()[:8]
    assert (
        news_card_id(1, "https://www.deadline.com/a/?utm_source=x")
        == f"news:1:{digest}"
    )
    assert news_card_id(2, "https://deadline.com/a") == f"news:2:{digest}"


def test_news_card():
    item = NewsItem(
        1, "Renewed", "It was renewed.", "https://deadline.com/a", date(2026, 9, 26)
    )
    card = news_card(item, "One", "p1", "T")
    assert (
        card["type"],
        card["show_name"],
        card["headline"],
        card["body"],
        card["date"],
        card["link"],
        card["source_url"],
        card["image_url"],
    ) == (
        "news",
        "One",
        "Renewed",
        "It was renewed.",
        "2026-09-26",
        "https://deadline.com/a",
        "https://deadline.com/a",
        "p1",
    )


def card(**fields):
    return {
        "card_id": "x",
        "type": "suggestion",
        "tmdb_id": "9",
        "show_name": "Nine",
        "headline": "",
        "date": "2025",
        "status": "new",
        "created_at": "2026-09-27T06:00:00-04:00",
    } | fields


def test_llm_inputs_from_sheet_state():
    tracked_rows = [{"tmdb_id": "1"}, {"tmdb_id": "2"}, {"tmdb_id": "5"}]
    cards = [
        card(),
        card(tmdb_id="8", show_name="Eight", date="2019", status="ignored"),
        card(tmdb_id="7", show_name="Seven", status="tracked"),
        card(
            type="news",
            tmdb_id="1",
            show_name="One",
            headline="Old news",
            created_at="2026-08-01T06:00:00-04:00",
        ),
        card(
            type="news",
            tmdb_id="1",
            show_name="One",
            headline="Recent news",
            created_at="2026-09-20T06:00:00-04:00",
        ),
    ]
    inputs = llm_inputs(SHOWS, tracked_rows, cards, date(2026, 9, 27), 30)
    assert inputs["tracked"] == [
        {"tmdb_id": 1, "name": "One", "first_air_year": 2020},
        {"tmdb_id": 2, "name": "Two", "first_air_year": "?"},
    ]
    assert inputs["pending"] == [
        {"tmdb_id": 9, "name": "Nine", "first_air_year": "2025"}
    ]
    assert inputs["ignored"] == [
        {"tmdb_id": 8, "name": "Eight", "first_air_year": "2019"}
    ]
    assert inputs["recent_news"] == [{"show": "One", "headline": "Recent news"}]
    assert inputs["other_known_ids"] == [1, 2, 5, 7, 8, 9]

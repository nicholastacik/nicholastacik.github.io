from datetime import date

import httpx
from job.validate import fetch_page, normalize_url, published_date, validate_news

TODAY = date(2026, 9, 27)
URL = "https://deadline.com/2026/09/severance-season-3-date/"


def item(**overrides):
    return {
        "tmdb_id": 95396,
        "headline": "Severance season 3 gets a date",
        "summary": "Apple set a January premiere.",
        "source_url": URL,
        "published_date": "2026-09-25",
    } | overrides


def page(date_html=""):
    return f"<html><head>{date_html}</head><body>story</body></html>"


def run(raw, sources=(URL,), pages=None, tracked=(95396,)):
    pages = {URL: page()} if pages is None else pages
    return validate_news(raw, set(sources), set(tracked), pages.get, TODAY, 7)


def test_normalize_url_ignores_scheme_www_slash_fragment_and_tracking():
    assert (
        normalize_url("https://www.Deadline.com/a/b/?utm_source=chatgpt.com#x")
        == "deadline.com/a/b"
    )
    assert normalize_url("http://deadline.com/a/b") == "deadline.com/a/b"
    assert normalize_url("https://x.com/a?id=1&utm_medium=y&fbclid=z") == "x.com/a?id=1"


def test_normalize_url_keeps_meaningful_query():
    assert normalize_url("https://x.com/article?id=1") != normalize_url(
        "https://x.com/article?id=2"
    )
    assert normalize_url("https://x.com/a?b=2&a=1") == normalize_url(
        "https://x.com/a?a=1&b=2"
    )


def test_different_query_is_not_a_source_match():
    source = "https://x.com/article?id=1"
    kept, dropped = run(
        [item(source_url="https://x.com/article?id=2")],
        sources=(source,),
        pages={"https://x.com/article?id=2": page()},
    )
    assert kept == []
    assert dropped == ["Severance season 3 gets a date: URL not among search sources"]


def test_keeps_item_whose_url_is_a_search_source():
    kept, dropped = run([item()])
    assert [n.headline for n in kept] == ["Severance season 3 gets a date"]
    assert kept[0].published == date(2026, 9, 25)
    assert dropped == []


def test_tracking_params_on_either_side_still_match():
    kept, _ = run([item()], sources=(URL + "?utm_source=chatgpt.com",))
    assert len(kept) == 1
    tagged = URL + "?utm_source=chatgpt.com"
    kept, _ = run([item(source_url=tagged)], pages={tagged: page()})
    assert len(kept) == 1


def test_drops_untracked_show_bad_scheme_and_unsourced_url():
    _, dropped = run(
        [
            item(tmdb_id=1),
            item(source_url="ftp://deadline.com/x"),
            item(source_url="https://madeup.com/story"),
        ]
    )
    assert dropped == [
        "Severance season 3 gets a date: not a tracked show",
        "Severance season 3 gets a date: not an http(s) URL",
        "Severance season 3 gets a date: URL not among search sources",
    ]


def test_drops_unreachable_page():
    kept, dropped = run([item()], pages={})
    assert kept == []
    assert dropped == ["Severance season 3 gets a date: page unreachable"]


def test_page_date_overrides_model_date():
    stale = page(
        '<meta property="article:published_time" content="2026-08-01T10:00:00Z">'
    )
    kept, dropped = run([item()], pages={URL: stale})
    assert kept == []
    assert dropped == [
        "Severance season 3 gets a date: published 2026-08-01, outside window"
    ]

    fresh = page(
        '<meta property="article:published_time" content="2026-09-26T10:00:00Z">'
    )
    kept, _ = run([item(published_date="2020-01-01")], pages={URL: fresh})
    assert kept[0].published == date(2026, 9, 26)


def test_falls_back_to_model_date_and_drops_unusable_one():
    kept, _ = run([item(published_date="2026-09-01")])
    assert kept == []
    _, dropped = run([item(published_date="last week")])
    assert dropped == ["Severance season 3 gets a date: no usable publish date"]


def test_future_dates_rejected_from_page_or_model():
    _, dropped = run([item(published_date="2099-01-01")])
    assert dropped == [
        "Severance season 3 gets a date: published 2099-01-01, outside window"
    ]
    future_page = page(
        '<meta property="article:published_time" content="2026-09-28T09:00:00Z">'
    )
    kept, _ = run([item()], pages={URL: future_page})
    assert kept == []
    today_page = page(
        '<meta property="article:published_time" content="2026-09-27T09:00:00Z">'
    )
    kept, _ = run([item()], pages={URL: today_page})
    assert len(kept) == 1


def test_duplicate_url_for_same_show_kept_once():
    kept, dropped = run([item(), item(headline="Same story")])
    assert len(kept) == 1
    assert dropped == ["Same story: duplicate URL"]


def test_same_url_for_two_shows_keeps_both():
    raw = [item(), item(tmdb_id=136315, headline="The Bear renewed too")]
    kept, dropped = run(raw, tracked=(95396, 136315))
    assert [n.tmdb_id for n in kept] == [95396, 136315]
    assert dropped == []


def test_published_date_formats():
    assert published_date(
        '<meta property="article:published_time" content="2026-09-25T14:00:00-04:00">'
    ) == date(2026, 9, 25)
    assert published_date(
        '<meta content="2026-09-24" property="article:published_time">'
    ) == date(2026, 9, 24)
    assert published_date(
        '<script type="application/ld+json">{"datePublished": "2026-09-23T08:00:00Z"}</script>'
    ) == date(2026, 9, 23)
    assert published_date(
        '<time class="x" datetime="2026-09-22">Sept 22</time>'
    ) == date(2026, 9, 22)
    assert (
        published_date('<meta property="article:published_time" content="soon">')
        is None
    )
    assert published_date("<p>no date</p>") is None


def test_fetch_page_returns_text_on_success_and_none_otherwise():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/ok":
            return httpx.Response(200, text="<html>hi</html>")
        return httpx.Response(403)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_page("https://x.test/ok", client) == "<html>hi</html>"
    assert fetch_page("https://x.test/blocked", client) is None
    assert "Mozilla" in seen[0].headers["user-agent"]

    def boom(request):
        raise httpx.ConnectError("down")

    assert (
        fetch_page(
            "https://x.test/ok", httpx.Client(transport=httpx.MockTransport(boom))
        )
        is None
    )

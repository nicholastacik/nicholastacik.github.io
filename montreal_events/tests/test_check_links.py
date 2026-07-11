import httpx

from montreal_events.check_links import apply_link_checks, check_url


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ok_url_returns_true():
    client = _client(lambda request: httpx.Response(200))
    assert check_url(client, "https://example.com/") is True


def test_404_returns_false():
    client = _client(lambda request: httpx.Response(404))
    assert check_url(client, "https://example.com/gone") is False


def test_head_rejected_falls_back_to_get():
    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(200)

    assert check_url(_client(handler), "https://example.com/") is True


def test_network_error_returns_none():
    def handler(request):
        raise httpx.ConnectTimeout("boom")

    assert check_url(_client(handler), "https://example.com/") is None


def test_apply_link_checks_sets_flags_and_dedupes():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(404 if "dead" in str(request.url) else 200)

    data = {"events": [
        {"id": "a", "url": "https://ok.example/", "url_ok": None},
        {"id": "b", "url": "https://ok.example/", "url_ok": None},
        {"id": "c", "url": "https://dead.example/", "url_ok": None},
        {"id": "d", "url": None, "url_ok": None},
    ]}
    dead = apply_link_checks(data, _client(handler))
    assert [e["url_ok"] for e in data["events"]] == [True, True, False, None]
    assert dead == ["https://dead.example/"]
    assert len(set(calls)) == len(calls) == 2  # each distinct URL hit once

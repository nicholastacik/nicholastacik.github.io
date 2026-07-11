import httpx
import pytest

from montreal_events.fetch_doc import EXPORT_URL, fetch_text

LONG_TEXT = "Montreal Clubs & Events\n" + ("x" * 600)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_returns_body():
    def handler(request):
        assert str(request.url) == EXPORT_URL
        return httpx.Response(200, text=LONG_TEXT)

    assert fetch_text(_client(handler)) == LONG_TEXT


def test_fetch_raises_on_http_error():
    def handler(request):
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        fetch_text(_client(handler))


def test_fetch_raises_on_suspiciously_short_body():
    def handler(request):
        return httpx.Response(200, text="Sign in required")

    with pytest.raises(ValueError, match="short"):
        fetch_text(_client(handler))

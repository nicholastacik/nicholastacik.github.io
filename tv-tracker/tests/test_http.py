import httpx
import pytest

from job.http import get_json


def client_for(responses):
    calls = []

    def handler(request):
        calls.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    client = httpx.Client(base_url="https://x.test", transport=httpx.MockTransport(handler))
    return client, calls


def test_retries_server_error_then_succeeds():
    client, calls = client_for([httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    sleeps = []
    assert get_json(client, "/a", sleep=sleeps.append) == {"ok": 1}
    assert len(calls) == 2
    assert sleeps == [1]


def test_client_error_raises_without_retry():
    client, calls = client_for([httpx.Response(404)])
    with pytest.raises(httpx.HTTPStatusError):
        get_json(client, "/a", sleep=lambda s: None)
    assert len(calls) == 1


def test_gives_up_after_three_tries():
    client, calls = client_for([httpx.Response(503)] * 3)
    with pytest.raises(httpx.HTTPStatusError):
        get_json(client, "/a", sleep=lambda s: None)
    assert len(calls) == 3


def test_retries_transport_error():
    client, calls = client_for([httpx.ConnectError("down"), httpx.Response(200, json=[])])
    assert get_json(client, "/a", sleep=lambda s: None) == []
    assert len(calls) == 2


def test_passes_query_params():
    client, calls = client_for([httpx.Response(200, json={})])
    get_json(client, "/a", {"q": "x"}, sleep=lambda s: None)
    assert calls[0].url.params["q"] == "x"

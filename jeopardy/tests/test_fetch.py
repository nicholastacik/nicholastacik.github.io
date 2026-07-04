from jeopardy import fetch as fetch_mod
from jeopardy.fetch import fetch


def test_cache_hit_avoids_network(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_mod.config, "HTML_CACHE", tmp_path)
    (tmp_path / "abc.html").write_text("<html>cached</html>")

    def boom(*a, **k):
        raise AssertionError("network was hit on a cache hit")

    monkeypatch.setattr(fetch_mod.httpx, "get", boom)
    assert fetch("https://example.com/x", "abc") == "<html>cached</html>"


def test_cache_miss_fetches_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_mod.config, "HTML_CACHE", tmp_path)
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda *_: None)

    class FakeResp:
        text = "<html>live</html>"
        def raise_for_status(self): pass

    calls = {}
    def fake_get(url, headers, timeout):
        calls["url"] = url
        calls["ua"] = headers["User-Agent"]
        return FakeResp()

    monkeypatch.setattr(fetch_mod.httpx, "get", fake_get)
    out = fetch("https://example.com/y", "def")
    assert out == "<html>live</html>"
    assert (tmp_path / "def.html").read_text() == "<html>live</html>"
    assert calls["url"] == "https://example.com/y"
    assert "jeopardy-ds-research" in calls["ua"]

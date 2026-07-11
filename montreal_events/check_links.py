"""Advisory link health sweep over events.json. Sets url_ok; never fails the run."""

import json
import sys
from pathlib import Path

import httpx

TIMEOUT = 10
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; nicholastacik.github.io link check)"}


def check_url(client: httpx.Client, url: str) -> bool | None:
    try:
        response = client.head(url, follow_redirects=True, timeout=TIMEOUT)
        if response.status_code >= 400 and response.status_code != 404:
            # many sites reject HEAD (405) or bot-block it (403); retry with GET. 404 is trusted.
            response = client.get(url, follow_redirects=True, timeout=TIMEOUT)
        return response.status_code < 400
    except httpx.HTTPError:
        return None  # inconclusive, not confirmed dead


def apply_link_checks(data: dict, client: httpx.Client) -> list[str]:
    urls = {e["url"] for e in data["events"] if e["url"]}
    results = {url: check_url(client, url) for url in sorted(urls)}
    for event in data["events"]:
        event["url_ok"] = results[event["url"]] if event["url"] else None
    return [url for url, ok in results.items() if ok is False]


def main() -> int:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    with httpx.Client(headers=HEADERS) as client:
        dead = apply_link_checks(data, client)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    for url in dead:
        print(f"DEAD LINK: {url}")
    print(f"checked {len({e['url'] for e in data['events'] if e['url']})} urls, "
          f"{len(dead)} dead")
    return 0


if __name__ == "__main__":
    sys.exit(main())

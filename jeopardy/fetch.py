"""Polite, cached HTTP fetching. Network cost is paid once per URL."""
import random
import time

import httpx

from jeopardy import config


def fetch(url, cache_key):
    """Return page text for `url`, using an on-disk cache keyed by `cache_key`."""
    config.HTML_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = config.HTML_CACHE / f"{cache_key}.html"
    if cache_file.exists():
        return cache_file.read_text()

    resp = httpx.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=30.0,
    )
    resp.raise_for_status()
    text = resp.text
    cache_file.write_text(text)
    time.sleep(config.MIN_DELAY + random.uniform(0, config.MAX_DELAY - config.MIN_DELAY))
    return text

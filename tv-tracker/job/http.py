import time

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}


def get_json(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    *,
    tries: int = 3,
    sleep=time.sleep,
):
    for attempt in range(tries):
        last = attempt == tries - 1
        try:
            response = client.get(url, params=params)
        except httpx.TransportError:
            if last:
                raise
        else:
            if response.status_code not in RETRY_STATUS or last:
                response.raise_for_status()
                return response.json()
        sleep(2**attempt)

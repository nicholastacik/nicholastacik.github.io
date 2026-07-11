"""Fetch the Montreal events Google Doc as plain text via its public export URL."""

import sys

import httpx

DOC_ID = "15o4_PIve4R0K3Wgle58lUCxQwmDLBCiMn6f4M0FVOV4"
EXPORT_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"
MIN_LENGTH = 500  # a real doc is thousands of chars; short bodies mean auth/error pages


def fetch_text(client: httpx.Client) -> str:
    response = client.get(EXPORT_URL, follow_redirects=True)
    response.raise_for_status()
    text = response.text
    if len(text.strip()) < MIN_LENGTH:
        raise ValueError(
            f"export body suspiciously short ({len(text)} chars) — "
            "doc may no longer be link-shared"
        )
    return text


def main() -> int:
    try:
        with httpx.Client(timeout=30) as client:
            print(fetch_text(client))
    except (httpx.HTTPError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

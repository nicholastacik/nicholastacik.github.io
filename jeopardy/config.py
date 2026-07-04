"""Shared paths and constants for the jeopardy offline pipeline."""
from pathlib import Path

BASE_URL = "https://www.j-archive.com"
USER_AGENT = "jeopardy-ds-research (personal research; contact nick@gray-os.com)"

# Politeness: seconds to sleep between *network* fetches (not cache hits).
MIN_DELAY = 1.0
MAX_DELAY = 1.5

# Clue dollar values doubled on this air date; used to derive board values.
VALUE_DOUBLING_DATE = "2001-11-26"

PKG_DIR = Path(__file__).resolve().parent          # .../jeopardy
REPO_ROOT = PKG_DIR.parent                          # repo root
DATA_DIR = PKG_DIR / "data"
HTML_CACHE = DATA_DIR / "html_cache"
JSONL_PATH = DATA_DIR / "games.jsonl"
PARQUET_PATH = REPO_ROOT / "posts" / "jeopardy_ds" / "clues.parquet"

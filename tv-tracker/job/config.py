import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
NEWS_WINDOW_DAYS = int(os.environ.get("NEWS_WINDOW_DAYS", "7"))
NEWS_MEMORY_DAYS = 30
MAX_PENDING_SUGGESTIONS = 3
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6")
SUGGESTIONS_EFFORT = os.environ.get("SUGGESTIONS_EFFORT", "low")
NEWS_EFFORT = os.environ.get("NEWS_EFFORT", "medium")


def tmdb_token() -> str:
    return os.environ["TMDB_TOKEN"]


def sheet_id() -> str:
    return os.environ["SHEET_ID"]


def service_account_info() -> dict:
    if raw := os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        return json.loads(raw)
    return json.loads(
        Path(os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"]).expanduser().read_text()
    )


def omdb_key() -> str | None:
    return os.environ.get("OMDB_API_KEY") or None


def openai_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or None


def special_links() -> dict[int, dict]:
    path = Path(__file__).parent.parent / "special_links.json"
    if not path.exists():
        return {}
    return {
        int(tmdb_id): links for tmdb_id, links in json.loads(path.read_text()).items()
    }

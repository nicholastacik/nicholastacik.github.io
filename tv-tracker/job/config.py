import os
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

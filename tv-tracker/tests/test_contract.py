import json
from pathlib import Path

from job.sheet import HEADERS

APP_HEADERS = Path(__file__).resolve().parents[2] / "posts/tv_tracker/app/headers.js"


def test_app_headers_match_job_headers():
    text = APP_HEADERS.read_text()
    literal = text.split("=", 1)[1].strip().rstrip(";")
    assert json.loads(literal) == HEADERS

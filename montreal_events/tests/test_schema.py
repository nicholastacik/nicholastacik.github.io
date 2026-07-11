import json
from pathlib import Path

from jsonschema.validators import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent.parent / "events.schema.json"


def test_schema_is_valid_jsonschema():
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)


def test_schema_accepts_minimal_valid_document():
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = {
        "last_updated": "2026-07-11",
        "source_doc": "https://docs.google.com/document/d/x/",
        "events": [{
            "id": "nuits-dafrique-2026",
            "title": "Nuits d'Afrique",
            "category": "festival",
            "status": "date-specific",
            "start_date": "2026-07-07",
            "end_date": "2026-07-19",
            "location": "Quartier des spectacles",
            "url": "https://festivalnuitsdafrique.com/",
            "url_ok": None,
            "description": "World-music festival downtown.",
        }],
    }
    assert list(Draft202012Validator(schema).iter_errors(doc)) == []


def test_schema_rejects_bad_category_and_extra_key():
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = {
        "last_updated": "2026-07-11",
        "source_doc": "x",
        "events": [{
            "id": "a", "title": "A", "category": "nightclub",
            "status": "evergreen", "start_date": None, "end_date": None,
            "location": None, "url": None, "url_ok": None,
            "description": "d", "surprise": 1,
        }],
    }
    errors = list(Draft202012Validator(schema).iter_errors(doc))
    assert len(errors) >= 2  # bad enum + additionalProperties

import datetime

from montreal_events.validate import validate_events

TODAY = datetime.date(2026, 7, 11)


def make_doc(**event_overrides):
    event = {
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
    }
    event.update(event_overrides)
    return {
        "last_updated": "2026-07-11",
        "source_doc": "https://docs.google.com/document/d/x/",
        "events": [event],
    }


def test_valid_document_has_no_errors():
    assert validate_events(make_doc(), TODAY) == []


def test_schema_violation_reported():
    errors = validate_events(make_doc(category="nightclub"), TODAY)
    assert len(errors) == 1
    assert "nightclub" in errors[0]


def test_expired_date_specific_event_rejected():
    errors = validate_events(make_doc(end_date="2026-07-01"), TODAY)
    assert any("expired" in e for e in errors)


def test_start_after_end_rejected():
    errors = validate_events(
        make_doc(start_date="2026-07-20", end_date="2026-07-19"), TODAY
    )
    assert any("start_date after end_date" in e for e in errors)


def test_invalid_calendar_date_rejected():
    errors = validate_events(make_doc(start_date="2026-02-31"), TODAY)
    assert any("not a valid date" in e for e in errors)


def test_duplicate_ids_rejected():
    doc = make_doc()
    doc["events"].append(dict(doc["events"][0]))
    errors = validate_events(doc, TODAY)
    assert any("duplicate id" in e for e in errors)


def test_stale_last_updated_rejected():
    doc = make_doc()
    doc["last_updated"] = "2026-07-01"
    errors = validate_events(doc, TODAY)
    assert any("last_updated" in e for e in errors)

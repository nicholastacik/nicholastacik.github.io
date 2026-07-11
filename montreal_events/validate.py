"""Schema + sanity validation for events.json. Gate between LLM extraction and commit."""

import datetime
import json
import sys
from pathlib import Path

from jsonschema.validators import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent / "events.schema.json"


def _parse_date(value, field, event_id, errors):
    if value is None:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{event_id}: {field} {value!r} is not a valid date")
        return None


def validate_events(data: dict, today: datetime.date) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text())
    errors = [
        f"schema: {e.json_path}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(data)
    ]
    if errors:
        return errors  # semantic checks assume structural validity

    if data["last_updated"] != today.isoformat():
        errors.append(
            f"last_updated is {data['last_updated']}, expected {today.isoformat()}"
        )

    seen = set()
    for ev in data["events"]:
        eid = ev["id"]
        if eid in seen:
            errors.append(f"duplicate id: {eid}")
        seen.add(eid)

        start = _parse_date(ev["start_date"], "start_date", eid, errors)
        end = _parse_date(ev["end_date"], "end_date", eid, errors)
        if start and end and start > end:
            errors.append(f"{eid}: start_date after end_date")
        if ev["status"] == "date-specific" and end and end < today:
            errors.append(f"{eid}: expired (ended {end.isoformat()})")

    return errors


def main() -> int:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    errors = validate_events(data, datetime.date.today())
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        return 1
    print(f"OK ({len(data['events'])} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

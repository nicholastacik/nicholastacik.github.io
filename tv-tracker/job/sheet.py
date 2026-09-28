import string
from dataclasses import dataclass

HEADERS = {
    "Tracked": [
        "tmdb_id",
        "tvmaze_id",
        "name",
        "first_air_year",
        "poster_url",
        "added_at",
        "source",
        "active",
        "updated_at",
    ],
    "Cards": [
        "card_id",
        "type",
        "tmdb_id",
        "show_name",
        "headline",
        "body",
        "date",
        "link",
        "image_url",
        "source_url",
        "created_at",
        "current",
        "status",
        "updated_at",
    ],
    "Schedule": [
        "tmdb_id",
        "airstamp",
        "show_name",
        "episode_label",
        "network",
        "image_url",
        "refreshed_at",
        "link",
    ],
    "Meta": ["key", "value"],
}

UNFORMATTED = {"valueRenderOption": "UNFORMATTED_VALUE"}


@dataclass
class Update:
    tab: str
    key: str | int
    fields: dict


def column_letter(index: int) -> str:
    letters, index = "", index + 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = string.ascii_uppercase[remainder] + letters
    return letters


def _last_column(tab: str) -> str:
    return column_letter(len(HEADERS[tab]) - 1)


def parse_rows(tab: str, values: list[list[str]]) -> list[dict]:
    header = HEADERS[tab]
    rows = []
    for number, cells in enumerate(values[1:], start=2):
        raw = [str(cell) for cell in cells]
        if not any(raw):
            continue
        row = dict(zip(header, raw + [""] * (len(header) - len(raw))))
        row["_row"] = number
        rows.append(row)
    return rows


def _values(tab: str, rows: list[dict]) -> list[list]:
    return [[row.get(column, "") for column in HEADERS[tab]] for row in rows]


class Sheet:
    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet

    @classmethod
    def open(cls, service_account_info: dict, sheet_id: str) -> "Sheet":
        import gspread

        return cls(
            gspread.service_account_from_dict(service_account_info).open_by_key(
                sheet_id
            )
        )

    def read_all(self) -> dict[str, list[dict]]:
        tabs = list(HEADERS)
        response = self.spreadsheet.values_batch_get(
            [f"{tab}!A:{_last_column(tab)}" for tab in tabs], params=UNFORMATTED
        )
        return {
            tab: parse_rows(tab, vr.get("values", []))
            for tab, vr in zip(tabs, response["valueRanges"])
        }

    def write(self, updates: list[Update], appends: dict[str, list[dict]]) -> None:
        tabs = sorted(
            {u.tab for u in updates} | {tab for tab, rows in appends.items() if rows}
        )
        if not tabs:
            return
        response = self.spreadsheet.values_batch_get(
            [f"{tab}!A:A" for tab in tabs], params=UNFORMATTED
        )
        keys = {
            tab: [str(row[0]) if row else "" for row in vr.get("values", [])]
            for tab, vr in zip(tabs, response["valueRanges"])
        }
        data = []
        for update in updates:
            header = HEADERS[update.tab]
            for number, key in enumerate(keys[update.tab], start=1):
                if number > 1 and key == str(update.key):
                    for column, value in update.fields.items():
                        cell = f"{update.tab}!{column_letter(header.index(column))}{number}"
                        data.append({"range": cell, "values": [[value]]})
        for tab, rows in appends.items():
            if rows:
                data.append(
                    {
                        "range": f"{tab}!A{len(keys[tab]) + 1}",
                        "values": _values(tab, rows),
                    }
                )
        if data:
            self.spreadsheet.values_batch_update(
                {"valueInputOption": "RAW", "data": data}
            )

    def replace(self, tab: str, rows: list[dict]) -> None:
        response = self.spreadsheet.values_batch_get([f"{tab}!A:A"], params=UNFORMATTED)
        existing = len(response["valueRanges"][0].get("values", [])) - 1
        values = _values(tab, rows)
        values += [[""] * len(HEADERS[tab])] * max(0, existing - len(values))
        if values:
            self.spreadsheet.values_batch_update(
                {
                    "valueInputOption": "RAW",
                    "data": [{"range": f"{tab}!A2", "values": values}],
                }
            )

    def ensure_tabs(self) -> list[str]:
        existing = {worksheet.title for worksheet in self.spreadsheet.worksheets()}
        created = [tab for tab in HEADERS if tab not in existing]
        for tab in created:
            self.spreadsheet.add_worksheet(
                title=tab, rows=10000, cols=len(HEADERS[tab])
            )
        self.spreadsheet.values_batch_update(
            {
                "valueInputOption": "RAW",
                "data": [
                    {"range": f"{tab}!A1", "values": [h]} for tab, h in HEADERS.items()
                ],
            }
        )
        return created

"""Curate data/games.jsonl into the committed clues.parquet."""
import json

import pandas as pd

from jeopardy import config

_ROUND_FULL = {"J": "Jeopardy", "DJ": "Double Jeopardy", "Final": "Final"}

_NAMED_SEASONS = {
    "cwcpi": "audio_only",
    "jm": "jeopardy_masters",
    "pcj": "primetime_celebrity",
    "ncc": "national_college_championship",
    "goattournament": "goat",
    "bbab": "battle_bay_area_brains",
    "superjeopardy": "super_jeopardy",
    "trebekpilots": "trebek_pilots",
}

# Ordered: first matching keyword (lowercased comments) wins.
_COMMENT_RULES = [
    ("tournament of champions", "toc"),
    ("teen tournament", "teen"),
    ("teachers tournament", "teachers"),
    ("college champ", "college"),
    ("college tournament", "college"),
    ("celebrity", "celebrity"),
    ("kids week", "kids"),
    ("all-star games", "all_star"),
    ("power players", "celebrity"),
]


def board_value(round_, row, air_date):
    """Standard board dollar value for a cell (None for Final / rowless)."""
    if round_ == "Final" or row is None:
        return None
    doubled = air_date is not None and air_date >= config.VALUE_DOUBLING_DATE
    base = (200 if doubled else 100) if round_ == "J" else (400 if doubled else 200)
    return base * row


def classify_game_type(season, comments):
    if season in _NAMED_SEASONS:
        return _NAMED_SEASONS[season]
    text = (comments or "").lower()
    for keyword, label in _COMMENT_RULES:
        if keyword in text:
            return label
    return "regular"


def game_rows(record):
    game_type = classify_game_type(record["season"], record.get("game_comments", ""))
    rows = []
    for c in record["clues"]:
        value = c["value"]
        if value is None and not (c["round"] == "Final" or c["row"] is None):
            value = board_value(c["round"], c["row"], record["air_date"])
        rows.append({
            "game_id": record["game_id"],
            "air_date": record["air_date"],
            "season": record["season"],
            "game_type": game_type,
            "round": _ROUND_FULL.get(c["round"], c["round"]),
            "category": c["category"],
            "clue_value": value,
            "row": c["row"],
            "column": c["col"],
            "is_daily_double": c["is_daily_double"],
            "dd_wager": c["dd_wager"],
            "clue": c["clue"],
            "answer": c["answer"],
        })
    return rows


def run_build():
    rows = []
    with config.JSONL_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.extend(game_rows(json.loads(line)))
    df = pd.DataFrame(rows)
    df["air_date"] = pd.to_datetime(df["air_date"])
    config.PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.PARQUET_PATH, compression="zstd", index=False)
    print(f"Wrote {len(df):,} clues to {config.PARQUET_PATH}")

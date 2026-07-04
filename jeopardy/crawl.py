"""Resumable orchestration: seasons -> games -> games.jsonl."""
import json
import re

from jeopardy import config
from jeopardy.fetch import fetch
from jeopardy.parse import parse_game

_SEASON_RE = re.compile(r"showseason\.php\?season=([0-9a-z]+)")
_GAME_RE = re.compile(r"showgame\.php\?game_id=(\d+)")


def parse_season_ids(listseasons_html):
    seen, out = set(), []
    for m in _SEASON_RE.finditer(listseasons_html):
        sid = m.group(1)
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def parse_game_ids(season_html):
    seen, out = set(), []
    for m in _GAME_RE.finditer(season_html):
        gid = int(m.group(1))
        if gid not in seen:
            seen.add(gid)
            out.append(gid)
    return out


def existing_game_ids(jsonl_path):
    if not jsonl_path.exists():
        return set()
    ids = set()
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                ids.add(json.loads(line)["game_id"])
    return ids


def run_crawl():
    config.JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    done = existing_game_ids(config.JSONL_PATH)
    print(f"Resuming: {len(done)} games already scraped.")

    seasons_html = fetch(f"{config.BASE_URL}/listseasons.php", "listseasons")
    season_ids = parse_season_ids(seasons_html)
    print(f"Found {len(season_ids)} seasons.")

    with config.JSONL_PATH.open("a") as out:
        for sid in season_ids:
            season_html = fetch(
                f"{config.BASE_URL}/showseason.php?season={sid}", f"season_{sid}"
            )
            game_ids = parse_game_ids(season_html)
            print(f"Season {sid}: {len(game_ids)} games.")
            for gid in game_ids:
                if gid in done:
                    continue
                html = fetch(
                    f"{config.BASE_URL}/showgame.php?game_id={gid}", f"game_{gid}"
                )
                record = parse_game(html)
                if record is None:
                    done.add(gid)
                    continue
                record["game_id"] = gid
                record["season"] = sid
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                done.add(gid)
    print(f"Done. {len(done)} games total.")

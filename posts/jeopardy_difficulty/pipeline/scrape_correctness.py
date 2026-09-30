"""Parse J-Archive game HTML to extract per-clue contestant response counts."""
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

_CID_RE = re.compile(r"clue_(J|DJ)_(\d+)_(\d+)$")
_ROUND_FULL = {"J": "Jeopardy", "DJ": "Double Jeopardy"}
_TRIPLE_STUMPER = "Triple Stumper"


def _parse_response(rtd):
    right_cells = rtd.find_all("td", class_="right")
    wrong_cells = rtd.find_all("td", class_="wrong")
    wrong_names = [td.get_text(strip=True) for td in wrong_cells]
    is_triple_stumper = _TRIPLE_STUMPER in wrong_names
    n_right = len(right_cells)
    n_wrong = sum(1 for name in wrong_names if name != _TRIPLE_STUMPER)
    return n_right, n_wrong, is_triple_stumper


def parse_game_correctness(html: str, game_id: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []

    for prefix, div_id in [("J", "jeopardy_round"), ("DJ", "double_jeopardy_round")]:
        round_div = soup.find("div", id=div_id)
        if round_div is None:
            continue
        for cell in round_div.find_all("td", class_="clue"):
            ctd = cell.find("td", id=_CID_RE)
            if ctd is None:
                continue
            m = _CID_RE.search(ctd["id"])
            col, row = int(m.group(2)), int(m.group(3))
            rtd = cell.find("td", id=ctd["id"] + "_r")
            if rtd is None:
                continue
            n_right, n_wrong, is_ts = _parse_response(rtd)
            rows.append({
                "game_id": game_id,
                "round": _ROUND_FULL[prefix],
                "row": float(row),
                "column": float(col),
                "n_right": n_right,
                "n_wrong": n_wrong,
                "is_triple_stumper": is_ts,
            })

    fj_div = soup.find("div", id="final_jeopardy_round")
    if fj_div is not None:
        rtd = fj_div.find("td", id="clue_FJ_r")
        if rtd is not None:
            n_right, n_wrong, is_ts = _parse_response(rtd)
            rows.append({
                "game_id": game_id,
                "round": "Final",
                "row": float("nan"),
                "column": float("nan"),
                "n_right": n_right,
                "n_wrong": n_wrong,
                "is_triple_stumper": is_ts,
            })

    return rows


def run_scrape(cache_dir: Path, clues_parquet: Path, out_path: Path) -> None:
    clues = pd.read_parquet(clues_parquet, columns=["game_id"])
    game_ids = clues["game_id"].unique()
    print(f"Scraping correctness for {len(game_ids):,} games...")

    all_rows = []
    for i, game_id in enumerate(sorted(game_ids)):
        cache_file = cache_dir / f"game_{game_id}.html"
        if not cache_file.exists():
            continue
        html = cache_file.read_text()
        all_rows.extend(parse_game_correctness(html, int(game_id)))
        if (i + 1) % 500 == 0:
            print(f"  {i+1:,}/{len(game_ids):,}")

    df = pd.DataFrame(all_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, compression="zstd", index=False)
    print(f"Wrote {len(df):,} rows to {out_path}")


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parents[3]
    run_scrape(
        cache_dir=ROOT / "jeopardy" / "data" / "html_cache",
        clues_parquet=ROOT / "posts" / "jeopardy_ds" / "clues.parquet",
        out_path=Path(__file__).parent.parent / "correctness.parquet",
    )

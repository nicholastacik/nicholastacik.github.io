"""Turn a cached j-archive game page into a faithful per-game record."""
import html as _html
import re
from bs4 import BeautifulSoup

_TITLE_RE = re.compile(r"Show #(\d+),\s*aired\s*(\d{4}-\d{2}-\d{2})")
_CID_RE = re.compile(r"clue_(J|DJ)_(\d+)_(\d+)$")
_ROUND_DIVS = [("J", "jeopardy_round"), ("DJ", "double_jeopardy_round")]


def parse_game(page_html):
    """Parse a game page. Returns None if the page has no game (unaired/missing)."""
    soup = BeautifulSoup(page_html, "lxml")
    if soup.find("div", id="game_title") is None:
        return None

    show_number = None
    air_date = None
    title = soup.find("title")
    if title:
        m = _TITLE_RE.search(title.get_text())
        if m:
            show_number = int(m.group(1))
            air_date = m.group(2)

    comments_div = soup.find("div", id="game_comments")
    game_comments = comments_div.get_text(" ", strip=True) if comments_div else ""

    clues = []
    clues += _parse_board_clues(soup)
    clues += _parse_final_clue(soup)

    return {
        "show_number": show_number,
        "air_date": air_date,
        "game_comments": game_comments,
        "clues": clues,
    }


def _parse_board_clues(soup):
    clues = []
    for round_, div_id in _ROUND_DIVS:
        round_div = soup.find("div", id=div_id)
        if round_div is None:
            continue
        categories = [
            _html.unescape(td.get_text(" ", strip=True))
            for td in round_div.find_all("td", class_="category_name")
        ]
        for cell in round_div.find_all("td", class_="clue"):
            ctd = cell.find("td", class_="clue_text", id=_CID_RE)
            if ctd is None:
                continue  # unrevealed / empty cell
            clue_text = ctd.get_text(" ", strip=True)
            if not clue_text:
                continue
            m = _CID_RE.search(ctd["id"])
            col, row = int(m.group(2)), int(m.group(3))

            rtd = cell.find("td", id=ctd["id"] + "_r")
            answer = None
            if rtd is not None:
                em = rtd.find("em", class_="correct_response")
                if em is not None:
                    answer = em.get_text(" ", strip=True)

            value, is_dd, dd_wager = _parse_value_cell(cell)
            order_number = _parse_order(cell)
            category = categories[col - 1] if col - 1 < len(categories) else None

            clues.append({
                "round": round_, "row": row, "col": col, "category": category,
                "value": value, "is_daily_double": is_dd, "dd_wager": dd_wager,
                "clue": clue_text, "answer": answer, "order_number": order_number,
            })
    return clues


def _parse_value_cell(cell):
    """Return (value:int|None, is_daily_double:bool, dd_wager:int|None)."""
    val_td = cell.find("td", class_="clue_value")
    if val_td is not None:
        digits = re.sub(r"[^\d]", "", val_td.get_text())
        return (int(digits) if digits else None), False, None
    dd_td = cell.find("td", class_="clue_value_daily_double")
    if dd_td is not None:
        digits = re.sub(r"[^\d]", "", dd_td.get_text())
        return None, True, (int(digits) if digits else None)
    return None, False, None


def _parse_order(cell):
    order_td = cell.find("td", class_="clue_order_number")
    if order_td is None:
        return None
    text = order_td.get_text(strip=True)
    return int(text) if text.isdigit() else None


def _parse_final_clue(soup):
    return []  # implemented in Task 4

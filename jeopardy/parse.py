"""Turn a cached j-archive game page into a faithful per-game record."""
import re
from bs4 import BeautifulSoup

_TITLE_RE = re.compile(r"Show #(\d+),\s*aired\s*(\d{4}-\d{2}-\d{2})")


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
    return []  # implemented in Task 3


def _parse_final_clue(soup):
    return []  # implemented in Task 4

"""Render a small, fixed research page for the jsdom Practice-mode harness.

Builds tiny fixture DataFrames, runs them through the REAL build_research_data +
render_html, and prints the self-contained HTML to stdout. Run as:
    uv run --frozen --group analysis python -m jeopardy.tests.browser.render_fixture
"""
import pandas as pd

from jeopardy.analysis.research import build_research_data, render_html

# Two topics; era 2010 only, so the page's currentEra defaults to 2010.
_LABELS = {1: "Topic Alpha", 2: "Topic Beta"}


def _tokens_df():
    return pd.DataFrame([
        {"era": 2010, "cluster_id": 1, "rank": 1, "phrase": "Alpha One", "count": 10},
        {"era": 2010, "cluster_id": 1, "rank": 2, "phrase": "Alpha Two", "count": 8},
        {"era": 2010, "cluster_id": 2, "rank": 1, "phrase": "Beta One", "count": 6},
    ])


def _eras_df():
    return pd.DataFrame([
        {"era": 2010, "cluster_id": 1, "size": 100, "share": 0.05, "n_qualifying_phrases": 2},
        {"era": 2010, "cluster_id": 2, "size": 50, "share": 0.02, "n_qualifying_phrases": 1},
    ])


def _quiz_refs_df():
    # 'dup' is referenced in both the general pool and an entity -> must dedupe to one card.
    # 'old' is pre-2010 -> excluded by the era filter at runtime (era 2010).
    return pd.DataFrame([
        {"cluster_id": 1, "phrase": None, "clue_ids": ["g1", "g2", "dup"]},
        {"cluster_id": 1, "phrase": "Alpha One", "clue_ids": ["a1", "dup"]},
        {"cluster_id": 1, "phrase": "Alpha Two", "clue_ids": ["a2", "old"]},
        {"cluster_id": 2, "phrase": None, "clue_ids": ["b1", "b2"]},
    ])


def _clues_df():
    rows = [("g1", 2011), ("g2", 2012), ("dup", 2013), ("a1", 2014),
            ("a2", 2015), ("old", 2005), ("b1", 2016), ("b2", 2017)]
    return pd.DataFrame([
        {"clue_id": cid, "clue": f"Clue text for {cid}", "answer": f"Answer {cid}",
         "year": yr, "category": "FIXTURE CATEGORY", "game_id": 1000 + i}
        for i, (cid, yr) in enumerate(rows)
    ])


def build_fixture_data():
    return build_research_data(_tokens_df(), _eras_df(), _LABELS,
                               fingerprints_df=None, quiz_refs_df=_quiz_refs_df(),
                               clues_df=_clues_df())


def build_fixture_html():
    return render_html(build_fixture_data())


if __name__ == "__main__":
    print(build_fixture_html())

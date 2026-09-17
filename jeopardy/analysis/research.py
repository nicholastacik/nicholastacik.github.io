"""Generate the interactive research tool (type -> entities -> live Wikipedia facts)."""
import json
from pathlib import Path

import pandas as pd

from jeopardy import config

_PRACTICE_JS_PATH = Path(__file__).resolve().parent / "practice.js"


def _practice_js() -> str:
    src = _PRACTICE_JS_PATH.read_text(encoding="utf-8")
    # Strip ES-module export lines so the declarations inline as page-level globals.
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("export "))


def build_research_data(tokens_df, eras_df, labels, fingerprints_df=None, quiz_refs_df=None, clues_df=None):
    """Per-era, per-type entity data for the research page.

    Returns {"eras": [...], "byEra": {"<era>": [ {cluster_id, name, applicability,
    prevalence, entities:[{phrase,count}]} sorted by applicability desc ]}}.
    Entities arrive count-sorted via `rank`; applicability is `n_qualifying_phrases`;
    prevalence is `share`.
    """
    eras = sorted(eras_df["era"].unique())
    by_era = {}
    for era in eras:
        tokens_era = tokens_df[tokens_df["era"] == era]
        stats_era = eras_df[eras_df["era"] == era].set_index("cluster_id")
        entries = []
        for cluster_id, name in labels.items():
            rows = tokens_era[tokens_era["cluster_id"] == cluster_id].sort_values("rank")
            stat = stats_era.loc[cluster_id] if cluster_id in stats_era.index else None
            entries.append({
                "cluster_id": int(cluster_id),
                "name": name,
                "applicability": int(stat["n_qualifying_phrases"]) if stat is not None else 0,
                "prevalence": float(stat["share"]) if stat is not None else 0.0,
                "entities": [
                    {"phrase": r["phrase"], "count": int(r["count"])}
                    for _, r in rows.iterrows()
                    if r["phrase"] is not None and pd.notna(r["phrase"])
                ],
            })
        entries.sort(key=lambda d: d["applicability"], reverse=True)
        by_era[str(int(era))] = entries
    def _clean_cue(c):
        out = {"term": c["term"], "support": int(c["support"]), "total": int(c["total"])}
        g = c.get("gloss")
        if g is not None and not (isinstance(g, float) and pd.isna(g)) and str(g).strip():
            out["gloss"] = str(g)
        return out

    fingerprints = {}
    if fingerprints_df is not None:
        for _, r in fingerprints_df.iterrows():
            fingerprints.setdefault(str(int(r["cluster_id"])), {})[r["phrase"]] = {
                "cues": [_clean_cue(c) for c in r["cues"]], "exampleClueIds": list(r["example_clue_ids"])}
    quiz = {}
    if quiz_refs_df is not None:
        for _, r in quiz_refs_df.iterrows():
            key = "" if (r["phrase"] is None or pd.isna(r["phrase"])) else r["phrase"]
            quiz.setdefault(str(int(r["cluster_id"])), {})[key] = list(r["clue_ids"])
    referenced = set()
    for byphrase in fingerprints.values():
        for v in byphrase.values():
            referenced.update(v["exampleClueIds"])
    for byphrase in quiz.values():
        for ids in byphrase.values():
            referenced.update(ids)
    clues = {}
    if clues_df is not None:
        for _, r in clues_df[clues_df["clue_id"].isin(referenced)].iterrows():
            clues[r["clue_id"]] = {"clue": r["clue"], "answer": r["answer"], "year": int(r["year"]),
                                   "category": r["category"], "game_id": int(r["game_id"])}
    return {"eras": [int(e) for e in eras], "byEra": by_era,
            "fingerprints": fingerprints, "quiz": quiz, "clues": clues,
            "jarchive": config.JARCHIVE_GAME_URL}


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Board &mdash; A Jeopardy! Category Field Guide</title>
<style>
  :root {
    --ink: #0b1640;
    --panel: #121f52;
    --panel-2: #1a2c68;
    --gold: #e8b923;
    --gold-dim: #a9821f;
    --paper: #f4f1e6;
    --ash: #8a93be;
    --brick: #d6614a;
    --line: #263572;
    --radius: 3px;
    --display: Haettenschweiler, "Arial Narrow Bold", "Franklin Gothic Bold", Impact, sans-serif;
    --body: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  * { box-sizing: border-box; }

  html, body {
    margin: 0;
    padding: 0;
    background: var(--ink);
    color: var(--paper);
    font-family: var(--body);
    min-height: 100%;
  }

  a { color: var(--gold); }
  a:hover { color: var(--paper); }

  button {
    font: inherit;
    color: inherit;
  }

  :focus-visible {
    outline: 2px solid var(--gold);
    outline-offset: 2px;
  }

  .topbar {
    padding: 28px clamp(16px, 4vw, 48px) 22px;
    border-bottom: 1px solid var(--line);
    background: linear-gradient(180deg, #0d1a4c, var(--ink));
  }

  .topbar .eyebrow {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--gold);
    margin: 0 0 8px;
  }

  .topbar h1 {
    font-family: var(--display);
    font-weight: 400;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: clamp(30px, 5vw, 46px);
    margin: 0 0 10px;
    line-height: 1;
  }

  .topbar p {
    max-width: 62ch;
    margin: 0;
    color: var(--ash);
    font-size: 15px;
    line-height: 1.5;
  }

  .era-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    padding: 14px clamp(16px, 4vw, 48px);
    background: var(--panel);
    border-bottom: 1px solid var(--line);
  }

  .era-bar-label {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ash);
    flex: none;
  }

  .era-toggle {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .era-pill {
    font-family: var(--mono);
    font-size: 12.5px;
    letter-spacing: 0.03em;
    background: var(--panel-2);
    border: 1px solid var(--line);
    color: var(--ash);
    border-radius: var(--radius);
    padding: 6px 14px;
    cursor: pointer;
  }

  .era-pill:hover { color: var(--paper); border-color: var(--gold-dim); }

  .era-pill.active {
    background: var(--gold);
    border-color: var(--gold);
    color: var(--ink);
    font-weight: 600;
  }

  .layout {
    display: grid;
    grid-template-columns: 280px 1fr 380px;
    grid-template-areas: "side main detail";
    min-height: calc(100vh - 220px);
  }

  .side {
    grid-area: side;
    border-right: 1px solid var(--line);
    background: #0e1a4a;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .side-head {
    padding: 14px;
    border-bottom: 1px solid var(--line);
  }

  #filter-input {
    width: 100%;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    color: var(--paper);
    padding: 9px 10px;
    font-family: var(--body);
    font-size: 13px;
  }

  #filter-input::placeholder { color: var(--ash); }

  .side-list {
    overflow-y: auto;
    padding: 6px;
  }

  .side-item {
    display: block;
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: var(--radius);
    padding: 10px 12px;
    margin-bottom: 2px;
    cursor: pointer;
  }

  .side-item:hover { background: var(--panel); }

  .side-item.active {
    background: var(--panel-2);
    border-left-color: var(--gold);
  }

  .side-item .name {
    font-family: var(--display);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    font-size: 15px;
    display: block;
  }

  .side-item .meta {
    display: block;
    margin-top: 3px;
  }

  .side-item .meta .stat {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ash);
    display: block;
  }

  .side-item.dim { opacity: 0.45; }
  .side-item.dim .meta .stat { color: var(--brick); }

  .prevalence {
    display: block;
    height: 3px;
    margin-top: 5px;
    background: var(--line);
    border-radius: 2px;
    overflow: hidden;
  }

  .prevalence-fill {
    display: block;
    height: 100%;
    background: var(--gold-dim);
  }

  .side-item.active .prevalence-fill { background: var(--gold); }

  .side-empty {
    padding: 16px 14px;
    color: var(--ash);
    font-size: 13px;
  }

  .main {
    grid-area: main;
    padding: clamp(16px, 3vw, 32px);
    overflow-y: auto;
    border-right: 1px solid var(--line);
    min-height: 0;
  }

  .placeholder {
    color: var(--ash);
    font-size: 14px;
    max-width: 46ch;
    line-height: 1.6;
    margin-top: 40px;
  }

  .main-head h2 {
    font-family: var(--display);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    font-size: clamp(24px, 3vw, 32px);
    margin: 0 0 6px;
  }

  .main-head .sub {
    color: var(--ash);
    font-size: 13px;
    font-family: var(--mono);
    margin: 0 0 20px;
  }

  .sample-box { margin: 0 0 22px; }
  .sample-clue-btn, .reveal-answer-btn {
    font-family: var(--mono); font-size: 12px; letter-spacing: 0.04em;
    text-transform: uppercase; background: var(--panel-2); border: 1px solid var(--gold-dim);
    color: var(--gold); border-radius: var(--radius); padding: 8px 14px; cursor: pointer;
  }
  .sample-clue-btn:hover, .reveal-answer-btn:hover { color: var(--paper); border-color: var(--gold); }
  .sample-card {
    margin-top: 12px; padding: 14px 16px; background: var(--panel);
    border: 1px solid var(--line); border-left: 3px solid var(--gold); border-radius: var(--radius);
  }
  .sample-card .clue-text { font-size: 15px; line-height: 1.55; margin: 0 0 12px; }
  .sample-card .scope { font-family: var(--mono); font-size: 11px; color: var(--ash); margin: 0 0 8px; }
  .sample-card .answer-text { font-size: 15px; color: var(--gold); margin: 10px 0 0; }

  .fingerprint { margin: 0 0 18px; }
  .fingerprint .eyebrow { color: var(--gold); }
  .cue-chip { display: inline-block; font-family: var(--mono); font-size: 11px; background: var(--panel-2);
    border: 1px solid var(--line); border-radius: var(--radius); padding: 3px 8px; margin: 0 6px 6px 0;
    cursor: pointer; }
  .cue-chip:hover { border-color: var(--gold-dim); color: var(--paper); }
  .cue-chip.active { border-color: var(--gold); background: var(--panel); color: var(--paper); }
  .cue-plain { cursor: default; }
  .cue-plain:hover { border-color: var(--line); color: inherit; }
  .cue-chip .support { color: var(--ash); }
  .cue-why { margin: 2px 0 14px; font-size: 13px; line-height: 1.55; color: var(--paper); }
  .cue-why .fallback { color: var(--ash); }
  .fp-label { cursor: pointer; }
  .fp-info { color: var(--ash); font-size: 10px; vertical-align: super; }
  .fp-help { color: var(--ash); font-size: 12px; line-height: 1.5; margin: 2px 0 12px; max-width: 46ch; }
  .fp-none { color: var(--ash); font-size: 13px; font-style: italic; margin: 4px 0 10px; }
  .fp-clue { border-left: 3px solid var(--gold); padding: 8px 12px; margin: 8px 0; background: var(--panel); }
  .fp-clue .meta { font-family: var(--mono); font-size: 11px; color: var(--ash); }

  .tag-brick {
    display: inline-block;
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--brick);
    border: 1px solid var(--brick);
    border-radius: var(--radius);
    padding: 2px 7px;
    margin-bottom: 16px;
  }

  .entity-list {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .entity-row {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    background: var(--panel);
    border: 1px solid var(--line);
    border-left: 3px solid transparent;
    border-radius: var(--radius);
    padding: 11px 14px;
    margin-bottom: 6px;
    cursor: pointer;
    text-align: left;
  }

  .entity-row:hover { background: var(--panel-2); }

  .entity-row.active {
    border-left-color: var(--gold);
    background: var(--panel-2);
  }

  .entity-row .rank {
    font-family: var(--mono);
    color: var(--ash);
    font-size: 12px;
    width: 2.2em;
    flex: none;
  }

  .entity-row .phrase {
    flex: 1;
    font-size: 15px;
  }

  .entity-row .count {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--ink);
    background: var(--gold);
    border-radius: var(--radius);
    padding: 3px 8px;
    flex: none;
  }

  .detail {
    grid-area: detail;
    padding: clamp(16px, 3vw, 28px);
    overflow-y: auto;
    min-height: 0;
  }

  .detail .eyebrow {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--gold);
    margin: 0 0 12px;
  }

  .detail h3 {
    font-size: 20px;
    margin: 0 0 12px;
    line-height: 1.3;
  }

  .detail img {
    max-width: 100%;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    margin-bottom: 14px;
    display: block;
  }

  .detail .extract {
    font-size: 14px;
    line-height: 1.65;
    color: var(--paper);
    margin: 0 0 16px;
  }

  .detail .fallback {
    color: var(--ash);
    font-size: 14px;
    line-height: 1.6;
  }

  .pulse {
    color: var(--ash);
    font-size: 14px;
  }

  @media (prefers-reduced-motion: no-preference) {
    .pulse { animation: pulse 1.2s ease-in-out infinite; }
    .detail.flash { animation: flash 0.5s ease-out; }
  }

  @keyframes pulse {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1; }
  }

  @keyframes flash {
    0% { box-shadow: inset 0 0 0 2px var(--gold); }
    100% { box-shadow: inset 0 0 0 0 transparent; }
  }

  .footer {
    padding: 16px clamp(16px, 4vw, 48px) 26px;
    border-top: 1px solid var(--line);
    color: var(--ash);
    font-family: var(--mono);
    font-size: 11.5px;
    line-height: 1.6;
    max-width: 90ch;
  }

  @media (max-width: 980px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-areas: "side" "main" "detail";
    }
    .side {
      border-right: none;
      border-bottom: 1px solid var(--line);
      max-height: 260px;
    }
    .main { border-right: none; }
  }

  .practice-open {
    margin-left: auto;
    font-family: var(--mono); font-size: 12.5px; letter-spacing: 0.03em;
    background: var(--gold); border: 1px solid var(--gold); color: var(--ink);
    font-weight: 600; border-radius: var(--radius); padding: 6px 16px; cursor: pointer;
  }
  .practice-open:hover { background: var(--paper); border-color: var(--paper); }
  .practice-overlay {
    position: fixed; inset: 0; z-index: 50; background: rgba(6, 12, 38, 0.96);
    display: flex; align-items: flex-start; justify-content: center; overflow-y: auto;
  }
  .practice-overlay[hidden] { display: none; }
  .practice-inner {
    width: min(680px, 100%); margin: clamp(16px, 5vh, 64px) 16px;
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: clamp(18px, 3vw, 30px);
  }
  .practice-head { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
  .practice-exit {
    font-family: var(--mono); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em;
    background: var(--panel-2); border: 1px solid var(--line); color: var(--ash);
    border-radius: var(--radius); padding: 6px 12px; cursor: pointer;
  }
  .practice-exit:hover { color: var(--paper); border-color: var(--gold-dim); }
  .practice-progress { font-family: var(--mono); font-size: 12px; color: var(--ash); }
  .practice-tally { font-family: var(--mono); font-size: 12px; color: var(--gold); margin-left: auto; }
  .practice-notice {
    margin-bottom: 14px; padding: 8px 12px; border: 1px solid var(--brick);
    border-radius: var(--radius); color: var(--brick); font-size: 13px;
  }
  .practice-title { font-family: var(--display); text-transform: uppercase; letter-spacing: 0.03em; font-size: 26px; margin: 0 0 6px; }
  .practice-sub { color: var(--ash); font-family: var(--mono); font-size: 12px; margin: 0 0 18px; }
  .practice-topics { display: flex; flex-direction: column; gap: 4px; max-height: 40vh; overflow-y: auto; margin-bottom: 18px; }
  .ptopic { font-size: 14px; cursor: pointer; }
  .practice-opts { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; font-size: 14px; }
  .popt-label { font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ash); }
  .pextra { display: block; font-size: 14px; margin-bottom: 18px; cursor: pointer; }
  .pextra-note { color: var(--ash); font-size: 12px; }
  .practice-actions { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
  .practice-start {
    font-family: var(--mono); font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase;
    background: var(--gold); border: 1px solid var(--gold); color: var(--ink); font-weight: 600;
    border-radius: var(--radius); padding: 9px 18px; cursor: pointer;
  }
  .practice-start:hover { background: var(--paper); border-color: var(--paper); }
  .practice-start:disabled { opacity: 0.45; cursor: not-allowed; }
  .practice-start:disabled:hover { background: var(--gold); border-color: var(--gold); }
  .practice-startnote { color: var(--brick); font-size: 13px; }
  .practice-reset {
    font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em;
    background: transparent; border: 1px solid var(--line); color: var(--ash);
    border-radius: var(--radius); padding: 6px 12px; cursor: pointer;
  }
  .practice-reset:hover { color: var(--brick); border-color: var(--brick); }
  .pcard-scope { font-family: var(--mono); font-size: 11px; color: var(--ash); margin: 0 0 10px; }
  .pcard-clue { font-size: 18px; line-height: 1.5; margin: 0 0 18px; }
  .pcard-answer { font-size: 16px; color: var(--gold); margin: 0 0 16px; }
  .pcard-grades { display: flex; gap: 10px; flex-wrap: wrap; }
  .pgrade {
    font-size: 14px; background: var(--panel-2); border: 1px solid var(--line); color: var(--paper);
    border-radius: var(--radius); padding: 10px 16px; cursor: pointer;
  }
  .pgrade:hover { border-color: var(--gold); }
  .pgrade span { font-family: var(--mono); font-size: 11px; color: var(--ash); margin-left: 6px; }
  .psummary-tally { font-size: 16px; margin: 0 0 8px; }
  .psummary-sched { color: var(--ash); font-size: 14px; margin: 0 0 18px; }
</style>
</head>
<body>
  <header class="topbar">
    <p class="eyebrow">Field notes for trivia prep</p>
    <h1>The Board</h1>
    <p>50 Jeopardy! category clusters, ranked by how deep you can actually study them.
       Pick a study window to see what dominated the board then, drill into its most recurring
       entities, and pull live facts from Wikipedia. A type's <em>recurring entities</em> count is
       how many distinct people, places &amp; things come up 5+ times across its clues and answers
       &mdash; a rough, exploratory signal of how studyable a type is, not a precise payoff score.</p>
  </header>
  <div class="era-bar" role="group" aria-label="Study era">
    <span class="era-bar-label">Study window (cumulative)</span>
    <div id="era-toggle" class="era-toggle"></div>
    <button type="button" id="practice-open" class="practice-open">Practice &#9654;</button>
  </div>
  <div class="layout">
    <aside class="side" aria-label="Categories">
      <div class="side-head">
        <input id="filter-input" type="search" placeholder="Filter categories&hellip;" aria-label="Filter categories">
      </div>
      <div id="side-list" class="side-list" role="list"></div>
    </aside>
    <main id="main-panel" class="main" aria-label="Ranked entities"></main>
    <section id="detail-panel" class="detail" aria-label="Wikipedia facts"></section>
  </div>
  <div id="practice" class="practice-overlay" role="dialog" aria-modal="true" aria-label="Practice session" hidden>
    <div class="practice-inner">
      <header class="practice-head">
        <button type="button" id="practice-exit" class="practice-exit">Exit</button>
        <span id="practice-progress" class="practice-progress"></span>
        <span id="practice-tally" class="practice-tally"></span>
      </header>
      <div id="practice-notice" class="practice-notice" hidden></div>
      <div id="practice-body" class="practice-body"></div>
    </div>
  </div>
  <footer class="footer">
    Categories mined from j-archive.com box scores; ranked entities are the phrases that keep
    reappearing as answers within a cluster. Wikipedia facts are fetched live in your browser on
    each click &mdash; nothing here is cached, curated, or fact-checked.
  </footer>
  <script>__PRACTICE_JS__</script>
  <script>
    const DATA = __DATA_JSON__;

    (function () {
      const sideList = document.getElementById('side-list');
      const filterInput = document.getElementById('filter-input');
      const mainPanel = document.getElementById('main-panel');
      const detailPanel = document.getElementById('detail-panel');
      const eraToggle = document.getElementById('era-toggle');
      const wikiCache = new Map();
      let activeCueBtn = null;

      function showCueGloss(gloss, btn) {
        const slot = document.getElementById('cue-why');
        if (!slot) return;
        if (activeCueBtn === btn) {
          btn.classList.remove('active'); activeCueBtn = null; slot.innerHTML = ''; return;
        }
        if (activeCueBtn) activeCueBtn.classList.remove('active');
        activeCueBtn = btn; btn.classList.add('active');
        slot.innerHTML = '<div class="cue-why"><p>' + escapeHtml(gloss) + '</p></div>';
      }

      let currentEra = DATA.eras.includes(2010) ? 2010 : DATA.eras[0];
      let selectedTypeId = null;
      let selectedEntity = null;
      let lastSampleClue = null;

      function currentList() {
        return DATA.byEra[String(currentEra)] || [];
      }

      function maxPrevalence(list) {
        return Math.max(0.0001, ...list.map(d => d.prevalence));
      }

      function pctLabel(prevalence) {
        const pct = prevalence * 100;
        return (pct >= 10 ? pct.toFixed(0) : pct.toFixed(1)) + '%';
      }

      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
      }

      async function fetchWiki(phrase) {
        const REST = t => `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(t)}?redirect=true`;
        try {
          let r = await fetch(REST(phrase));
          if (r.ok) {
            const j = await r.json();
            if (j.type !== 'disambiguation' && j.extract) return j;
          }
          const s = await fetch(`https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(phrase)}&format=json&origin=*`);
          if (s.ok) {
            const hit = (await s.json())?.query?.search?.[0];
            if (hit) {
              const r2 = await fetch(REST(hit.title));
              if (r2.ok) { const j2 = await r2.json(); if (j2.extract) return j2; }
            }
          }
        } catch (e) { /* fall through to null */ }
        return null;
      }

      function renderEraToggle() {
        eraToggle.innerHTML = '';
        for (const era of DATA.eras) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'era-pill' + (era === currentEra ? ' active' : '');
          btn.setAttribute('aria-pressed', era === currentEra ? 'true' : 'false');
          btn.textContent = (era === DATA.eras[0]) ? 'All-time' : ('Since ' + era);
          btn.addEventListener('click', () => selectEra(era));
          eraToggle.appendChild(btn);
        }
      }

      function selectEra(era) {
        if (era === currentEra) return;
        currentEra = era;
        selectedEntity = null;
        renderEraToggle();
        renderSide(filterInput.value);
        renderMain();
        renderDetailEmpty();
      }

      function renderSide(filterText) {
        const q = (filterText || '').trim().toLowerCase();
        const list = currentList();
        const maxShare = maxPrevalence(list);
        sideList.innerHTML = '';
        const filtered = list.filter(d => d.name.toLowerCase().includes(q));
        if (!filtered.length) {
          const empty = document.createElement('div');
          empty.className = 'side-empty';
          empty.textContent = 'No categories match that filter.';
          sideList.appendChild(empty);
          return;
        }
        for (const d of filtered) {
          const studyable = d.entities.length > 0;
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'side-item' + (!studyable ? ' dim' : '') +
            (selectedTypeId === d.cluster_id ? ' active' : '');
          btn.setAttribute('role', 'listitem');
          const barPct = Math.max(4, (d.prevalence / maxShare) * 100);
          const metaHtml = studyable
            ? `<span class="stat">${d.applicability} recurring entities &middot; ${pctLabel(d.prevalence)} of board</span>` +
              `<span class="prevalence"><span class="prevalence-fill" style="width:${barPct}%"></span></span>`
            : '<span class="stat">not really studyable</span>';
          btn.innerHTML = `<span class="name">${escapeHtml(d.name)}</span>` +
            `<span class="meta">${metaHtml}</span>`;
          btn.addEventListener('click', () => selectType(d.cluster_id));
          sideList.appendChild(btn);
        }
      }

      function selectType(clusterId) {
        selectedTypeId = clusterId;
        selectedEntity = null;
        renderSide(filterInput.value);
        renderMain();
        renderDetailEmpty();
      }

      function renderMain() {
        const d = selectedTypeId != null
          ? currentList().find(x => x.cluster_id === selectedTypeId)
          : null;
        if (!d) {
          mainPanel.innerHTML = '<p class="placeholder">Select a category from the left to see its most recurring entities.</p>';
          return;
        }
        let html = `<div class="main-head"><h2>${escapeHtml(d.name)}</h2>` +
          `<p class="sub">${d.applicability} recurring entities &middot; ${pctLabel(d.prevalence)} of categories in this window</p></div>`;
        const hasSamples = !!(DATA.quiz && DATA.quiz[String(d.cluster_id)]);
        if (hasSamples) {
          html += '<div class="sample-box" id="sample-box">' +
            '<button type="button" class="sample-clue-btn" id="sample-clue-btn">Sample clue &#9860;</button>' +
            '<div id="sample-card"></div></div>';
        }
        if (!d.entities.length) {
          html += '<span class="tag-brick">Not really studyable</span>' +
            '<p class="placeholder">This cluster didn\\'t turn up enough repeating answers to study directly ' +
            '&mdash; treat it as a grab-bag and review its categories individually.</p>';
          mainPanel.innerHTML = html;
          wireSampleButton(d.cluster_id);
          return;
        }
        html += '<ul class="entity-list">';
        d.entities.forEach((e, i) => {
          const active = selectedEntity === e ? ' active' : '';
          html += `<li><button type="button" class="entity-row${active}" data-idx="${i}">` +
            `<span class="rank">${i + 1}</span>` +
            `<span class="phrase">${escapeHtml(e.phrase)}</span>` +
            `<span class="count">${e.count}&times;</span>` +
            `</button></li>`;
        });
        html += '</ul>';
        mainPanel.innerHTML = html;
        wireSampleButton(d.cluster_id);
        mainPanel.querySelectorAll('.entity-row').forEach(row => {
          row.addEventListener('click', () => selectEntity(d.entities[Number(row.dataset.idx)]));
        });
      }

      function wireSampleButton(clusterId) {
        const sampleBtn = document.getElementById('sample-clue-btn');
        if (sampleBtn) sampleBtn.addEventListener('click', () => rollSampleClue(clusterId));
      }

      function clueById(id) { return DATA.clues && DATA.clues[id]; }

      function eligibleClues(clusterId) {
        const refs = (DATA.quiz && DATA.quiz[String(clusterId)]) || {};
        const toClues = ids => (ids || []).map(clueById).filter(Boolean);
        // The "any answer" pool is the deduped union of this cluster's general + every per-entity
        // ref, so un-highlighted / fallback sampling has real variety (not just the ~12 general).
        const anyClues = () => {
          const seen = new Set(), out = [];
          for (const key in refs) for (const id of refs[key]) {
            if (seen.has(id)) continue;
            seen.add(id);
            const c = clueById(id);
            if (c) out.push(c);
          }
          return out.filter(c => c.year >= currentEra);
        };
        if (selectedEntity) {
          const scoped = toClues(refs[selectedEntity.phrase]).filter(c => c.year >= currentEra);
          if (scoped.length) return { clues: scoped, scoped: true, fellBack: false };
          return { clues: anyClues(), scoped: false, fellBack: true };
        }
        return { clues: anyClues(), scoped: false, fellBack: false };
      }

      function rollSampleClue(clusterId) {
        const card = document.getElementById('sample-card');
        if (!card) return;
        const { clues, scoped, fellBack } = eligibleClues(clusterId);
        if (!clues.length) {
          const msg = fellBack
            ? 'No clue on this board has &ldquo;' + escapeHtml(selectedEntity.phrase) + '&rdquo; as its answer.'
            : 'No clue on the board for this filter.';
          card.innerHTML = '<div class="sample-card"><p class="scope">' + msg + '</p></div>';
          return;
        }
        let choices = clues;
        if (clues.length > 1 && lastSampleClue) {
          const filtered = clues.filter(c => c.clue !== lastSampleClue);
          if (filtered.length) choices = filtered;
        }
        const pick = choices[Math.floor(Math.random() * choices.length)];
        lastSampleClue = pick.clue;
        const scopeLabel = scoped
          ? 'Answer is related to &ldquo;' + escapeHtml(selectedEntity.phrase) + '&rdquo; &middot; tap the answer again to broaden'
          : (fellBack
              ? 'No clue for &ldquo;' + escapeHtml(selectedEntity.phrase) + '&rdquo; this era &mdash; showing another from this category (tap the answer again to broaden)'
              : 'Any answer in this category');
        card.innerHTML = '<div class="sample-card">' +
          '<p class="scope">' + escapeHtml(pick.category) + ' &middot; ' + pick.year + '</p>' +
          '<p class="scope">' + scopeLabel + '</p>' +
          '<p class="clue-text">' + escapeHtml(pick.clue) + '</p>' +
          '<button type="button" class="reveal-answer-btn" id="reveal-answer-btn">Reveal answer</button>' +
          '<button type="button" class="sample-clue-btn" id="another-clue-btn" style="margin-left:8px">Another</button>' +
          '<p class="answer-text" id="answer-text" hidden>' + escapeHtml(pick.answer) + '</p></div>';
        document.getElementById('reveal-answer-btn').addEventListener('click', () => {
          const a = document.getElementById('answer-text'); if (a) a.hidden = false;
        });
        document.getElementById('another-clue-btn').addEventListener('click', () => rollSampleClue(clusterId));
      }

      function renderDetailEmpty() {
        detailPanel.classList.remove('flash');
        detailPanel.innerHTML = '<p class="eyebrow">The answer</p>' +
          '<p class="placeholder">Click an answer to pull its Wikipedia summary &mdash; fetched live, right now, from your browser.</p>';
      }

      function renderFingerprint(entity) {
        activeCueBtn = null;
        const byPhrase = (DATA.fingerprints && DATA.fingerprints[String(selectedTypeId)]) || {};
        const fp = byPhrase[entity.phrase];
        let html = '<p class="eyebrow">The answer</p>' + `<h3>${escapeHtml(entity.phrase)}</h3>`;
        if (fp) {
          html += '<div class="fingerprint"><p class="eyebrow fp-label" id="fp-label" role="button" tabindex="0">' +
            'Clue Fingerprint <span class="fp-info">&#9432;</span></p>' +
            '<p id="fp-help" class="fp-help" hidden>The words Jeopardy uses most when this is the answer &mdash; ' +
            'the recurring angles worth recognizing. Counted across all years; &ldquo;N of M&rdquo; = it appeared in ' +
            'N of this answer&rsquo;s M all-time clues. Tap a cue to see why it connects.</p>';
          if (fp.cues && fp.cues.length) {
            html += fp.cues.map(c => {
              const label = escapeHtml(c.term) + ` <span class="support">&middot; ${c.support} of ${c.total}</span>`;
              return c.gloss
                ? `<button type="button" class="cue-chip" data-gloss="${escapeHtml(c.gloss)}">${label}</button>`
                : `<span class="cue-chip cue-plain">${label}</span>`;
            }).join('');
            html += '<div id="cue-why"></div>';
          } else {
            html += '<p class="fp-none">No single recurring angle &mdash; this answer gets clued many different ways.</p>';
          }
          const allExamples = (fp.exampleClueIds || []).map(clueById).filter(Boolean);
          const examples = allExamples.filter(c => c.year >= currentEra);
          const shown = examples.length ? examples : allExamples.slice(0, 1);
          if (!examples.length && allExamples.length) {
            html += '<p class="fp-none">No examples in this window; showing the newest available.</p>';
          }
          shown.slice(0, 3).forEach(c => {
            const url = escapeHtml(DATA.jarchive.replace('{game_id}', c.game_id));
            html += `<div class="fp-clue"><p class="clue-text">${escapeHtml(c.clue)}</p>` +
              `<p class="meta">${escapeHtml(c.answer)} &middot; ${escapeHtml(c.category)} &middot; ${c.year} ` +
              `&middot; <a class="j-archive" href="${url}" target="_blank" rel="noopener">J-Archive &#8599;</a></p></div>`;
          });
          html += '</div>';
        }
        html += '<div id="wiki-slot"><p class="pulse">Asking Wikipedia&hellip;</p></div>';
        detailPanel.innerHTML = html;
        const fpLabel = document.getElementById('fp-label');
        if (fpLabel) fpLabel.addEventListener('click', () => {
          const help = document.getElementById('fp-help');
          if (help) help.hidden = !help.hidden;
        });
        detailPanel.querySelectorAll('button.cue-chip').forEach(btn => {
          btn.addEventListener('click', () => showCueGloss(btn.dataset.gloss, btn));
        });
      }

      async function selectEntity(entity) {
        if (selectedEntity === entity) {
          selectedEntity = null; renderMain(); renderDetailEmpty(); return;
        }
        selectedEntity = entity;
        renderMain();
        renderFingerprint(entity);
        if (window.matchMedia('(max-width: 980px)').matches) detailPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        let summary;
        if (wikiCache.has(entity.phrase)) {
          summary = wikiCache.get(entity.phrase);
        } else {
          summary = await fetchWiki(entity.phrase);
          wikiCache.set(entity.phrase, summary);
        }
        if (selectedEntity !== entity) return;
        const slot = document.getElementById('wiki-slot');
        if (!slot) return;
        if (summary && summary.extract) {
          const thumb = summary.thumbnail && summary.thumbnail.source;
          const url = summary.content_urls && summary.content_urls.desktop && summary.content_urls.desktop.page;
          slot.innerHTML = (thumb ? `<img src="${escapeHtml(thumb)}" alt="${escapeHtml(entity.phrase)}">` : '') +
            `<p class="extract">${escapeHtml(summary.extract)}</p>` +
            (url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">Read the full article on Wikipedia &#8599;</a>` : '');
        } else {
          const s = 'https://en.wikipedia.org/w/index.php?search=' + encodeURIComponent(entity.phrase);
          slot.innerHTML = `<p class="fallback">No Wikipedia summary. <a href="${escapeHtml(s)}" target="_blank" rel="noopener">Search &#8599;</a></p>`;
        }
      }

      filterInput.addEventListener('input', () => renderSide(filterInput.value));

      // ---- Practice mode ----
      const PKEY = 'jeopardy-practice-v1';
      const practice = {
        screen: 'start', config: null, store: { v: 1, cards: {} },
        session: null, current: null, revealed: false,
        tally: { knew: 0, unsure: 0, missed: 0 }, seen: new Set(),
        saveFailed: false, returnFocus: null,
      };
      const overlay = document.getElementById('practice');
      const pBody = document.getElementById('practice-body');
      const pProgress = document.getElementById('practice-progress');
      const pTally = document.getElementById('practice-tally');
      const pNotice = document.getElementById('practice-notice');
      const bgEls = ['.topbar', '.era-bar', '.layout', '.footer']
        .map(sel => document.querySelector(sel)).filter(Boolean);
      function setBackgroundInert(on) {
        for (const el of bgEls) {
          if (on) { el.setAttribute('aria-hidden', 'true'); el.setAttribute('inert', ''); }
          else { el.removeAttribute('aria-hidden'); el.removeAttribute('inert'); }
        }
      }

      function nextCard() {
        if (!practice.session.queue.length) { renderSummary(); return; }
        practice.current = practice.session.queue[0].id;
        practice.revealed = false;
        practice.screen = 'card';
        renderCard();
      }
      function updateProgressHeader() {
        const p = sessionProgress(practice.session);
        pProgress.textContent = p.done + ' / ' + p.size + ' cards' +
          (p.retriesPending ? ' · ' + p.retriesPending + ' retr' + (p.retriesPending === 1 ? 'y' : 'ies') + ' remaining' : '');
        pTally.textContent = '✓' + practice.tally.knew + ' · ?' + practice.tally.unsure + ' · ✗' + practice.tally.missed;
      }
      function renderCard() {
        updateProgressHeader();
        const c = clueById(practice.current);
        let html = '<div class="pcard"><p class="pcard-scope">' + escapeHtml(c.category) + ' · ' + c.year + '</p>' +
          '<p class="pcard-clue">' + escapeHtml(c.clue) + '</p>';
        if (!practice.revealed) {
          html += '<button type="button" id="pcard-reveal" class="practice-start">Reveal</button>';
        } else {
          const url = escapeHtml(DATA.jarchive.replace('{game_id}', c.game_id));
          html += '<p class="pcard-answer">' + escapeHtml(c.answer) +
            ' · <a href="' + url + '" target="_blank" rel="noopener">J-Archive ↗</a></p>' +
            '<div class="pcard-grades">' +
            '<button type="button" class="pgrade" data-g="knew">Knew it <span>1</span></button>' +
            '<button type="button" class="pgrade" data-g="unsure">Unsure <span>2</span></button>' +
            '<button type="button" class="pgrade" data-g="missed">Missed <span>3</span></button></div>';
        }
        html += '</div>';
        pBody.innerHTML = html;
        if (!practice.revealed) {
          const rb = document.getElementById('pcard-reveal');
          rb.addEventListener('click', reveal);
          rb.focus();
        } else {
          pBody.querySelectorAll('.pgrade').forEach(b => b.addEventListener('click', () => grade(b.dataset.g)));
          const first = pBody.querySelector('.pgrade');
          if (first) first.focus();
        }
      }
      function reveal() { practice.revealed = true; renderCard(); }
      function grade(g) {
        practice.tally[g] = (practice.tally[g] || 0) + 1;
        practice.seen.add(practice.current);
        const rec = applyGrade(practice.store.cards[practice.current] || null, g, Date.now(), !practice.config.extra);
        saveCard(practice.current, rec);
        practice.session = gradeCurrent(practice.session, g);
        nextCard();
      }
      function renderSummary() {
        practice.screen = 'summary';
        updateProgressHeader();
        const now = Date.now();
        let scheduled = 0;
        for (const id of practice.seen) {
          const r = practice.store.cards[id];
          if (r && r.due > now) scheduled++;
        }
        const t = practice.tally;
        pBody.innerHTML = '<h2 class="practice-title">Session complete</h2>' +
          '<p class="psummary-tally">' + t.knew + ' knew · ' + t.unsure + ' unsure · ' + t.missed + ' missed</p>' +
          '<p class="psummary-sched">' + scheduled + ' card' + (scheduled === 1 ? '' : 's') + ' scheduled to come back later.</p>' +
          '<div class="practice-actions">' +
          '<button type="button" id="practice-again" class="practice-start">Practice again</button>' +
          '<button type="button" id="practice-done" class="practice-reset">Done</button></div>';
        document.getElementById('practice-again').addEventListener('click', () => {
          const ids = assembleSession(practicePool(practice.config.clusterIds, practice.config.era),
            practice.store.cards, Date.now(), practice.config.size, practice.config.extra, Math.random);
          if (!ids.length) {
            // Nothing left due — return to setup but keep this session's topics/size/extra.
            renderStart({ clusterIds: practice.config.clusterIds, size: practice.config.size,
              extra: practice.config.extra, note: 'Nothing left due — adjust topics/era or turn on Extra practice.' });
            const startBtn = document.getElementById('practice-start');
            if (startBtn) startBtn.focus();
            return;
          }
          practice.session = initSession(ids);
          practice.tally = { knew: 0, unsure: 0, missed: 0 };
          practice.seen = new Set();
          nextCard();
        });
        document.getElementById('practice-done').addEventListener('click', closePractice);
        document.getElementById('practice-again').focus();
      }

      function loadStore() {
        try { return sanitizeStore(JSON.parse(localStorage.getItem(PKEY))); }
        catch (e) { return { v: 1, cards: {} }; }
      }
      function saveCard(id, rec) {
        practice.store.cards[id] = rec;
        try { localStorage.setItem(PKEY, JSON.stringify(practice.store)); }
        catch (e) {
          practice.saveFailed = true;
          pNotice.textContent = "Progress isn't being saved (storage unavailable).";
          pNotice.hidden = false;
        }
      }
      function resetProgress() {
        try { localStorage.removeItem(PKEY); } catch (e) { /* ignore */ }
        practice.store = { v: 1, cards: {} };
      }
      function practicePool(clusterIds, era) {
        const ids = new Set();
        for (const cid of clusterIds) {
          const refs = (DATA.quiz && DATA.quiz[String(cid)]) || {};
          for (const key in refs) for (const id of refs[key]) ids.add(id);
        }
        const out = [];
        for (const id of ids) { const c = clueById(id); if (c && c.year >= era) out.push(id); }
        return out;
      }

      function renderStart(prefill) {
        practice.screen = 'start';
        pProgress.textContent = ''; pTally.textContent = '';
        const list = DATA.byEra[String(currentEra)] || [];
        const nameById = {};
        for (const d of list) nameById[d.cluster_id] = d.name;
        const clusters = Object.keys(DATA.quiz || {}).map(Number)
          .filter(cid => nameById[cid] !== undefined)
          .sort((a, b) => (nameById[a] || '').localeCompare(nameById[b] || ''));
        const isOn = cid => !prefill || prefill.clusterIds.indexOf(cid) !== -1;
        const size = prefill ? prefill.size : 20;
        const extra = prefill ? prefill.extra : false;
        let html = '<h2 class="practice-title">Practice</h2>' +
          '<p class="practice-sub">Study window: ' +
          (currentEra === DATA.eras[0] ? 'All-time' : 'Since ' + currentEra) + '</p>' +
          '<div class="practice-topics" role="group" aria-label="Topics">' +
          '<label class="ptopic"><input type="checkbox" id="ptopic-all"' +
          (clusters.every(isOn) ? ' checked' : '') + '> <b>Select all / none</b></label>';
        for (const cid of clusters) {
          html += '<label class="ptopic"><input type="checkbox" class="ptopic-cb" value="' + cid + '"' +
            (isOn(cid) ? ' checked' : '') + '> ' + escapeHtml(nameById[cid]) + '</label>';
        }
        html += '</div>' +
          '<div class="practice-opts"><span class="popt-label">Cards</span>' +
          [10, 20, 30].map(n => '<label><input type="radio" name="psize" value="' + n + '"' +
            (n === size ? ' checked' : '') + '> ' + n + '</label>').join('') + '</div>' +
          '<label class="pextra"><input type="checkbox" id="pextra"' + (extra ? ' checked' : '') + '> Extra practice ' +
          '<span class="pextra-note">(drill everything; correct answers don\\'t change your schedule)</span></label>' +
          '<div class="practice-actions">' +
          '<button type="button" id="practice-start" class="practice-start">Start session</button>' +
          '<span id="practice-startnote" class="practice-startnote">' +
          (prefill && prefill.note ? escapeHtml(prefill.note) : '') + '</span></div>' +
          '<button type="button" id="practice-reset" class="practice-reset">Reset progress</button>';
        pBody.innerHTML = html;
        const all = document.getElementById('ptopic-all');
        const cbs = () => Array.from(pBody.querySelectorAll('.ptopic-cb'));
        all.addEventListener('change', () => { cbs().forEach(cb => { cb.checked = all.checked; }); updateStartAvailability(); });
        cbs().forEach(cb => cb.addEventListener('change', () => {
          all.checked = cbs().every(c => c.checked); updateStartAvailability();
        }));
        document.getElementById('pextra').addEventListener('change', updateStartAvailability);
        pBody.querySelectorAll('input[name=psize]').forEach(r => r.addEventListener('change', updateStartAvailability));
        document.getElementById('practice-start').addEventListener('click', startSession);
        document.getElementById('practice-reset').addEventListener('click', () => {
          if (window.confirm('Erase all saved practice progress?')) { resetProgress(); updateStartAvailability(); }
        });
        updateStartAvailability();
      }

      function currentSelection() {
        const cids = Array.from(pBody.querySelectorAll('.ptopic-cb')).filter(cb => cb.checked).map(cb => Number(cb.value));
        const extra = document.getElementById('pextra').checked;
        const sizeEl = pBody.querySelector('input[name=psize]:checked');
        return { cids, extra, size: Number(sizeEl ? sizeEl.value : 20) };
      }
      function updateStartAvailability() {
        const sel = currentSelection();
        const avail = assembleSession(practicePool(sel.cids, currentEra), practice.store.cards,
          Date.now(), 1, sel.extra, Math.random).length;
        const btn = document.getElementById('practice-start');
        const note = document.getElementById('practice-startnote');
        btn.disabled = avail === 0;
        note.textContent = avail !== 0 ? '' : (sel.extra
          ? 'No clues match — widen your era or topics.'
          : 'Nothing due — turn on Extra practice, or widen your era / topics.');
      }

      function startSession() {
        const sel = currentSelection();
        const ids = assembleSession(practicePool(sel.cids, currentEra), practice.store.cards,
          Date.now(), sel.size, sel.extra, Math.random);
        if (!ids.length) { updateStartAvailability(); return; }
        practice.config = { clusterIds: sel.cids, size: sel.size, extra: sel.extra, era: currentEra };
        practice.session = initSession(ids);
        practice.tally = { knew: 0, unsure: 0, missed: 0 };
        practice.seen = new Set();
        nextCard();
      }

      function trapTab(e) {
        if (e.key !== 'Tab') return;
        const items = Array.from(overlay.querySelectorAll('button, input, a[href], [tabindex]:not([tabindex="-1"])'))
          .filter(el => !el.disabled && el.offsetParent !== null);
        if (!items.length) return;
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      function practiceKeys(e) {
        if (e.key === 'Escape') { closePractice(); return; }
        trapTab(e);
        if (practice.screen !== 'card') return;
        const tag = (e.target.tagName || '').toLowerCase();
        const interactive = tag === 'button' || tag === 'a' || tag === 'input' || tag === 'textarea';
        if (!practice.revealed) {
          // Space reveals — but never override native activation of a focused button/link
          // (Exit, Reveal, etc. must keep their default Space/Enter behavior).
          if (e.key === ' ' && !interactive) { e.preventDefault(); reveal(); }
        } else if (e.key === '1' || e.key === '2' || e.key === '3') {
          // Digit keys aren't native button activators, so grading by number is safe regardless of focus.
          grade({ '1': 'knew', '2': 'unsure', '3': 'missed' }[e.key]);
        }
      }
      function openPractice() {
        practice.returnFocus = document.activeElement;
        practice.store = loadStore();
        practice.saveFailed = false; pNotice.hidden = true;
        overlay.hidden = false;
        document.body.style.overflow = 'hidden';
        setBackgroundInert(true);
        renderStart();
        document.addEventListener('keydown', practiceKeys);
        const firstFocus = pBody.querySelector('input, button');
        if (firstFocus) firstFocus.focus();
      }
      function closePractice() {
        overlay.hidden = true;
        document.body.style.overflow = '';
        setBackgroundInert(false);
        document.removeEventListener('keydown', practiceKeys);
        if (practice.returnFocus && practice.returnFocus.focus) practice.returnFocus.focus();
      }
      document.getElementById('practice-exit').addEventListener('click', closePractice);
      document.getElementById('practice-open').addEventListener('click', openPractice);

      renderEraToggle();
      renderSide('');
      renderMain();
      renderDetailEmpty();
    })();
  </script>
</body>
</html>
"""


def render_html(data: dict) -> str:
    """Render the self-contained research page with `data` embedded as JSON."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = _HTML_TEMPLATE.replace("__PRACTICE_JS__", _practice_js())
    return html.replace("__DATA_JSON__", payload)


def run_research():
    tokens = pd.read_parquet(config.CATEGORY_TOKENS_PATH)
    eras = pd.read_parquet(config.CATEGORY_ERAS_PATH)
    labels = pd.read_csv(config.CLUSTER_LABELS_PATH).set_index("cluster_id")["name"].to_dict()
    if config.MISC_ID in set(tokens["cluster_id"]) and config.MISC_ID not in labels:
        labels[config.MISC_ID] = config.MISC_LABEL
    fp = pd.read_parquet(config.CATEGORY_FINGERPRINTS_PATH) if config.CATEGORY_FINGERPRINTS_PATH.exists() else None
    qr = pd.read_parquet(config.CATEGORY_QUIZ_REFS_PATH) if config.CATEGORY_QUIZ_REFS_PATH.exists() else None
    cs = pd.read_parquet(config.CLUES_STORE_PATH) if config.CLUES_STORE_PATH.exists() else None
    data = build_research_data(tokens, eras, labels, fp, qr, cs)
    html = render_html(data)
    config.RESEARCH_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.RESEARCH_HTML_PATH.write_text(html, encoding="utf-8")
    last_era = data["byEra"][str(data["eras"][-1])]
    studyable = sum(1 for d in last_era if d["entities"])
    print(
        f"Wrote {config.RESEARCH_HTML_PATH} "
        f"({len(data['eras'])} eras, {len(last_era)} types/era, {studyable} studyable in {data['eras'][-1]}s)"
    )

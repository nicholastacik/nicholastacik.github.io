"""Generate the interactive research tool (type -> entities -> live Wikipedia facts)."""
import json

import pandas as pd

from jeopardy import config


def build_research_data(tokens_df, eras_df, labels, sample_clues_df=None):
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
    sample_map = {}
    if sample_clues_df is not None:
        for cid, grp in sample_clues_df.groupby("cluster_id"):
            sample_map[str(int(cid))] = [
                {"phrase": (None if pd.isna(r["phrase"]) else r["phrase"]),
                 "clue": r["clue"], "answer": r["answer"], "year": int(r["year"])}
                for _, r in grp.iterrows()
            ]
    return {"eras": [int(e) for e in eras], "byEra": by_era, "sampleClues": sample_map}


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
</style>
</head>
<body>
  <header class="topbar">
    <p class="eyebrow">Field notes for trivia prep</p>
    <h1>The Board</h1>
    <p>50 Jeopardy! category clusters, ranked by how deep you can actually study them.
       Pick a decade to see what dominated the board then, drill into its most recurring
       answers, and pull live facts from Wikipedia.</p>
  </header>
  <div class="era-bar" role="group" aria-label="Study era">
    <span class="era-bar-label">The board, as of</span>
    <div id="era-toggle" class="era-toggle"></div>
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
  <footer class="footer">
    Categories mined from j-archive.com box scores; ranked entities are the phrases that keep
    reappearing as answers within a cluster. Wikipedia facts are fetched live in your browser on
    each click &mdash; nothing here is cached, curated, or fact-checked.
  </footer>
  <script>
    const DATA = __DATA_JSON__;

    (function () {
      const sideList = document.getElementById('side-list');
      const filterInput = document.getElementById('filter-input');
      const mainPanel = document.getElementById('main-panel');
      const detailPanel = document.getElementById('detail-panel');
      const eraToggle = document.getElementById('era-toggle');
      const wikiCache = new Map();

      let currentEra = DATA.eras.includes(2010) ? 2010 : DATA.eras[0];
      let selectedTypeId = null;
      let selectedEntity = null;

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
          btn.textContent = era + 's';
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
            ? `<span class="stat">${d.applicability} qualifying &middot; ${pctLabel(d.prevalence)} of board</span>` +
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
          mainPanel.innerHTML = '<p class="placeholder">Select a category from the left to see its most recurring answers.</p>';
          return;
        }
        let html = `<div class="main-head"><h2>${escapeHtml(d.name)}</h2>` +
          `<p class="sub">applicability score ${d.applicability} &middot; ${pctLabel(d.prevalence)} of ${currentEra}s categories &middot; ${d.entities.length} ranked answers</p></div>`;
        html += '<div class="sample-box" id="sample-box">' +
          '<button type="button" class="sample-clue-btn" id="sample-clue-btn">Sample clue &#9860;</button>' +
          '<div id="sample-card"></div></div>';
        if (!d.entities.length) {
          html += '<span class="tag-brick">Not really studyable</span>' +
            '<p class="placeholder">This cluster didn\\'t turn up enough repeating answers to study directly ' +
            '&mdash; treat it as a grab-bag and review its categories individually.</p>';
          mainPanel.innerHTML = html;
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
        const sampleBtn = document.getElementById('sample-clue-btn');
        if (sampleBtn) sampleBtn.addEventListener('click', () => rollSampleClue(d.cluster_id));
        mainPanel.querySelectorAll('.entity-row').forEach(row => {
          row.addEventListener('click', () => selectEntity(d.entities[Number(row.dataset.idx)]));
        });
      }

      function eligibleClues(clusterId) {
        const pool = (DATA.sampleClues && DATA.sampleClues[String(clusterId)]) || [];
        const byEra = pool.filter(c => c.year >= currentEra);
        if (selectedEntity) {
          const scoped = byEra.filter(c => c.phrase === selectedEntity.phrase);
          if (scoped.length) return { clues: scoped, scoped: true };
        }
        const general = byEra.length ? byEra : pool;
        return { clues: general, scoped: false };
      }

      function rollSampleClue(clusterId) {
        const card = document.getElementById('sample-card');
        if (!card) return;
        const { clues, scoped } = eligibleClues(clusterId);
        if (!clues.length) {
          card.innerHTML = '<div class="sample-card"><p class="scope">No clue on the board for this filter.</p></div>';
          return;
        }
        const pick = clues[Math.floor(Math.random() * clues.length)];
        const scopeLabel = scoped
          ? 'Answer is &ldquo;' + escapeHtml(selectedEntity.phrase) + '&rdquo; &middot; ' + pick.year
          : 'Any answer in this category &middot; ' + pick.year + ' &middot; un-highlight to broaden';
        card.innerHTML = '<div class="sample-card">' +
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

      function renderDetailLoading(entity) {
        detailPanel.classList.remove('flash');
        detailPanel.innerHTML = '<p class="eyebrow">The answer</p>' +
          `<h3>${escapeHtml(entity.phrase)}</h3>` +
          `<p class="pulse">Asking Wikipedia about &ldquo;${escapeHtml(entity.phrase)}&rdquo;&hellip;</p>`;
      }

      function renderDetail(entity, summary) {
        let html = '<p class="eyebrow">The answer</p>' + `<h3>${escapeHtml(entity.phrase)}</h3>`;
        if (summary && summary.extract) {
          const thumb = summary.thumbnail && summary.thumbnail.source;
          const url = summary.content_urls && summary.content_urls.desktop && summary.content_urls.desktop.page;
          if (thumb) html += `<img src="${escapeHtml(thumb)}" alt="${escapeHtml(entity.phrase)}">`;
          html += `<p class="extract">${escapeHtml(summary.extract)}</p>`;
          if (url) html += `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">Read the full article on Wikipedia &#8599;</a>`;
        } else {
          const searchUrl = 'https://en.wikipedia.org/w/index.php?search=' + encodeURIComponent(entity.phrase);
          html += `<p class="fallback">No summary came back for &ldquo;${escapeHtml(entity.phrase)}&rdquo;. ` +
            `<a href="${escapeHtml(searchUrl)}" target="_blank" rel="noopener">Search Wikipedia directly &#8599;</a></p>`;
        }
        detailPanel.innerHTML = html;
        detailPanel.classList.remove('flash');
        void detailPanel.offsetWidth;
        detailPanel.classList.add('flash');
      }

      async function selectEntity(entity) {
        selectedEntity = entity;
        renderMain();
        renderDetailLoading(entity);
        let summary;
        if (wikiCache.has(entity.phrase)) {
          summary = wikiCache.get(entity.phrase);
        } else {
          summary = await fetchWiki(entity.phrase);
          wikiCache.set(entity.phrase, summary);
        }
        if (selectedEntity !== entity) return;
        renderDetail(entity, summary);
      }

      filterInput.addEventListener('input', () => renderSide(filterInput.value));

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
    return _HTML_TEMPLATE.replace("__DATA_JSON__", payload)


def run_research():
    tokens = pd.read_parquet(config.CATEGORY_TOKENS_PATH)
    eras = pd.read_parquet(config.CATEGORY_ERAS_PATH)
    labels = pd.read_csv(config.CLUSTER_LABELS_PATH).set_index("cluster_id")["name"].to_dict()
    sample = pd.read_parquet(config.CATEGORY_SAMPLE_CLUES_PATH) \
        if config.CATEGORY_SAMPLE_CLUES_PATH.exists() else None
    data = build_research_data(tokens, eras, labels, sample)
    html = render_html(data)
    config.RESEARCH_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.RESEARCH_HTML_PATH.write_text(html, encoding="utf-8")
    last_era = data["byEra"][str(data["eras"][-1])]
    studyable = sum(1 for d in last_era if d["entities"])
    print(
        f"Wrote {config.RESEARCH_HTML_PATH} "
        f"({len(data['eras'])} eras, {len(last_era)} types/era, {studyable} studyable in {data['eras'][-1]}s)"
    )

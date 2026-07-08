"""Generate the interactive research tool (type -> entities -> live Wikipedia facts)."""
import json

import pandas as pd

from jeopardy import config


def build_research_data(tokens_df, labels):
    """Per-type entity data for the research page, sorted by applicability desc."""
    out = []
    for cluster_id, name in labels.items():
        rows = tokens_df[tokens_df["cluster_id"] == cluster_id]
        applicability = int(rows["n_qualifying_phrases"].iloc[0]) if len(rows) else 0
        entities = [
            {"phrase": r["phrase"], "count": int(r["count"])}
            for _, r in rows.iterrows()
            if r["phrase"] is not None and pd.notna(r["phrase"])
        ]
        out.append({
            "cluster_id": int(cluster_id),
            "name": name,
            "applicability": applicability,
            "entities": entities,
        })
    out.sort(key=lambda d: d["applicability"], reverse=True)
    return out


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
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ash);
    display: block;
    margin-top: 3px;
  }

  .side-item.dim { opacity: 0.45; }
  .side-item.dim .meta { color: var(--brick); }

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
       Pick one, drill into its most recurring answers, and pull live facts from Wikipedia.</p>
  </header>
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
      const wikiCache = new Map();

      let selectedType = null;
      let selectedEntity = null;

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

      function renderSide(filterText) {
        const q = (filterText || '').trim().toLowerCase();
        sideList.innerHTML = '';
        const filtered = DATA.filter(d => d.name.toLowerCase().includes(q));
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
            (selectedType && selectedType.cluster_id === d.cluster_id ? ' active' : '');
          btn.setAttribute('role', 'listitem');
          btn.innerHTML = `<span class="name">${escapeHtml(d.name)}</span>` +
            `<span class="meta">${studyable ? d.entities.length + ' answers' : 'not really studyable'}</span>`;
          btn.addEventListener('click', () => selectType(d));
          sideList.appendChild(btn);
        }
      }

      function selectType(d) {
        selectedType = d;
        selectedEntity = null;
        renderSide(filterInput.value);
        renderMain();
        renderDetailEmpty();
      }

      function renderMain() {
        if (!selectedType) {
          mainPanel.innerHTML = '<p class="placeholder">Select a category from the left to see its most recurring answers.</p>';
          return;
        }
        const d = selectedType;
        let html = `<div class="main-head"><h2>${escapeHtml(d.name)}</h2>` +
          `<p class="sub">applicability score ${d.applicability} &middot; ${d.entities.length} ranked answers</p></div>`;
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
        mainPanel.querySelectorAll('.entity-row').forEach(row => {
          row.addEventListener('click', () => selectEntity(d.entities[Number(row.dataset.idx)]));
        });
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

      renderSide('');
      renderMain();
      renderDetailEmpty();
    })();
  </script>
</body>
</html>
"""


def render_html(data: list[dict]) -> str:
    """Render the self-contained research page with `data` embedded as JSON."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__DATA_JSON__", payload)


def run_research():
    tokens = pd.read_parquet(config.CATEGORY_TOKENS_PATH)
    labels = pd.read_csv(config.CLUSTER_LABELS_PATH).set_index("cluster_id")["name"].to_dict()
    data = build_research_data(tokens, labels)
    html = render_html(data)
    config.RESEARCH_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.RESEARCH_HTML_PATH.write_text(html)
    studyable = sum(1 for d in data if d["entities"])
    print(f"Wrote {config.RESEARCH_HTML_PATH} ({len(data)} types, {studyable} studyable)")

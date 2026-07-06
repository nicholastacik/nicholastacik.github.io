# Build log — Jeopardy data science

A running dev journal. Each phase drops a short dated entry with the decisions
made and *why*. Raw material for the eventual blog post (Sub-project C) —
captured while the reasoning is fresh, not reconstructed at the end.

This file is prose only; it does not execute at render time. Excerpts can be
pulled into `index.qmd` later (directly or via `{{< include >}}`).

---

## 2026-07-04 — Project shape: three phased sub-projects

The overall goal (learn what to study for Jeopardy via data science) splits into
three independently-buildable pieces, built in order:

- **A — Scraper + storage:** produce a committed, analysis-ready dataset of all
  ~500k clues from j-archive.com.
- **B — Analysis toolkit:** date/game-type filtering, category clustering
  (embeddings), most-common answers per category, and general DS questions
  (daily-double location, difficulty over time, final-Jeopardy category mix).
- **C — Quarto blog post:** interactive, reproducible narrative over the dataset.

**Why phased:** the scraper teaches us what the data actually looks like (field
quirks, missing values, 40 years of format drift). Designing B and C against real
data beats speculating up front.

---

## 2026-07-04 — Storage: JSONL archive → committed Parquet

**The constraint that drove everything:** ~500k clues of category + clue + answer
text is roughly 75–150 MB of raw text. GitHub rejects files over 100 MB and gets
unhappy well before that. Since the whole point is a *committed, reproducible*
dataset the blog post can read, format choice is really "what stays under the
limit and reads fast in pandas."

**Options considered:**

- **Raw JSON only** — faithful archive, but no columnar querying and awkward for
  pandas at scale.
- **SQLite** — lovely for ad-hoc SQL, but uncompressed it's ~120–150 MB, likely
  over GitHub's limit → forces Git LFS (extra setup + quota). Rejected.
- **Two layers: JSONL crawl → Parquet artifact** — *chosen.*

**What we picked:**

- The scraper writes one JSON object per game to an append-only `.jsonl` file.
  Append-only makes it **resumable** (crash at game 6000, restart from 6000) and
  keeps the raw source faithful.
- A separate build step normalizes that into a single **Parquet** file (one row
  per clue) with zstd compression. Text compresses ~4×, so the committed artifact
  should land around **20–40 MB** — comfortably under GitHub's limit, no LFS.
- The blog post reads it with `pd.read_parquet()` in milliseconds.

**Why Parquet:** columnar layout means (1) similar values sit together and
compress far better than mixed rows, (2) selective reads — asking "what
categories exist?" only touches the category column, and (3) types are baked in
(dates are dates, values are ints), so no re-parsing on every load. Tradeoff vs.
SQLite is no ad-hoc SQL, but our workflow is load-into-DataFrame-then-slice, so
that costs nothing.

**The reproducibility boundary, made physical:** the raw crawl (huge,
non-reproducible, network-dependent) stays gitignored on the author's machine;
only the compact `clues.parquet` is committed. Anyone who clones — including CI —
gets the data without re-scraping. This is *why the scrape can never run at Quarto
render time*: CI renders on every push, and scraping hundreds of thousands of
pages per build would be slow, fragile, and abusive to a free community resource.

---

## 2026-07-04 — Scrape scope: everything, tagged by game type

**Decision:** scrape *every* game j-archive has, including special formats
(Tournament of Champions, Teen/College, Celebrity, Masters, GOAT, etc.), and tag
each with a `game_type`. Nothing is discarded at scrape time; the analyst filters
downstream. `game_type` becomes a filter dimension in Sub-project B and seeds
Step 5 questions ("are celebrity games easier?", "do tournament categories
differ?").

Rejected "regular episodes only" (can't ever ask cross-format questions without
re-scraping) and "everything, untagged" (muddies difficulty/category analyses).

---

## 2026-07-04 — Scraper architecture: fetch / parse / crawl, one CLI

**Three-stage offline pipeline, single front door:**

1. **fetch** — polite (~1 req/s + jitter, descriptive User-Agent), sequential
   HTTP; caches every raw page to disk so the network cost is paid once.
2. **parse** — pure function `html → clue records`; no network, re-runnable
   against the cache as the parser is refined.
3. **crawl** — resumable orchestration: enumerate seasons → games, skip
   `game_id`s already in the JSONL, append one object per game.
4. **build** — normalize JSONL → one row per clue → zstd Parquet.

Front door is a `click` CLI (`python -m jeopardy {crawl,build,all}`); analysis
subcommands slot in later.

**Highest-leverage decision — the local HTML cache.** Scraping is really two
concerns: *fetching* (slow, network-bound, rude to repeat) and *parsing* (fast,
CPU-bound, we'll get it wrong a few times). Caching raw HTML on first fetch means
we pay the ~3-hour network cost exactly once, then iterate on the parser against
local files forever. Conflating fetch and parse is the classic scraper mistake.

**Politeness:** sequential, ~1 req/s with jitter, honest User-Agent identifying
it as personal research. Full first crawl ≈ 2.5–4 hours. Slow-and-polite beats
getting IP-banned mid-scrape.

**Dependencies (uv-managed):** `httpx`, `beautifulsoup4`, `lxml`, `click` in a
dedicated `scraper` group so CI's render-only `uv sync --frozen` stays lean.

---

## 2026-07-04 — j-archive structure (reverse-engineered)

Discoveries from inspecting real pages — gold for the post, hard to reconstruct
later:

- **Seasons:** `listseasons.php` lists **50 seasons — 42 numeric + 8 named
  specials** (`goattournament`, `superjeopardy`, `cwcpi` = audio-only, `jm`,
  `pcj`, `ncc`, `bbab`, `trebekpilots`). Season pages
  (`showseason.php?season=X`) list games as
  `<a href="showgame.php?game_id=…">#8235, aired 2020-06-12</a>`. Note **game_id
  ≠ show number**.
- **Board position lives in the cell ID:** clue cells are
  `id="clue_{J|DJ}_{col}_{row}"`, e.g. `clue_J_1_1`. So we read `row` (1–5,
  difficulty tier) and `column` (1–6) *directly from the DOM* — no inferring
  position from the dollar value. This is robust to the **Nov 2001 value
  doubling** ($500→$1000 top clue), which makes raw dollar amounts
  non-comparable across eras; the row is the era-stable difficulty signal.
- **Answers are hidden:** the correct response sits in a sibling cell
  `id="clue_J_1_1_r"` (`display:none`), revealed by a JS `onmouseover`, as
  `<em class="correct_response">the Model T</em>`. The `_r` cell also holds a
  table of which contestant answered — ignored (contestant data is out of scope).
- **Daily doubles show the wager, not the board value:** DD cells are
  `class="clue_value_daily_double"` with text like `DD: $1,600` — that's the
  *bet*, not the clue's board value. So `clue_value` is derived from the row
  ladder (round + row + era), and the wager goes into `dd_wager`.
- **Rounds:** cell-ID prefixes `J` (Jeopardy) and `DJ` (Double Jeopardy). Final
  Jeopardy is separate: `id="clue_FJ"` (clue) + `clue_FJ_r` (answer), with the
  category in the `final_round` table. No row/column/value for Final.
- **13 categories per game:** 6 + 6 + 1 (Final).
- **`game_comments`** (`<div id="game_comments">`) carries tournament-round
  context — the signal used to classify `game_type` for in-season tournaments
  that a numeric season ID alone doesn't reveal.

**The two-layer split pays off here:** `parse.py` extracts a *faithful, rich*
per-game record (keeps `game_comments`, `show_number`, clue order numbers —
everything on the page), and `build_parquet.py` *curates* it into the agreed
schema, deriving `game_type` (from season ID + comments keywords) and
`clue_value` (from the row ladder, era-adjusted). Faithful capture, curatorial
projection.

### Committed schema (one row per clue)

`game_id, air_date, season, game_type, round, category, clue_value, row, column,
is_daily_double, dd_wager, clue, answer`.

- `clue`/`answer` named to dodge Jeopardy's inverted "answer/question" phrasing:
  `clue` = the displayed statement, `answer` = the correct response.
- Contestant-level data (who rang in, scores) deliberately **out of scope** —
  none of the planned analyses need it and it ~doubles parser complexity.

---

## 2026-07-05 — Sub-project B, Phase 1: category clustering (Step 3)

The scraper produced the full dataset (**563,266 clues**, 9,485 games, seasons
1984–2026, one 29 MB committed `clues.parquet`). Sanity checks were clean: 0 null
categories/clues/answers; the 112 null air-dates are exactly the never-aired Trebek
pilots; `game_type` classification landed sensibly (regular 474k, then ToC, teen,
college, teachers, celebrity, masters, GOAT, …).

**We reordered B to do Step 3 (clustering) first** — it's the exploratory piece, and
what the embeddings reveal about the data's semantic structure will inform Steps 4–5 and
the eventual post.

### Goal

Discover the most common **types** of categories, to guide what to study.

### Decisions

- **Unit = category instance.** One document per `(game_id, round, category)` — name +
  its clues/answers. Cluster **all ~123k** instances (not deduped by name) so that a
  perennial type recurs and cluster *size* reads directly as "how common this type is."
- **Embedding: local sentence-transformer, `BAAI/bge-small-en-v1.5`.** Semantic (unlike
  TF-IDF), free/offline (no API cost, unlike an embeddings API), 512-token window (fits
  full category docs — `all-MiniLM-L6-v2`'s 256 would truncate), compact 384-dim.
- **Document construction:** `CATEGORY NAME.` first (anchor), then the clue→answer pairs
  **shuffled** per document via a *seeded* RNG — non-systematic order across the corpus
  (kills positional bias) but reproducible. 512 tokens makes truncation a non-issue, so
  no front-loading needed.
- **Clustering: KMeans (seeded) + UMAP for 2D viz only.** KMeans assigns *every* instance
  (no noise bucket), partitions cleanly, and ranks by size — the study signal. Chosen
  over UMAP→HDBSCAN (big awkward noise bucket, harder to rank) and hierarchical
  (memory-prohibitive at 123k). `k`≈50, over-segment and lean on labels.
- **Cluster labels = three-part deterministic fingerprint:** top actual category names +
  centroid exemplars + c-TF-IDF distinctive terms. Free, deterministic, human-readable.
- **Optional LLM naming as an enrichment layer.** The pipeline emits a paste-ready
  `cluster_naming_prompt.md`; an optional `name-clusters` command calls the OpenAI API
  (one batched call, ~$0.01–0.30 one-time — pennies) to write a **committed, curated**
  `cluster_labels.csv`. Kept *outside* the deterministic pipeline (re-running may rename);
  can also be filled by hand via the ChatGPT web app for $0. The summary/post read the
  labels if present, else fall back to the fingerprint.

### Architecture

Same reproducibility boundary as the scraper: heavy compute (`torch`/`umap`/`sklearn`,
in an offline `analysis` uv group) runs on the machine and commits small artifacts;
CI/the post read them with pandas only. Embedding (slow) is cached and split from
clustering (fast, re-tunable) — the fetch/parse split, again. Committed:
`category_clusters.parquet` (per-instance cluster_id + 2D coords) and
`cluster_summary.parquet` (per-cluster fingerprints); embedding matrix cached +
gitignored.

---

## 2026-07-06 — Step 3 RESULTS: what the clusters revealed

Ran the full pipeline: **122,954 category instances** embedded (`bge-small-en-v1.5`),
KMeans **k=50** (seed 42), UMAP 2D, three-part fingerprints, names hand-authored into
`cluster_labels.csv`. Committed artifacts: `category_clusters.parquet` (per-instance
cluster + 2D coords), `cluster_summary.parquet`, `cluster_naming_prompt.md`,
`cluster_labels.csv`.

### The clusters are clean, interpretable types
Nearly every one of the 50 clusters is a recognizable category type — e.g. cluster 25 =
Shakespeare (terms: shakespeare, macbeth, hamlet), 35 = U.S. Presidents, 46 = World
Geography & Waters (river, island, sea, lake), 24 = Mythology (god, greek, zeus).

### Headline finding: wordplay is the single largest meta-domain (~10-13%)
Grouping the 50 clusters into broad domains (share of all categories):
wordplay/language ~13% · history & politics ~11% · geography & travel ~11% · science &
nature ~10% · literature & writing ~9% · screen (film/TV) ~9% · music ~5% · a ~5%
genuine "potpourri/grab-bag" that correctly resists typing; the rest split into food,
sports, art, religion, business, etc. as clean 1-3% clusters.

### The k-sweep sharpened the study takeaway
- **k=30** = executive-summary view (over-merges: science+astronomy+measures lump together).
- **k=50** = the sweet spot (distinct, coherent types) — chosen as primary.
- **k=80** = drill-down: *wordplay fractures into distinct prep tracks* — letter/anagram
  **games** (a drill-it skill), vs **etymology/word-origins** and **idioms/proverbs**
  (memorizable knowledge, Latin/French roots). So "practice wordplay" is really two
  different study strategies. This reframing is exactly why we did Step 3 first.

### Method notes / caveats
- c-TF-IDF labels needed light stopword filtering ("it's", ordinal "th" from the
  `\d` tokenizer boundary) for clean readouts — cosmetic.
- A few near-duplicate clusters at k=50 (TV 15/31, movies 19/33, literature 0/26) — fine,
  the names distinguish them.
- Cluster names authored in-session (free); optional OpenAI `name-clusters` path exists
  but wasn't used.

---

## 2026-07-06 — Most common tokens per category-type (Step 4)

Built `jeopardy/analysis/tokens.py` + `tokens` CLI → committed
`category_tokens.parquet` (1,250 rows: top-25 phrases for each of the 50 cluster-types,
+ an `n_qualifying_phrases` applicability signal).

### Design
- **Unit:** the 50 cluster-types (not raw category names — too sparse).
- **Token = capitalized proper-noun phrase** mined from clue **and** answer text (answers
  alone lose entities that live in the clue, e.g. "What year was Richard III born?"). A
  transparent regex (no NER) keeps entities whole: "Richard III", "World War II",
  "United States of America". Digits excluded (kills year-gluing); "and" excluded (splits
  distinct entities); clue and answer extracted separately (avoids cross-boundary gluing).
- **Ranking:** c-TF-IDF (`idf = log(n_clusters / doc_freq)`, no smoothing) with a
  min-frequency floor (≥5), top-25 per cluster.

### Noise-cleaning journey (three passes)
1. **Un-smoothed idf.** The first cut was polluted with nationalities ("American",
   "French") ranking top. Root cause: `+1.0` idf smoothing floored idf near 1, so
   ubiquitous words scored ≈ raw count. Removing smoothing lets words in all 50 clusters
   go to weight 0.
2. **Drop titles.** "President/King/Mr/Dr/Lord" were leaking as tokens; now stripped like
   stopwords (the name survives, the title vanishes).
3. **Capitalization-dominance filter.** Residual single-word generic nouns ("Species",
   "Scientists") remained. Filter: drop a single-word phrase if its lowercase form
   dominates in the corpus (appears more lowercase than capitalized). This keeps homonym
   entities ("China", "Turkey" — capitalized-dominant) while dropping generic nouns —
   the key advantage over a naive dictionary/stoplist. Multi-word phrases always kept.
   Known tradeoff: genuinely capitalized-dominant labels ("Republican", "Democrat")
   survive — acceptable (they're real proper nouns, just not study entities).

### Results (sample)
- **Books & Authors:** Jane Eyre, Willa Cather, Thomas Hardy, Agatha Christie, Sinclair Lewis…
- **World Geography & Waters:** Caspian Sea, Bay of Bengal, Black Sea, Indian Ocean, Volga, Greenland…
- **U.S. Presidents:** Woodrow Wilson, Gerald Ford, Andrew Jackson, John Quincy Adams…
- **Animals & Zoology:** Galapagos Islands, Manx, Gila, Stegosaurus, Komodo…
- **Applicability ranking** (most studyable → entity-dense types like Books & Authors,
  Movies, Pop Music; least → wordplay/generic types), via `n_qualifying_phrases`.

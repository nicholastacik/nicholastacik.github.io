# Clue Fingerprints — Design

**Date:** 2026-09-15
**Status:** Draft (pending user review) — revised after spec review
**Part of:** the "Jeopardy data science" research tool. A new feature (not a fix): for each
recurring entity, distill the *distinctive cues Jeopardy uses to clue it* — answering "what
should I recognize?" better than a generic Wikipedia bio. First of two proposed additions; the
spaced-repetition **practice session** is a separate follow-on sub-project (out of scope here).

## Goal

When you drill into an entity, show its **fingerprint**: the handful of terms that keep recurring
across the real clues where it's the answer — each with the evidence behind it (how many of the
entity's clues it appears in) — plus 2–3 example clues with J-Archive links. Jeopardy-specific
study signal on top of the existing live Wikipedia bio.

## Architecture — one clue store, two consumers

The fingerprint's "representative examples" and the quiz's "varied, date-eligible sample" are
different selections over the *same* clues. So store each clue **once** and have both features
**reference clue IDs** — no duplicated clue text in the embedded page, and each keeps its own
selection rule. This supersedes the earlier (rejected) "fold sample clues into fingerprints" idea,
which would have collapsed the quiz pool.

### 1. `clues_store.parquet` — intrinsic clue fields (identity only, no cluster/entity)
A physical clue can belong to its original cluster **and** to Misc (≈20k such clues), so
`cluster_id`/`phrase` must NOT live on the clue — they belong on the references (§1b). The store
holds each distinct clue once, keyed by identity:
`clue_id, clue, answer, year, category, game_id, round, row, column`
- **`clue_id`** = stable per-clue identity `"{game_id}:{round}:{row}:{column}"` (game_id alone
  identifies a game, not a clue). Final-Jeopardy clues (null row/column) use `row=col=0`.
- `category` is kept — the original Jeopardy category often carries essential constraints and the
  quiz already displays it.

### 1b. References — `(cluster_id, phrase)` → clue IDs (carry the context)
Cluster/entity membership lives here, so the same `clue_id` can be referenced from its original
cluster's entity **and** from Misc:
- **Quiz refs** (replacing `category_sample_clues`): per `(cluster_id, phrase)` its date-eligible
  clue IDs, and per `cluster_id` the general (`phrase=null`) clue IDs — both selection rules
  preserved, now as ID lists.
- **Fingerprint refs**: see §3 (`example_clue_ids` per `(cluster_id, phrase)`).

### 2. Resolution & the window contract (explicit)
- **Clue → entity provenance** is deterministic and window-aware without blind dict-union: resolve
  each clue using the **all-time** mapping if its answer maps there; otherwise fall back to the
  narrowest recent window where it maps (so recent-only entities like *Stranger Things* are
  covered, per the fix already shipped in `sample_clues`). First assignment wins — no later window
  silently overwrites an earlier interpretation.
- **Cues are all-time** and labeled as such ("how it's usually clued") — an entity's distinctive
  vocabulary is stable across windows, and computing per-window cues would 5× the work for little
  gain.
- **Examples are window-aware:** the fingerprint stores its representative clue IDs, but the tool
  filters them to the active study window (`year >= cutoff`) and **always keeps the newest eligible
  clue** — the same recency guarantee (`_sample`) we just added to the quiz, so "Since 2020" never
  shows only pre-2020 examples when newer ones exist. If none are eligible in the window, fall back
  to the entity's newest overall (labeled) rather than showing nothing.

### 3. `category_fingerprints.parquet` — cues + example references
One row per `(cluster_id, phrase)`, nested lists (resolves the earlier one-row-vs-three ambiguity):
`cluster_id, phrase, cues (list[{term, support, total}]), example_clue_ids (list[str])`
- **`cues`**: distinctive terms via TF-IDF over the entity's concatenated clue text vs the corpus
  of all entities' clue-documents (reusing `label.ctfidf_terms`, `TfidfVectorizer(stop_words=
  "english", ngram_range=(1,2), token_pattern=r"[A-Za-z][A-Za-z'\-]+")`). Each kept cue carries
  **`support`** = number of the entity's DISTINCT clues it appears in, and **`total`** = the
  entity's clue count, so the UI can show "Hannibal · 7 of 24 clues".
- Keep at most 6 cues, **require `support >= 2`** (genuinely recurring), and **allow fewer than 6**
  (or zero). Drop a unigram that is fully subsumed by a kept bigram (keep "Tom Sawyer", drop "Tom"
  and "Sawyer"); drop the entity's own name tokens and a small Jeopardy-filler stoplist.
- **`example_clue_ids`**: selected as **the entity's single newest clue, plus up to 3 more ranked
  by cue coverage, deduplicated**. Ranking by coverage alone does not guarantee a recent candidate
  (all top-coverage clues could be old); reserving the newest at build time does. With cumulative
  windows this guarantees the tool's window filter has a recent-eligible example whenever one
  exists in the corpus.

Built by a new offline CLI command **`fingerprints`** (`jeopardy/analysis/fingerprints.py`),
which also writes `clues_store.parquet` and the quiz refs. Reuses `_cluster_resolution` for provenance so
fingerprints, the clue store, and the displayed entities stay consistent. Only entities in
`category_tokens.parquet` get a fingerprint.

**J-Archive link:** `https://www.j-archive.com/showgame.php?game_id={game_id}` per example clue.

### Relationship to the existing sample-clue feature
`category_sample_clues.parquet` is replaced by references into `clues_store.parquet`: the quiz
keeps **both** its per-entity date-eligible selection **and** the general pool (coverage and the
un-highlighted "any answer" behavior are unchanged), now expressed as clue-ID lists. Net effect on
page size is roughly neutral (clue text stored once, referenced twice).

## Cue extraction — empty/degenerate states
- **0 clues** (entity is a valid clue-mention that is never itself the answer — explicitly allowed
  in this project): no fingerprint block; fall through to Wikipedia with a neutral note
  ("shows up in clues but is rarely the answer"). Absence of answer examples does **not** imply
  misclassification.
- **1 clue:** show it as the single example with **no cue chips** — a cue requires `support >= 2`
  *distinct* clues, so a single clue never yields recurring cues regardless of repeated words.
- **No qualifying repeated terms:** show example clues with no cue chips (cues are optional).

## Tool UI (detail pane)
On entity select, render the **fingerprint immediately from local data** — it must NOT wait on,
and must survive the failure/hang of, the Wikipedia request:
1. eyebrow "How Jeopardy clues it" + cue chips ("term · N of M clues") + the window-filtered
   example clues (answer shown — study card, not quiz), each with a "J-Archive ↗" link;
2. THEN kick off the async Wikipedia fetch and render its summary **below** when it resolves; on
   failure, the fingerprint remains fully usable.

Embedded in the research JSON as: `fingerprints` (cluster → phrase → {cues, example_clue_ids}),
the quiz refs (cluster → phrase/general → clue IDs), and a `clues` map (id → fields) containing
**only the union of clue IDs actually referenced** by a fingerprint example or a quiz ref — never
the full pool (see size). The tool looks up clue text by ID.

## Reproducibility & size
`clues_store.parquet` (full pool), the quiz refs, and `category_fingerprints.parquet` are
committed, regenerated by `jeopardy fingerprints` (offline; deterministic — TF-IDF is stable, no
RNG). The full clue pool (~33k answer-clues, ~2.9 MB of text alone) stays in the **offline**
artifact; the **embedded** page carries only the union of *referenced* clue IDs (fingerprint
examples + quiz selections) — pruning unreferenced clues is what actually bounds size (trimming
example/cue caps does not, if unreferenced clues remain). Verify the page stays near ~3 MB; if it
exceeds ~3.5 MB, lower the per-entity example/quiz caps (fewer referenced IDs).

## Testing
- Cue extraction: a repeated distinctive term surfaces with correct `support`/`total`; the
  entity's own name tokens and stopwords are excluded; a term in only one clue is not a cue;
  a unigram subsumed by a kept bigram is dropped; zero/one-clue and no-repeated-term states behave.
- Clue store / provenance: `clue_id` is stable and unique per clue; a merged-answer clue attaches
  to the canonical entity; a recent-only entity is covered; `category`/`game_id`/`year` present.
- Window contract: `example_clue_ids` always includes the entity's newest clue even when several
  older clues have higher cue coverage; the tool's filter keeps `year >= cutoff` incl. the newest
  eligible, and falls back (labeled) when none eligible.
- Embed pruning: the `clues` payload contains exactly the union of referenced IDs — no unreferenced
  clue is embedded.
- Research build: payload has `clues` + `fingerprints`; `render_html` contains cue-chip + J-Archive
  markup; existing render tests still pass.
- **Offline browser check** (new): with network/Wikipedia blocked, fingerprints still render and
  are usable; plus the normal browser pass (cues sensible, links open the right game).

## Out of scope (YAGNI / separate)
- The **practice session** (spaced repetition) — its own spec/plan next.
- LLM-authored cue blurbs; deep-linking to the specific clue on J-Archive; per-window cue sets;
  mention-based fingerprints for never-the-answer entities.

## Decisions (settled per spec review)
1. Cue method = distinctive TF-IDF terms **with support counts** + example clues + J-Archive links.
2. **Shared clue store** (`clues_store.parquet`, stable `clue_id`, intrinsic fields only); fingerprints and quiz both
   reference IDs but keep separate selection rules; quiz retains per-entity + general pools.
3. Cues all-time; **examples window-aware with the newest-eligible guarantee**.
4. Fingerprint renders immediately and independently of Wikipedia (which loads below, async).

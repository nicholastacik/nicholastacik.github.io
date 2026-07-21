# LLM Entity-Cleaning Pass (Token Quality v2) — Design

**Date:** 2026-07-21
**Status:** Approved (pending spec review)
**Part of:** the "Jeopardy data science" effort. A refinement of the token analysis after
first-look feedback: the rule-based entity extraction leaves diverse noise in the research
tool's lists that hand-rules can't cleanly judge (vague bare first names, interjections,
months, nationalities, Jeopardy "Clue Crew" production metadata, broken possessives like
Grey/Anatomy). This adds an LLM "second look" to validate and canonicalize entities.

## Goal

The research tool should show genuinely **studyable entities**. An LLM judges the candidate
entities per category type and marks each **keep/drop** + a **canonical form** (for merges the
rules miss), so noise is removed and variants collapse.

## Why an LLM (not more rules)

"Is this a studyable entity?" is a semantic judgment, not a string pattern: "John" vs "John
Adams", "Grey" vs "Grey's Anatomy", "May the month" vs "Theresa May", "Sarah of the Clue Crew"
(a clue presenter, not an answer) vs a real name. Rules keep losing because the distinction
lives in meaning + context. We've already compressed millions of clues to a few thousand
candidate entities, so the LLM only judges the shortlist, once.

## Architecture — two layers, then apply

### 1. Deterministic pre-filter (mechanical, in code)

Drop only the **100%-unambiguous** noise (no judgment needed, no LLM tokens spent):
- any phrase containing "Clue Crew" (case-insensitive) — Jeopardy presenter metadata;
- a tiny interjection stoplist: `Oh, Hi, Ah, Hey`.

Everything requiring judgment — months (May/March are name-ambiguous), nationalities, vague
first names, merges — is left to the LLM. Applied to the raw candidate counts.

### 2. LLM pass (in-session, per cluster)

For each of the 50 clusters, an in-session LLM (me, via subagents) judges that cluster's
candidate entities **with the cluster's context** (name + the ranked candidate phrases +
counts). It returns, per phrase: `keep` (bool) and `canonical` (str — the phrase itself if
kept as-is, or a fuller/joined form to merge into, e.g. `Grey`→`Grey's Anatomy`,
`Canadian`→`Canada`; `keep=False` drops it — vague names, months-as-months, nationalities,
junk). Fanned across subagents.

**Candidates judged:** the union of distinct `(cluster_id, phrase)` pairs that appear in the
current committed `category_tokens.parquet` (i.e. what's actually displayed, across all eras)
— that's the set worth cleaning. (Build ordering: current artifacts already exist → derive
candidates → LLM → decisions → apply on regeneration.)

**Review gate:** the drop/merge decisions are shown to the author before they're baked in
(same safety as the dedup merge-review). Tune the prompt / fix specific decisions if needed.

**Output (committed):** `posts/jeopardy_ds/entity_decisions.csv` —
`cluster_id, phrase, keep, canonical, source`. A curated committed artifact (like
`cluster_labels.csv`): the pipeline applies it deterministically; re-running the LLM may
differ. The `source` column (`llm | manual`) protects hand-fixes — see Iteration workflow.

### 3. Apply deterministically (token pipeline)

`jeopardy/analysis/tokens.py` reads `entity_decisions.csv` and applies it in `era_tokens`
**after** the existing dedup, for every era (decisions are keyed by `(cluster_id, phrase)`,
era-independent):
- drop phrases with `keep == False`;
- remap phrases whose `canonical != phrase` into the canonical (summing counts);
- phrases with no decision default to **keep** (conservative — covers any phrase not in the
  file, e.g. after future data changes).
Then re-rank count-desc and take top_n as today. Regenerate `category_tokens.parquet` /
`category_eras.parquet`, the research tool, and the post.

## New config

`ENTITY_DECISIONS_PATH = _POST_DIR / "entity_decisions.csv"`.

## Post story beat

Add a short methodology section (and one before/after example) to `index.qmd`: hand-rules got
most of the way, but couldn't judge "John" vs "John Adams" or spot "Clue Crew" metadata — so
an LLM took a second look and cleaned the lists. This is the "story addition" the author wants.

## Iteration workflow (this strategy will be tuned several times)

The design assumes multiple refinement rounds. Each is cheap because the LLM output is a plain
committed CSV the pipeline only *reads*:

- **Spot-fix a bad call:** edit the row in `entity_decisions.csv` directly (set `keep`/`canonical`,
  set `source=manual`). No LLM re-run.
- **Re-apply is fast:** `uv run --group analysis python -m jeopardy tokens` then `... research`
  regenerate the artifacts + tool from the CSV in ~a minute — **no re-embed/re-cluster** (the
  expensive steps never re-run). Then re-view.
- **Scoped re-judge:** the LLM can be re-run for just the cluster(s) you're unhappy with;
  decisions are keyed per `(cluster_id, phrase)`, so only those rows change.
- **Hand-fixes survive:** an LLM re-run only replaces `source==llm` rows; any row with
  `source==manual` is never overwritten. So a manual correction persists across future LLM passes.
- **Default-keep:** a phrase absent from the CSV defaults to keep, so partial/edited decision
  files always work (and new candidates after a data change stay until judged).
- **Prompt tuning:** if the whole strategy needs adjusting, edit the LLM prompt and re-run the
  pass (respecting `manual` rows); the tests and apply-logic are unchanged.

## Reproducibility

`entity_decisions.csv` is a curated committed artifact; the token pipeline applies it
deterministically. The deterministic pre-filter is pure code. No embed/cluster recompute
(stable taxonomy untouched). No new runtime dependency in the pipeline (the LLM pass is an
offline authoring step, like cluster naming; the pipeline only reads the CSV).

## Testing

- Unit-test the deterministic pre-filter (`is_mechanical_noise`): drops "Sarah of the Clue
  Crew" and "Oh"; keeps "Isaac Newton", "May", "April" (those are LLM's job, not the
  pre-filter's).
- Unit-test the apply-decisions logic: `keep=False` drops; `canonical != phrase` remaps and
  sums counts; a phrase absent from the decisions defaults to keep.
- The LLM pass is the reviewed curated step (not unit-tested).
- Browser check of the cleaned tool at the end.

## Out of scope (YAGNI)

- The "Oscars & Movie Quotes vs Movies" clustering-granularity question (a taxonomy tweak,
  separate — flag if the two movie clusters should be merged).
- Changing the applicability *sort metric* (the LLM cleans the visible entity lists; the
  deterministic pre-filter also removes Clue-Crew/interjection noise from the raw counts).
- Making the LLM a runtime pipeline dependency (it stays an offline authoring step).

# TV Tracker — build notes

Running notes for the blog post. Aggregate findings only: the real tracked
list is private (`tv-tracker/shows.json`, gitignored).

## Plan 1 dry runs (2026-09-27)

### Debugging the news call (sample list)

- First runs returned no news at 7- and 30-day windows. The sample list was
  genuinely quiet (one ended show, one between seasons, one renewed a year
  earlier), so "empty" was partly correct.
- A debug run with reasoning summaries (`reasoning.summary: "auto"`) showed
  the model finding relevant articles and still returning `[]`, and skipping
  one show's search entirely. Cause: the prompt asked it to self-filter
  ("an empty list is a good answer") while unsure of dates.
  Fix: search per show, propose every candidate, let validation check dates.
- The model cited a reconstructed "original report" URL it never retrieved.
  Validation dropped it correctly. Fix: URL must come from search results.
- The model embedded markdown citation links inside JSON strings. Stripped in
  code; prompt asks for plain text.
- Results are nondeterministic: identical prompts gave 0 and 1 items.
- Reasoning effort: news at `medium` found items `low` missed (~80k vs ~30k
  input tokens). Suggestions stay at `low`.

### Day 1 (real list, 11 shows, mostly adult animation)

- Suggestions: 3 proposed, 3 confirmed on TMDB, 0 dropped. Verdict: solid.
  One reason stretched a link to a tracked show.
- News: 1 proposed, 1 kept (trailer for a special found in neither TMDB nor
  TVmaze, an argument for the hybrid design). Verdict: useful.
  8 searches for 11 shows, so some shows went unsearched; watch for misses.
- Cost: ~21k in / 0.5k out, 2 searches (suggestions); ~72k in / 1.6k out,
  8 searches (news).

### For Plan 2

- A special listed in TMDB (`next_episode_to_air`) was missing from TVmaze.
  The schedule is TVmaze-only in the spec; fall back to TMDB's next episode
  (date only) when TVmaze has nothing.
- TMDB episode titles can be `TBA` on air day: confirms the spec's job-owned
  episode metadata updates.
- TMDB dates vs TVmaze UTC airstamps differ by a day for evening airings;
  convert everything to America/Toronto.

## Plan 2 go-live (2026-09-28)

- `setup` created the four tabs and imported 11 shows; the first local run
  appended 7 cards (1 season, 1 episode, 3 suggestions, 2 news) and backfilled
  every TVmaze id. A special missing from TVmaze reached This Week through the
  TMDB fallback.
- The first GitHub Actions run (manual dispatch) was green and appended
  nothing: card ids made the second run of the day a no-op.
- Final review caught a locale trap: formatted reads return booleans in the
  Sheet's language (a French Sheet says VRAI/FAUX), which would have made every
  show look inactive while reporting success. Reads are now unformatted.
- Actions logs are public on a Pages repo, so the job logs counts and
  positions, never show names; names live in the private Meta tab.

## Plan 3 app go-live (2026-09-28)

- Static ES-module app, no framework or build; 36 node tests on the pure
  modules, DOM wiring checked by hand. A Python test pins the app's column list
  to the job's so the two writers can't drift.
- Publishing the OAuth app to Production needed a home page, a privacy policy
  link and the authorized domain `nicholastacik.github.io` (a public-suffix
  domain, so it only covers this site). The "unverified app" screen appears
  once per account.
- First real writes from the browser: a Noted tap changed exactly two cells;
  a Track from search appended one Tracked row that the next job run completes.
- Final review caught a dead end: a wrong-account sign-in cached a token that
  kept hitting 403 for an hour. A 403 now clears it and offers another account.

# Pokémon TCG AI Battle Challenge — Agent + Blog Post Design

**Date:** 2026-08-05
**Status:** Approved pending user review

## Overview

Compete in The Pokémon Company's PTCG AI Battle Challenge on Kaggle, and ship an
interactive Quarto post about it. Two coupled competitions:

- **Simulation** (closes **2026-08-16**, 11 days out): submit a Python agent that
  plays ranked matches on a 24/7 automated ladder. Up to 5 submissions/day. No
  prize money — it is the proving ground.
- **Strategy** (closes **2026-09-13**, 39 days out): submit a written report on
  the agent's strategic logic. $240k pool; top 8 teams get $30k each and advance
  to finals in Japan. Judged on approach stability, deck design, and *Simulation
  performance*.

The tracks are coupled: a Strategy report with no ladder agent behind it has a
hard ceiling. So the plan has two deadlines, and the Aug 16 one is load-bearing.

The blog post is not a separate workstream. Its centerpiece — an annotated replay
viewer — is built from the agent's own decision traces, which we need for
debugging regardless.

## The environment

`cabt` engine, built by the University of Tokyo's Matsuo Institute on top of
`kaggle_environments` (observed `module_version` **1.32.3**). Not on public PyPI —
the engine (C++ headers under `ptcg_engine/`) and card
assets are distributed through the competition data page and require accepting
the rules.

The entire agent contract:

```python
def agent(obs_dict: dict) -> list[int]:
    return random.sample(range(len(obs_dict["select"]["option"])),
                         obs_dict["select"]["maxCount"])
```

Observation has three parts:

- `logs` — event log of past actions and game events
- `current` — board state; `None` during deck selection. Contains `players`,
  `stadium`, turn count, results. Each `PlayerState` has `active` (0–1 cards),
  `bench` (≤5), `hand`, `prize` (face-down entries are `None`), `deckCount`,
  `discard`, `handCount`, `benchMax`, and status flags (poisoned, burned, asleep,
  paralyzed, confused).
- `select` — `option` (the legal choices) and `maxCount`. **Return indices into
  `option`.**

Decks are CSVs of 60 card IDs, one per line, drawn from `all_card_data()`. During
the deck-selection observation the agent returns 60 card IDs.

The SDK ships **prebuilt shared libraries** — `libcg.dylib`, `libcg.so`,
`libcg-arm64.so`, `cg.dll` — loaded via `ctypes` in `cg/sim.py`. **No build step.**
The 60 C++ headers (1.3 MB, Competition-Use-Only licence) are reference source;
`CardImpl.h` is the authoritative card-resolution reference.

Other engine APIs: `battle_start`, `battle_select`, `battle_finish`,
`visualize_data`, `all_card_data` (returns exactly **1,267** entries, confirming
the pool size), `all_attack`, and `search_begin` / `search_step` / `search_end` /
`search_release`. Local play:

```python
env = make("cabt", configuration={"decks": [deck, deck]})
env.run([agent, agent])
env.render(mode="html")
```

Ladder ranking is TrueSkill-style (Gaussian μ/σ).

## Key decisions (with rationale)

| Decision | Rationale |
|---|---|
| Heuristic evaluator first, forward search layered on second | The engine enumerates legal moves, so we never implement PTCG's rules — only *score* pre-validated options. A 1,267-card game collapses into "rank this list," which is why rule-based agents are competitive here. Greedy ships fast and guarantees a ladder entry; search is the upgrade. |
| Hard fallback from search → greedy | State serialization is confirmed (`search_begin_input` is a base64 state blob in every observation) and the time budget is confirmed ample, but `search_step` throughput is unrun. The fallback is not a consolation prize: the greedy-vs-search delta becomes a *measured result* in the report — especially since the one observed deep-thinking agent lost. |
| No PPO / learned value function | No GPU, and 11 days to the Simulation deadline. A neural agent is a coin flip against a tuned heuristic on that timeline. |
| Interpretable evaluator over marginally-stronger black box | Pokémon has said they want *transferable insight into how the game is best played*. Strategy judging rewards explicability. This also happens to be what the blog post needs — the same property serves both. |
| Prize tempo as the evaluator's spine | PTCG is a race to six prizes. Nearly every good heuristic is a proxy for "am I taking prizes faster than they are." Anchoring the feature set here keeps it coherent rather than a bag of tricks. |
| Time bank manager, not a per-move timeout | The limit is **10 minutes per player per game, cumulative**; exceeding it is an instant loss. That makes time a resource to *allocate*, like a chess clock — spend deeply on pivotal decisions, instantly on trivial ones. See below. |
| Netdeck a proven archetype; do not invent a deck | Deck and policy must be co-designed — an evaluator that understands one line of play deeply beats a generic one. Archetype chosen after mining episode dumps. |
| Seat-balanced A/B testing, with volume instead of common random numbers | TCG outcomes are variance-dominated, but **shared-shuffle pairing is impossible** — `ApiBattleStart` takes only cards and reseeds from `std::random_device`, so no two games share a shuffle (verified empirically). Seat balancing still cancels the first-player advantage exactly, and at 39 ms/game the ~400 games needed for ±5 points costs ~16 core-seconds. See below. |
| Decision traces as the blog interface | The trace is instrumentation we need anyway ("why did it play *that*"). The replay viewer consumes the same artifact, so the post's centerpiece is a byproduct, not bolted-on work. |
| Static precomputed replays, not a live engine | The site is Quarto → static GitHub Pages and `cabt` is a gated Python package. Nothing in the post can call the engine live. Matches the `jeopardy_ds/research/` and `montreal_events/events/` precedent. |

## The time budget is a chess clock

**Verified 2026-08-05 against six real ladder episodes (12 agent-games, 964
decisions).** Numbers below are measured, not estimated.

Each agent gets **600 s per game**, and `remainingOverageTime` is exposed *inside
the observation* — the agent can read its own clock and adapt depth.

What the field actually spends: **median 13.5 s of 600 (2.2%)**, or 182 ms per
decision. Decisions per agent per game run 39–153, median 74, so full budget is
about **8 s per decision**. One agent of twelve (`flxwld`) spent 297.6 s (49.6%)
at 4.0 s/decision — and lost that game.

Two consequences:

1. **The unused clock is the opportunity.** ~98% of the budget sits idle across the
   field. A search agent has room for roughly 40× the median competitor's thinking
   per decision while staying inside budget. The caveat matters: the one agent
   visibly using its budget isn't dominating, so deep search over a weak evaluator
   is just an expensive way to be wrong. **Evaluator quality gates search depth**,
   which is why greedy-first staging is right.
2. **A turn is a sequence, not a move.** Playing your Supporter first constrains
   everything after it; the value of attaching Energy to a benched Pokémon only
   makes sense given a retreat planned three decisions later. Per-decision greedy
   scoring is myopic in exactly the way that loses games. Searching over the
   turn's action *sequence* is where the strength is — and `search_begin_input` in
   the observation is a base64 serialized engine state (1,938 occurrences
   observed), so state is forkable from any decision point. **This retires the
   spec's biggest architectural risk.**

Correction to an earlier assumption: forced moves are **not** the big win. Only
**10.8%** of decisions have a single option and 22.4% have ≤2; median is 5, tail
out to 32. Short-circuiting forced moves is nearly free so we still do it, but it
is a minor optimization rather than a strategy.

The bank manager tracks elapsed time and degrades search depth as the bank
depletes, with a guaranteed-cheap greedy path always available.

## Decision taxonomy

Options are typed variants. Observed frequency across 964 decisions:

| type | payload | n | reading |
|---|---|---|---|
| 8 | `area, inPlayArea, inPlayIndex, index` | 1625 | attach to in-play Pokémon |
| 7 | `index` | 1555 | plain indexed pick (hand card) |
| 3 | `area, index, playerIndex` | 1432 | target a card in a player's area |
| 14 | *(bare)* | 545 | pass / end |
| 13 | `attackId` | 329 | declare attack |
| 9 | `area, inPlayArea, inPlayIndex, index` | 288 | evolve (likely) |
| 10 | `area, index` | 274 | — |
| 12 | *(bare)* | 247 | done / decline |

Types 0–6 appear in the low tens. Engine is `cabt` **module_version 1.32.3** —
newer than the `1.30.1` pinned by `wmh/ptcg-abc`, so that pin is stale.

## Search is determinization, not simulation

**The single most important architectural finding**, invisible from the public
docs. `search_begin` does not merely fork the current state — it requires a
complete hypothesis about every hidden card:

```python
search_begin(agent_observation,
             your_deck,        # your remaining deck: cards known, order not
             your_prize,       # your 6 face-down prizes
             opponent_deck, opponent_prize, opponent_hand,
             opponent_active,  # only when their Active is face-down
             manual_coin=False)
```

You cannot search without first guessing the hidden state. This makes the agent a
**Perfect-Information Monte Carlo (determinization)** player: sample consistent
worlds, search each as if observable, average. Standard for Bridge and Skat; it is
the central algorithmic choice here, not an API detail.

Consequences:

1. **Own-deck bookkeeping.** We know our 60 cards (we submitted them) but not the
   shuffle. Subtracting everything seen yields an exact multiset for `your_deck` —
   strictly better information than we have about the opponent.
2. **Opponent-deck inference is the competitive edge.** Decks are public in the
   next day's episode dumps, and lists are copied verbatim (two teams submitted
   byte-identical Grimmsnarl decks). So: mine an archetype → decklist table from
   the dumps, fingerprint the opponent from their opening plays, then determinize
   against their *actual known 60* rather than a generic prior. This is the
   spine of the Strategy report.
3. **`manual_coin=True`** makes coin flips choosable during search, enabling
   deliberate best/worst-case branch exploration.

## Verified performance

Measured 2026-08-05, single core, random policy, real ladder decklists:

| metric | value |
|---|---|
| game wall time | **39 ms** (13 ms with the 9-distinct-card sample deck) |
| games/sec/core | **~25** |
| decisions/game | 157–253 (random play; real agents run shorter) |
| `search_begin` | **0.39 ms** |
| `search_step` | **13,001 steps/sec** |
| affordable steps per decision @ 8 s | **~104,000** |

Two planning consequences:

- **Statistical rigour is nearly free.** A 400-game comparison is ~16 core-seconds
  at random speed; even at 20 s/game for thinking agents it's ~2 core-hours, or
  minutes across the remote box. There is no excuse for under-powered A/Bs — which
  appears to be exactly the field's mistake.
- **Search depth is not the constraint; evaluator and determinization quality are.**
  104k steps per decision is ample tree. Benchmark with real decks only — the
  sample deck is 3× too fast to be representative.

## Measurement

The piece most likely to separate this entry from the field.

TCG outcomes are dominated by variance — mulligans, prize flips, draw order. A
50-game A/B showing 56% is uninformative: the 95% interval on 50 games is about
±14 points. Reaching ±5 points needs roughly 400 games per comparison.

**The textbook fix is unavailable.** Common random numbers — replaying the same
shuffle for both agents, standard practice in chess-engine testing — cannot be
done here. `ApiBattleStart(int* cards)` accepts only the decks, sets
`config.seed = std::random_device()()`, and then overwrites the RNG with a fresh
`std::seed_seq`. No seed parameter is exposed anywhere in the SDK. Confirmed
empirically: eight runs of one deterministic policy gave different winners and
decision counts.

What remains:

- **Seat balancing.** Going first is a systematic edge, so every matchup is played
  an equal number of times from each seat, cancelling that bias exactly. This is
  the reachable half of pairing.
- **Volume for the rest.** Shuffle luck must be beaten by sample size. Affordable:
  at 39 ms/game the ~400 games for a ±5-point interval is ~16 core-seconds, and
  the runner fans out across the remote box by process (the engine is a
  process-global singleton, so threads are not an option).
- **Wilson intervals, always.** Results are reported as a range with an explicit
  "does the interval clear 50%" verdict, so an under-powered comparison looks
  under-powered instead of persuasive.
- A **fixed benchmark gauntlet** so progress is measured against a stable
  yardstick, not a moving one: random agent, greedy-attack agent, and our own
  prior versions.

## Layout

```
ptcg/                        # root-level package (mirrors jeopardy/)
  agent/                     # self-contained submitted agent
  eval/                      # tournament runner, paired seeds, CIs, gauntlet
  decks/                     # deck CSVs (60 card IDs each)
  episodes/                  # fetch + parse Kaggle episode dumps
  trace/                     # decision-trace emission
  tests/
posts/ptcg/                  # post + served tool (mirrors posts/jeopardy_ds/)
  index.qmd                  # draft: true until promoted
  notes/build-log.md         # running decision journal, feeds the post
  replay/                    # standalone static viewer, copied verbatim
    index.html
    app.js
    styles.css
  replays/*.json             # precomputed annotated decision traces
```

`_quarto.yml` changes: add `posts/ptcg/replay/**` to `project.resources`;
exclude `posts/ptcg/notes/` from render. Public tool URL: `/posts/ptcg/replay/`.

## Trace format

One JSON per game. Per decision point: board snapshot, ranked options with
per-feature score breakdown, chosen action, search depth, nodes explored, time
spent. Plus per-game metadata (agents, decks, seed, result) and hand-written
commentary keyed to turn numbers.

Schema to be pinned during the spike, once a real observation has been dumped.

## The post

Spine: *a 1,267-card hidden-information game collapses into "rank this list" —
here is how far that gets you, and where it breaks.*

Beats:

1. The action-index API as the central simplification.
2. Prize tempo as the evaluator's spine.
3. The time budget as a chess clock, and forced-move short-circuiting.
4. The variance trap and seed-paired testing.
5. Greedy vs. search, measured.
6. The annotated replay viewer (centerpiece).
7. Honest ladder results, whatever they are.

## Staging

| Window | Goal |
|---|---|
| Day 1 | **Spike.** Install engine, run one game, dump one real observation, confirm schemas and `search_*` ergonomics. |
| Days 2–4 | Greedy evaluator + deck + eval harness. **Submit by day 4** — 5/day cap means we need days of iteration. |
| Days 5–11 | Turn-sequence search, weight tuning, gauntlet-driven iteration. Resubmit daily. |
| Aug 16 | Simulation closes. |
| Aug 17 – Sep 13 | Trace capture, replay viewer, post, Strategy report. |

Deadlines confirmed from the authenticated Kaggle API on 2026-08-05: Simulation
**2026-08-16 23:59**, Strategy **2026-09-13 23:59**. Press reports that said Aug 17
/ Sept 14 are wrong. Team counts: Strategy 311, Simulation 6,369.

## Risks

- ~~Engine unrun / unscoped build step~~ **Retired 2026-08-05.** Engine runs
  locally from prebuilt libraries; no build step. Games and search benchmarked.
- **Determinization quality is now the dominant risk.** Search requires guessing
  all hidden cards, so a bad hidden-state model poisons the whole tree no matter
  how deep it goes. This replaces "is search fast enough" as the central unknown.
- **Trace-emission cost is still unmeasured.** Games are 39 ms; if tracing adds
  much, it must be a debug-only flag rather than always-on.
- **No variance reduction via common random numbers** (see Measurement). Every
  comparison must be sized with `games_for_margin` up front rather than run and
  then interpreted hopefully.
- 11 days is tight. Kaggle packaging and dependency constraints reliably eat a
  day.
- Agent crashes are losses. Robustness (always return a legal fallback) is a
  correctness requirement, not polish — needs a test that fuzzes observations.
- Card-pool rules are "based on official PTCG rules but uniquely adjusted for
  this tournament," so real-world deck knowledge may not transfer cleanly.
- **Deep search may not pay.** The one observed agent spending real time lost. With
  104k steps/decision affordable, a loss like that points at the evaluator or the
  determinization rather than at search depth. If search doesn't beat greedy in the
  gauntlet, that is a finding to report, not a failure to hide.

## Open items

- ~~Accept the Simulation competition rules~~ **Done 2026-08-05**; engine
  downloaded to `ptcg/engine/` (gitignored, Competition-Use-Only licence).
- Deck archetype: decide after a proper archetype census (mine a full day's
  dataset, ~5,000 episodes, weighted by rating). **The press-derived guesses
  (Dragapult/Gardevoir/Lucario/Charizard) are wrong** — none appear in 12 real
  decklists. The pool is Mega-centric: Mega Kangaskhan ex leads the sample, with
  Mega Lopunny/Froslass ex, Marnie's Grimmsnarl ex and an Alakazam line. Field
  deck shape converges on 18–21 Pokémon / 32–34 Trainer / 7–10 Energy.
- Note: our submitted deck becomes public in the next day's episode dump, so any
  deck-building edge has a ~24h shelf life before it can be copied.
- Trace schema: pin once the engine runs. The episode JSON format
  (`steps[i][player].observation` + `.action` + `.visualize`) is a strong
  candidate to mirror, since it's already what the ladder emits.

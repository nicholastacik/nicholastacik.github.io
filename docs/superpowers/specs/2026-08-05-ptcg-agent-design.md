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

Other engine APIs: `battle_start`, `battle_select`, `battle_finish`,
`visualize_data`, `all_card_data`, `all_attack`, and `search_begin()` /
`search_step()` for state exploration. Local play:

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
| Seed-paired mirrored matches for all A/B testing | TCG outcomes are variance-dominated. Pairing cancels most of the luck term. See below. |
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

## Measurement

The piece most likely to separate this entry from the field.

TCG outcomes are dominated by variance — mulligans, prize flips, draw order. A
50-game A/B showing 56% is uninformative: the 95% interval on 50 games is about
±14 points. Reaching ±5 points needs roughly 400 games per comparison.

Mitigation: **seed-paired mirrored matches.** Play every matchup twice with the
same RNG seed and the seats/decks swapped, so both agents face the same draws
from both sides. This cancels most of the luck term and sharply cuts the games
needed for a given confidence. Standard in chess-engine testing, largely absent
from Kaggle notebooks.

Requirements:

- Tournament runner fanning out across the remote Linux box's cores.
- Fixed seeds, paired mirrors, win rate reported with confidence intervals.
- A **fixed benchmark gauntlet** so progress is measured against a stable
  yardstick, not a moving one: random agent, greedy-attack agent, the official
  pilot agents, and our own prior versions.

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

- **The engine is still unrun.** Schema, option taxonomy, time budget and search
  serialization are now verified from real ladder episodes, but nothing has been
  *executed* — the engine needs the Simulation competition's rules accepted (see
  Open items). Unknowns that remain: the C++ build step, whether `search_step` is
  fast enough to be worth calling, and trace-emission cost.
- **`ptcg_engine/` is C++ headers, not Python.** `cabt` wraps a compiled core
  (`CardImpl.h` alone is 878 KB). There is an unscoped build step. Upside: card
  behaviour is readable source rather than inferred from card text.
- 11 days is tight. Kaggle packaging and dependency constraints reliably eat a
  day.
- Agent crashes are losses. Robustness (always return a legal fallback) is a
  correctness requirement, not polish — needs a test that fuzzes observations.
- Card-pool rules are "based on official PTCG rules but uniquely adjusted for
  this tournament," so real-world deck knowledge may not transfer cleanly.
- **Deep search may not pay.** The one observed agent spending real time lost. If
  search doesn't beat greedy in the gauntlet, that is a finding to report, not a
  failure to hide.

## Open items

- **Accept the Simulation competition rules** (`pokemon-tcg-ai-battle`). The API
  reports `userHasEntered: False` and downloads 403. This gates the engine, local
  play, and any ladder submission — the critical-path blocker.
- Deck archetype: decide after mining episode dumps. Public signal points at
  Dragapult ex, Gardevoir ex, Lucario, Charizard as ladder-dominant; the episode
  dumps can confirm directly now that they're accessible.
- Trace schema: pin once the engine runs. The episode JSON format
  (`steps[i][player].observation` + `.action` + `.visualize`) is a strong
  candidate to mirror, since it's already what the ladder emits.

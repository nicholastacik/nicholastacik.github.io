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
`kaggle_environments` (pinned `1.30.1`). Not on public PyPI — the wheel and card
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
| Heuristic evaluator first, forward search layered on second | The engine enumerates legal moves, so we never implement PTCG's rules — only *score* pre-validated options. A ~2,000-card game collapses into "rank this list," which is why rule-based agents are competitive here. Greedy ships fast and guarantees a ladder entry; search is the upgrade. |
| Hard fallback from search → greedy | Search viability depends on `search_begin`/`search_step` ergonomics we have not run yet, and on the time budget. The fallback is not a consolation prize: the greedy-vs-search delta becomes a *measured result* in the report. |
| No PPO / learned value function | No GPU, and 11 days to the Simulation deadline. A neural agent is a coin flip against a tuned heuristic on that timeline. |
| Interpretable evaluator over marginally-stronger black box | Pokémon has said they want *transferable insight into how the game is best played*. Strategy judging rewards explicability. This also happens to be what the blog post needs — the same property serves both. |
| Prize tempo as the evaluator's spine | PTCG is a race to six prizes. Nearly every good heuristic is a proxy for "am I taking prizes faster than they are." Anchoring the feature set here keeps it coherent rather than a bag of tricks. |
| Time bank manager, not a per-move timeout | The limit is **10 minutes per player per game, cumulative**; exceeding it is an instant loss. That makes time a resource to *allocate*, like a chess clock — spend deeply on pivotal decisions, instantly on trivial ones. See below. |
| Netdeck a proven archetype; do not invent a deck | Deck and policy must be co-designed — an evaluator that understands one line of play deeply beats a generic one. Archetype chosen after mining episode dumps. |
| Seed-paired mirrored matches for all A/B testing | TCG outcomes are variance-dominated. Pairing cancels most of the luck term. See below. |
| Decision traces as the blog interface | The trace is instrumentation we need anyway ("why did it play *that*"). The replay viewer consumes the same artifact, so the post's centerpiece is a byproduct, not bolted-on work. |
| Static precomputed replays, not a live engine | The site is Quarto → static GitHub Pages and `cabt` is a gated Python package. Nothing in the post can call the engine live. Matches the `jeopardy_ds/research/` and `montreal_events/events/` precedent. |

## The time budget is a chess clock

10 minutes per player per *game*, not per move. A game runs ~25 turns a side, and
each turn is a sequence of decisions (play Supporter → attach Energy → evolve →
retreat → attack), so expect 150–300 decision points per game — roughly 2–4
seconds average per decision.

Two consequences:

1. **Short-circuit forced moves.** When `len(options) == 1` there is nothing to
   decide; return instantly at zero cost. Near-forced positions are similarly
   cheap. If forced/trivial decisions are a large fraction of the total, this
   hands most of the 10-minute bank to the ~30 decisions that actually decide the
   game. Highest-leverage cheap win in the whole agent.
2. **A turn is a sequence, not a move.** Playing your Supporter first constrains
   everything after it; the value of attaching Energy to a benched Pokémon only
   makes sense given a retreat planned three decisions later. Per-decision greedy
   scoring is myopic in exactly the way that loses games. Searching over the
   turn's action *sequence* is where the strength is, and `search_begin` /
   `search_step` exist to allow it.

The bank manager tracks elapsed time and degrades search depth as the bank
depletes, with a guaranteed-cheap greedy path always available.

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

Spine: *a 2,000-card hidden-information game collapses into "rank this list" —
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

Sources disagree on the Strategy deadline (Sept 13 vs Sept 14) and on Simulation
(Aug 16 vs Aug 17). Both are treated as the earlier date throughout; confirm
against the competition pages once authenticated.

## Risks

- **Everything downstream of installing the engine is unverified.** The
  observation schema, `search_*` ergonomics, and trace cost are inferred from
  public docs, not run. Day 1 is a spike specifically to close this. If the
  search API is unusable, we ship greedy and say so in the report.
- 11 days is tight. Kaggle packaging and dependency constraints reliably eat a
  day.
- Agent crashes are losses. Robustness (always return a legal fallback) is a
  correctness requirement, not polish — needs a test that fuzzes observations.
- Card-pool rules are "based on official PTCG rules but uniquely adjusted for
  this tournament," so real-world deck knowledge may not transfer cleanly.

## Open items

- Kaggle username needed to construct `~/.kaggle/kaggle.json` (the dropped file
  contains a bare API key, not the JSON wrapper).
- Deck archetype: decide after mining episode dumps. Public signal points at
  Dragapult ex, Gardevoir ex, Lucario, Charizard as ladder-dominant.

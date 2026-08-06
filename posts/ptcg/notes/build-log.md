---
draft: true
---
# Build log — Pokémon TCG AI Battle Challenge

A running dev journal. Each phase drops a short dated entry with the decisions
made and *why*. Raw material for the blog post — captured while the reasoning is
fresh, not reconstructed at the end.

This file is prose only; it does not execute at render time. Excerpts can be
pulled into `index.qmd` later (directly or via `{{< include >}}`).

---

## 2026-08-05 — Scoping: the competition is not over

Started from the assumption that we were too late. We weren't. Two independent
sources put the deadlines at:

- **Simulation: 2026-08-16** — 11 days out from today.
- **Strategy: 2026-09-14** — 40 days out.

The Strategy track is where the money is: $240k pool, top 8 teams take $30k each
and advance to finals in Japan in September. Strategy is judged on approach
stability, deck design, **and Simulation performance** — so the two tracks are
coupled. A report with no ladder agent behind it has a hard ceiling. That single
fact is what set the whole shape of the plan: sprint something onto the ladder by
Aug 16, then spend four weeks writing.

**Decision: compete for real** rather than blog-only or analysis-only. The ladder
gives us real numbers, and real numbers are also what makes the post good.

Sources worth citing in the post: [misprint's
explainer](https://www.misprint.com/posts/pokemon-ai-tcg-competition-explained),
[PokéBeach](https://www.pokebeach.com/2026/06/the-pokemon-company-launches-ai-competition-to-build-the-strongest-pokemon-tcg-player-featuring-300000-in-prizes),
[AICU's Japanese
writeup](https://note.com/aicu/n/ne9cc5c7b4157) (best technical detail of the
three), and the [cabt engine docs](https://matsuoinstitute.github.io/cabt/).

---

## 2026-08-05 — The API shape is the story

The engine is `cabt`, built by the University of Tokyo's Matsuo Institute on
`kaggle_environments`. The entire agent contract is:

```python
def agent(obs_dict: dict) -> list[int]:
    return random.sample(range(len(obs_dict["select"]["option"])),
                         obs_dict["select"]["maxCount"])
```

**This is the most important fact about the competition and probably the post's
lede.** The engine enumerates the legal moves for you and you return *indices*.
So you never implement Pokémon's rules — you only *score* options the engine has
already validated. A ~2,000-card game with byzantine interlocking card text
collapses into "rank this list."

That's why the leaderboard is full of rule-based agents rather than deep RL, and
it's the thing a reader who's never touched a card game will find surprising.

Observation has three parts: `logs` (event history), `current` (board state;
`None` during deck selection), `select` (`option` + `maxCount`). Decks are CSVs
of 60 card IDs from `all_card_data()`.

Also present: `search_begin()` / `search_step()` for state exploration — meaning
real forward search is on the table, not just greedy scoring. And
`env.render(mode="html")` emits an HTML replay, which is a gift for the post.

---

## 2026-08-05 — The 10-minute clock reframed the architecture

Found late in scoping, and it changed the design: the limit is **10 minutes per
player per game, cumulative** — not per move. Exceeding it is an immediate loss.

A game is ~25 turns a side, and each turn is a *sequence* of decisions (play
Supporter → attach Energy → evolve → retreat → attack), so 150–300 decision
points per game. Call it 2–4 seconds average.

Two consequences, both good post material:

**1. The budget is a resource to allocate, not a limit to respect.** It's a chess
clock. When `len(options) == 1` there is nothing to decide — return instantly at
zero cost. Short-circuiting forced and near-forced moves hands most of the bank to
the ~30 decisions that actually decide the game. Cheapest big win available.

**2. A turn is a sequence, not a move.** Playing your Supporter first constrains
everything after it. The value of attaching Energy to a benched Pokémon only makes
sense given a retreat you're planning three decisions later. Per-decision greedy
scoring is myopic in precisely the way that loses games. This is the argument for
searching over the turn's action sequence, and it's why `search_*` matters.

---

## 2026-08-05 — Architecture: greedy first, search second, hard fallback

Three separable pieces: **deck** (60 card IDs), **evaluator** (score candidate
states), **turn-sequence search** (enumerate action sequences, evaluate leaves).

- **Greedy evaluator ships first.** It guarantees a ladder entry, which is the
  non-negotiable part given Strategy depends on Simulation performance.
- **Search layers on second, with a hard fallback to greedy.** The fallback isn't
  a consolation prize — the greedy-vs-search delta becomes a *measured result* for
  the report.
- **No PPO / learned value function.** No GPU and 11 days; a neural agent is a
  coin flip against a tuned heuristic on that timeline.
- **Interpretability is a requirement, not a nicety.** Pokémon has said they want
  transferable insight into how the game is best played, and Strategy judging
  rewards explicability. Conveniently the same property is what the blog post
  needs — one design choice serving both.

**Evaluator spine: prize tempo.** PTCG is a race to six prizes, so nearly every
good heuristic is a proxy for "am I taking prizes faster than they are." Anchoring
there keeps the feature set coherent instead of a bag of tricks. Features hanging
off it: prize differential and expected prizes/turn, KO reachability both
directions, board development, energy efficiency, hand quality, denial (cutting
off evolution lines).

**Deck: netdeck a proven archetype, don't invent one.** Deck and policy have to be
co-designed — an evaluator that understands one line of play deeply beats a
generic one. Archetype chosen after mining the episode dumps. Public signal points
at Dragapult ex, Gardevoir ex, Lucario, Charizard.

Caveat to check during the spike: the card-pool rules are "based on official PTCG
rules but uniquely adjusted for this tournament," so real-world deck knowledge may
not transfer cleanly.

---

## 2026-08-05 — Measurement is the real engineering problem

Probably what separates this entry from the field, and a strong post beat.

TCG outcomes are variance-dominated — mulligans, prize flips, draw order. A
50-game A/B showing 56% tells you essentially nothing: the 95% interval on 50
games is about ±14 points. Getting to ±5 needs ~400 games per comparison.

**Fix: seed-paired mirrored matches.** Play every matchup twice with the same RNG
seed and the seats/decks swapped, so both agents see the same draws from both
sides. Cancels most of the luck term and sharply cuts the games needed for a given
confidence. Standard practice in chess-engine testing; largely absent from the
Kaggle notebooks on this competition.

Plus a **fixed benchmark gauntlet** — random, greedy-attack, official pilot
agents, our own prior versions — so progress is measured against a stable
yardstick rather than a moving one. Fanned out across the remote Linux box's
cores.

---

## 2026-08-05 — Blog: annotated replay viewer, fed by debug traces

Interactive centerpiece is an **annotated replay viewer**: step through full games
turn by turn, with the board on one side and the agent's internals on the other
(ranked options, per-feature score breakdown, search depth, nodes), plus
hand-written commentary on the pivotal turns.

The elegant part: **this is instrumentation we want anyway.** "Why on earth did it
play that" is the question we'll ask a hundred times while debugging. The viewer
consumes the same trace artifact, so the post's centerpiece is a byproduct of the
debugging tooling rather than extra work bolted on at the end.

Constraint that ruled out the alternative: the site is Quarto → static GitHub
Pages, and `cabt` is a gated package. Nothing in the post can call the engine
live, so "play against the bot in the browser" is out. Everything is precomputed
JSON + client-side JS. Same pattern as `jeopardy_ds/research/` and
`montreal_events/events/`.

Considered and set aside (both still viable later): a **decision explorer**
(reader guesses the move, then sees the agent's ranking — quiz-style) and a **meta
explorer** (archetype share over time, matchup matrix from the public episode
dumps). The meta explorer is cheap and might make a good second figure even if it
isn't the centerpiece.

---

## 2026-08-05 — Blocked on Kaggle credentials

`~/.kaggle/kaggle.json` was dropped but contains a **bare API key**, not the JSON
wrapper Kaggle hands you — no `username` field, so the CLI can't authenticate.
Tried to recover the username from the repo (no Kaggle handle anywhere in it), and
declined to probe candidate usernames against the auth endpoint since that's
indistinguishable from credential stuffing.

Need the Kaggle username to proceed. Everything downstream of installing the
engine — observation schema, `search_*` ergonomics, trace cost — is still
inferred from public docs rather than run. Day 1 is a spike specifically to close
that gap.

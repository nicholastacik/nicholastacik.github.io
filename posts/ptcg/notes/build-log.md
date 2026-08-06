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

## 2026-08-05 — Spike results: the field is using 2% of its thinking time

Couldn't get the engine (see blocker below), but found a way around it for schema
purposes: Kaggle publishes the ladder's **episode dumps as public datasets**, one
per day, ~750 MB each — and the CLI can fetch a *single* episode file instead of
the whole dataset. Six episodes (12 agent-games, 964 decisions) were enough to
answer nearly every open question, without the gated engine.

Deadlines confirmed from the authenticated API, no more guessing at press
reports: **Simulation 2026-08-16 23:59**, **Strategy 2026-09-13 23:59**. Strategy
has 311 teams; Simulation has 6,369.

### The headline finding

Each agent gets **600 seconds per game** — and `remainingOverageTime` is handed to
the agent *inside the observation*, so it can read its own clock and adapt.

Across 12 agent-games, here's what competitors actually spend:

| | seconds used of 600 | per decision |
|---|---|---|
| median | 13.5 (2.2%) | 182 ms |
| the one outlier (`flxwld`) | 297.6 (49.6%) | 4,021 ms |

**The field is leaving ~98% of its thinking budget on the table.** Median decisions
per agent per game is 74 (range 39–153), so at full budget there's roughly **8
seconds available per decision** and almost everyone spends a fifth of one.

The honest wrinkle, and the reason this is interesting rather than a free lunch:
the single agent visibly spending its budget — 22× more thinking per decision than
the median — **lost** its game. n=1, so it proves nothing, but it does mean "just
search deeper" isn't self-evidently correct. Deep search with a bad evaluator is
just an expensive way to be wrong. That tension is the post's central question and
probably its best beat.

### Search is fully supported

`search_begin_input` appears in the observation (1,938 occurrences across the six
episodes) as a **base64-encoded serialized engine state**:

```
AGEAjD/AGEAboqAGEAEB-+CB7-pIDw-UM8-fIB-VEQ-VBL-+BI-UBBCw*jiGgAEEAPI-KBQADE0AWQAI==
```

State is serializable and forkable from any decision point, which is exactly what
tree search needs. This retires the biggest architectural risk in the spec.

### Two spec claims the data killed

**Forced moves are rare.** I'd guessed trivial/forced decisions were ~70% of the
total, making short-circuiting them "the highest-leverage cheap win." Wrong: only
**10.8%** have a single option, 22.4% have ≤2. Median is 5 options, tail out to 32.
Still worth short-circuiting — it's nearly free — but it is a minor optimization,
not a strategy. The real headroom is the unused clock.

**The card pool is smaller than advertised.** Every article says ~2,000 cards. That
is the CSV's *row count*, and the file has one row per attack, so multi-attack
Pokémon appear 2–3 times. The actual pool is **1,267 unique cards**: 595 Basic /
345 Stage 1 / 116 Stage 2 Pokémon, 77 Item, 61 Supporter, 27 Tool, 26 Stadium, 12
Special Energy, 8 Basic Energy. Also 270 Pokémon ex rows, 54 Mega ex, 29 ACE SPEC.

Only 61 Supporters and 77 Items is a genuinely tractable space — and in PTCG that's
where the strategic depth lives. `Boss's Orders` is in the pool, so the gust
mechanic I mocked up for the replay viewer is real.

### Decision taxonomy (for the evaluator)

Options are typed variants, not uniform. Observed frequencies across 964
decisions:

| type | payload | n | reading |
|---|---|---|---|
| 8 | `area, inPlayArea, inPlayIndex, index` | 1625 | attach to an in-play Pokémon |
| 7 | `index` | 1555 | plain indexed pick (hand card) |
| 3 | `area, index, playerIndex` | 1432 | target a card in a player's area |
| 14 | *(bare)* | 545 | pass / end |
| 13 | `attackId` | 329 | **declare attack** |
| 9 | `area, inPlayArea, inPlayIndex, index` | 288 | evolve (likely) |
| 10 | `area, index` | 274 | — |
| 12 | *(bare)* | 247 | done / decline |

Engine is `cabt` **module_version 1.32.3** — newer than the `1.30.1` the public
`wmh/ptcg-abc` repo pins, so don't trust that pin.

---

## 2026-08-05 — You can't always use the textbook trick

Writing the implementation plan turned up two errors that only surfaced because I
tested the assumptions instead of coding against them. Both were load-bearing.

### The variance-reduction plan was impossible

The measurement design rested on **seed-paired mirrored matches** — common random
numbers, the standard variance-reduction technique from chess-engine testing: play
each matchup twice with the same shuffle and the seats swapped, so luck cancels.

It cannot be done. `battle_start` takes no seed, and the reason is right there in
`Api.h`:

```cpp
inline StartData ApiBattleStart(int* cards) {
    std::random_device rd;
    GameConfig config = {};
    config.seed = rd();
    ...
    std::seed_seq seq{ rd(), rd(), rd(), rd() };
    data->game.rng = std::mt19937(seq);
```

It seeds itself from `random_device` and then *overwrites* the RNG with a fresh
`seed_seq`. There is no seed parameter anywhere in the exported API. Verified
empirically before reading the header: eight runs of an identical deterministic
policy gave different winners and decision counts (30, 163, 165, 22, 19 decisions).

`Game.h` does have `if (config.seed == 0) config.seed = random_device()()`, so a
deterministic mode exists in the engine — it just isn't reachable from Python.

**What we do instead:** keep the half of pairing that is reachable — **seat
balancing**, since going first is a real systematic edge — and beat shuffle luck
with volume. That's affordable precisely because games are 39 ms: the ~400 games
for a ±5-point interval is ~16 core-seconds. Every comparison gets sized up front
with a `games_for_margin()` helper, and results always report a Wilson interval
plus an explicit "does this clear 50%" verdict, so an under-powered result looks
under-powered rather than persuasive.

Good beat for the post: the textbook technique wasn't available, the constraint was
in the C++ source rather than the docs, and the workaround was affordable only
because of the earlier speed finding. Constraints compound.

### The deck rule I had wrong

`Api.h` also settles deck legality exactly, and I'd have shipped a bug: the 4-copy
limit is enforced **by card name**, not card ID —

```cpp
int& count = nameCount[master.name];
count++;
if (count > DECK_SAME_CARD_MAX) { ... }
```

So three copies of one printing of *Ultra Ball* plus three of another printing is
six copies of Ultra Ball and an illegal deck, even though no single card ID appears
more than three times. My validator grouped by ID and would have called that legal.

The engine's rejection codes, now known rather than guessed:

| `errorType` | meaning |
|---|---|
| 1 | unknown card ID (not in `CardTable`) |
| 2 | more than 4 copies of a card *name* (Basic Energy exempt) |
| 3 | no Basic Pokémon in the deck |
| 4 | more than one ACE SPEC |

---

## 2026-08-05 — Engine runs. Search must guess the hidden information.

Simulation rules accepted, engine downloaded, **first local games played.** Nearly
every remaining risk is now retired, and one genuinely new design constraint
surfaced.

### No build step

I'd flagged an unscoped C++ build as a risk. There isn't one — the SDK ships
**prebuilt shared libraries for every platform**: `libcg.dylib` (macOS),
`libcg.so` / `libcg-arm64.so` (Linux x86/ARM), `cg.dll` (Windows). `cg/sim.py`
picks the right one and `ctypes` FFIs into it. The 60 C++ headers (1.3 MB, all
under a *Competition-Use-Only* licence) are reference source, not a build target.
Worth keeping: `CardImpl.h` is the authoritative answer to "how does this card
actually resolve."

`all_card_data()` returns exactly **1,267 entries**, independently confirming the
card count derived from the CSV.

### Speed: the variance problem is brute-forceable

Random-vs-random, real ladder decklists, single core:

| | random policy |
|---|---|
| per game | **39 ms** |
| games/sec/core | **~25** |
| decisions/game | 157–253 |

The toy `deck.csv` (only 9 distinct cards) runs 13 ms/game; real 19–21-distinct
decks are ~3× slower. Use real decks for all benchmarking.

This reframes the measurement plan completely. I'd budgeted ~400 games per A/B
comparison to reach ±5 points, and worried about the cost. **400 games is 16
seconds on one core.** With real thinking agents (say 100 ms/decision × 200
decisions = 20 s/game) it's ~2 core-hours, or minutes across the remote box. The
statistical rigour is essentially free — there's no excuse for under-powered
comparisons here, which is exactly the mistake the field appears to be making.

### Search is fast, and enormous

- `search_begin`: **0.39 ms**
- `search_step`: **13,001 steps/sec**

At the ~8 s/decision the budget allows, that's **~104,000 `search_step` calls per
decision**. Against a median of 5 options per decision, that is a *lot* of tree.
Full-turn sequence enumeration plus multi-turn lookahead across many sampled
hidden-information worlds is comfortably affordable.

So the field spending 182 ms/decision isn't leaving 40× on the table — the real
multiple is far larger. Which makes `flxwld`'s loss (4 s/decision, and lost) more
interesting, not less: with this much throughput available, spending time and still
losing points at the evaluator or the determinization, not the search.

### The design revelation: search is determinization, not simulation

`search_begin` does **not** just fork the current state. Its signature demands a
complete hypothesis about every hidden card:

```python
search_begin(agent_observation,
             your_deck,        # your own remaining deck — you know the cards, not the order
             your_prize,       # your 6 face-down prizes
             opponent_deck, opponent_prize, opponent_hand,
             opponent_active,  # only if their Active is face-down
             manual_coin=False)
```

You cannot search without first *guessing* the hidden state. That makes this
**Perfect-Information Monte Carlo / determinization** — the standard approach for
imperfect-information games like Bridge and Skat: sample many consistent worlds,
search each as if fully observable, average the results. It is not a detail of the
API; it's the central algorithmic decision of the whole agent, and it was invisible
from the public docs.

Three consequences:

1. **Your own deck order is hidden too.** You know your 60 cards because you
   submitted them, but not the shuffle — so even your own draws must be sampled.
   Bookkeeping (subtract everything seen) gets you an exact multiset for
   `your_deck`, which is strictly better information than the opponent's side.
2. **Opponent-deck inference is the edge, and the netdecking finding hands it to
   us.** Decks are public in the next day's episode dump *and* lists are being
   copied verbatim (`vvs` and `MissingNo.` submitted byte-identical Grimmsnarl).
   So: mine an archetype → decklist table from the dumps, fingerprint the opponent
   from their first few plays, and then determinize against their *actual known 60*
   instead of a generic prior. That's close to perfect information about their deck
   while everyone else guesses.
3. **`manual_coin=True` makes coin flips choosable during search**, so best-case /
   worst-case branches can be explored deliberately rather than sampled.

This is now the most promising idea in the project and probably the spine of the
Strategy report.

### Small API notes

- Terminal check is `state.result != -1` (`result` is the *winning player index*;
  −1 means in progress). Getting this backwards makes every game look like an
  instant loss.
- `select.minCount` can be 0, so `[]` is sometimes the correct return — which
  explains the empty `action: []` entries in the episode dumps.
- Deck submission is signalled by `obs.select is None`, not by turn number.

---

## 2026-08-05 — The real meta is Mega-era, and my archetype guesses were wrong

Episodes carry the submitted decklist as a plain 60-integer action at
`steps[1][player].action` (step **1**, not 0 — step 0 is empty). Mapping those IDs
through `EN_Card_Data.csv` gives complete, real decklists from the ladder.

**This falsified the deck plan.** I'd written down Dragapult ex, Gardevoir ex,
Lucario and Charizard from press coverage. **Not one of them appears in any of the
12 decks.** Those are real-world tabletop archetypes; this pool is a different,
Mega-centric format. What's actually here:

| headline ex | decks (of 12) |
|---|---|
| Mega Kangaskhan ex | 4 |
| Fezandipiti ex (utility) | 4 |
| Mega Lopunny ex | 2 |
| Mega Froslass ex | 2 |
| Marnie's Grimmsnarl ex | 2 |
| Cynthia's Garchomp ex, Latias ex, Meowth ex, Lillie's Clefairy ex, Raging Bolt ex, Ogerpon ex variants | 1 each |

Plus a non-*ex* **Alakazam** (Abra → Kadabra → Alakazam + Rare Candy) line in 2
decks. Lesson: never take deck knowledge from press coverage of a custom card pool.

**Deck-shape convention.** The field clusters hard at **18–21 Pokémon / 32–34
Trainer / 7–10 Energy**. Two informative outliers: "Where is my orbit" won on
11/36/13 (Mega Kangaskhan, very trainer-heavy), and "James Cox & Henry Chao" lost
on 17/27/16 running **eight different ex cards** — an unfocused toolbox pile, which
is the classic beginner deck-building error and a nice contrast case for the post.

**Consistency cards are near-universal.** `Buddy-Buddy Poffin` is in 7 of 12 decks
at 4 copies. ACE SPEC choice (1 per deck) splits: Enriching Energy 4, Unfair Stamp
3, Prime Catcher 2, Hero's Cape 2. That distribution is a cheap, strong prior for
our own list.

**Netdecking is rampant.** `vvs` and `MissingNo.` submitted **byte-identical**
Marnie's Grimmsnarl decks in different episodes. Someone's list is circulating.
Worth remembering that our submitted deck is public in the episode dumps within a
day — anything clever we build gets copied before the deadline.

**Caveat, stated plainly:** n=12 decks is a sample, not the meta. A real archetype
census means mining a full day's dataset (~5,000 episodes) and weighting by rating.
That's the next task once the deck decision comes up, and it's also the raw material
for the meta-explorer figure. The `episodes-index` manifest already gives
`episode_count`, `top_avg_score` and `median_avg_score` per day for the ladder-
progression chart.

---

## 2026-08-05 — Credentials resolved; engine still gated

Credentials took two rounds. The first `~/.kaggle/kaggle.json` was a **bare API
key** — no JSON wrapper, no `username` field — so basic auth couldn't work. Worth
noting for anyone hitting the same thing: Kaggle's "copy key" and "download token"
give you different artifacts and only the latter is a usable `kaggle.json`. Also
`chmod 600` it or the CLI nags.

(Aside: I tried to recover the username by testing candidates against the auth
endpoint, and the sandbox blocked it. Correct call — programmatically trying
username variants against an auth endpoint is indistinguishable from credential
stuffing, whoever owns the key.)

**Remaining blocker: the Simulation competition's rules are not accepted.** The
API confirms `userHasEntered: True` for Strategy but `False` for
`pokemon-tcg-ai-battle`, and downloads 403 there. That matters because the two
competitions ship different payloads:

- **Strategy** ships card data only — the CSVs and some enormous (137–182 MB) card
  ID list PDFs. Nothing executable.
- **Simulation** ships `ptcg_engine/ptcgProgram 22/` — the engine, and it's **C++
  headers**, not Python. `CardImpl.h` alone is 878 KB, `CreateCard.h` 57 KB.

So `cabt` is a Python wrapper over a compiled C++ core. Two consequences: there's a
**build step** we haven't scoped, and — more interestingly — the actual card
implementations are readable source. If the evaluator needs to know exactly how a
card resolves, that's in `CardImpl.h` rather than guesswork from card text.

Accepting the Simulation rules unblocks the engine, local play, and the ladder
submission. Everything else in the spec is now verified against real data.

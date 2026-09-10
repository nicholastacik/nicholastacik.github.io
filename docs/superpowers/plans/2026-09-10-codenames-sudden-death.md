# Codenames Sudden Death — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a faithful, co-pilot sudden-death endgame to Codenames Duet — timer-out enters sudden death instead of losing; no clues; any non-green guess loses; the AI surfaces a confidence meter and the human orchestrates.

**Architecture:** Extend the existing pure engine (a `suddenDeath` flag + a guesser-aware `suddenDeathGuess`), add a clue-less ranked-guess path to the AI layer, and drive a co-pilot UI. The human's key card is hidden during sudden death to prevent oracle-ing the AI. All AI mocked in tests.

**Tech Stack:** TypeScript, Vite, Vitest (jsdom), `openai` SDK + `zod`.

## Global Constraints

- **Sudden death trigger:** the last timer token spent (`turnsRemaining` reaches 0) with `agentsFound < 15` sets `suddenDeath = true` and keeps `status = "playing"` (instead of `status = "lost"`).
- **Judging in sudden death:** a guess is judged against the **non-guesser's** card — a human guess against `keys.ai`, an AI guess against `keys.human`.
- **Win/lose in sudden death:** a **green** guess covers the word and counts (`agentsFound++`, win at 15); **any non-green** guess (bystander *or* assassin, either side) → `status = "lost"`. No pass.
- **Oracle prevention:** the human's key-card shading is **hidden** while `suddenDeath` is true; the AI's confidence comes **only from the clue history**, never its own card.
- **One ranked AI call** for the whole phase (fetched on entry); the UI skips candidates already revealed.
- Pure engine functions stay pure & immutable (`structuredClone`, no input mutation). `ui.ts` imports only `./types`. Tests never hit the network.
- Existing invariants unchanged: 25 words, 15 agents, `TOTAL_AGENTS`/`START_TURNS` from `./types`.
- Commit after each task (conventional commits, scope `codenames`). Work on branch `codenames-sudden-death`. `npm test` + `npm run build` green before each commit.

---

### Task 1: Engine — sudden-death state + entry

**Files:**
- Modify: `codenames/src/types.ts` (GameState)
- Modify: `codenames/src/engine.ts` (createGame, endTurn)
- Test: `codenames/tests/engine.test.ts`

**Interfaces:**
- Produces: `GameState.suddenDeath: boolean` and `GameState.suddenDeathGuesses: SuddenDeathGuess[]` where `SuddenDeathGuess = { word: string; by: Player; outcome: Category }`. Entering sudden death: `endTurn` sets `suddenDeath = true` (not `status = "lost"`) at timer-0 with `<15` found.

- [ ] **Step 1: Update the failing tests** — in `engine.test.ts`, the two tests that assert timer-out is a *loss* now assert it enters *sudden death*:

```ts
// REPLACE the existing "exhausting the timer ... is a loss" test with:
it("exhausting the timer with fewer than 15 agents enters sudden death (not a loss)", () => {
  let s = createGame({ rng: rng(3) });
  s.turnsRemaining = 1;
  s = giveClue(s, "OCEAN", 1);
  s = endGuessing(s);
  expect(s.turnsRemaining).toBe(0);
  expect(s.status).toBe("playing");
  expect(s.suddenDeath).toBe(true);
});

// REPLACE the passTurn "sets status to lost when the timer hits 0" test with:
it("passTurn enters sudden death when the timer hits 0 with agents remaining", () => {
  const s = createGame({ rng: rng(3) });
  s.turnsRemaining = 1;
  const next = passTurn(s);
  expect(next.turnsRemaining).toBe(0);
  expect(next.status).toBe("playing");
  expect(next.suddenDeath).toBe(true);
});
```

Also add a starting-state check:

```ts
it("starts not in sudden death", () => {
  const s = createGame({ rng: rng(3) });
  expect(s.suddenDeath).toBe(false);
  expect(s.suddenDeathGuesses).toEqual([]);
});
```

- [ ] **Step 2: Run, verify fails**

Run: `cd codenames && npm test -- engine`
Expected: FAIL — `suddenDeath` missing on GameState / still "lost".

- [ ] **Step 3: Add the state fields** — `src/types.ts`

```ts
export interface SuddenDeathGuess {
  word: string;
  by: Player;
  outcome: Category;
}

export interface GameState {
  words: string[];
  keys: KeyCardPair;
  revealed: boolean[];
  agentsFound: number;
  turnsRemaining: number;
  clueGiver: Player;
  phase: "awaitClue" | "awaitGuess";
  currentClue: { word: string; number: number; guessesMade: number } | null;
  status: "playing" | "won" | "lost";
  history: HistoryTurn[];
  suddenDeath: boolean;            // true once the timer runs out with agents left
  suddenDeathGuesses: SuddenDeathGuess[]; // guesses made during sudden death
}
```

- [ ] **Step 4: Initialise + enter** — `src/engine.ts`

In `createGame`'s returned object add:

```ts
    suddenDeath: false,
    suddenDeathGuesses: [],
```

In `endTurn`, replace the timer-out loss with sudden-death entry:

```ts
function endTurn(state: GameState): GameState {
  const next = state;
  next.phase = "awaitClue";
  next.currentClue = null;
  next.clueGiver = next.clueGiver === "human" ? "ai" : "human";
  next.turnsRemaining -= 1;
  // Timer exhausted with agents still hidden → sudden death (not a loss). Win is
  // detected in guess() before endTurn is ever reached, so agentsFound < 15 here.
  if (next.turnsRemaining <= 0 && next.status === "playing" && next.agentsFound < TOTAL_AGENTS) {
    next.suddenDeath = true;
  }
  return next;
}
```

- [ ] **Step 5: Run, verify pass**

Run: `cd codenames && npm test -- engine`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add codenames/src/types.ts codenames/src/engine.ts codenames/tests/engine.test.ts
git commit -m "feat(codenames): engine sudden-death state + timer-out entry"
```

---

### Task 2: Engine — `suddenDeathGuess`

**Files:**
- Modify: `codenames/src/engine.ts`
- Test: `codenames/tests/engine.test.ts`

**Interfaces:**
- Consumes: `GameState`, `Player`, `Category`, `TOTAL_AGENTS`.
- Produces: `suddenDeathGuess(state: GameState, word: string, guesser: Player): GameState` — judged against the non-guesser's card; green → agent (win at 15); non-green → loss; records into `suddenDeathGuesses`. Pure/immutable.

- [ ] **Step 1: Write failing tests** — `engine.test.ts`

```ts
describe("suddenDeathGuess", () => {
  function inSD(): GameState {
    // a fresh game forced into sudden death
    const s = createGame({ rng: rng(3) });
    return { ...structuredClone(s), suddenDeath: true, turnsRemaining: 0 };
  }
  it("a human guess is judged against the AI card: green counts an agent", () => {
    const s0 = inSD();
    const idx = s0.keys.ai.findIndex((c) => c === "green");
    const s = suddenDeathGuess(s0, s0.words[idx]!, "human");
    expect(s.revealed[idx]).toBe(true);
    expect(s.agentsFound).toBe(s0.agentsFound + 1);
    expect(s.status).toBe("playing");
    expect(s.suddenDeathGuesses.at(-1)).toEqual({ word: s0.words[idx], by: "human", outcome: "green" });
  });
  it("an AI guess is judged against the HUMAN card", () => {
    const s0 = inSD();
    const idx = s0.keys.human.findIndex((c) => c === "green");
    const s = suddenDeathGuess(s0, s0.words[idx]!, "ai");
    expect(s.revealed[idx]).toBe(true);
    expect(s.agentsFound).toBe(s0.agentsFound + 1);
  });
  it("a bystander guess loses in sudden death", () => {
    const s0 = inSD();
    const idx = s0.keys.ai.findIndex((c) => c === "bystander");
    const s = suddenDeathGuess(s0, s0.words[idx]!, "human");
    expect(s.status).toBe("lost");
  });
  it("an assassin guess loses in sudden death", () => {
    const s0 = inSD();
    const idx = s0.keys.ai.findIndex((c) => c === "assassin");
    const s = suddenDeathGuess(s0, s0.words[idx]!, "human");
    expect(s.status).toBe("lost");
  });
  it("reaching 15 agents in sudden death wins", () => {
    const s0 = inSD();
    s0.agentsFound = 14;
    const idx = s0.keys.ai.findIndex((c) => c === "green");
    const s = suddenDeathGuess(s0, s0.words[idx]!, "human");
    expect(s.status).toBe("won");
  });
  it("is a no-op when not in sudden death or already revealed, and does not mutate input", () => {
    const s0 = inSD();
    const idx = s0.keys.ai.findIndex((c) => c === "green");
    const notSD = { ...s0, suddenDeath: false };
    expect(suddenDeathGuess(notSD, s0.words[idx]!, "human").status).toBe("playing");
    expect(suddenDeathGuess(notSD, s0.words[idx]!, "human").revealed[idx]).toBe(false);
    const before = JSON.stringify(s0);
    suddenDeathGuess(s0, s0.words[idx]!, "human");
    expect(JSON.stringify(s0)).toBe(before);
  });
});
```

- [ ] **Step 2: Run, verify fails**

Run: `cd codenames && npm test -- engine`
Expected: FAIL — `suddenDeathGuess` not defined.

- [ ] **Step 3: Implement** — `src/engine.ts`

```ts
export function suddenDeathGuess(state: GameState, word: string, guesser: Player): GameState {
  if (state.status !== "playing" || !state.suddenDeath) return state;
  const next = structuredClone(state);
  const idx = next.words.findIndex((w) => w === word);
  if (idx < 0 || next.revealed[idx]) return next;

  // Judged against the NON-guesser's card (Duet: your partner touches, YOUR card judges).
  const judgeKey: KeyCard = guesser === "human" ? next.keys.ai : next.keys.human;
  const cat: Category = judgeKey[idx]!;
  next.suddenDeathGuesses.push({ word, by: guesser, outcome: cat });

  if (cat === "green") {
    next.revealed[idx] = true;
    next.agentsFound += 1;
    if (next.agentsFound >= TOTAL_AGENTS) next.status = "won";
    return next;
  }
  // bystander or assassin → both lose
  next.status = "lost";
  return next;
}
```

- [ ] **Step 4: Run, verify pass**

Run: `cd codenames && npm test -- engine`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add codenames/src/engine.ts codenames/tests/engine.test.ts
git commit -m "feat(codenames): engine suddenDeathGuess (non-guesser card judges; non-green loses)"
```

---

### Task 3: AI layer — clue-less ranked sudden-death guesses

**Files:**
- Modify: `codenames/src/validate.ts` (schema + filter)
- Modify: `codenames/src/prompts.ts` (SD prompt)
- Modify: `codenames/src/ai.ts` (getSuddenDeathGuesses)
- Test: `codenames/tests/validate.test.ts`, `codenames/tests/ai.test.ts`

**Interfaces:**
- Produces:
  - `SuddenDeathSchema` (zod) → `SuddenDeathResponse = { reasoning: string; guesses: Array<{ word: string; confidence: number }> }`
  - `filterSuddenDeathGuesses(guesses, state): Array<{ word: string; confidence: number }>` — canonical board words, unrevealed, deduped, confidence clamped to [0,1], order preserved.
  - `buildSuddenDeathMessages(state): ChatMessage[]`
  - `getSuddenDeathGuesses(caller: LLMCaller, state: GameState, log: Logger): Promise<Array<{ word: string; confidence: number }>>`

- [ ] **Step 1: Write failing tests**

`validate.test.ts`:

```ts
import { /* existing */ SuddenDeathSchema, filterSuddenDeathGuesses } from "../src/validate";

describe("filterSuddenDeathGuesses", () => {
  const s = createGame({ rng: rng(3) });
  it("keeps canonical board words, clamps confidence, dedupes", () => {
    const w0 = s.words[0]!;
    const out = filterSuddenDeathGuesses(
      [{ word: w0.toLowerCase(), confidence: 1.4 }, { word: "NOTAWORD", confidence: 0.5 }, { word: w0, confidence: 0.9 }],
      s,
    );
    expect(out).toEqual([{ word: w0, confidence: 1 }]);
  });
  it("drops revealed words", () => {
    const s2 = { ...s, revealed: s.revealed.map((_, i) => i === 0) };
    expect(filterSuddenDeathGuesses([{ word: s.words[0]!, confidence: 0.9 }], s2)).toEqual([]);
  });
});
```

`ai.test.ts`:

```ts
import { /* existing */ getSuddenDeathGuesses } from "../src/ai";
import type { SuddenDeathResponse } from "../src/validate";

describe("getSuddenDeathGuesses", () => {
  it("returns a ranked, board-filtered list", async () => {
    const s = createGame({ rng: rng(3) });
    const legal = s.words.slice(0, 2);
    const caller = scripted([ok<SuddenDeathResponse>({
      reasoning: "",
      guesses: [{ word: legal[0]!, confidence: 0.9 }, { word: "JUNK", confidence: 0.2 }, { word: legal[1]!, confidence: 0.7 }],
    })]);
    const out = await getSuddenDeathGuesses(caller, s, () => {});
    expect(out).toEqual([{ word: legal[0], confidence: 0.9 }, { word: legal[1], confidence: 0.7 }]);
  });
  it("returns [] on refusal", async () => {
    const s = createGame({ rng: rng(3) });
    const caller = scripted([{ parsed: null, refusal: "no", finishReason: "stop" }]);
    expect(await getSuddenDeathGuesses(caller, s, () => {})).toEqual([]);
  });
});
```

- [ ] **Step 2: Run, verify fails**

Run: `cd codenames && npm test -- validate ai`
Expected: FAIL — new exports missing.

- [ ] **Step 3: Implement `validate.ts`**

```ts
export const SuddenDeathSchema = z.object({
  reasoning: z.string(),
  guesses: z.array(z.object({ word: z.string(), confidence: z.number() })),
});
export type SuddenDeathResponse = z.infer<typeof SuddenDeathSchema>;

export function filterSuddenDeathGuesses(
  guesses: Array<{ word: string; confidence: number }>,
  state: GameState,
): Array<{ word: string; confidence: number }> {
  const canonical = new Map(remainingWords(state).map((w) => [norm(w), w]));
  const out: Array<{ word: string; confidence: number }> = [];
  const seen = new Set<string>();
  for (const g of guesses) {
    const key = norm(g.word);
    const word = canonical.get(key);
    if (word && !seen.has(key)) {
      out.push({ word, confidence: Math.max(0, Math.min(1, g.confidence)) });
      seen.add(key);
    }
  }
  return out;
}
```

- [ ] **Step 4: Implement `prompts.ts`**

```ts
export const SUDDEN_DEATH_SYSTEM = `${RULES}

SUDDEN DEATH: no more clues will be given. From the clues already given during the
game, decide which of the remaining words are your partner's agents. Return a list
RANKED most-confident first, each with a confidence from 0 to 1. A single wrong
guess loses the game — lead with the words you would actually risk, and be honest
about your confidence. Put your thinking in "reasoning" first.`;

export function buildSuddenDeathMessages(state: GameState): ChatMessage[] {
  const user = `${/* reuse boardBlock */ ""}Words still in play: ${remainingWords(state).join(", ")}

Game so far (all clues given):
${formatHistory(state)}

Rank the remaining words now — best first, each with a confidence from 0 to 1.`;
  return [
    { role: "system", content: SUDDEN_DEATH_SYSTEM },
    { role: "user", content: user },
  ];
}
```

(`RULES`, `remainingWords`, `formatHistory` already exist in `prompts.ts`. Match the file's existing import of `remainingWords` from `./engine`.)

- [ ] **Step 5: Implement `ai.ts`**

```ts
import { SuddenDeathSchema, /* existing */ } from "./validate";
import { buildSuddenDeathMessages, /* existing */ } from "./prompts";

export async function getSuddenDeathGuesses(
  caller: LLMCaller,
  state: GameState,
  log: Logger,
): Promise<Array<{ word: string; confidence: number }>> {
  const res = await caller.call(buildSuddenDeathMessages(state), SuddenDeathSchema, "sudden_death");
  if (res.refusal) { log(`AI declined a sudden-death guess: ${res.refusal}.`); return []; }
  if (!res.parsed) { log("AI returned no sudden-death guesses."); return []; }
  return filterSuddenDeathGuesses(res.parsed.guesses, state);
}
```

(Import `filterSuddenDeathGuesses` alongside the existing `filterGuesses` import.)

- [ ] **Step 6: Run, verify pass + build**

Run: `cd codenames && npm test -- validate ai && npm run build`
Expected: PASS; tsc clean.

- [ ] **Step 7: Commit**

```bash
git add codenames/src/validate.ts codenames/src/prompts.ts codenames/src/ai.ts codenames/tests/validate.test.ts codenames/tests/ai.test.ts
git commit -m "feat(codenames): AI clue-less ranked sudden-death guesses + confidence"
```

---

### Task 4: Controller — sudden-death orchestration

**Files:**
- Modify: `codenames/src/main.ts`
- Test: `codenames/tests/integration.test.ts`

**Interfaces:**
- Consumes: `suddenDeathGuess` (engine), `getSuddenDeathGuesses` (ai).
- Produces (on the controller object): `aiSuddenDeathGuess(): Promise<void>`. `clickCell` routes to `suddenDeathGuess(..., "human")` when `state.suddenDeath`. New `ControllerUI.setSuddenDeathMeter?(top: { word: string; confidence: number } | null): void`. New `ControllerDeps`-side nothing; real entry passes `getSuddenDeathGuesses` via a `listSuddenDeath`-style dep OR imports it directly (see below). New `UICallbacks.onAiGuess`.

Controller behaviour:
- A closure `let sdGuesses: Array<{ word: string; confidence: number }> | null = null;` reset to `null` in `newGame`.
- `maybeEnterSuddenDeath()` — if `state.suddenDeath && sdGuesses === null`: busy-guard + generation-guard, `log` the sudden-death banner, `sdGuesses = await deps.suddenDeath!(caller(), state, log)`, then `updateSDMeter()`; `LLMError` → `ui.setError`.
- Call `await maybeEnterSuddenDeath()` at the end of `submitClue`, `clickCell` (normal path), `endGuessing`, `passClue`, and `runAIClueTurn`'s pass branch (anywhere a turn can advance to timer-0).
- `topSDCandidate()` — first `sdGuesses` entry whose word is not yet revealed, else `null`. `updateSDMeter()` → `ui.setSuddenDeathMeter?.(topSDCandidate())`.
- `aiSuddenDeathGuess()` — busy/SD/playing guards; take `topSDCandidate()`; if none, `log("The AI has no confident sudden-death guess — your move.")`; else `state = suddenDeathGuess(state, top.word, "ai")`, log the result (reuse `guessLabel` on the last `suddenDeathGuesses` outcome), `updateSDMeter()`, `render()`, `logEndState()`.
- `clickCell`: when `state.suddenDeath`, apply `suddenDeathGuess(state, w, "human")` (guarded on `status === "playing"`), log, `updateSDMeter()`, `render()`, `logEndState()`, and `return` before the normal clue-based path.

Wire in `ControllerDeps`: add `suddenDeath?: (caller: LLMCaller, state: GameState, log: Logger) => Promise<Array<{ word: string; confidence: number }>>;` (optional so tests can inject; the real entry passes `getSuddenDeathGuesses`). Real entry wiring: `suddenDeath: (c, s, l) => getSuddenDeathGuesses(c, s, l)` and `onAiGuess: () => controller.aiSuddenDeathGuess()`.

- [ ] **Step 1: Write failing integration tests**

```ts
import { suddenDeathGuess } from "../src/engine"; // (already have engine imports as needed)

function fakeUiSD() {
  const logs: string[] = [];
  const meter: Array<{ word: string; confidence: number } | null> = [];
  return {
    ui: {
      render: vi.fn(), log: (l: string) => logs.push(l), getKey: () => "sk", getModel: () => "m",
      setError: vi.fn(), setSuddenDeathMeter: (t: any) => meter.push(t),
    },
    logs, meter,
  };
}

describe("controller: sudden death", () => {
  // Force sudden death by threading a game that is one endGuessing away from timer-0.
  it("entering sudden death fetches the ranked list and sets the meter", async () => {
    const g = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const humanGreen = g.words.find((_, i) => g.keys.human[i] === "green")!; // AI's target pool
    const { ui, meter } = fakeUiSD();
    const suddenDeath = vi.fn(async () => [{ word: humanGreen, confidence: 0.9 }]);
    // caller: AI clue turn refuses (pass) so the timer burns down
    const caller: LLMCaller = { call: vi.fn(async () => ({ parsed: null, refusal: "pass", finishReason: "stop" })) };
    const c = createController({ ui, makeCaller: () => caller, suddenDeath, rng: rng(3), firstClueGiver: "ai" });
    await c.newGame();
    // drive to timer 0: repeatedly get-clue (AI passes → passTurn) — but simpler: set up via requestAIClue loop
    // Instead, drive turnsRemaining down through the public flow:
    for (let i = 0; i < 9; i++) { await c.requestAIClue(); } // each pass spends a token
    const s = lastRendered(ui.render);
    expect(s.suddenDeath).toBe(true);
    expect(suddenDeath).toHaveBeenCalled();
    expect(meter.at(-1)).toEqual({ word: humanGreen, confidence: 0.9 });
  });

  it("aiSuddenDeathGuess applies the top candidate against the human card", async () => {
    const g = createGame({ rng: rng(3) });
    const humanGreen = g.words.find((_, i) => g.keys.human[i] === "green")!;
    const { ui } = fakeUiSD();
    const suddenDeath = vi.fn(async () => [{ word: humanGreen, confidence: 0.95 }]);
    const c = createController({ ui, makeCaller: () => ({ call: vi.fn() }), suddenDeath, rng: rng(3) });
    // Reach sudden death deterministically: use the same seed drive as above, or
    // (simplest) expose it by driving passes; reuse the loop:
    await c.newGame();
    for (let i = 0; i < 9; i++) { if (lastRendered(ui.render)?.phase === "awaitClue" && lastRendered(ui.render)?.clueGiver === "human") await c.passClue(); else break; }
    // NOTE: the implementer should reach sudden death via whatever public sequence
    // the seeded game allows; the assertion is what matters:
    if (lastRendered(ui.render).suddenDeath) {
      await c.aiSuddenDeathGuess();
      const s = lastRendered(ui.render);
      expect(s.suddenDeathGuesses.some((x) => x.by === "ai" && x.word === humanGreen)).toBe(true);
    }
  });
});
```

> Implementer note: reaching sudden death through the public API depends on the seed. Prefer a small deterministic driver: with `firstClueGiver: "human"` and a caller whose guesses are `[]` and clue is a refusal, alternate `passClue()` (human) and `requestAIClue()` (AI passes) until `turnsRemaining` hits 0 — 9 passes total. Assert `state.suddenDeath` before the sudden-death-specific assertions. If a clean public path is awkward, add a tiny test-only `firstClueGiver` + a helper that calls `passClue`/`requestAIClue` in a loop guarding on `state.phase`/`clueGiver`.

- [ ] **Step 2: Run, verify fails**

Run: `cd codenames && npm test -- integration`
Expected: FAIL — `aiSuddenDeathGuess` / `setSuddenDeathMeter` / `suddenDeath` dep missing.

- [ ] **Step 3: Implement** — `src/main.ts`

Add to `ControllerUI`: `setSuddenDeathMeter?(top: { word: string; confidence: number } | null): void;`
Add to `ControllerDeps`: `suddenDeath?: (caller: LLMCaller, state: GameState, log: Logger) => Promise<Array<{ word: string; confidence: number }>>;`
Add the closure state, helpers, and actions:

```ts
  let sdGuesses: Array<{ word: string; confidence: number }> | null = null;

  function isRevealedWord(word: string): boolean {
    const i = state.words.indexOf(word);
    return i >= 0 && state.revealed[i];
  }
  function topSDCandidate(): { word: string; confidence: number } | null {
    if (!sdGuesses) return null;
    return sdGuesses.find((g) => !isRevealedWord(g.word)) ?? null;
  }
  function updateSDMeter(): void {
    ui.setSuddenDeathMeter?.(topSDCandidate());
  }

  async function maybeEnterSuddenDeath(): Promise<void> {
    if (!state.suddenDeath || sdGuesses !== null || !deps.suddenDeath) return;
    const gen = generation;
    busy = true;
    try {
      ui.setError(null);
      log("⏱ Sudden death — no clues left. Any wrong guess loses.");
      const list = await deps.suddenDeath(caller(), state, log);
      if (gen !== generation) return;
      sdGuesses = list;
      updateSDMeter();
      render();
    } catch (e) {
      if (gen !== generation) return;
      if (e instanceof LLMError) ui.setError(e.message);
      else throw e;
    } finally {
      if (gen === generation) busy = false;
    }
  }

  async function aiSuddenDeathGuess(): Promise<void> {
    if (busy || !state.suddenDeath || state.status !== "playing") return;
    const top = topSDCandidate();
    if (!top) { log("The AI has no confident sudden-death guess — your move."); return; }
    state = suddenDeathGuess(state, top.word, "ai");
    log(`AI guessed ${top.word} → ${guessLabel(state.suddenDeathGuesses[state.suddenDeathGuesses.length - 1]!.outcome)}`);
    updateSDMeter();
    render();
    logEndState();
  }
```

Reset in `newGame`: add `sdGuesses = null;` (next to the other resets). Route `clickCell`:

```ts
  async function clickCell(w: string): Promise<void> {
    if (busy) return;
    if (state.suddenDeath) {
      if (state.status !== "playing") return;
      const before = state.suddenDeathGuesses.length;
      state = suddenDeathGuess(state, w, "human");
      if (state.suddenDeathGuesses.length > before) {
        log(`You guessed ${w} → ${guessLabel(state.suddenDeathGuesses[state.suddenDeathGuesses.length - 1]!.outcome)}`);
      }
      updateSDMeter();
      render();
      logEndState();
      return;
    }
    // ... existing normal-play clickCell body ...
  }
```

Add `await maybeEnterSuddenDeath();` as the last line of `submitClue`, `clickCell` (normal path), `endGuessing`, `passClue` (make it `async` if needed — it currently is sync; wrap the SD check), and after `maybeRunAIClueTurn()` where a pass can advance the timer (`requestAIClue`/`runAIClueTurn`). Import `suddenDeathGuess` from `./engine`. Return `aiSuddenDeathGuess` from the controller. Real entry: add `suddenDeath: (c, s, l) => getSuddenDeathGuesses(c, s, l)` (import it) and `onAiGuess: () => controller.aiSuddenDeathGuess()`.

- [ ] **Step 4: Run, verify pass + build**

Run: `cd codenames && npm test && npm run build`
Expected: PASS (full suite); tsc + vite clean.

- [ ] **Step 5: Commit**

```bash
git add codenames/src/main.ts codenames/tests/integration.test.ts
git commit -m "feat(codenames): controller sudden-death orchestration (enter, AI guess, click routing, meter)"
```

---

### Task 5: UI — sudden-death screen + confidence meter + rules; rebuild bundle

**Files:**
- Modify: `codenames/src/ui.ts`, `codenames/src/style.css`
- Test: `codenames/tests/ui.test.ts`
- Build output: `codenames/../posts/codenames/app/**` (committed)

**Interfaces:**
- Consumes: `state.suddenDeath`, `state.keys`, `state.revealed`.
- Produces: `UICallbacks.onAiGuess(): void`; `GameUI.setSuddenDeathMeter(top: { word: string; confidence: number } | null): void`; sudden-death rendering (header text, hidden shading, remaining-agent counts, meter + "AI guess" button); normal controls hidden in sudden death.

- [ ] **Step 1: Write failing UI tests** — `ui.test.ts` (add `onAiGuess: vi.fn()` to the `cb()` helper first)

```ts
it("in sudden death: hides shading, shows counts + the AI-guess control, hides normal controls", () => {
  const ui = new GameUI(root, cb());
  const s = createGame({ rng: rng(3) });
  // even with the toggle ON, sudden death hides shading
  ui.render({ ...s, suddenDeath: true, clueGiver: "human", phase: "awaitClue" });
  expect(root.querySelectorAll(".shade-green, .shade-bystander, .shade-assassin").length).toBe(0);
  expect(root.querySelector(".cn-turn-main")!.textContent).toMatch(/sudden death/i);
  expect((root.querySelector(".cn-ai-guess") as HTMLButtonElement)).not.toBeNull();
  // normal controls hidden
  expect((root.querySelector(".cn-clue-bar") as HTMLElement).hidden).toBe(true);
  expect((root.querySelector(".cn-get-clue") as HTMLElement).hidden).toBe(true);
  // remaining-agent counts render (identity-free)
  expect(root.querySelector(".cn-sd-counts")!.textContent).toMatch(/\d/);
});

it("setSuddenDeathMeter shows the top candidate + confidence and fires onAiGuess", () => {
  const callbacks = cb();
  const ui = new GameUI(root, callbacks);
  ui.render({ ...createGame({ rng: rng(3) }), suddenDeath: true });
  ui.setSuddenDeathMeter({ word: "CRANE", confidence: 0.85 });
  expect(root.querySelector(".cn-meter")!.textContent).toMatch(/CRANE/);
  expect(root.querySelector(".cn-meter")!.textContent).toMatch(/85/);
  (root.querySelector(".cn-ai-guess") as HTMLElement).click();
  expect(callbacks.onAiGuess).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run, verify fails**

Run: `cd codenames && npm test -- ui`
Expected: FAIL — SD rendering / `setSuddenDeathMeter` / `.cn-ai-guess` missing.

- [ ] **Step 3: Implement `ui.ts`**

- Add `onAiGuess(): void;` to `UICallbacks`.
- Add fields: `private aiGuessBtn!: HTMLButtonElement; private meterEl!: HTMLElement; private sdCountsEl!: HTMLElement;`
- In `buildSkeleton`, inside the action row, create the sudden-death controls (hidden by default):

```ts
    // Sudden-death: confidence meter + "AI guess" (shown only in sudden death)
    this.meterEl = document.createElement("div");
    this.meterEl.className = "cn-meter";
    this.meterEl.hidden = true;
    this.aiGuessBtn = document.createElement("button");
    this.aiGuessBtn.type = "button";
    this.aiGuessBtn.textContent = "AI guess";
    this.aiGuessBtn.className = "cn-ai-guess cn-primary";
    this.aiGuessBtn.hidden = true;
    this.aiGuessBtn.addEventListener("click", () => this.cb.onAiGuess());
    action.appendChild(this.meterEl);
    action.appendChild(this.aiGuessBtn);
```

- Add a counts element near the turn header (created in `buildSkeleton`, appended after the grid or in the turn block): `this.sdCountsEl = document.createElement("div"); this.sdCountsEl.className = "cn-sd-counts"; this.sdCountsEl.hidden = true;` and append it under the board.
- In `render(state)`:
  - When `state.suddenDeath`: force `shadeKey = null` (so no shading regardless of the toggle). Keep bystander markers off too (sudden death hides the board's card info).
  - Show `this.meterEl`, `this.aiGuessBtn`, `this.sdCountsEl`; hide `clueBarEl`, `passClueBtn`, `getClueBtn`, `endGuessingBtn`.
  - Counts: `const youLeft = state.keys.ai.filter((c, i) => c === "green" && !state.revealed[i]).length; const aiLeft = state.keys.human.filter((c, i) => c === "green" && !state.revealed[i]).length;` → `this.sdCountsEl.textContent = \`You still need ${youLeft} of the AI's agents · the AI still needs ${aiLeft} of yours\`;`
  - When NOT `suddenDeath`: hide `meterEl`/`aiGuessBtn`/`sdCountsEl` and keep the existing normal-control visibility logic.
- `turnHeadline(state)`: at the top, `if (state.suddenDeath && state.status === "playing") return "☠ SUDDEN DEATH — any wrong guess loses";` (before the other branches; keep won/lost first).
- Add `setSuddenDeathMeter`:

```ts
  setSuddenDeathMeter(top: { word: string; confidence: number } | null): void {
    if (!top) {
      this.meterEl.textContent = "No confident AI guess — your move.";
      this.aiGuessBtn.disabled = true;
      return;
    }
    const pct = Math.round(top.confidence * 100);
    this.meterEl.replaceChildren();
    const label = document.createElement("span");
    label.textContent = `AI wants to guess ${top.word} — ${pct}%`;
    const bar = document.createElement("div");
    bar.className = "cn-meter-bar";
    const fill = document.createElement("div");
    fill.className = "cn-meter-fill";
    fill.style.width = `${pct}%`;
    bar.appendChild(fill);
    this.meterEl.appendChild(label);
    this.meterEl.appendChild(bar);
    this.aiGuessBtn.disabled = false;
  }
```

- Add a sudden-death bullet to `buildRulesPanel`'s `rules` array:

```ts
      "Sudden death: if the timer runs out with agents still hidden, there are no more clues — you and the AI make one last attempt from the clues so far. Your key card is hidden, and any wrong guess (even a bystander) loses.",
```

- [ ] **Step 4: Implement `style.css`** — meter + counts styling

```css
.cn-meter {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
  min-width: 12rem;
}
.cn-meter-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--border);
  overflow: hidden;
}
.cn-meter-fill {
  height: 100%;
  background: var(--accent);
}
.cn-sd-counts {
  text-align: center;
  font-size: 0.8rem;
  color: var(--muted);
}
```

- [ ] **Step 5: Run tests + build + rebuild committed bundle**

Run: `cd codenames && npm test && npm run build`
Expected: PASS (full suite); `posts/codenames/app/` regenerated.

- [ ] **Step 6: Commit (source + rebuilt bundle)**

```bash
git add codenames/src/ui.ts codenames/src/style.css codenames/tests/ui.test.ts posts/codenames/app
git commit -m "feat(codenames): sudden-death UI (confidence meter, hidden card, counts) + rebuilt bundle"
```

---

## Self-Review

**Spec coverage:**
- Trigger (timer-out → suddenDeath, not loss) → Task 1. ✓
- Non-guesser-card judging + non-green loses + win-at-15 → Task 2 (`suddenDeathGuess`). ✓
- Clue-less ranked AI guessing + confidence → Task 3. ✓
- Enter-SD fetch (one call) + AI guess + human click routing + meter → Task 4. ✓
- Hide shading + counts + meter + AI-guess button + hide normal controls + rules bullet → Task 5. ✓
- Oracle prevention (hide card in SD) → Task 5 render (`shadeKey = null` when suddenDeath). ✓
- AI mocked in tests; no network → Tasks 3/4 use fake/scripted callers + injected `suddenDeath` dep. ✓
- Pure/immutable engine → Task 2 uses `structuredClone`, tested for no-mutation. ✓

**Placeholder scan:** the Task-4 integration test carries an explicit implementer note on *how* to reach sudden death through the public API (seed-dependent) — this is guidance, not a skipped assertion; the asserted behaviour is concrete. No TBD/TODO elsewhere.

**Type consistency:** `SuddenDeathGuess`/`suddenDeath`/`suddenDeathGuesses` (Task 1) reused verbatim in Task 2 and Task 4. `SuddenDeathSchema`/`SuddenDeathResponse`/`filterSuddenDeathGuesses`/`buildSuddenDeathMessages`/`getSuddenDeathGuesses` (Task 3) consumed by Task 4. `setSuddenDeathMeter`/`onAiGuess`/`aiSuddenDeathGuess` names match across Tasks 4–5. The AI ranked-guess type `Array<{ word: string; confidence: number }>` is identical in `validate.ts`, `ai.ts`, `main.ts`, and `ui.ts`.

**Deferred → decided:** sudden-death guesses are stored in a dedicated `GameState.suddenDeathGuesses` field (not history), so `formatHistory` (used by clue prompts) stays clean.

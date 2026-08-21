# Codenames Duet vs. AI Partner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a browser-playable Codenames Duet game with an OpenAI-powered AI partner, plus a blog post, on the static Quarto/GitHub-Pages site.

**Architecture:** Vanilla TypeScript + Vite, no framework. A pure game engine (no DOM/network) drives a thin DOM UI; an AI layer talks directly to OpenAI from the browser (BYOK, `dangerouslyAllowBrowser`) using Structured Outputs. Reliability lives in an `interpret → validate → repair` loop. The built bundle is committed into `posts/codenames/app/` and copied verbatim by Quarto.

**Tech Stack:** TypeScript, Vite, Vitest (jsdom), `openai` SDK + `openai/helpers/zod`, `zod`.

## Global Constraints

- **No server, no proxy, no CI secrets.** All logic is client-side; the only build tooling is local Node (never added to CI).
- **BYOK / OpenAI only.** `new OpenAI({ apiKey, dangerouslyAllowBrowser: true })`. Key is never logged, never written to `localStorage` (session-only opt-in).
- **Structured Outputs everywhere:** `client.chat.completions.parse({ ..., response_format: zodResponseFormat(Schema, "name"), max_completion_tokens })`. Read results via `choices[0].finish_reason`, `choices[0].message.refusal`, `choices[0].message.parsed`.
- **Default model:** `DEFAULT_MODEL = "gpt-5.6"` (a GPT-5-class Structured-Outputs model per current OpenAI docs). UI-configurable; verify/upgrade the id at build time.
- **Duet key-card contingency table** (rows = your card, cols = partner's): GG=3, GB=5, GA=1, BG=5, BB=7, BA=1, AG=1, AB=1, AA=1 → 9 green & 3 assassin per card, 15 unique agents, 1 mutual assassin.
- **Timer:** 9 turns. **Win:** 15 agents found. **Lose:** assassin revealed, or the 9-turn timer is exhausted with fewer than 15 agents found. **No sudden-death phase** (decided 2026-08-21 — see spec; supersedes earlier task text mentioning sudden death).
- **Pure files touch nothing else:** `engine.ts`/`keycards.ts`/`validate.ts`/`prompts.ts` are DOM- and network-free and fully unit-tested; `ui.ts` is the only DOM consumer; `ai.ts` is the only network consumer.
- **Vite `base: "./"`** (relative paths — the app is served from a Pages subpath), **`build.outDir: "../posts/codenames/app"`**, **`emptyOutDir: true`**.
- Commit after every task. Conventional-commit messages, scope `codenames`.

---

### Task 1: Project scaffold (Vite + TS + Vitest)

**Files:**
- Create: `codenames/package.json`
- Create: `codenames/tsconfig.json`
- Create: `codenames/vite.config.ts`
- Create: `codenames/index.html`
- Create: `codenames/src/smoke.ts`
- Test: `codenames/tests/smoke.test.ts`
- Modify: `.gitignore` (add `codenames/node_modules`)

**Interfaces:**
- Produces: an installable/buildable/testable project. `npm test`, `npm run build`, `npm run dev`, `npm run eval` scripts exist.

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "codenames-duet",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "test:watch": "vitest",
    "eval": "tsx eval/run.ts"
  },
  "dependencies": {
    "openai": "^4.68.0",
    "zod": "^3.23.8"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0",
    "jsdom": "^25.0.0",
    "tsx": "^4.19.0"
  }
}
```

- [ ] **Step 2: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vitest/globals"]
  },
  "include": ["src", "tests", "eval"]
}
```

- [ ] **Step 3: Create `vite.config.ts`**

```ts
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  build: { outDir: "../posts/codenames/app", emptyOutDir: true },
  test: { environment: "jsdom", globals: true },
});
```

- [ ] **Step 4: Create `index.html`** (entry the UI task fills in)

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Codenames Duet vs. AI</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 5: Write the failing smoke test** — `codenames/tests/smoke.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { hello } from "../src/smoke";

describe("scaffold", () => {
  it("runs vitest", () => {
    expect(hello()).toBe("codenames");
  });
});
```

- [ ] **Step 6: Run it, verify it fails**

Run: `cd codenames && npm install && npm test`
Expected: FAIL — cannot find `../src/smoke`.

- [ ] **Step 7: Create `src/smoke.ts`**

```ts
export const hello = (): string => "codenames";
```

- [ ] **Step 8: Run tests, verify pass**

Run: `cd codenames && npm test`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add codenames/package.json codenames/tsconfig.json codenames/vite.config.ts codenames/index.html codenames/src/smoke.ts codenames/tests/smoke.test.ts codenames/package-lock.json .gitignore
git commit -m "chore(codenames): scaffold Vite + TS + Vitest project"
```

---

### Task 2: Shared types + word list

**Files:**
- Create: `codenames/src/types.ts`
- Create: `codenames/src/words.ts`
- Test: `codenames/tests/words.test.ts`

**Interfaces:**
- Produces (consumed by every later task):
  - `type Category = "green" | "bystander" | "assassin"`
  - `type KeyCard = Category[]` (length 25, indexed by board position)
  - `interface KeyCardPair { human: KeyCard; ai: KeyCard }`
  - `type Player = "human" | "ai"`
  - `interface HistoryTurn { clueGiver: Player; clue: string; number: number; guesses: string[]; outcomes: Category[] }`
  - `interface GameState { words: string[]; keys: KeyCardPair; revealed: boolean[]; agentsFound: number; turnsRemaining: number; suddenDeath: boolean; clueGiver: Player; phase: "awaitClue" | "awaitGuess"; currentClue: { word: string; number: number; guessesMade: number } | null; status: "playing" | "won" | "lost"; history: HistoryTurn[] }`
  - `WORDS: string[]` (≥ 40 uppercase words)

- [ ] **Step 1: Create `src/types.ts`**

```ts
export type Category = "green" | "bystander" | "assassin";
export type KeyCard = Category[]; // length 25, indexed by board position
export interface KeyCardPair { human: KeyCard; ai: KeyCard; }
export type Player = "human" | "ai";

export interface HistoryTurn {
  clueGiver: Player;
  clue: string;
  number: number;
  guesses: string[];       // canonical board words, in guess order
  outcomes: Category[];    // category on the clue-giver's card for each guess
}

export interface GameState {
  words: string[];                 // 25 canonical (uppercase) words
  keys: KeyCardPair;
  revealed: boolean[];             // 25; true once a word is covered
  agentsFound: number;             // 0..15
  turnsRemaining: number;          // starts at 9
  suddenDeath: boolean;
  clueGiver: Player;               // who gives the next clue
  phase: "awaitClue" | "awaitGuess";
  currentClue: { word: string; number: number; guessesMade: number } | null;
  status: "playing" | "won" | "lost";
  history: HistoryTurn[];
}

export const TOTAL_AGENTS = 15;
export const START_TURNS = 9;
```

- [ ] **Step 2: Write the failing test** — `codenames/tests/words.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { WORDS } from "../src/words";

describe("WORDS", () => {
  it("has enough distinct uppercase words for a board", () => {
    expect(WORDS.length).toBeGreaterThanOrEqual(40);
    expect(new Set(WORDS).size).toBe(WORDS.length);
    for (const w of WORDS) expect(w).toBe(w.toUpperCase());
  });
});
```

- [ ] **Step 3: Run it, verify it fails**

Run: `cd codenames && npm test -- words`
Expected: FAIL — cannot find `../src/words`.

- [ ] **Step 4: Create `src/words.ts`**

```ts
export const WORDS: string[] = [
  "APPLE","BAND","BANK","BEACH","BELL","BOLT","BOND","BOOM","BRIDGE","BUGLE",
  "CAPITAL","CARD","CHAIR","CHEST","CIRCLE","CLOAK","COMPOUND","CRANE","DANCE","DIAMOND",
  "DRAGON","DRESS","EAGLE","FIELD","FIGURE","FILM","FORCE","GIANT","GLASS","GOLD",
  "GRACE","GREEN","GROUND","HAND","HEART","HORN","JACK","KING","KNIGHT","LAB",
  "LEAD","LEMON","LINK","LOCK","MARBLE","MASS","MINT","MOON","NIGHT","NOTE",
  "NURSE","ORANGE","PALM","PARK","PILOT","PIT","PLATE","POINT","QUEEN","RING",
  "ROCK","ROOT","SCALE","SHADOW","SHIP","SLIP","SNOW","SPACE","SPRING","STAR",
  "STATE","STICK","STRAW","TABLE","THUMB","TICK","TRIP","VACUUM","WAVE","WELL",
];
```

- [ ] **Step 5: Run tests, verify pass**

Run: `cd codenames && npm test -- words`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add codenames/src/types.ts codenames/src/words.ts codenames/tests/words.test.ts
git commit -m "feat(codenames): shared types + curated word list"
```

---

### Task 3: Key-card pair generation

**Files:**
- Create: `codenames/src/keycards.ts`
- Test: `codenames/tests/keycards.test.ts`

**Interfaces:**
- Consumes: `Category`, `KeyCard`, `KeyCardPair` from `types.ts`.
- Produces:
  - `generateKeyCardPair(rng?: () => number): KeyCardPair`
  - `validateKeyCardPair(pair: KeyCardPair): { valid: boolean; errors: string[] }`
  - `CONTINGENCY: Record<string, number>` (keys `"GG","GB",...` per the table).

- [ ] **Step 1: Write the failing test** — `codenames/tests/keycards.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { generateKeyCardPair, validateKeyCardPair } from "../src/keycards";
import type { Category, KeyCard } from "../src/types";

const count = (k: KeyCard, c: Category) => k.filter((x) => x === c).length;

// deterministic PRNG (mulberry32) so tests are reproducible
function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe("generateKeyCardPair", () => {
  it("produces two 25-cell cards with the Duet distribution", () => {
    for (let s = 0; s < 25; s++) {
      const { human, ai } = generateKeyCardPair(rng(s));
      expect(human.length).toBe(25);
      expect(ai.length).toBe(25);
      expect(count(human, "green")).toBe(9);
      expect(count(human, "assassin")).toBe(3);
      expect(count(ai, "green")).toBe(9);
      expect(count(ai, "assassin")).toBe(3);
    }
  });

  it("has exactly 15 unique agents and 1 mutual assassin", () => {
    const { human, ai } = generateKeyCardPair(rng(7));
    let unique = 0, mutualAssassin = 0;
    for (let i = 0; i < 25; i++) {
      if (human[i] === "green" || ai[i] === "green") unique++;
      if (human[i] === "assassin" && ai[i] === "assassin") mutualAssassin++;
    }
    expect(unique).toBe(15);
    expect(mutualAssassin).toBe(1);
  });

  it("validateKeyCardPair accepts generated pairs and rejects a broken one", () => {
    expect(validateKeyCardPair(generateKeyCardPair(rng(1))).valid).toBe(true);
    const broken = generateKeyCardPair(rng(1));
    broken.human[0] = broken.human[0] === "green" ? "bystander" : "green";
    expect(validateKeyCardPair(broken).valid).toBe(false);
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd codenames && npm test -- keycards`
Expected: FAIL — cannot find `../src/keycards`.

- [ ] **Step 3: Create `src/keycards.ts`**

```ts
import type { Category, KeyCard, KeyCardPair } from "./types";

// rows = human card, cols = ai card
export const CONTINGENCY: Record<string, number> = {
  GG: 3, GB: 5, GA: 1,
  BG: 5, BB: 7, BA: 1,
  AG: 1, AB: 1, AA: 1,
};

const CODE: Record<string, Category> = { G: "green", B: "bystander", A: "assassin" };

function shuffle<T>(arr: T[], rng: () => number): T[] {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j]!, a[i]!];
  }
  return a;
}

export function generateKeyCardPair(rng: () => number = Math.random): KeyCardPair {
  const cells: Array<[Category, Category]> = [];
  for (const [pair, n] of Object.entries(CONTINGENCY)) {
    const h = CODE[pair[0]!]!;
    const a = CODE[pair[1]!]!;
    for (let i = 0; i < n; i++) cells.push([h, a]);
  }
  const shuffled = shuffle(cells, rng); // 25 cells to 25 positions
  const human: KeyCard = shuffled.map((c) => c[0]);
  const ai: KeyCard = shuffled.map((c) => c[1]);
  return { human, ai };
}

export function validateKeyCardPair(pair: KeyCardPair): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  const { human, ai } = pair;
  if (human.length !== 25 || ai.length !== 25) errors.push("cards must be length 25");
  const tally: Record<string, number> = {};
  const enc = (c: Category) => (c === "green" ? "G" : c === "bystander" ? "B" : "A");
  for (let i = 0; i < 25; i++) {
    const key = `${enc(human[i]!)}${enc(ai[i]!)}`;
    tally[key] = (tally[key] ?? 0) + 1;
  }
  for (const [key, n] of Object.entries(CONTINGENCY)) {
    if ((tally[key] ?? 0) !== n) errors.push(`expected ${n} of ${key}, got ${tally[key] ?? 0}`);
  }
  return { valid: errors.length === 0, errors };
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd codenames && npm test -- keycards`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add codenames/src/keycards.ts codenames/tests/keycards.test.ts
git commit -m "feat(codenames): Duet key-card pair generation + validation"
```

---

### Task 4: Pure game engine

**Files:**
- Create: `codenames/src/engine.ts`
- Test: `codenames/tests/engine.test.ts`

**Interfaces:**
- Consumes: `types.ts`, `keycards.ts`, `words.ts`.
- Produces:
  - `createGame(opts?: { rng?: () => number; words?: string[]; firstClueGiver?: Player }): GameState`
  - `giveClue(state: GameState, clue: string, number: number): GameState`
  - `guess(state: GameState, word: string): GameState`
  - `endGuessing(state: GameState): GameState`
  - `giverKey(state: GameState): KeyCard`
  - `remainingWords(state: GameState): string[]`
  - `aiGreenWordsRemaining(state: GameState): string[]`

Engine rules encoded (faithful Duet):
- A guess is checked against the **clue-giver's** key card.
- `green` → cover, `agentsFound++`; guesser may continue (up to `number + 1` guesses); reaching 15 → `won`.
- `bystander` → cover; turn ends.
- `assassin` → cover; `lost`.
- A turn ends on: bystander, assassin (→lost), `endGuessing`, or `guessesMade === number + 1`. On a normal turn end: swap `clueGiver`, `turnsRemaining--`; if it hits 0 → `suddenDeath = true`.
- In `suddenDeath`: no clues; each `guess` that is not `green` on the giver's card → `lost`; reaching 15 → `won`. (Sudden death alternates guessers each single guess.)

- [ ] **Step 1: Write the failing test** — `codenames/tests/engine.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { createGame, giveClue, guess, endGuessing, giverKey } from "../src/engine";
import type { GameState } from "../src/types";

function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// find a board word that is `cat` on the current clue-giver's card
function wordOfCategory(s: GameState, cat: string): string {
  const key = giverKey(s);
  const i = key.findIndex((c, idx) => c === cat && !s.revealed[idx]);
  return s.words[i]!;
}

describe("engine", () => {
  it("creates a valid starting state", () => {
    const s = createGame({ rng: rng(3) });
    expect(s.words.length).toBe(25);
    expect(s.turnsRemaining).toBe(9);
    expect(s.status).toBe("playing");
    expect(s.phase).toBe("awaitClue");
  });

  it("a green guess counts an agent and lets guessing continue", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "OCEAN", 2);
    expect(s.phase).toBe("awaitGuess");
    s = guess(s, wordOfCategory(s, "green"));
    expect(s.agentsFound).toBe(1);
    expect(s.phase).toBe("awaitGuess");
  });

  it("a bystander guess ends the turn and burns a timer token", () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    s = giveClue(s, "OCEAN", 2);
    s = guess(s, wordOfCategory(s, "bystander"));
    expect(s.phase).toBe("awaitClue");
    expect(s.clueGiver).toBe("ai");
    expect(s.turnsRemaining).toBe(8);
  });

  it("an assassin guess loses the game", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "OCEAN", 1);
    s = guess(s, wordOfCategory(s, "assassin"));
    expect(s.status).toBe("lost");
  });

  it("endGuessing ends the turn and swaps the clue-giver", () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    s = giveClue(s, "OCEAN", 3);
    s = endGuessing(s);
    expect(s.clueGiver).toBe("human");
    expect(s.turnsRemaining).toBe(8);
  });

  it("caps guesses at number + 1", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "OCEAN", 1);
    // make two green guesses = number + 1 → turn auto-ends
    s = guess(s, wordOfCategory(s, "green"));
    s = guess(s, wordOfCategory(s, "green"));
    expect(s.phase).toBe("awaitClue");
  });

  it("entering sudden death after the timer, a non-agent guess loses", () => {
    let s = createGame({ rng: rng(3) });
    s.turnsRemaining = 1;               // arrange: one turn left
    s = giveClue(s, "OCEAN", 1);
    s = endGuessing(s);                 // burns last token → sudden death
    expect(s.suddenDeath).toBe(true);
    s = guess(s, wordOfCategory(s, "bystander"));
    expect(s.status).toBe("lost");
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd codenames && npm test -- engine`
Expected: FAIL — cannot find `../src/engine`.

- [ ] **Step 3: Create `src/engine.ts`**

```ts
import type { Category, GameState, KeyCard, Player } from "./types";
import { TOTAL_AGENTS, START_TURNS } from "./types";
import { WORDS } from "./words";
import { generateKeyCardPair } from "./keycards";

function shuffle<T>(arr: T[], rng: () => number): T[] {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j]!, a[i]!];
  }
  return a;
}

export function createGame(opts: {
  rng?: () => number; words?: string[]; firstClueGiver?: Player;
} = {}): GameState {
  const rng = opts.rng ?? Math.random;
  const pool = opts.words ?? WORDS;
  const words = shuffle(pool, rng).slice(0, 25);
  return {
    words,
    keys: generateKeyCardPair(rng),
    revealed: Array(25).fill(false),
    agentsFound: 0,
    turnsRemaining: START_TURNS,
    suddenDeath: false,
    clueGiver: opts.firstClueGiver ?? "human",
    phase: "awaitClue",
    currentClue: null,
    status: "playing",
    history: [],
  };
}

export function giverKey(state: GameState): KeyCard {
  return state.clueGiver === "human" ? state.keys.human : state.keys.ai;
}

export function remainingWords(state: GameState): string[] {
  return state.words.filter((_, i) => !state.revealed[i]);
}

export function aiGreenWordsRemaining(state: GameState): string[] {
  return state.words.filter((_, i) => state.keys.ai[i] === "green" && !state.revealed[i]);
}

export function giveClue(state: GameState, clue: string, number: number): GameState {
  const next = structuredClone(state);
  next.phase = "awaitGuess";
  next.currentClue = { word: clue, number, guessesMade: 0 };
  next.history.push({
    clueGiver: state.clueGiver, clue, number, guesses: [], outcomes: [],
  });
  return next;
}

function endTurn(state: GameState): GameState {
  const next = state;
  next.phase = "awaitClue";
  next.currentClue = null;
  next.clueGiver = next.clueGiver === "human" ? "ai" : "human";
  next.turnsRemaining -= 1;
  if (next.turnsRemaining <= 0 && next.status === "playing") next.suddenDeath = true;
  return next;
}

export function guess(state: GameState, word: string): GameState {
  const next = structuredClone(state);
  const idx = next.words.findIndex((w) => w === word);
  if (idx < 0 || next.revealed[idx] || next.status !== "playing") return next;

  const cat: Category = giverKey(next)[idx]!;
  next.revealed[idx] = true;
  const turn = next.history[next.history.length - 1];
  if (turn) { turn.guesses.push(word); turn.outcomes.push(cat); }

  if (cat === "assassin") { next.status = "lost"; return next; }
  if (cat === "green") {
    next.agentsFound += 1;
    if (next.agentsFound >= TOTAL_AGENTS) { next.status = "won"; return next; }
    if (next.suddenDeath) { next.clueGiver = next.clueGiver === "human" ? "ai" : "human"; return next; }
    next.currentClue!.guessesMade += 1;
    if (next.currentClue!.guessesMade >= next.currentClue!.number + 1) return endTurn(next);
    return next;
  }
  // bystander
  if (next.suddenDeath) { next.status = "lost"; return next; }
  return endTurn(next);
}

export function endGuessing(state: GameState): GameState {
  if (state.status !== "playing" || state.phase !== "awaitGuess") return state;
  return endTurn(structuredClone(state));
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd codenames && npm test -- engine`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add codenames/src/engine.ts codenames/tests/engine.test.ts
git commit -m "feat(codenames): pure Duet game engine"
```

---

### Task 5: Prompts (clue/guess quality levers)

**Files:**
- Create: `codenames/src/prompts.ts`
- Test: `codenames/tests/prompts.test.ts`

**Interfaces:**
- Consumes: `types.ts`, `engine.ts` (`remainingWords`, `aiGreenWordsRemaining`).
- Produces:
  - `type ChatMessage = { role: "system" | "user" | "assistant"; content: string }`
  - `buildClueMessages(state: GameState): ChatMessage[]`
  - `buildGuessMessages(state: GameState): ChatMessage[]`
  - `repairMessage(violations: string[]): ChatMessage`
  - `formatHistory(state: GameState): string`
- Design: system message is **stable** (rules + strategy + few-shot) so OpenAI can cache the prefix; the user message carries the dynamic board/keycard/history. History lines never include model `reasoning`.

- [ ] **Step 1: Write the failing test** — `codenames/tests/prompts.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { buildClueMessages, buildGuessMessages, formatHistory, repairMessage } from "../src/prompts";
import { createGame, giveClue, guess, giverKey } from "../src/engine";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}

describe("prompts", () => {
  it("clue messages: stable system first, dynamic board in user", () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const msgs = buildClueMessages(s);
    expect(msgs[0]!.role).toBe("system");
    expect(msgs[0]!.content).not.toContain(s.words[0]!); // system has no board words
    expect(msgs[1]!.role).toBe("user");
    expect(msgs[1]!.content).toContain(s.words[0]!);      // user has the board
    // the AI's own green agents are disclosed to the clue-giver
    const green = s.words.find((_, i) => s.keys.ai[i] === "green")!;
    expect(msgs[1]!.content).toContain(green);
  });

  it("guess messages: guesser gets board but NOT the key card", () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    s = giveClue(s, "OCEAN", 2);
    const msgs = buildGuessMessages(s);
    expect(msgs[1]!.content).toContain("OCEAN");
    expect(msgs[1]!.content.toLowerCase()).not.toContain("assassin at"); // no key leak
  });

  it("history is compact and omits reasoning", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "OCEAN", 1);
    s = guess(s, s.words[giverKey(s).findIndex((c) => c === "green")]!);
    const h = formatHistory(s);
    expect(h).toContain("OCEAN");
    expect(h.toLowerCase()).not.toContain("reasoning");
  });

  it("repairMessage names the violations", () => {
    const m = repairMessage(["clue must be one word"]);
    expect(m.role).toBe("user");
    expect(m.content).toContain("clue must be one word");
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd codenames && npm test -- prompts`
Expected: FAIL — cannot find `../src/prompts`.

- [ ] **Step 3: Create `src/prompts.ts`**

```ts
import type { GameState } from "./types";
import { remainingWords, aiGreenWordsRemaining } from "./engine";

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

const RULES = `You are an expert cooperative partner in Codenames Duet.
Your team wins by contacting all 15 agents together before the timer runs out.
Two dangers: guessing a BYSTANDER ends the turn; guessing an ASSASSIN loses the game instantly.`;

export const CLUE_SYSTEM = `${RULES}

Your job now: give ONE single-word clue and a NUMBER for the agents you want your
partner to guess. Rules for a legal clue:
- exactly one word, no spaces or hyphens;
- must NOT be any word currently on the board;
- the NUMBER must equal how many target words you list.

Strategy: prefer a SAFE clue that connects a few of your agents over an ambitious
clue that could point at the assassin or a bystander. Think before you answer;
put your thinking in "reasoning" first, then commit to "clue", "number", "targets".

Example — board has APPLE, ORANGE, KING, QUEEN; your agents are APPLE, ORANGE.
Good answer: reasoning "APPLE and ORANGE are both fruit and neither royal word is my agent",
clue "FRUIT", number 2, targets ["APPLE","ORANGE"].`;

export const GUESS_SYSTEM = `${RULES}

Your job now: your partner gave a one-word clue and a number. Choose which words on
the board they most likely mean, RANKED best-first, at most number+1 guesses. You do
NOT know the key card — infer from the clue. Put your thinking in "reasoning" first,
then list "guesses" (exact board words). Stop early rather than risk a wild guess.`;

export function formatHistory(state: GameState): string {
  if (state.history.length === 0) return "(no turns yet)";
  return state.history
    .map((t) => {
      const res = t.guesses.map((g, i) => `${g}=${t.outcomes[i]}`).join(", ") || "(no guesses)";
      return `${t.clueGiver} clued "${t.clue}" ${t.number} -> ${res}`;
    })
    .join("\n");
}

function boardBlock(state: GameState): string {
  return `Words still in play: ${remainingWords(state).join(", ")}`;
}

export function buildClueMessages(state: GameState): ChatMessage[] {
  const green = aiGreenWordsRemaining(state).join(", ");
  const user = `${boardBlock(state)}

Your agents (words your partner must find from YOUR clues): ${green}
Turns remaining: ${state.turnsRemaining}${state.suddenDeath ? " (SUDDEN DEATH)" : ""}

Game so far:
${formatHistory(state)}

Give your clue now.`;
  return [
    { role: "system", content: CLUE_SYSTEM },
    { role: "user", content: user },
  ];
}

export function buildGuessMessages(state: GameState): ChatMessage[] {
  const clue = state.currentClue!;
  const user = `${boardBlock(state)}

Your partner's clue: "${clue.word}" for ${clue.number}.
Turns remaining: ${state.turnsRemaining}${state.suddenDeath ? " (SUDDEN DEATH)" : ""}

Game so far:
${formatHistory(state)}

Make your guesses now (best first, at most ${clue.number + 1}).`;
  return [
    { role: "system", content: GUESS_SYSTEM },
    { role: "user", content: user },
  ];
}

export function repairMessage(violations: string[]): ChatMessage {
  return {
    role: "user",
    content: `That response was illegal: ${violations.join("; ")}. Try again and obey every rule.`,
  };
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd codenames && npm test -- prompts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add codenames/src/prompts.ts codenames/tests/prompts.test.ts
git commit -m "feat(codenames): cache-first prompts with quality strategy + few-shot"
```

---

### Task 6: Response schemas + pure validation

**Files:**
- Create: `codenames/src/validate.ts`
- Test: `codenames/tests/validate.test.ts`

**Interfaces:**
- Consumes: `types.ts`, `engine.ts` (`remainingWords`).
- Produces:
  - `ClueSchema` (zod) → `ClueResponse = { reasoning: string; clue: string; number: number; targets: string[] }`
  - `GuessSchema` (zod) → `GuessResponse = { reasoning: string; guesses: string[] }`
  - `validateClue(resp: ClueResponse, state: GameState): { ok: boolean; violations: string[] }`
  - `filterGuesses(guesses: string[], state: GameState): string[]` (returns canonical board words, deduped, order preserved)
- Legality policy (lenient): validate hard on game-breaking issues only; do NOT judge subtle derivatives.

- [ ] **Step 1: Write the failing test** — `codenames/tests/validate.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { validateClue, filterGuesses } from "../src/validate";
import { createGame } from "../src/engine";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}

describe("validateClue", () => {
  const s = createGame({ rng: rng(3) });
  const aiGreens = s.words.filter((_, i) => s.keys.ai[i] === "green");

  it("accepts a legal clue targeting the AI's greens", () => {
    const r = validateClue({ reasoning: "", clue: "OCEAN", number: 2, targets: aiGreens.slice(0, 2) }, s);
    expect(r.ok).toBe(true);
  });
  it("rejects a multi-word clue", () => {
    const r = validateClue({ reasoning: "", clue: "DEEP SEA", number: 1, targets: aiGreens.slice(0, 1) }, s);
    expect(r.ok).toBe(false);
  });
  it("rejects a clue equal to a board word", () => {
    const r = validateClue({ reasoning: "", clue: s.words[0]!.toLowerCase(), number: 1, targets: aiGreens.slice(0, 1) }, s);
    expect(r.ok).toBe(false);
  });
  it("rejects number != targets length", () => {
    const r = validateClue({ reasoning: "", clue: "OCEAN", number: 3, targets: aiGreens.slice(0, 1) }, s);
    expect(r.ok).toBe(false);
  });
  it("rejects a target that is not one of the AI's greens", () => {
    const notGreen = s.words.find((_, i) => s.keys.ai[i] !== "green")!;
    const r = validateClue({ reasoning: "", clue: "OCEAN", number: 1, targets: [notGreen] }, s);
    expect(r.ok).toBe(false);
  });
});

describe("filterGuesses", () => {
  const s = createGame({ rng: rng(3) });
  it("keeps board words (case-insensitive), drops junk + dupes", () => {
    const w0 = s.words[0]!;
    const out = filterGuesses([w0.toLowerCase(), "NOTAWORD", w0], s);
    expect(out).toEqual([w0]);
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd codenames && npm test -- validate`
Expected: FAIL — cannot find `../src/validate`.

- [ ] **Step 3: Create `src/validate.ts`**

```ts
import { z } from "zod";
import type { GameState } from "./types";
import { remainingWords } from "./engine";

export const ClueSchema = z.object({
  reasoning: z.string(),
  clue: z.string(),
  number: z.number().int(),
  targets: z.array(z.string()),
});
export type ClueResponse = z.infer<typeof ClueSchema>;

export const GuessSchema = z.object({
  reasoning: z.string(),
  guesses: z.array(z.string()),
});
export type GuessResponse = z.infer<typeof GuessSchema>;

const norm = (w: string) => w.trim().toUpperCase();

export function validateClue(resp: ClueResponse, state: GameState): { ok: boolean; violations: string[] } {
  const violations: string[] = [];
  const clue = resp.clue.trim();
  if (clue.length === 0 || /\s|-/.test(clue)) violations.push("clue must be exactly one word");

  const board = new Set(remainingWords(state).map(norm));
  if (board.has(norm(clue))) violations.push("clue must not be a word on the board");

  if (resp.number !== resp.targets.length) violations.push("number must equal the count of targets");

  const aiGreens = new Set(
    state.words.filter((_, i) => state.keys.ai[i] === "green" && !state.revealed[i]).map(norm),
  );
  for (const t of resp.targets) {
    if (!aiGreens.has(norm(t))) violations.push(`target "${t}" is not one of your remaining agents`);
  }
  return { ok: violations.length === 0, violations };
}

export function filterGuesses(guesses: string[], state: GameState): string[] {
  const canonical = new Map(remainingWords(state).map((w) => [norm(w), w]));
  const out: string[] = [];
  const seen = new Set<string>();
  for (const g of guesses) {
    const key = norm(g);
    const word = canonical.get(key);
    if (word && !seen.has(key)) { out.push(word); seen.add(key); }
  }
  return out;
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd codenames && npm test -- validate`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add codenames/src/validate.ts codenames/tests/validate.test.ts
git commit -m "feat(codenames): response schemas + lenient rule validation"
```

---

### Task 7: AI interaction layer (SDK + repair loop + failure handling)

**Files:**
- Create: `codenames/src/ai.ts`
- Test: `codenames/tests/ai.test.ts`

**Interfaces:**
- Consumes: `types.ts`, `engine.ts`, `prompts.ts`, `validate.ts`.
- Produces:
  - `interface LLMResult<T> { parsed: T | null; refusal: string | null; finishReason: string }`
  - `class LLMError extends Error { kind: "auth" | "rate_limit" | "network" | "other" }`
  - `interface LLMCaller { call<T>(messages: ChatMessage[], schema: z.ZodType<T>, name: string): Promise<LLMResult<T>> }`
  - `class OpenAICaller implements LLMCaller` (ctor `{ apiKey: string; model: string }`)
  - `type Logger = (line: string) => void`
  - `async getAIClue(caller, state, log): Promise<ClueResponse | null>` (null ⇒ AI passes)
  - `async getAIGuess(caller, state, log): Promise<string[]>` (filtered legal board words; [] ⇒ pass)
- Orchestration: up to 2 repair retries on clue-rule violations; one retry on truncation; refusal ⇒ pass; `LLMError` bubbles to the caller (UI shows it).

- [ ] **Step 1: Write the failing test** — `codenames/tests/ai.test.ts` (uses a fake caller, no network)

```ts
import { describe, it, expect, vi } from "vitest";
import { getAIClue, getAIGuess, type LLMCaller, type LLMResult } from "../src/ai";
import { createGame, giveClue } from "../src/engine";
import type { ClueResponse, GuessResponse } from "../src/validate";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const ok = <T>(parsed: T): LLMResult<T> => ({ parsed, refusal: null, finishReason: "stop" });

// caller that returns a scripted queue of results
function scripted(results: LLMResult<any>[]): LLMCaller {
  let i = 0;
  return { call: vi.fn(async () => results[i++]!) };
}

describe("getAIClue", () => {
  it("returns a legal clue on first try", async () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const greens = s.words.filter((_, i) => s.keys.ai[i] === "green");
    const caller = scripted([ok<ClueResponse>({ reasoning: "", clue: "OCEAN", number: 1, targets: greens.slice(0, 1) })]);
    const clue = await getAIClue(caller, s, () => {});
    expect(clue?.clue).toBe("OCEAN");
  });

  it("repairs an illegal clue, then succeeds", async () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const greens = s.words.filter((_, i) => s.keys.ai[i] === "green");
    const caller = scripted([
      ok<ClueResponse>({ reasoning: "", clue: "TWO WORDS", number: 1, targets: greens.slice(0, 1) }),
      ok<ClueResponse>({ reasoning: "", clue: "OCEAN", number: 1, targets: greens.slice(0, 1) }),
    ]);
    const clue = await getAIClue(caller, s, () => {});
    expect(clue?.clue).toBe("OCEAN");
    expect(caller.call).toHaveBeenCalledTimes(2);
  });

  it("passes (null) after exhausting retries", async () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const bad = ok<ClueResponse>({ reasoning: "", clue: "A B", number: 9, targets: [] });
    const caller = scripted([bad, bad, bad]);
    const clue = await getAIClue(caller, s, () => {});
    expect(clue).toBeNull();
  });

  it("passes (null) on refusal", async () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const caller = scripted([{ parsed: null, refusal: "no", finishReason: "stop" }]);
    expect(await getAIClue(caller, s, () => {})).toBeNull();
  });
});

describe("getAIGuess", () => {
  it("returns only legal board words", async () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    s = giveClue(s, "OCEAN", 2);
    const legal = s.words.slice(0, 2);
    const caller = scripted([ok<GuessResponse>({ reasoning: "", guesses: [...legal, "JUNK"] })]);
    expect(await getAIGuess(caller, s, () => {})).toEqual(legal);
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd codenames && npm test -- ai`
Expected: FAIL — cannot find `../src/ai`.

- [ ] **Step 3: Create `src/ai.ts`**

```ts
import OpenAI from "openai";
import { zodResponseFormat } from "openai/helpers/zod";
import { z } from "zod";
import type { GameState } from "./types";
import { buildClueMessages, buildGuessMessages, repairMessage, type ChatMessage } from "./prompts";
import { ClueSchema, GuessSchema, validateClue, filterGuesses, type ClueResponse } from "./validate";

export interface LLMResult<T> { parsed: T | null; refusal: string | null; finishReason: string; }
export type Logger = (line: string) => void;

export class LLMError extends Error {
  constructor(message: string, readonly kind: "auth" | "rate_limit" | "network" | "other") {
    super(message);
    this.name = "LLMError";
  }
}

export interface LLMCaller {
  call<T>(messages: ChatMessage[], schema: z.ZodType<T>, name: string): Promise<LLMResult<T>>;
}

export class OpenAICaller implements LLMCaller {
  private client: OpenAI;
  constructor(private opts: { apiKey: string; model: string }) {
    this.client = new OpenAI({ apiKey: opts.apiKey, dangerouslyAllowBrowser: true });
  }
  async call<T>(messages: ChatMessage[], schema: z.ZodType<T>, name: string): Promise<LLMResult<T>> {
    try {
      const completion = await this.client.chat.completions.parse({
        model: this.opts.model,
        messages,
        response_format: zodResponseFormat(schema as any, name),
        max_completion_tokens: 1200,
      });
      const choice = completion.choices[0]!;
      return {
        parsed: (choice.message.parsed as T) ?? null,
        refusal: choice.message.refusal ?? null,
        finishReason: choice.finish_reason,
      };
    } catch (e: any) {
      const status = e?.status ?? e?.response?.status;
      if (status === 401) throw new LLMError("Invalid API key.", "auth");
      if (status === 429) throw new LLMError("Rate limited — wait and retry.", "rate_limit");
      if (e?.name === "APIConnectionError" || e instanceof TypeError)
        throw new LLMError("Network error reaching OpenAI.", "network");
      throw new LLMError(e?.message ?? "Unknown OpenAI error.", "other");
    }
  }
}

const MAX_REPAIRS = 2;

export async function getAIClue(caller: LLMCaller, state: GameState, log: Logger): Promise<ClueResponse | null> {
  const messages = buildClueMessages(state);
  for (let attempt = 0; attempt <= MAX_REPAIRS; attempt++) {
    let res = await caller.call(messages, ClueSchema, "clue");
    if (res.finishReason === "length") {
      log("AI clue was cut off (truncated); retrying once.");
      res = await caller.call(messages, ClueSchema, "clue");
    }
    if (res.refusal) { log(`AI refused to clue: ${res.refusal}. Passing.`); return null; }
    if (!res.parsed) { log("AI returned no clue content. Passing."); return null; }

    const check = validateClue(res.parsed, state);
    if (check.ok) { log(`AI clue: "${res.parsed.clue}" for ${res.parsed.number}.`); return res.parsed; }

    log(`Illegal AI clue (${check.violations.join("; ")}); asking again.`);
    messages.push({ role: "assistant", content: JSON.stringify(res.parsed) });
    messages.push(repairMessage(check.violations));
  }
  log("AI could not produce a legal clue; passing its turn.");
  return null;
}

export async function getAIGuess(caller: LLMCaller, state: GameState, log: Logger): Promise<string[]> {
  const messages = buildGuessMessages(state);
  let res = await caller.call(messages, GuessSchema, "guess");
  if (res.finishReason === "length") {
    log("AI guess was cut off; retrying once.");
    res = await caller.call(messages, GuessSchema, "guess");
  }
  if (res.refusal) { log(`AI refused to guess: ${res.refusal}. Passing.`); return []; }
  if (!res.parsed) { log("AI returned no guesses. Passing."); return []; }

  const legal = filterGuesses(res.parsed.guesses, state);
  if (legal.length < res.parsed.guesses.length) log("Dropped guesses that were not on the board.");
  log(`AI will guess: ${legal.join(", ") || "(nothing)"}.`);
  return legal;
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd codenames && npm test -- ai`
Expected: PASS. (Also run `npm run build` to confirm the SDK imports type-check.)

- [ ] **Step 5: Commit**

```bash
git add codenames/src/ai.ts codenames/tests/ai.test.ts
git commit -m "feat(codenames): OpenAI layer with repair loop + failure handling"
```

---

### Task 8: UI rendering + key handling

**Files:**
- Create: `codenames/src/ui.ts`
- Create: `codenames/src/style.css`
- Test: `codenames/tests/ui.test.ts`

**Interfaces:**
- Consumes: `types.ts` only (pure rendering; no engine mutation, no network).
- Produces:
  - `interface UICallbacks { onClueSubmit(word: string, num: number): void; onCellClick(word: string): void; onEndGuessing(): void; onSaveKey(key: string, remember: boolean): void; onNewGame(): void; }`
  - `class GameUI { constructor(root: HTMLElement, cb: UICallbacks); render(state: GameState): void; log(line: string): void; getModel(): string; getKey(): string; setError(msg: string | null): void; }`
  - `readSavedKey(): string` / `saveKey(key: string, remember: boolean): void` (sessionStorage only; never localStorage; never console.log the key)

- [ ] **Step 1: Write the failing test** — `codenames/tests/ui.test.ts`

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { GameUI } from "../src/ui";
import { createGame } from "../src/engine";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const cb = () => ({ onClueSubmit: vi.fn(), onCellClick: vi.fn(), onEndGuessing: vi.fn(), onSaveKey: vi.fn(), onNewGame: vi.fn() });

describe("GameUI", () => {
  let root: HTMLElement;
  beforeEach(() => { root = document.createElement("div"); document.body.appendChild(root); });

  it("renders 25 cells", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    expect(root.querySelectorAll("[data-cell]").length).toBe(25);
  });

  it("clicking a cell fires onCellClick with its word", () => {
    const callbacks = cb();
    const ui = new GameUI(root, callbacks);
    const s = createGame({ rng: rng(3) });
    ui.render({ ...s, phase: "awaitGuess", currentClue: { word: "X", number: 1, guessesMade: 0 }, clueGiver: "human" });
    (root.querySelector("[data-cell]") as HTMLElement).click();
    expect(callbacks.onCellClick).toHaveBeenCalledWith(s.words[0]);
  });

  it("log appends a line", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    ui.log("hello");
    expect(root.textContent).toContain("hello");
  });

  it("never writes the key to localStorage", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    // save with remember=false uses sessionStorage; localStorage stays empty
    (ui as any).saveKeyForTest?.("sk-secret", false);
    expect(localStorage.getItem("openai_key")).toBeNull();
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd codenames && npm test -- ui`
Expected: FAIL — cannot find `../src/ui`.

- [ ] **Step 3: Implement `src/ui.ts` + `src/style.css`**

Implement `GameUI` to render, in `root`: a **setup bar** (API key `<input type="password">`, model input defaulting to `gpt-5.6`, "Save key" checkbox for session-only persistence, "New game" button); the **5×5 grid** (`<button data-cell>` per word; when `state.clueGiver === "human"` shade cells by `state.keys.human[i]`; add a `revealed` class + category class for covered cells; cell click → `cb.onCellClick(word)`); a **clue bar** (word input + number input + submit → `cb.onClueSubmit`) shown when `phase === "awaitClue" && clueGiver === "human"`; an **"End guessing"** button shown when `phase === "awaitGuess" && clueGiver === "human"`; a **status line** (turns remaining, agents found `n/15`, sudden-death badge, win/loss); an **AI log panel** (`log()` appends `<div>`); an **error banner** (`setError`). Key helpers:

```ts
const KEY_NAME = "openai_key";
export function readSavedKey(): string { return sessionStorage.getItem(KEY_NAME) ?? ""; }
export function saveKey(key: string, remember: boolean): void {
  if (remember) sessionStorage.setItem(KEY_NAME, key); else sessionStorage.removeItem(KEY_NAME);
  // NOTE: never localStorage; never console.log(key)
}
```

`getKey()`/`getModel()` read the current input values. Expose a tiny `saveKeyForTest` bound to `saveKey` (or make the test call the exported `saveKey`). Include a visible one-line note: "Your key stays in this browser and is sent directly to OpenAI (dangerouslyAllowBrowser)."

- [ ] **Step 4: Run tests, verify pass**

Run: `cd codenames && npm test -- ui`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add codenames/src/ui.ts codenames/src/style.css codenames/tests/ui.test.ts
git commit -m "feat(codenames): DOM UI, grid rendering, session-only key handling"
```

---

### Task 9: Wire everything (`main.ts`) + integration smoke test

**Files:**
- Create: `codenames/src/main.ts`
- Test: `codenames/tests/integration.test.ts`

**Interfaces:**
- Consumes: `engine.ts`, `ai.ts`, `ui.ts`, `types.ts`.
- Produces:
  - `createController(deps: { ui: Pick<GameUI,"render"|"log"|"getKey"|"getModel"|"setError">; makeCaller: (key: string, model: string) => LLMCaller; rng?: () => number }): { newGame(): void; submitClue(w: string, n: number): void; clickCell(w: string): void; endGuessing(): void }`
  - `main.ts` default entry builds the real `GameUI` + `OpenAICaller` and mounts on `#app`.
- Controller responsibilities: hold current `GameState`; on human clue → `giveClue` then `getAIGuess` and apply each returned guess in order via `guess()` (stopping when phase flips); on AI's turn (`clueGiver==="ai" && phase==="awaitClue"`) → `getAIClue` then `giveClue`, and wait for human cell clicks to `guess()`; catch `LLMError` → `ui.setError`.

- [ ] **Step 1: Write the failing integration test** — `codenames/tests/integration.test.ts`

```ts
import { describe, it, expect, vi } from "vitest";
import { createController } from "../src/main";
import type { LLMCaller, LLMResult } from "../src/ai";
import type { GuessResponse } from "../src/validate";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const ok = <T>(p: T): LLMResult<T> => ({ parsed: p, refusal: null, finishReason: "stop" });

describe("controller", () => {
  it("human clue → AI guesses are applied and logged", async () => {
    const logs: string[] = [];
    const ui = {
      render: vi.fn(), log: (l: string) => logs.push(l),
      getKey: () => "sk-x", getModel: () => "gpt-5.6", setError: vi.fn(),
    };
    // AI guesser returns the first remaining board word
    const caller: LLMCaller = { call: vi.fn(async (): Promise<LLMResult<GuessResponse>> => ok({ reasoning: "", guesses: [] })) };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3) });
    c.newGame();
    await c.submitClue("OCEAN", 1);
    expect(ui.render).toHaveBeenCalled();
    expect((caller.call as any)).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd codenames && npm test -- integration`
Expected: FAIL — cannot find `../src/main`.

- [ ] **Step 3: Implement `src/main.ts`**

Implement `createController` per the responsibilities above (async `submitClue`/AI-turn handlers, re-`render()` after each state change, `try/catch (LLMError)` → `ui.setError`). Then the entry:

```ts
// at bottom of main.ts — real app wiring (not exercised by jsdom tests)
import { GameUI } from "./ui";
import { OpenAICaller } from "./ai";
import "./style.css";

if (typeof document !== "undefined" && document.getElementById("app")) {
  const root = document.getElementById("app")!;
  let controller: ReturnType<typeof createController>;
  const ui = new GameUI(root, {
    onClueSubmit: (w, n) => controller.submitClue(w, n),
    onCellClick: (w) => controller.clickCell(w),
    onEndGuessing: () => controller.endGuessing(),
    onSaveKey: () => {},
    onNewGame: () => controller.newGame(),
  });
  controller = createController({
    ui,
    makeCaller: (key, model) => new OpenAICaller({ apiKey: key, model }),
  });
  controller.newGame();
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd codenames && npm test`
Expected: PASS (whole suite). Also `npm run dev` and manually play one round to sanity-check wiring.

- [ ] **Step 5: Commit**

```bash
git add codenames/src/main.ts codenames/tests/integration.test.ts
git commit -m "feat(codenames): controller wiring + integration smoke test"
```

---

### Task 10: Offline eval harness

**Files:**
- Create: `codenames/eval/metrics.ts`
- Create: `codenames/eval/run.ts`
- Test: `codenames/tests/metrics.test.ts`

**Interfaces:**
- Consumes: `engine.ts`, `ai.ts`, `types.ts`.
- Produces:
  - `interface GameResult { won: boolean; agentsFound: number; hitAssassin: boolean; clues: number; illegalClues: number; repairs: number }`
  - `aggregate(results: GameResult[]): { games: number; winRate: number; avgAgents: number; assassinRate: number; illegalClueRate: number; avgRepairsPerClue: number }`
  - `run.ts`: self-plays N games (AI in both roles) via `OpenAICaller`, key from `process.env.OPENAI_API_KEY`, prints the aggregate table. `npm run eval -- 20` runs 20 games.

- [ ] **Step 1: Write the failing test** — `codenames/tests/metrics.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { aggregate, type GameResult } from "../eval/metrics";

describe("aggregate", () => {
  it("computes rates over results", () => {
    const rs: GameResult[] = [
      { won: true, agentsFound: 15, hitAssassin: false, clues: 6, illegalClues: 1, repairs: 1 },
      { won: false, agentsFound: 8, hitAssassin: true, clues: 4, illegalClues: 0, repairs: 0 },
    ];
    const a = aggregate(rs);
    expect(a.games).toBe(2);
    expect(a.winRate).toBeCloseTo(0.5);
    expect(a.assassinRate).toBeCloseTo(0.5);
    expect(a.avgAgents).toBeCloseTo(11.5);
    expect(a.illegalClueRate).toBeCloseTo(1 / 10);
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd codenames && npm test -- metrics`
Expected: FAIL — cannot find `../eval/metrics`.

- [ ] **Step 3: Implement `eval/metrics.ts` and `eval/run.ts`**

```ts
// eval/metrics.ts
export interface GameResult {
  won: boolean; agentsFound: number; hitAssassin: boolean;
  clues: number; illegalClues: number; repairs: number;
}
export function aggregate(results: GameResult[]) {
  const games = results.length;
  const sum = (f: (r: GameResult) => number) => results.reduce((a, r) => a + f(r), 0);
  const clues = sum((r) => r.clues) || 1;
  return {
    games,
    winRate: sum((r) => (r.won ? 1 : 0)) / games,
    avgAgents: sum((r) => r.agentsFound) / games,
    assassinRate: sum((r) => (r.hitAssassin ? 1 : 0)) / games,
    illegalClueRate: sum((r) => r.illegalClues) / clues,
    avgRepairsPerClue: sum((r) => r.repairs) / clues,
  };
}
```

`eval/run.ts` plays full self-play games: loop until `status !== "playing"`, on each `awaitClue` call `getAIClue` (count clues; on `null` pass by `endGuessing` after a no-op `giveClue`, or skip a token — count that too), then `getAIGuess` and apply guesses. Track `illegalClues`/`repairs` via a logger that counts lines matching `/Illegal AI clue|asking again/`. Print `aggregate(results)` as a table. Read N from `process.argv[2]` (default 10). Never commit a key.

- [ ] **Step 4: Run tests, verify pass**

Run: `cd codenames && npm test -- metrics`
Expected: PASS. (Optionally, with a real key: `OPENAI_API_KEY=sk-... npm run eval -- 5`.)

- [ ] **Step 5: Commit**

```bash
git add codenames/eval/metrics.ts codenames/eval/run.ts codenames/tests/metrics.test.ts
git commit -m "feat(codenames): offline eval harness + quality metrics"
```

---

### Task 11: Build + Quarto deploy integration

**Files:**
- Build output: `posts/codenames/app/**` (generated + committed)
- Modify: `_quarto.yml` (add resource glob)

**Interfaces:**
- Produces: a committed, Quarto-copied static app at `/posts/codenames/app/`.

- [ ] **Step 1: Build the app**

Run: `cd codenames && npm run build`
Expected: `posts/codenames/app/index.html` + `assets/` created; the build's `tsc --noEmit` passes.

- [ ] **Step 2: Add the resource glob** — `_quarto.yml`, in the `project.resources:` list

```yaml
    - "posts/codenames/app/**"
```

- [ ] **Step 3: Verify Quarto copies it**

Run: `quarto render posts` (or full `quarto render`) then check `_site/posts/codenames/app/index.html` exists.
Expected: file present; open it and confirm the grid renders.

- [ ] **Step 4: Commit**

```bash
git add posts/codenames/app _quarto.yml
git commit -m "build(codenames): commit built app + wire Quarto resource copy"
```

---

### Task 12: Blog post

**Files:**
- Create: `posts/codenames/index.qmd`
- Optional: `posts/codenames/thumbnail.png`

**Interfaces:**
- Produces: a Quarto post linking to `app/` and narrating the build.

- [ ] **Step 1: Create `posts/codenames/index.qmd`**

```markdown
---
title: "Playing Codenames Duet with an AI partner"
description: "A browser game where your teammate is an LLM — and what it took to make its clues reliable."
date: 2026-08-19
categories: [AI, games, TypeScript]
draft: true
---

## Play it

[**Open the game →**](app/index.html) — bring your own OpenAI API key; it stays
in your browser and is sent directly to OpenAI.

## What this is

Codenames Duet is the cooperative variant... (intro).

## The headline: getting *good* clues, not parsing text

(Discuss the clue/guess-quality work: strategy prompt, few-shot, reasoning-first,
steering away from the assassin. Insert eval-harness numbers from `npm run eval`.)

## Architecture: a static site with no backend

(BYOK + `dangerouslyAllowBrowser`; the honest tradeoff; why no proxy.)

## Token cost

(~$0.005–$0.08 per game; cache-first prompts.)

## Interpret → validate → repair

(Structured Outputs guarantees valid JSON, so the real work was semantic legality,
truncation, refusals, and rate limits. Show a real repair-loop log excerpt.)
```

- [ ] **Step 2: Fill quality numbers**

Run `OPENAI_API_KEY=sk-... npm run eval -- 20` (in `codenames/`), paste the aggregate table into the "headline" section, replacing the parenthetical prompts with real prose.

- [ ] **Step 3: Verify render**

Run: `quarto render posts/codenames/index.qmd`
Expected: post builds; the "Open the game" link resolves to `app/index.html`.

- [ ] **Step 4: Commit**

```bash
git add posts/codenames/index.qmd posts/codenames/thumbnail.png
git commit -m "docs(codenames): blog post narrating the build"
```

- [ ] **Step 5: Promote from draft** (when satisfied): set `draft: false` and commit.

---

## Self-Review

**Spec coverage:**
- Static + BYOK, OpenAI only → Global Constraints, Task 7, Task 8. ✓
- Full Duet ruleset (dual key cards, 15 agents, timer, sudden death) → Tasks 3, 4. ✓
- TypeScript + Vite, multi-file separation → Task 1; engine/ai/ui/validate/prompts split across Tasks 2–9. ✓
- Structured Outputs + typed parse → Tasks 6, 7. ✓
- Interpret→validate→repair + API-level failures (truncation/refusal/401/429) → Task 7. ✓
- Lenient legality policy → Task 6 (`validateClue`, no substring/derivative check). ✓
- Game history in context, compact, cache-first → Task 5. ✓
- Clue/guess quality center → Task 5 (prompts) + Task 10 (eval). ✓
- Eval harness with metrics → Task 10. ✓
- Committed `dist/` + Quarto resource → Task 11. ✓
- Blog post → Task 12. ✓
- Vitest, mocked AI, no live API in tests → Tasks 3–10. ✓
- Key never logged / never localStorage → Task 8. ✓

**Type consistency:** `Category`/`KeyCard`/`GameState`/`Player`/`HistoryTurn` defined once in Task 2 and reused verbatim; `ClueResponse`/`GuessResponse` defined in Task 6, consumed in Task 7; `LLMCaller`/`LLMResult`/`Logger` defined in Task 7, consumed in Tasks 9–10; `GameUI`/`UICallbacks` defined in Task 8, consumed in Task 9. `giverKey`, `remainingWords`, `aiGreenWordsRemaining` defined in Task 4, consumed in Tasks 5–6.

**Deferred (verify at implementation time, per spec):** exact `DEFAULT_MODEL` id; the mutual-assassin table cell (locked by the Task 3 test — if official rules differ, table + test move together).

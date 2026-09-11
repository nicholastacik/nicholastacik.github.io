import { describe, it, expect } from "vitest";
import { createGame, giveClue, guess, endGuessing, passTurn, giverKey, remainingWords, aiGreenWordsRemaining, aiWordsRemaining, confirmedBystanders, makeRng, suddenDeathGuess } from "../src/engine";
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

  it("starts not in sudden death", () => {
    const s = createGame({ rng: rng(3) });
    expect(s.suddenDeath).toBe(false);
    expect(s.suddenDeathGuesses).toEqual([]);
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

  it("exhausting the timer with fewer than 15 agents enters sudden death (not a loss)", () => {
    let s = createGame({ rng: rng(3) });
    s.turnsRemaining = 1;
    s = giveClue(s, "OCEAN", 1);
    s = endGuessing(s);
    expect(s.turnsRemaining).toBe(0);
    expect(s.status).toBe("playing");
    expect(s.suddenDeath).toBe(true);
  });

  it("win condition: reaching 15 agents found", () => {
    let s = createGame({ rng: rng(3) });
    s.agentsFound = 14;
    s = giveClue(s, "FINAL", 1);
    s = guess(s, wordOfCategory(s, "green"));
    expect(s.status).toBe("won");
  });

  it("remainingWords returns all unrevealed words", () => {
    const s = createGame({ rng: rng(3) });
    expect(remainingWords(s)).toHaveLength(25);
  });

  it("aiGreenWordsRemaining returns unrevealed green words on AI's key", () => {
    const s = createGame({ rng: rng(3) });
    const green = aiGreenWordsRemaining(s);
    expect(green).toHaveLength(9);
    expect(green.every(w => s.keys.ai[s.words.indexOf(w)] === "green")).toBe(true);
  });

  it("aiWordsRemaining returns unrevealed words of a given category on AI's key", () => {
    const s = createGame({ rng: rng(3) });
    for (const cat of ["green", "bystander", "assassin"] as const) {
      const words = aiWordsRemaining(s, cat);
      expect(words.every(w => s.keys.ai[s.words.indexOf(w)] === cat)).toBe(true);
    }
    // 3 assassins per Duet key card
    expect(aiWordsRemaining(s, "assassin")).toHaveLength(3);
    // matches the green-specific helper
    expect(aiWordsRemaining(s, "green")).toEqual(aiGreenWordsRemaining(s));
  });

  it("aiWordsRemaining excludes revealed words", () => {
    const s = createGame({ rng: rng(3) });
    const assassin = s.words[s.keys.ai.findIndex((c) => c === "assassin")]!;
    const before = aiWordsRemaining(s, "assassin");
    const revealed = { ...s, revealed: s.revealed.map((r, i) => i === s.words.indexOf(assassin) ? true : r) };
    const after = aiWordsRemaining(revealed, "assassin");
    expect(before).toContain(assassin);
    expect(after).not.toContain(assassin);
    expect(after).toHaveLength(before.length - 1);
  });

  it("endTurn skips a clue-giver with no agents left (the other gives all remaining clues)", () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    // Reveal ALL of the human's greens → the human has nothing left to clue for.
    s = { ...s, revealed: s.revealed.map((r, i) => (s.keys.human[i] === "green" ? true : r)) };
    s = giveClue(s, "OCEAN", 1);
    s = endGuessing(s); // end the AI's clue turn
    // Would normally flip to the human, but the human has no agents → stay on AI.
    expect(s.clueGiver).toBe("ai");
  });

  it("endTurn still alternates normally when both players have agents left", () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    s = giveClue(s, "OCEAN", 1);
    s = endGuessing(s);
    expect(s.clueGiver).toBe("human");
  });

  it("confirmedBystanders lists bystanders on the CURRENT clue-giver's card only", () => {
    const base = createGame({ rng: rng(3), firstClueGiver: "ai" });
    // A past "ai"-clue turn where ANT was a bystander on the AI's card; current giver = ai.
    const s = { ...base, clueGiver: "ai" as const, history: [
      { clueGiver: "ai" as const, clue: "X", number: 1, guesses: ["ANT"], outcomes: ["bystander" as const] },
      { clueGiver: "human" as const, clue: "Y", number: 1, guesses: ["BEE"], outcomes: ["bystander" as const] },
    ]};
    expect(confirmedBystanders(s)).toContain("ANT");     // ai's card
    expect(confirmedBystanders(s)).not.toContain("BEE"); // human's card — different card
  });

  it("immutability: guess does not mutate input state", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "TEST", 2);
    const before = JSON.stringify(s);
    guess(s, wordOfCategory(s, "green"));
    const after = JSON.stringify(s);
    expect(before).toBe(after);
  });

  it("immutability: giveClue does not mutate input state", () => {
    const s = createGame({ rng: rng(3) });
    const before = JSON.stringify(s);
    giveClue(s, "TEST", 2);
    const after = JSON.stringify(s);
    expect(before).toBe(after);
  });

  it("immutability: endGuessing does not mutate input state", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "TEST", 2);
    const before = JSON.stringify(s);
    endGuessing(s);
    const after = JSON.stringify(s);
    expect(before).toBe(after);
  });

  it("giveClue when status is lost is a no-op with no history appended", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "OCEAN", 1);
    s = guess(s, wordOfCategory(s, "assassin"));
    expect(s.status).toBe("lost");
    const historyLenBefore = s.history.length;
    s = giveClue(s, "NOPE", 5);
    expect(s.history.length).toBe(historyLenBefore);
  });

  it("calling guess when phase is awaitClue (no active clue) does not crash and does not reveal", () => {
    const s = createGame({ rng: rng(3) });
    expect(s.phase).toBe("awaitClue");
    const revealedBefore = s.revealed.slice();
    const result = guess(s, s.words[0]!);
    expect(result.status).toBe("playing");
    expect(result.revealed).toEqual(revealedBefore);
  });

  it("calling guess when status is not playing does not reveal", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "OCEAN", 1);
    s = guess(s, wordOfCategory(s, "assassin"));
    expect(s.status).toBe("lost");
    const revealedBefore = s.revealed.slice();
    const result = guess(s, s.words[0]!);
    expect(result.revealed).toEqual(revealedBefore);
  });

  it("createGame sizes revealed array to words.length", () => {
    const s = createGame({ rng: rng(3) });
    expect(s.revealed.length).toBe(s.words.length);
  });

  describe("passTurn", () => {
    it("advances the turn: swaps clueGiver, decrements the timer, clears the clue", () => {
      const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
      const next = passTurn(s);
      expect(next.clueGiver).toBe("human");
      expect(next.turnsRemaining).toBe(8);
      expect(next.phase).toBe("awaitClue");
      expect(next.currentClue).toBeNull();
    });

    it("passTurn enters sudden death when the timer hits 0 with agents remaining", () => {
      const s = createGame({ rng: rng(3) });
      s.turnsRemaining = 1;
      const next = passTurn(s);
      expect(next.turnsRemaining).toBe(0);
      expect(next.status).toBe("playing");
      expect(next.suddenDeath).toBe(true);
    });

    it("is a no-op when status is not playing", () => {
      let s = createGame({ rng: rng(3) });
      s = giveClue(s, "OCEAN", 1);
      s = guess(s, wordOfCategory(s, "assassin"));
      expect(s.status).toBe("lost");
      const next = passTurn(s);
      expect(next).toBe(s);
    });

    it("is a no-op when phase is not awaitClue", () => {
      let s = createGame({ rng: rng(3) });
      s = giveClue(s, "OCEAN", 1);
      expect(s.phase).toBe("awaitGuess");
      const next = passTurn(s);
      expect(next).toBe(s);
    });

    it("does not mutate the input state", () => {
      const s = createGame({ rng: rng(3) });
      const before = JSON.stringify(s);
      passTurn(s);
      const after = JSON.stringify(s);
      expect(before).toBe(after);
    });
  });
});

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

describe("makeRng", () => {
  it("is deterministic per seed and differs across seeds, values in [0,1)", () => {
    const a = makeRng("hello");
    const b = makeRng("hello");
    const seqA = [a(), a(), a()];
    expect([b(), b(), b()]).toEqual(seqA); // same seed → same sequence
    const c = makeRng("world");
    expect([c(), c(), c()]).not.toEqual(seqA); // different seed → different
    for (const v of seqA) {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("accepts a numeric seed", () => {
    expect(makeRng(42)()).toBe(makeRng(42)());
  });

  it("same seed → identical board and key cards", () => {
    const g1 = createGame({ rng: makeRng("board-seed") });
    const g2 = createGame({ rng: makeRng("board-seed") });
    expect(g1.words).toEqual(g2.words);
    expect(g1.keys).toEqual(g2.keys);
  });
});

describe("bystander stays in play (Duet rule)", () => {
  it("a bystander guess does not cover the word; it can still be found as the partner's agent", () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    // a word that's a bystander on the HUMAN card but an AGENT on the AI card
    const idx = s.words.findIndex((_, i) => s.keys.human[i] === "bystander" && s.keys.ai[i] === "green");
    expect(idx).toBeGreaterThanOrEqual(0);
    const word = s.words[idx]!;

    s = giveClue(s, "AAA", 1);            // human clues
    s = guess(s, word);                    // partner guesses it → bystander on human's card
    expect(s.revealed[idx]).toBe(false);   // NOT covered
    expect(remainingWords(s)).toContain(word);
    expect(s.clueGiver).toBe("ai");        // turn ended → AI's clue turn

    s = giveClue(s, "BBB", 1);             // AI clues (its turn)
    const before = s.agentsFound;
    s = guess(s, word);                     // human guesses the same word → green on AI's card
    expect(s.revealed[idx]).toBe(true);     // now covered as an agent
    expect(s.agentsFound).toBe(before + 1);
  });
})

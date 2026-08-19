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

import { describe, it, expect } from "vitest";
import { createGame, giveClue, guess, endGuessing, passTurn, giverKey, remainingWords, aiGreenWordsRemaining } from "../src/engine";
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

  it("win condition: reaching 15 agents found", () => {
    let s = createGame({ rng: rng(3) });
    s.agentsFound = 14;
    s = giveClue(s, "FINAL", 1);
    s = guess(s, wordOfCategory(s, "green"));
    expect(s.status).toBe("won");
  });

  it("sudden death green alternates guesser and does not decrement timer", () => {
    let s = createGame({ rng: rng(3) });
    s.suddenDeath = true;
    s.phase = "awaitGuess";
    const giverBefore = s.clueGiver;
    const timerBefore = s.turnsRemaining;
    s = guess(s, wordOfCategory(s, "green"));
    expect(s.status).toBe("playing");
    expect(s.clueGiver).not.toBe(giverBefore);
    expect(s.turnsRemaining).toBe(timerBefore);
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

  it("giveClue during sudden death is a no-op with no history appended", () => {
    let s = createGame({ rng: rng(3) });
    s.suddenDeath = true;
    const historyLenBefore = s.history.length;
    s = giveClue(s, "NOPE", 5);
    expect(s.suddenDeath).toBe(true);
    expect(s.history.length).toBe(historyLenBefore);
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

    it("sets suddenDeath when the timer hits 0", () => {
      const s = createGame({ rng: rng(3) });
      s.turnsRemaining = 1;
      const next = passTurn(s);
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

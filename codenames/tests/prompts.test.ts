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

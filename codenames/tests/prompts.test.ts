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

  it("clue messages: disclose the AI's own assassins and bystanders, distinctly", () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const user = buildClueMessages(s)[1]!.content;
    const assassin = s.words.find((_, i) => s.keys.ai[i] === "assassin")!;
    const bystander = s.words.find((_, i) => s.keys.ai[i] === "bystander")!;
    // both danger words are named to the clue-giver...
    expect(user).toContain(assassin);
    expect(user).toContain(bystander);
    // ...under distinct, severity-labelled headings (assassin = instant loss)
    expect(user).toMatch(/ASSASSINS on YOUR key card/);
    expect(user).toMatch(/BYSTANDERS on YOUR key card/);
    expect(user).toMatch(/lose instantly/i);
    // the assassin is listed under the assassin heading, not the bystander one
    const assassinLine = user.split("\n").find((l) => /ASSASSINS on YOUR key card/.test(l))!;
    expect(assassinLine).toContain(assassin);
    expect(assassinLine).not.toContain(bystander);
  });

  it("guess messages: guesser gets board but NOT the key card", () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    s = giveClue(s, "OCEAN", 2);
    const msgs = buildGuessMessages(s);
    expect(msgs[1]!.content).toContain("OCEAN");
    // Category labels (assassin, bystander) only appear in system message, never in user message
    expect(msgs[1]!.content).not.toMatch(/assassin|bystander/i); // no key-card leak
  });

  it("guesser system prompt makes the bonus (N+1) guess conservative", () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    s = giveClue(s, "OCEAN", 2);
    const sys = buildGuessMessages(s)[0]!.content.toLowerCase();
    expect(sys).toContain("bonus");
    expect(sys).toMatch(/earlier clue/);
    expect(sys).toContain("stop after the clue's number");
  });

  it("history is compact and omits reasoning", () => {
    let s = createGame({ rng: rng(3) });
    s = giveClue(s, "OCEAN", 1);
    const greenWord = s.words[giverKey(s).findIndex((c) => c === "green")]!;
    s = guess(s, greenWord);
    const h = formatHistory(s);
    // Exact compact format: one line per turn, no reasoning fields or extra cruft
    const expected = `human clued "OCEAN" 1 -> ${greenWord}=green`;
    expect(h).toBe(expected);
  });

  it("repairMessage names the violations", () => {
    const m = repairMessage(["clue must be one word"]);
    expect(m.role).toBe("user");
    expect(m.content).toContain("clue must be one word");
  });
});

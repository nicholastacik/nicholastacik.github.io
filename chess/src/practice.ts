import type { Path } from "./tree";
import { positionAt } from "./tree";

export type Grade =
  | { kind: "correct"; expected: string }
  | { kind: "mismatch"; expected: string; played: string };

export interface PracticeState {
  fen: string;
  ply: number; // number of book moves applied so far (0 = start position)
  toMove: "user" | "opponent" | "done";
  mistakes: number;
  revealed: number;
  cleanFirstTry: number;
}

export interface Summary {
  plies: number;
  cleanFirstTry: number;
  mistakes: number;
  revealed: number;
}

export interface Drill {
  state(): PracticeState;
  playOpponent(): { san: string } | null;
  submit(san: string): Grade;
  reveal(): string;
  summary(): Summary;
}

// line[0] is the root; line[i] (i>=1) is the book move at ply i. White plays odd
// plies, Black even plies. The user owns the plies for `userSide`.
export function createDrill(line: Path, userSide: "white" | "black"): Drill {
  const moves = line.slice(1); // book SAN nodes, ply 1..N
  const total = moves.length;
  let ply = 0; // book moves applied
  let mistakes = 0;
  let revealed = 0;
  let cleanFirstTry = 0;
  let dirtyThisPly = false; // a mismatch or reveal happened at the current ply

  const sideAt = (nextPly: number): "white" | "black" => (nextPly % 2 === 1 ? "white" : "black");
  const isUsersTurn = (): boolean => ply < total && sideAt(ply + 1) === userSide;

  const toMove = (): PracticeState["toMove"] =>
    ply >= total ? "done" : isUsersTurn() ? "user" : "opponent";

  const expectedSan = (): string => moves[ply]!.san as string;

  const fen = (): string => positionAt(line.slice(0, ply + 1)).fen;

  const advance = (): void => {
    ply += 1;
    dirtyThisPly = false;
  };

  return {
    state(): PracticeState {
      return { fen: fen(), ply, toMove: toMove(), mistakes, revealed, cleanFirstTry };
    },
    playOpponent() {
      if (toMove() !== "opponent") return null;
      const san = expectedSan();
      advance();
      return { san };
    },
    submit(san: string): Grade {
      if (toMove() !== "user") throw new Error("submit() called when it is not the user's turn");
      const expected = expectedSan();
      if (san === expected) {
        if (!dirtyThisPly) cleanFirstTry += 1;
        advance();
        return { kind: "correct", expected };
      }
      mistakes += 1;
      dirtyThisPly = true;
      return { kind: "mismatch", expected, played: san };
    },
    reveal(): string {
      if (toMove() !== "user") throw new Error("reveal() called when it is not the user's turn");
      const expected = expectedSan();
      revealed += 1;
      advance();
      return expected;
    },
    summary(): Summary {
      return { plies: total, cleanFirstTry, mistakes, revealed };
    },
  };
}

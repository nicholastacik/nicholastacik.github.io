export interface EngineEval {
  bestMove: string; // UCI, e.g. "e2e4"
  cp: number | null; // White-perspective centipawns; null iff mate is set
  mate: number | null; // White-perspective mate-in-N; null iff cp is set
  depth: number;
}

export interface EvalProvider {
  evaluate(fen: string): Promise<EngineEval>;
}

interface ChessApiOpts {
  depth?: number;
  endpoint?: string;
  fetchFn?: typeof fetch;
}

export class ChessApiProvider implements EvalProvider {
  private depth: number;
  private endpoint: string;
  private fetchFn: typeof fetch;

  constructor(opts: ChessApiOpts = {}) {
    this.depth = opts.depth ?? 12;
    this.endpoint = opts.endpoint ?? "https://chess-api.com/v1";
    this.fetchFn = opts.fetchFn ?? fetch;
  }

  async evaluate(fen: string): Promise<EngineEval> {
    const res = await this.fetchFn(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fen, depth: this.depth }),
    });
    if (!res.ok) throw new Error(`chess-api ${res.status}`);
    const data = (await res.json()) as Record<string, unknown>;
    const move = data["move"];
    if (typeof move !== "string") throw new Error("chess-api: missing move");
    const mateRaw = data["mate"];
    const mate = typeof mateRaw === "number" ? mateRaw : null;
    let cp: number | null = null;
    if (mate === null) {
      const evalNum = Number(data["eval"]);
      if (!Number.isFinite(evalNum)) throw new Error("chess-api: non-numeric eval");
      cp = Math.round(evalNum * 100);
    }
    const depth = typeof data["depth"] === "number" ? (data["depth"] as number) : this.depth;
    return { bestMove: move, cp, mate, depth };
  }
}

// Wraps any provider with a localStorage-backed cache keyed by FEN. The inner
// provider owns depth, so a fixed-depth provider yields a stable key space.
export class CachingEvalProvider implements EvalProvider {
  constructor(
    private inner: EvalProvider,
    private store: Storage | undefined = typeof localStorage !== "undefined" ? localStorage : undefined,
  ) {}

  async evaluate(fen: string): Promise<EngineEval> {
    const key = `chess:eval:${fen}`;
    try {
      const hit = this.store?.getItem(key);
      if (hit) return JSON.parse(hit) as EngineEval;
    } catch {
      /* ignore corrupt/absent storage */
    }
    const result = await this.inner.evaluate(fen);
    try {
      this.store?.setItem(key, JSON.stringify(result));
    } catch {
      /* ignore quota/absent storage */
    }
    return result;
  }
}

export type MismatchVerdict =
  | { kind: "playable"; bestMoveUci: string }
  | { kind: "loses"; lossCp: number; bestMoveUci: string }
  | { kind: "mated"; mateIn: number }
  | { kind: "missed-mate"; mateIn: number; bestMoveUci: string };

const PLAYABLE_CP = 50; // within this loss vs best play, treat as a fine alternative

// Convert a White-perspective score to the trainee's perspective.
function toTrainee<T extends number | null>(v: T, trainee: "white" | "black"): T {
  return (v === null ? null : trainee === "white" ? v : -v) as T;
}

export function analyzeMismatch(
  baseline: EngineEval,
  played: EngineEval,
  trainee: "white" | "black",
): MismatchVerdict {
  const baseMate = toTrainee(baseline.mate, trainee);
  const playedMate = toTrainee(played.mate, trainee);

  // Played position is a forced mate against the trainee.
  if (playedMate !== null && playedMate < 0) {
    return { kind: "mated", mateIn: Math.abs(playedMate) };
  }
  // Best play had a forced mate for the trainee that the played move gave up.
  // (If the played move itself still mates for the trainee, that's fine → playable.)
  if (baseMate !== null && baseMate > 0 && !(playedMate !== null && playedMate > 0)) {
    return { kind: "missed-mate", mateIn: baseMate, bestMoveUci: baseline.bestMove };
  }
  // Played move also mates for the trainee, or any non-cp edge → playable.
  if (playedMate !== null && playedMate > 0) {
    return { kind: "playable", bestMoveUci: baseline.bestMove };
  }
  // Baseline was already a forced mate against the trainee: the position was
  // lost before this move, so the played move loses nothing relative to it.
  if (baseMate !== null && baseMate < 0) {
    return { kind: "playable", bestMoveUci: baseline.bestMove };
  }
  // cp path: loss vs best play, trainee perspective.
  const baseCp = toTrainee(baseline.cp, trainee) ?? 0;
  const playedCp = toTrainee(played.cp, trainee) ?? 0;
  const lossCp = baseCp - playedCp;
  if (lossCp <= PLAYABLE_CP) return { kind: "playable", bestMoveUci: baseline.bestMove };
  return { kind: "loses", lossCp, bestMoveUci: baseline.bestMove };
}

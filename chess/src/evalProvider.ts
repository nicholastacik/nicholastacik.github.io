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
    // eval (pawns) is always numeric and White-perspective; centipawns may be a
    // string, so derive cp from eval when not mate.
    const cp = mate === null ? Math.round(Number(data["eval"]) * 100) : null;
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

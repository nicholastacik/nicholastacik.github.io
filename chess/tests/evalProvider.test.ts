import { describe, it, expect, vi } from "vitest";
import { ChessApiProvider, CachingEvalProvider, type EvalProvider, type EngineEval } from "../src/evalProvider";

// Recorded chess-api.com response (POST /v1), Black-to-move position — proves
// White-perspective: raw stockfish "score cp -32" comes back as eval +0.32.
const CP_RESPONSE = {
  type: "bestmove", move: "f8c5", san: "Bc5", eval: 0.32, centipawns: 32,
  mate: null, depth: 12,
};
const CP_RESPONSE_STRING_CENTIPAWNS = { ...CP_RESPONSE, centipawns: "32" };
const MATE_RESPONSE = {
  type: "bestmove", move: "d1h5", san: "Qh5#", eval: 99, centipawns: null,
  mate: 1, depth: 12,
};

function fakeFetch(json: unknown, ok = true) {
  return vi.fn(async () => ({ ok, json: async () => json }) as Response);
}

describe("ChessApiProvider", () => {
  it("maps a cp response to a White-perspective EngineEval", async () => {
    const fetchFn = fakeFetch(CP_RESPONSE);
    const p = new ChessApiProvider({ fetchFn, depth: 12 });
    const e = await p.evaluate("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3");
    expect(e).toEqual<EngineEval>({ bestMove: "f8c5", cp: 32, mate: null, depth: 12 });
  });

  it("coerces a string centipawns field to a number", async () => {
    const p = new ChessApiProvider({ fetchFn: fakeFetch(CP_RESPONSE_STRING_CENTIPAWNS) });
    const e = await p.evaluate("8/8/8/8/8/8/8/8 w - - 0 1");
    expect(e.cp).toBe(32);
  });

  it("maps a mate response (cp null, mate set)", async () => {
    const p = new ChessApiProvider({ fetchFn: fakeFetch(MATE_RESPONSE) });
    const e = await p.evaluate("8/8/8/8/8/8/8/8 w - - 0 1");
    expect(e.cp).toBeNull();
    expect(e.mate).toBe(1);
    expect(e.bestMove).toBe("d1h5");
  });

  it("POSTs { fen, depth } as JSON to the endpoint", async () => {
    const fetchFn = fakeFetch(CP_RESPONSE);
    await new ChessApiProvider({ fetchFn, depth: 14 }).evaluate("FEN");
    expect(fetchFn).toHaveBeenCalledOnce();
    const [url, init] = fetchFn.mock.calls[0]!;
    expect(url).toBe("https://chess-api.com/v1");
    expect(init!.method).toBe("POST");
    expect(JSON.parse(init!.body as string)).toEqual({ fen: "FEN", depth: 14 });
  });

  it("throws on a non-ok response or malformed body", async () => {
    await expect(new ChessApiProvider({ fetchFn: fakeFetch({}, false) }).evaluate("F")).rejects.toThrow();
    await expect(new ChessApiProvider({ fetchFn: fakeFetch({ nope: 1 }) }).evaluate("F")).rejects.toThrow();
  });
});

describe("CachingEvalProvider", () => {
  it("calls the inner provider once per distinct fen and caches the result", async () => {
    const inner: EvalProvider = { evaluate: vi.fn(async () => ({ bestMove: "e2e4", cp: 20, mate: null, depth: 12 })) };
    const store = new Map<string, string>();
    const fakeStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    } as unknown as Storage;
    const p = new CachingEvalProvider(inner, fakeStorage);
    const a = await p.evaluate("FEN1");
    const b = await p.evaluate("FEN1");
    expect(a).toEqual(b);
    expect(inner.evaluate).toHaveBeenCalledOnce();
  });
});

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

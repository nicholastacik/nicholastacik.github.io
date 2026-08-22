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

// Map an OpenAI SDK error to our typed LLMError. Shared by every network call.
export function toLLMError(e: any): LLMError {
  const status = e?.status ?? e?.response?.status;
  const msg: string = e?.message ?? "";
  if (status === 401) return new LLMError("Invalid API key.", "auth");
  if (status === 429) return new LLMError("Rate limited — wait and retry.", "rate_limit");
  // Model doesn't support Structured Outputs (json_schema) — the picker filters
  // most of these out, but a Custom pick (or a preview model) can still hit it.
  if (status === 400 && /response_format|json_schema|structured output/i.test(msg))
    return new LLMError(
      "This model can’t return the structured responses this game needs. Pick a different model (a gpt-4o / gpt-4.1 / gpt-5 / o-series model).",
      "other",
    );
  if (e?.name === "APIConnectionError" || e instanceof TypeError)
    return new LLMError("Network error reaching OpenAI.", "network");
  // parse() throws LengthFinishReasonError when the model was cut off before it
  // finished the JSON (common on reasoning models if the token budget is tight).
  if (e?.name === "LengthFinishReasonError" || /length limit was reached/i.test(msg))
    return new LLMError("The model ran out of output room before finishing. Try again, or pick a lighter model.", "other");
  return new LLMError(msg || "Unknown OpenAI error.", "other");
}

// Keep only models suitable for this game from a raw /v1/models listing. The
// endpoint returns embeddings, audio, image, moderation, etc. with no
// capability flags, so we filter by id convention. INCLUDE is restricted to
// families known to support Structured Outputs (json_schema) — which this game
// requires — so non-SO models (gpt-3.5, gpt-4-turbo, legacy gpt-4, search
// previews) stay out of the picker instead of 400-ing on use. Still best-effort
// (e.g. o1-mini / some previews may not support SO); a stray pick surfaces a
// clear error (see toLLMError) and "Custom…" remains the escape hatch. Deduped
// and sorted. Pure (unit-tested).
export function filterChatModels(ids: string[]): string[] {
  const EXCLUDE = /embedding|whisper|tts|audio|realtime|transcribe|image|dall-e|moderation|deep-research|search|instruct|davinci|babbage/i;
  const INCLUDE = /^(gpt-4o|gpt-4\.1|gpt-5|o[1-9]|chatgpt-4o)/i;
  const kept = new Set<string>();
  for (const id of ids) {
    if (INCLUDE.test(id) && !EXCLUDE.test(id)) kept.add(id);
  }
  return [...kept].sort();
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
        max_completion_tokens: MAX_OUTPUT_TOKENS,
      });
      const choice = completion.choices[0]!;
      return {
        parsed: (choice.message.parsed as T) ?? null,
        refusal: choice.message.refusal ?? null,
        finishReason: choice.finish_reason,
      };
    } catch (e: any) {
      throw toLLMError(e);
    }
  }
}

// Fetch the chat models this key can access, for the model picker. Throws
// LLMError (e.g. auth on a bad key) so the caller can surface it.
export async function listChatModels(apiKey: string): Promise<string[]> {
  const client = new OpenAI({ apiKey, dangerouslyAllowBrowser: true });
  try {
    const page = await client.models.list();
    return filterChatModels(page.data.map((m) => m.id));
  } catch (e: any) {
    throw toLLMError(e);
  }
}

// Generous output budget. Reasoning models (gpt-5.x, o-series) spend hidden
// reasoning tokens that ALSO count against this cap, so a small value (e.g.
// 1200) truncates before the JSON is produced — the SDK's parse() then throws
// LengthFinishReasonError. Our actual JSON output is tiny (~a few hundred
// tokens); this ceiling only needs to leave room for reasoning.
const MAX_OUTPUT_TOKENS = 8192;

const MAX_REPAIRS = 2;

export async function getAIClue(caller: LLMCaller, state: GameState, log: Logger): Promise<ClueResponse | null> {
  const messages = buildClueMessages(state);
  for (let attempt = 0; attempt <= MAX_REPAIRS; attempt++) {
    const res = await caller.call(messages, ClueSchema, "clue");
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
  const res = await caller.call(messages, GuessSchema, "guess");
  if (res.refusal) { log(`AI refused to guess: ${res.refusal}. Passing.`); return []; }
  if (!res.parsed) { log("AI returned no guesses. Passing."); return []; }

  const legal = filterGuesses(res.parsed.guesses, state);
  if (legal.length < res.parsed.guesses.length) log("Dropped guesses that were not on the board.");
  log(`AI will guess: ${legal.join(", ") || "(nothing)"}.`);
  return legal;
}

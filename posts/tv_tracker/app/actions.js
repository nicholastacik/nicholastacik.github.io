import { AuthError, tabRange } from "./sheets.js";
import { planCardStatus, planTrack, planUntrack, rowsFromValues } from "./state.js";

export class StaleError extends Error {}

function checkKey(columnA, card) {
  if (String(columnA[card._row - 1]?.[0] ?? "") !== card.card_id) {
    throw new StaleError("The Sheet changed since it loaded");
  }
}

export async function markCard(ctx, card, status) {
  const [cardKeys] = await ctx.sheets.get(["Cards!A:A"]);
  checkKey(cardKeys, card);
  await ctx.sheets.batchUpdate(planCardStatus(card, status, ctx.nowIso(), await ctx.sheets.sheetIds()));
}

export async function trackShow(ctx, show, source, card = null) {
  const [trackedValues, cardKeys] = await ctx.sheets.get([tabRange("Tracked"), "Cards!A:A"]);
  if (card) checkKey(cardKeys, card);
  const requests = planTrack({
    tracked: rowsFromValues("Tracked", trackedValues),
    show,
    source,
    card,
    today: ctx.today(),
    nowIso: ctx.nowIso(),
    sheetIds: await ctx.sheets.sheetIds(),
  });
  await ctx.sheets.batchUpdate(requests);
}

export async function untrackShow(ctx, tmdbId) {
  const [trackedValues] = await ctx.sheets.get([tabRange("Tracked")]);
  const requests = planUntrack({
    tracked: rowsFromValues("Tracked", trackedValues),
    tmdbId,
    nowIso: ctx.nowIso(),
    sheetIds: await ctx.sheets.sheetIds(),
  });
  if (requests.length) await ctx.sheets.batchUpdate(requests);
}

export async function perform(ctx, action) {
  try {
    await action();
    return "done";
  } catch (error) {
    if (error instanceof AuthError) {
      ctx.pending.push(action);
      if (ctx.pending.length === 1) ctx.onAuthNeeded();
      return "pending";
    }
    throw error;
  }
}

export async function resumePending(ctx) {
  const queued = ctx.pending.splice(0);
  let outcome = null;
  let failure = null;
  for (const [i, action] of queued.entries()) {
    try {
      outcome = await perform(ctx, action);
    } catch (error) {
      failure ??= error;
      continue;
    }
    if (outcome === "pending") {
      ctx.pending.push(...queued.slice(i + 1));
      break;
    }
  }
  if (failure) throw failure;
  return outcome;
}

function chain(ctx, run) {
  const result = (ctx.queue ?? Promise.resolve()).then(run);
  ctx.queue = result.catch(() => {});
  return result;
}

export function enqueue(ctx, action) {
  return chain(ctx, () => {
    if (ctx.pending.length) {
      ctx.pending.push(action);
      return "pending";
    }
    return perform(ctx, action);
  });
}

export function resume(ctx) {
  return chain(ctx, () => resumePending(ctx));
}

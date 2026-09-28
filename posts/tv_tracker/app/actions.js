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
      ctx.pending = action;
      ctx.onAuthNeeded();
      return "pending";
    }
    throw error;
  }
}

export async function resumePending(ctx) {
  const action = ctx.pending;
  ctx.pending = null;
  return action ? perform(ctx, action) : null;
}

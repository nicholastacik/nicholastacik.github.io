export interface GameResult {
  won: boolean; agentsFound: number; hitAssassin: boolean; reachedSuddenDeath: boolean;
  clues: number; illegalClues: number; turnsUsed: number;
}
export function aggregate(results: GameResult[]) {
  const games = results.length;
  const sum = (f: (r: GameResult) => number) => results.reduce((a, r) => a + f(r), 0);
  const delivered = sum((r) => r.clues);
  const illegal = sum((r) => r.illegalClues);
  const attempts = delivered + illegal; // every clue attempt: accepted + rejected
  return {
    games,
    winRate: sum((r) => (r.won ? 1 : 0)) / games,
    avgAgents: sum((r) => r.agentsFound) / games,
    assassinRate: sum((r) => (r.hitAssassin ? 1 : 0)) / games,
    suddenDeathRate: sum((r) => (r.reachedSuddenDeath ? 1 : 0)) / games,
    avgTurnsUsed: sum((r) => r.turnsUsed) / games,
    // Fraction of clue ATTEMPTS the model got illegal (bounded 0..1), not
    // rejections-over-delivered (which could exceed 100%).
    illegalClueRate: attempts ? illegal / attempts : 0,
  };
}

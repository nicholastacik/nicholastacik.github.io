export interface GameResult {
  won: boolean; agentsFound: number; hitAssassin: boolean;
  clues: number; illegalClues: number; repairs: number;
}
export function aggregate(results: GameResult[]) {
  const games = results.length;
  const sum = (f: (r: GameResult) => number) => results.reduce((a, r) => a + f(r), 0);
  const clues = sum((r) => r.clues) || 1;
  return {
    games,
    winRate: sum((r) => (r.won ? 1 : 0)) / games,
    avgAgents: sum((r) => r.agentsFound) / games,
    assassinRate: sum((r) => (r.hitAssassin ? 1 : 0)) / games,
    illegalClueRate: sum((r) => r.illegalClues) / clues,
    avgRepairsPerClue: sum((r) => r.repairs) / clues,
  };
}

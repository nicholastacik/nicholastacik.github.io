// Pure, DOM-free helper for the research page's Practice mode: pick a random,
// distinct N-clue deck from a pool. No imports, no Math.random() inside — rng is
// passed in. The single trailing `export { ... }` is stripped when inlined into the page.

function _shuffle(arr, rng) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
  return arr;
}

// pool is assumed distinct (the caller dedupes); returns up to `size` ids, shuffled.
function pickSession(pool, size, rng) {
  return _shuffle(pool.slice(), rng).slice(0, size);
}

// Cards are text-only, so a clue that points at an image/audio/video the reader can't
// see is unanswerable. Exclude the high-confidence J-Archive media tells: a "seen/shown/
// pictured/heard/depicted here|above|below" reference, or a bare "(pictured)".
function isMediaClue(text) {
  const t = text || "";
  return /\b(seen|shown|pictured|heard|depicted) (here|above|below)\b/i.test(t)
    || /\bpictured\b/i.test(t);
}

export { pickSession, isMediaClue };

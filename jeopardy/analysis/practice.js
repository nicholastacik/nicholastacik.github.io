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

export { pickSession };

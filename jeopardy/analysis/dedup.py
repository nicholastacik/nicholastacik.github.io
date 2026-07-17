"""Collapse variant entity phrases within a cluster (plurals, partial/full)."""


def _contiguous(short, long_):
    n, m = len(short), len(long_)
    if n == 0 or n >= m:
        return False
    return any(long_[i:i + n] == short for i in range(m - n + 1))


def _plural(a, b):  # a, b already lowercased
    return b in (a + "s", a + "es") or a in (b + "s", b + "es")


def canonicalize(counts):
    """Return (merged_counts, merges) for one cluster's phrase->count mapping."""
    phrases = list(counts)
    toks = {p: [t.lower() for t in p.split()] for p in phrases}
    low = {p: p.lower() for p in phrases}
    parent = {p: p for p in phrases}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        parent[find(a)] = find(b)

    # Rule 1: unambiguous component merge (shorter is a contiguous token subseq of exactly one longer)
    for a in phrases:
        containers = [b for b in phrases
                      if b != a and len(toks[b]) > len(toks[a]) and _contiguous(toks[a], toks[b])]
        if len(containers) == 1:
            union(a, containers[0])
    # Rule 2: plurals
    for i, a in enumerate(phrases):
        for b in phrases[i + 1:]:
            if _plural(low[a], low[b]):
                union(a, b)

    groups = {}
    for p in phrases:
        groups.setdefault(find(p), []).append(p)
    result, merges = {}, []
    for members in groups.values():
        canon = max(members, key=lambda p: (len(toks[p]), counts[p], p))
        result[canon] = sum(counts[m] for m in members)
        merges.extend((m, canon) for m in members if m != canon)
    return result, merges

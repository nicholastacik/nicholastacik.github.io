"""Collapse variant entity phrases within a cluster (plurals, partial/full, misspellings)."""


def edit_distance_le_1(a, b):
    """True if the Damerau-Levenshtein distance between a and b is <= 1.

    Allows a single substitution, insertion, deletion, or transposition of
    two adjacent characters (e.g. "niels" / "neils").
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:  # one substitution, or one adjacent transposition
        mismatches = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(mismatches) == 1:
            return True
        if len(mismatches) == 2:
            i, j = mismatches
            return j == i + 1 and a[i] == b[j] and a[j] == b[i]
        return False
    if la > lb:   # make a the shorter
        a, b, la, lb = b, a, lb, la
    i = j = diff = 0  # one insertion/deletion
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            diff += 1
            j += 1
            if diff > 1:
                return False
    return True


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
    # Rule 2 (plurals) + Rule 3 (single-token fuzzy, min length 5)
    for i, a in enumerate(phrases):
        for b in phrases[i + 1:]:
            if _plural(low[a], low[b]) or (
                len(toks[a]) == 1 and len(toks[b]) == 1
                and len(low[a]) >= 5 and len(low[b]) >= 5
                and edit_distance_le_1(low[a], low[b])
            ):
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

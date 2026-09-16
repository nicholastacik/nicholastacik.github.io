"""Sample clues per (type, entity) for the research tool's self-test feature."""
from jeopardy.analysis.dedup import canonicalize
from jeopardy.analysis.tokens import DEDUP_CANDIDATE_K, apply_entity_decisions


def _spread(items, n):
    """Up to n items, evenly spaced across the (year-sorted) list — for era coverage."""
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def _sample(items, n):
    """Up to n year-spread items, always including the most recent so recent-era
    filters (year >= cutoff) still have a clue. `items` is sorted oldest -> newest."""
    if len(items) <= n:
        return items
    return _spread(items[:-1], n - 1) + [items[-1]]


def _cluster_resolution(raw_counts, cluster_decisions, min_freq):
    """surface_phrase -> displayed entity (or None if dropped/below floor)."""
    topk = dict(sorted(raw_counts.items(), key=lambda kv: -kv[1])[:DEDUP_CANDIDATE_K])
    merged_counts, merges = canonicalize(topk)
    surface_to_canon = {p: p for p in topk}
    for lo, hi in merges:
        surface_to_canon[lo] = hi
    final_counts = apply_entity_decisions(merged_counts, cluster_decisions)
    canon_to_final = {}
    for canon in merged_counts:
        decision = cluster_decisions.get(canon)
        if decision is None:
            canon_to_final[canon] = canon
        elif not decision[0]:
            canon_to_final[canon] = None
        else:
            canon_to_final[canon] = decision[1] if (decision[1] and decision[1].strip()) else canon
    resolution = {}
    for surface, canon in surface_to_canon.items():
        final = canon_to_final.get(canon)
        if final is not None and final_counts.get(final, 0) >= min_freq:
            resolution[surface] = final
    return resolution

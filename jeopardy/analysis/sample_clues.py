"""Sample clues per (type, entity) for the research tool's self-test feature."""
import pandas as pd

from jeopardy import config
from jeopardy.analysis.dedup import canonicalize
from jeopardy.analysis.misc_pool import misc_membership
from jeopardy.analysis.tokens import (
    DEDUP_CANDIDATE_K,
    apply_entity_decisions,
    build_surface_counts,
    extract_phrases,
    load_entity_decisions,
    _cluster_phrase_counts,
)


def _spread(items, n):
    """Up to n items, evenly spaced across the (year-sorted) list — for era coverage."""
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


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


def build_sample_clues(clusters_df, clues_df, decisions, k=3, general_n=25, min_freq=5):
    keys = ["game_id", "round", "category"]
    merged = clues_df.merge(clusters_df[keys + ["cluster_id"]], on=keys, how="inner")
    merged["year"] = pd.to_datetime(merged["air_date"]).dt.year
    merged = merged[merged["year"].notna()]
    base_rows = merged[merged["cluster_id"] != config.MISC_ID]
    surface = build_surface_counts(
        list(base_rows["clue"].fillna("")) + list(base_rows["answer"].fillna(""))
    )
    out_rows = []
    for cid, sub in merged.groupby("cluster_id"):
        raw = _cluster_phrase_counts(sub, surface)
        resolution = _cluster_resolution(raw, decisions.get(int(cid), {}), min_freq)
        by_entity = {}
        general = []
        for row in sub.sort_values("year").itertuples():
            answer = row.answer if isinstance(row.answer, str) else ""
            entity = None
            for phrase in extract_phrases(answer):
                if phrase in resolution:
                    entity = resolution[phrase]
                    break
            rec = {"clue": row.clue, "answer": answer, "year": int(row.year), "category": row.category}
            if entity is not None:
                by_entity.setdefault(entity, []).append(rec)
            general.append(rec)
        seen = set()
        for entity, recs in by_entity.items():
            for rec in _spread(recs, k):
                seen.add((rec["clue"], rec["answer"]))
                out_rows.append({"cluster_id": int(cid), "phrase": entity, **rec})
        pool = [r for r in general if (r["clue"], r["answer"]) not in seen]
        for rec in _spread(pool, general_n):
            out_rows.append({"cluster_id": int(cid), "phrase": None, **rec})
    return pd.DataFrame(out_rows, columns=["cluster_id", "phrase", "clue", "answer", "year", "category"])


def run_sample_clues(min_freq=5):
    clusters = pd.read_parquet(config.CATEGORY_CLUSTERS_PATH)
    clues = pd.read_parquet(config.PARQUET_PATH)
    misc = misc_membership(clusters, config.MISC_FRACTION, config.MISC_ID)
    clusters = pd.concat([clusters, misc], ignore_index=True)
    decisions = load_entity_decisions(config.ENTITY_DECISIONS_PATH)
    df = build_sample_clues(clusters, clues, decisions, min_freq=min_freq)
    config.CATEGORY_SAMPLE_CLUES_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.CATEGORY_SAMPLE_CLUES_PATH, index=False)
    print(f"Wrote {len(df):,} sample clues across {df['cluster_id'].nunique()} types "
          f"-> {config.CATEGORY_SAMPLE_CLUES_PATH}")

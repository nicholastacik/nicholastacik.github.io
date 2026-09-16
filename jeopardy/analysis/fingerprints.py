"""Clue fingerprints: a shared clue store, quiz refs, and per-entity TF-IDF cues."""
import pandas as pd

from jeopardy import config
from jeopardy.analysis.sample_clues import _cluster_resolution, _sample
from jeopardy.analysis.tokens import (
    build_surface_counts,
    extract_phrases,
    _cluster_phrase_counts,
)

_STORE_COLS = ["clue_id", "clue", "answer", "year", "category", "game_id", "round", "row", "column"]


def clue_ids(clues_df):
    r = clues_df["row"].fillna(0).astype(int).astype(str)
    c = clues_df["column"].fillna(0).astype(int).astype(str)
    return (clues_df["game_id"].astype(int).astype(str) + ":" + clues_df["round"].astype(str)
            + ":" + r + ":" + c)


def build_clue_index(clusters_df, clues_df, decisions, quiz_k=2, quiz_general_n=12, min_freq=5):
    clues_df = clues_df.copy()
    clues_df["year"] = pd.to_datetime(clues_df["air_date"]).dt.year
    clues_df = clues_df[clues_df["year"].notna()]
    clues_df["year"] = clues_df["year"].astype(int)
    clues_df["clue_id"] = clue_ids(clues_df)
    store = clues_df.drop_duplicates("clue_id")[_STORE_COLS].reset_index(drop=True)

    keys = ["game_id", "round", "category"]
    merged = clues_df.merge(clusters_df[keys + ["cluster_id"]], on=keys, how="inner")
    base_rows = merged[merged["cluster_id"] != config.MISC_ID]
    surface = build_surface_counts(
        list(base_rows["clue"].fillna("")) + list(base_rows["answer"].fillna(""))
    )
    entity_clues, quiz_refs = {}, {}
    for cid, sub in merged.groupby("cluster_id"):
        cdec = decisions.get(int(cid), {})
        resolution = {}
        for cutoff in config.ERA_CUTOFFS:
            era_sub = sub[sub["year"] >= cutoff]
            if era_sub.empty:
                continue
            resolution.update(_cluster_resolution(_cluster_phrase_counts(era_sub, surface), cdec, min_freq))
        by_entity, general = {}, []
        for row in sub.sort_values("year").itertuples():
            answer = row.answer if isinstance(row.answer, str) else ""
            entity = None
            for phrase in extract_phrases(answer):
                if phrase in resolution:
                    entity = resolution[phrase]
                    break
            rec = {"clue_id": row.clue_id, "year": int(row.year), "clue": row.clue}
            if entity is not None:
                by_entity.setdefault(entity, []).append(rec)
            general.append(rec)
        refs, seen = {}, set()
        for entity, recs in by_entity.items():
            entity_clues[(int(cid), entity)] = recs
            picks = _sample(recs, quiz_k)
            refs[entity] = [r["clue_id"] for r in picks]
            seen.update(refs[entity])
        pool = [r for r in general if r["clue_id"] not in seen]
        refs[None] = [r["clue_id"] for r in _sample(pool, quiz_general_n)]
        quiz_refs[int(cid)] = refs
    return store, entity_clues, quiz_refs

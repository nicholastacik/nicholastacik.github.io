"""Clue fingerprints: a shared clue store, quiz refs, and per-entity TF-IDF cues."""
import re

import numpy as np
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


_CUE_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_FILLER = {"clue", "crew", "this", "these", "one"}


def _contains(term, text):
    toks = _CUE_TOKEN.findall((text or "").lower())
    parts = term.split()
    if len(parts) == 1:
        return parts[0] in toks
    joined = " ".join(toks)
    return term in joined


def _dedup_ngrams(cues):
    bigram_words = set()
    for c in cues:
        if " " in c["term"]:
            bigram_words.update(c["term"].split())
    out = []
    for c in cues:
        if " " not in c["term"] and c["term"] in bigram_words:
            continue  # unigram fully covered by a kept bigram
        out.append(c)
    return out


def build_cues(entity_clues, n_cues=6, n_examples=4):
    from sklearn.feature_extraction.text import TfidfVectorizer
    keys = list(entity_clues)
    docs = [" ".join(r["clue"] or "" for r in entity_clues[k]) for k in keys]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=20000,
                          token_pattern=r"[A-Za-z][A-Za-z'\-]+")
    matrix = vec.fit_transform(docs)
    terms = np.array(vec.get_feature_names_out())
    out = {}
    for i, k in enumerate(keys):
        cid, phrase = k
        recs = entity_clues[k]
        total = len(recs)
        name_toks = {t.lower() for t in phrase.split()}
        row = matrix.getrow(i).toarray().ravel()
        cues = []
        for j in row.argsort()[::-1]:
            if row[j] <= 0 or len(cues) >= n_cues * 3:
                break
            term = terms[j]
            tparts = term.split()
            if any(t in name_toks for t in tparts) or any(t in _FILLER for t in tparts):
                continue
            support = sum(1 for r in recs if _contains(term, r["clue"]))
            if support < 2:
                continue
            cues.append({"term": term, "support": int(support), "total": int(total)})
        cues = _dedup_ngrams(cues)[:n_cues]
        cue_terms = [c["term"] for c in cues]
        newest = max(recs, key=lambda r: r["year"])
        by_cov = sorted(recs, key=lambda r: -sum(1 for t in cue_terms if _contains(t, r["clue"])))
        picks, seen = [newest["clue_id"]], {newest["clue_id"]}
        for r in by_cov:
            if len(picks) >= n_examples:
                break
            if r["clue_id"] not in seen:
                picks.append(r["clue_id"]); seen.add(r["clue_id"])
        out[k] = {"cues": cues, "example_clue_ids": picks}
    return out

"""Clue fingerprints: a shared clue store, quiz refs, and per-entity TF-IDF cues."""
import re

import numpy as np
import pandas as pd

from jeopardy import config
from jeopardy.analysis.misc_pool import misc_membership
from jeopardy.analysis.sample_clues import _cluster_resolution, _sample
from jeopardy.analysis.tokens import (
    build_surface_counts,
    extract_phrases,
    load_entity_decisions,
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
    n = len(parts)
    return any(toks[i:i + n] == parts for i in range(len(toks) - n + 1))


def _select_cues(candidates, n_cues):
    kept, bigram_words = [], set()
    for c in candidates:
        term = c["term"]
        if " " not in term and term in bigram_words:
            continue  # unigram covered by an already-kept bigram
        kept.append(c)
        if " " in term:
            bigram_words.update(term.split())
        if len(kept) >= n_cues:
            break
    return kept


def _entity_terms(recs):
    out = set()
    for r in recs:
        toks = _CUE_TOKEN.findall((r["clue"] or "").lower())
        out.update(toks)
        out.update(toks[i] + " " + toks[i + 1] for i in range(len(toks) - 1))
    return out


def build_cues(entity_clues, n_cues=6, n_examples=4, generic_df_frac=0.2, generic_min_entities=10):
    from sklearn.feature_extraction.text import TfidfVectorizer
    keys = list(entity_clues)
    docs = [" ".join(r["clue"] or "" for r in entity_clues[k]) for k in keys]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=20000,
                          token_pattern=r"[A-Za-z][A-Za-z'\-]+")
    matrix = vec.fit_transform(docs)
    terms = np.array(vec.get_feature_names_out())
    # Per-cluster document frequency: a term in many of a cluster's entities' clue-pools is
    # type-generic (e.g. "author"/"novel" for Books & Authors), not entity-distinctive - drop it.
    entity_terms = {k: _entity_terms(entity_clues[k]) for k in keys}
    cluster_df, cluster_n = {}, {}
    for (cid, _phrase), tset in entity_terms.items():
        cluster_n[cid] = cluster_n.get(cid, 0) + 1
        df = cluster_df.setdefault(cid, {})
        for t in tset:
            df[t] = df.get(t, 0) + 1
    out = {}
    for i, k in enumerate(keys):
        cid, phrase = k
        recs = entity_clues[k]
        total = len(recs)
        name_toks = {t.lower() for t in phrase.split()}
        df, n = cluster_df[cid], cluster_n[cid]
        row = matrix.getrow(i).toarray().ravel()
        candidates = []
        for j in row.argsort()[::-1]:
            if row[j] <= 0 or len(candidates) >= n_cues * 3:
                break
            term = terms[j]
            tparts = term.split()
            if any(t in name_toks for t in tparts) or any(t in _FILLER for t in tparts):
                continue
            if n >= generic_min_entities and df.get(term, 0) / n > generic_df_frac:
                continue
            support = sum(1 for r in recs if _contains(term, r["clue"]))
            if support < 2:
                continue
            candidates.append({"term": term, "support": int(support), "total": int(total)})
        cues = _select_cues(candidates, n_cues)
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


def run_fingerprints(min_freq=5):
    clusters = pd.read_parquet(config.CATEGORY_CLUSTERS_PATH)
    clues = pd.read_parquet(config.PARQUET_PATH)
    misc = misc_membership(clusters, config.MISC_FRACTION, config.MISC_ID)
    clusters = pd.concat([clusters, misc], ignore_index=True)
    decisions = load_entity_decisions(config.ENTITY_DECISIONS_PATH)
    store, entity_clues, quiz_refs = build_clue_index(
        clusters, clues, decisions, quiz_k=2, quiz_general_n=12, min_freq=min_freq)
    cues = build_cues(entity_clues, n_cues=6, n_examples=4)

    tokens = pd.read_parquet(config.CATEGORY_TOKENS_PATH)
    displayed = {(int(c), p) for c, p in zip(tokens["cluster_id"], tokens["phrase"])}
    cues = {k: v for k, v in cues.items() if k in displayed}
    quiz_refs = {cid: {ph: ids for ph, ids in refs.items()
                       if ph is None or (int(cid), ph) in displayed}
                 for cid, refs in quiz_refs.items()}

    quiz_rows = [{"cluster_id": cid, "phrase": ph, "clue_ids": ids}
                 for cid, refs in quiz_refs.items() for ph, ids in refs.items()]
    fp_rows = [{"cluster_id": cid, "phrase": ph, "cues": v["cues"],
                "example_clue_ids": v["example_clue_ids"]} for (cid, ph), v in cues.items()]

    referenced = set()
    for refs in quiz_refs.values():
        for ids in refs.values():
            referenced.update(ids)
    for v in cues.values():
        referenced.update(v["example_clue_ids"])
    store = store[store["clue_id"].isin(referenced)].reset_index(drop=True)

    config.CLUES_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    store.to_parquet(config.CLUES_STORE_PATH, index=False)
    pd.DataFrame(quiz_rows, columns=["cluster_id", "phrase", "clue_ids"]).to_parquet(
        config.CATEGORY_QUIZ_REFS_PATH, index=False)
    pd.DataFrame(fp_rows, columns=["cluster_id", "phrase", "cues", "example_clue_ids"]).to_parquet(
        config.CATEGORY_FINGERPRINTS_PATH, index=False)
    print(f"Wrote {len(store):,} clues, {len(quiz_rows):,} quiz refs, {len(fp_rows):,} fingerprints")

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
        # All-time first (the earliest cutoff spans the most clues); recent windows only fill in
        # surfaces the all-time mapping didn't resolve (e.g. an entity that only qualifies since
        # 2020). setdefault keeps the all-time interpretation from being overwritten by a window.
        resolution = {}
        for cutoff in config.ERA_CUTOFFS:
            era_sub = sub[sub["year"] >= cutoff]
            if era_sub.empty:
                continue
            for sp, ent in _cluster_resolution(_cluster_phrase_counts(era_sub, surface), cdec, min_freq).items():
                resolution.setdefault(sp, ent)
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
    # Candidates are in rank order. Keep the best terms with no unigram/bigram redundancy in
    # EITHER ranking order: a unigram after its bigram is skipped, and accepting a bigram evicts
    # any already-kept constituent unigram (freeing a slot to refill from lower-ranked terms).
    kept, bigram_words = [], set()
    for c in candidates:
        term = c["term"]
        parts = term.split()
        if len(parts) >= 2:
            kept = [k for k in kept if k["term"] not in parts]
            bigram_words.update(parts)
        elif term in bigram_words:
            continue
        kept.append(c)
        if len(kept) >= n_cues:
            break
    return kept


def _merge_overlapping(cues, recs):
    # The vectorizer only emits up to bigrams, so a 3-word name arrives as two overlapping
    # bigrams ("harriet beecher" + "beecher stowe"). Stitch a b + b c -> a b c when the trigram
    # actually recurs, keeping the first position and dropping the second.
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(cues):
            ap = a["term"].split()
            for j, b in enumerate(cues):
                if i == j:
                    continue
                bp = b["term"].split()
                if ap[-1] != bp[0]:
                    continue
                phrase = " ".join(ap + bp[1:])
                support = sum(1 for r in recs if _contains(phrase, r["clue"]))
                if support < 2:
                    continue
                cues[i] = {"term": phrase, "support": int(support), "total": a["total"]}
                cues.pop(j)
                merged = True
                break
            if merged:
                break
    return cues


def build_cues(entity_clues, n_cues=6, n_examples=4, generic_df_frac=0.2, generic_min_entities=10):
    from sklearn.feature_extraction.text import TfidfVectorizer
    keys = list(entity_clues)
    docs = [" ".join(r["clue"] or "" for r in entity_clues[k]) for k in keys]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=20000,
                          token_pattern=r"[A-Za-z][A-Za-z'\-]+")
    matrix = vec.fit_transform(docs)
    terms = np.array(vec.get_feature_names_out())
    # Per-cluster document frequency: a term present in many of a cluster's entities is
    # type-generic (e.g. "author"/"novel" for Books & Authors), not entity-distinctive - drop it.
    # Counted from the TF-IDF matrix itself so the term-space matches the vectorizer exactly
    # (including its stopword-skipping bigrams).
    presence = (matrix > 0)
    cluster_rows = {}
    for i, (cid, _phrase) in enumerate(keys):
        cluster_rows.setdefault(cid, []).append(i)
    cluster_dfvec, cluster_n = {}, {}
    for cid, rows in cluster_rows.items():
        cluster_n[cid] = len(rows)
        cluster_dfvec[cid] = np.asarray(presence[rows].sum(axis=0)).ravel()
    out = {}
    for i, k in enumerate(keys):
        cid, phrase = k
        recs = entity_clues[k]
        total = len(recs)
        name_toks = {t.lower() for t in phrase.split()}
        dfvec, n = cluster_dfvec[cid], cluster_n[cid]
        row = matrix.getrow(i).toarray().ravel()
        candidates = []
        for j in row.argsort()[::-1]:
            if row[j] <= 0 or len(candidates) >= n_cues * 3:
                break
            term = terms[j]
            tparts = term.split()
            if any(t in name_toks for t in tparts) or any(t in _FILLER for t in tparts):
                continue
            if n >= generic_min_entities and dfvec[j] / n > generic_df_frac:
                continue
            support = sum(1 for r in recs if _contains(term, r["clue"]))
            if support < 2:
                continue
            candidates.append({"term": term, "support": int(support), "total": int(total)})
        cues = _merge_overlapping(_select_cues(candidates, n_cues), recs)
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

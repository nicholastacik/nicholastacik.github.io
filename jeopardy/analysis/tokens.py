"""Most-common proper-noun phrases per cluster-type."""
import csv
import math
import re
from collections import Counter

import pandas as pd

from jeopardy import config
from jeopardy.analysis.dedup import canonicalize

DEDUP_CANDIDATE_K = 150  # dedup the top-K by count per (era, cluster) before selecting top_n

# Single-token capitalized words that are sentence-initial/pronominal, not entities.
_STOPWORDS = {
    "This", "These", "That", "Those", "The", "A", "An", "He", "She", "It",
    "In", "On", "At", "Of", "To", "For", "His", "Her", "Its", "Their", "They",
    "You", "We", "I", "When", "What", "Where", "Who", "Why", "How", "As", "By",
    "From", "With", "One", "Now", "Here", "There", "Like", "Also", "But", "And",
    "Or", "If", "Then", "Both", "Each", "Some", "Many", "Most", "All", "No",
}

# Common capitalized titles/descriptors that regularly precede a proper name
# (e.g. "President Abraham Lincoln"). These are dropped like stopwords so a
# title shared across many categories doesn't rank high in its own right -
# it's noise, not an entity - while the distinctive name after it survives.
_TITLES = {
    "President", "King", "Queen", "Prince", "Princess", "Sir", "Saint", "St",
    "Lord", "Lady", "General", "Admiral", "Captain", "Colonel", "Major",
    "Sergeant", "Doctor", "Dr", "Mr", "Mrs", "Ms", "Miss", "Professor",
    "Pope", "Emperor", "Empress", "Duke", "Duchess", "Earl", "Baron",
    "Governor", "Senator", "Judge", "Justice", "Sultan", "Czar", "Tsar",
}

_WORD = r"[A-Z][a-z]+"
# Roman numerals only (regnal/era names like "Richard III", "World War II",
# "Louis XIV"). Bare digits are deliberately excluded: allowing `\d+` here
# caused years to glue onto adjacent entities (e.g. "In 1483 Richard III").
# Accepted trade-off: digit-suffixed entities like "Apollo 11" won't be
# captured as a single phrase; that loss is rarer and less noisy than the
# year-gluing it would otherwise cause.
_NUM = r"[IVX]+"
_CONNECT = r"(?:of|the|de|la|von|van)"
# Head cap-word, then continuations: cap-words / numerals, optionally preceded by
# lowercase connector words ("of the"). Maximal munch keeps "Richard III" whole.
# "and" is intentionally not a connector so "World War II and World War I"
# stays two entities rather than gluing into one.
_PHRASE_RE = re.compile(
    rf"\b{_WORD}(?:\s+(?:{_CONNECT}\s+)*(?:{_WORD}|{_NUM}))*"
)


def _strip_leading_stopwords(phrase):
    tokens = phrase.split()
    # Drop leading stopwords and titles. With bare digits excluded from
    # continuations above, a phrase can never start with (or contain) a bare
    # number, so there's no need to additionally strip leading numeric tokens.
    while tokens and (tokens[0] in _STOPWORDS or tokens[0] in _TITLES):
        tokens.pop(0)
    return " ".join(tokens)


_SURFACE_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")


def build_surface_counts(texts):
    """Tally, across `texts`, how often each word (keyed lowercase) appears
    Capitalized vs lowercase on the surface.

    Used to tell real single-word entities that are homonyms of common
    English words (e.g. "China", "Turkey", "Taft") - which appear
    capitalized throughout the corpus - apart from generic common nouns that
    only look like entities because they happen to start a sentence (e.g.
    "Species", "Scientists"), which appear lowercase far more often than
    capitalized.
    """
    cap_count = Counter()
    lower_count = Counter()
    for text in texts:
        for tok in _SURFACE_WORD_RE.findall(text or ""):
            if tok.islower():
                lower_count[tok.lower()] += 1
            elif tok[0].isupper() and not tok.isupper():
                cap_count[tok.lower()] += 1
            # else: ALL-CAPS token (e.g. acronym) - ignored, counts toward neither.
    return cap_count, lower_count


def extract_phrases(text):
    """All proper-noun phrases in `text` (dups kept), leading stopwords/titles stripped.

    A leading title word (e.g. "President") is dropped entirely, like a
    stopword, rather than emitted as its own phrase - it's noise, not an
    entity, and the distinctive name that follows it survives.
    """
    out = []
    for m in _PHRASE_RE.finditer(text or ""):
        phrase = _strip_leading_stopwords(m.group(0).strip())
        if phrase:
            out.append(phrase)
    return out


def _is_generic_single_word(phrase, cap_count, lower_count):
    """True for a single-word phrase that appears lowercase more often than
    capitalized across the corpus (e.g. "Species", "Scientists") - i.e. it
    only looks like an entity because it happened to be sentence-initial.
    Real single-word entities that are homonyms of common words (e.g.
    "China", "Volga", "Taft") are capitalized throughout the corpus and so
    are kept. Multi-word phrases are never considered generic here.
    """
    if " " in phrase:
        return False
    key = phrase.lower()
    return lower_count[key] > cap_count[key]


_INTERJECTIONS = {"Oh", "Hi", "Ah", "Hey"}


def is_mechanical_noise(phrase):
    """Unambiguous non-entity noise: Clue Crew presenter metadata + bare interjections."""
    if "clue crew" in phrase.lower():
        return True
    return phrase in _INTERJECTIONS


def load_entity_decisions(path):
    """{cluster_id: {phrase: (keep, canonical)}} from the CSV; {} if the file is absent."""
    out = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            keep = row["keep"].strip().lower() in ("true", "1", "yes")
            out.setdefault(int(row["cluster_id"]), {})[row["phrase"]] = (keep, row["canonical"])
    return out


def apply_entity_decisions(counts, cluster_decisions):
    """Drop keep=False; remap canonical!=phrase (summing); default-keep absent phrases."""
    out = {}
    for phrase, n in counts.items():
        decision = cluster_decisions.get(phrase)
        if decision is None:
            out[phrase] = out.get(phrase, 0) + n
            continue
        keep, canonical = decision
        if not keep:
            continue
        target = canonical if (canonical and canonical.strip()) else phrase
        out[target] = out.get(target, 0) + n
    return out


def _cluster_phrase_counts(sub, surface):
    """sub: rows (clue/answer) for one (era, cluster). Returns
    Counter(phrase -> count) after the cap-dominance filter.
    """
    cap_count, lower_count = surface
    c = Counter()
    for clue, ans in zip(sub["clue"].fillna(""), sub["answer"].fillna("")):
        # Extract from clue/answer separately (not concatenated) so a
        # trailing entity in the clue can't glue onto a leading entity in
        # the answer (e.g. "...Civil War" + "Abraham Lincoln").
        c.update(extract_phrases(clue))
        c.update(extract_phrases(ans))
    return Counter({
        p: n for p, n in c.items()
        if not _is_generic_single_word(p, cap_count, lower_count) and not is_mechanical_noise(p)
    })


def era_tokens(clusters_df, clues_df, cutoffs, min_freq=5, top_n=25):
    """Per-era, per-cluster top phrases: long-format (era, cluster_id, rank,
    phrase, count, tfidf_weight) plus per-(era, cluster) prevalence.

    For each era (clues with air_date year >= cutoff), phrase counts are
    built per cluster with the existing cap-dominance filter. Two decoupled
    views are derived from those raw, full counts:

    - `n_qualifying_phrases` (applicability/studyability signal, stored in
      eras_df) is the count of DISTINCT phrases in the full raw counts with
      count >= min_freq - uncapped and computed BEFORE the top-
      DEDUP_CANDIDATE_K candidate cap and BEFORE dedup, so it isn't
      suppressed by types with many dedupable near-duplicate names.
    - The displayed top-N entities (token_rows) still go through the
      existing path: top DEDUP_CANDIDATE_K candidates by count -> dedup via
      `canonicalize` -> min_freq floor -> count-sort -> top_n.

    Within a cluster, displayed phrases are ranked by count desc,
    tiebreaking on tfidf weight then phrase text.

    Returns (tokens_df, eras_df, merges) where merges is a flat list of
    (era, cluster_id, lo_phrase, hi_phrase) tuples describing every dedup
    merge that occurred.
    """
    keys = ["game_id", "round", "category"]
    merged = clues_df.merge(clusters_df[keys + ["cluster_id"]], on=keys, how="inner")
    merged["year"] = pd.to_datetime(merged["air_date"]).dt.year
    token_rows, era_rows, all_merges = [], [], []
    decisions = load_entity_decisions(config.ENTITY_DECISIONS_PATH)

    for cutoff in cutoffs:
        era = merged[merged["year"] >= cutoff]
        surface = build_surface_counts(
            list(era["clue"].fillna("")) + list(era["answer"].fillna(""))
        )
        total_instances = era.groupby(keys).ngroups or 1
        # per-cluster: full raw counts (for applicability) and the
        # capped+deduped+min_freq-filtered counts (for display)
        per_cluster_raw = {}
        per_cluster_counts = {}
        for cid, sub in era.groupby("cluster_id"):
            raw = _cluster_phrase_counts(sub, surface)
            per_cluster_raw[cid] = raw
            # dedup the top-K candidates by count, then keep >= min_freq
            topk = dict(sorted(raw.items(), key=lambda kv: -kv[1])[:DEDUP_CANDIDATE_K])
            merged_counts, merges = canonicalize(topk)
            all_merges.extend((cutoff, cid, lo, hi) for lo, hi in merges)
            merged_counts = apply_entity_decisions(merged_counts, decisions.get(int(cid), {}))
            per_cluster_counts[cid] = {p: n for p, n in merged_counts.items() if n >= min_freq}
        # c-TF-IDF idf within this era's cluster set
        doc_freq = Counter()
        for counts in per_cluster_counts.values():
            doc_freq.update(counts.keys())
        n_clusters = len(per_cluster_counts)
        # instances (distinct game/round/category) per cluster, for prevalence
        sizes = era.groupby("cluster_id").apply(
            lambda g: g.groupby(keys).ngroups, include_groups=False
        )
        for cid, counts in per_cluster_counts.items():
            n_qual = sum(1 for n in per_cluster_raw[cid].values() if n >= min_freq)
            era_rows.append({"era": cutoff, "cluster_id": int(cid),
                             "size": int(sizes.get(cid, 0)),
                             "share": float(sizes.get(cid, 0)) / total_instances,
                             "n_qualifying_phrases": n_qual})
            scored = []
            for phrase, n in counts.items():
                idf = math.log(n_clusters / doc_freq[phrase]) if doc_freq[phrase] else 0.0
                scored.append((phrase, n, n * idf))
            scored.sort(key=lambda x: (-x[1], -x[2], x[0]))  # count desc, then tfidf, then phrase
            for rank, (phrase, n, w) in enumerate(scored[:top_n], start=1):
                token_rows.append({"era": cutoff, "cluster_id": int(cid), "rank": rank,
                                   "phrase": phrase, "count": int(n), "tfidf_weight": float(w)})

    tokens_df = pd.DataFrame(token_rows, columns=["era", "cluster_id", "rank", "phrase", "count", "tfidf_weight"])
    eras_df = pd.DataFrame(era_rows, columns=["era", "cluster_id", "size", "share", "n_qualifying_phrases"])
    return tokens_df, eras_df, all_merges


def _write_merge_report(merges, path):
    lines = ["---", "draft: true", "---", "", "# Entity dedup merges", ""]
    by_key = {}
    for era, cid, lo, hi in merges:
        by_key.setdefault((era, cid), []).append((lo, hi))
    for (era, cid), pairs in sorted(by_key.items()):
        lines.append(f"## era {era}, cluster {cid}")
        for lo, hi in pairs:
            lines.append(f"- `{lo}` -> `{hi}`")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_tokens(min_freq=5, top_n=25):
    clusters = pd.read_parquet(config.CATEGORY_CLUSTERS_PATH)
    clues = pd.read_parquet(config.PARQUET_PATH)
    tokens_df, eras_df, merges = era_tokens(clusters, clues, config.ERA_CUTOFFS, min_freq, top_n)
    config.CATEGORY_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tokens_df.to_parquet(config.CATEGORY_TOKENS_PATH, index=False)
    eras_df.to_parquet(config.CATEGORY_ERAS_PATH, index=False)
    _write_merge_report(merges, config.DEDUP_MERGES_PATH)
    print(f"Wrote {len(tokens_df):,} token rows across {len(config.ERA_CUTOFFS)} eras; "
          f"{len(merges):,} merges -> {config.DEDUP_MERGES_PATH}")

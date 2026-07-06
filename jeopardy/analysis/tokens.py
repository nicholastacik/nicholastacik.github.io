"""Most-common proper-noun phrases per cluster-type."""
import math
import re
from collections import Counter

import pandas as pd

from jeopardy import config

# Single-token capitalized words that are sentence-initial/pronominal, not entities.
_STOPWORDS = {
    "This", "These", "That", "Those", "The", "A", "An", "He", "She", "It",
    "In", "On", "At", "Of", "To", "For", "His", "Her", "Its", "Their", "They",
    "You", "We", "I", "When", "What", "Where", "Who", "Why", "How", "As", "By",
    "From", "With", "One", "Now", "Here", "There", "Like", "Also", "But", "And",
    "Or", "If", "Then", "Both", "Each", "Some", "Many", "Most", "All", "No",
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
    # Drop leading stopwords. With bare digits excluded from continuations
    # above, a phrase can never start with (or contain) a bare number, so
    # there's no need to additionally strip leading numeric tokens.
    while tokens and tokens[0] in _STOPWORDS:
        tokens.pop(0)
    return " ".join(tokens)


def extract_phrases(text):
    """All proper-noun phrases in `text` (dups kept), leading stopwords stripped."""
    out = []
    for m in _PHRASE_RE.finditer(text or ""):
        phrase = _strip_leading_stopwords(m.group(0).strip())
        if phrase:
            out.append(phrase)
    return out


def cluster_top_phrases(clusters_df, clues_df, min_freq=5, top_n=25):
    keys = ["game_id", "round", "category"]
    merged = clues_df.merge(clusters_df[keys + ["cluster_id"]], on=keys, how="inner")
    clue_text = merged["clue"].fillna("").tolist()
    answer_text = merged["answer"].fillna("").tolist()
    cids = merged["cluster_id"].tolist()

    counts = {}  # cluster_id -> Counter(phrase -> count)
    for cid, clue, answer in zip(cids, clue_text, answer_text):
        # Extract from clue/answer separately (not concatenated) so a
        # trailing entity in the clue can't glue onto a leading entity in
        # the answer (e.g. "...Civil War" + "Abraham Lincoln").
        counter = counts.setdefault(cid, Counter())
        counter.update(extract_phrases(clue))
        counter.update(extract_phrases(answer))

    n_clusters = len(counts)
    doc_freq = Counter()  # phrase -> number of clusters containing it
    for counter in counts.values():
        doc_freq.update(counter.keys())

    rows = []
    for cid in sorted(counts):
        qualifying = {p: n for p, n in counts[cid].items() if n >= min_freq}
        n_qual = len(qualifying)
        if not qualifying:
            rows.append({"cluster_id": cid, "rank": 0, "phrase": None, "count": 0,
                         "tfidf_weight": 0.0, "n_qualifying_phrases": 0})
            continue
        scored = []
        for phrase, n in qualifying.items():
            idf = math.log(n_clusters / (1 + doc_freq[phrase])) + 1.0
            scored.append((phrase, n, n * idf))
        scored.sort(key=lambda x: (-x[2], -x[1], x[0]))
        for rank, (phrase, n, weight) in enumerate(scored[:top_n], start=1):
            rows.append({"cluster_id": cid, "rank": rank, "phrase": phrase, "count": n,
                         "tfidf_weight": weight, "n_qualifying_phrases": n_qual})
    return pd.DataFrame(
        rows, columns=["cluster_id", "rank", "phrase", "count", "tfidf_weight", "n_qualifying_phrases"]
    )


def run_tokens(min_freq=5, top_n=25):
    clusters = pd.read_parquet(config.CATEGORY_CLUSTERS_PATH)
    clues = pd.read_parquet(config.PARQUET_PATH)
    df = cluster_top_phrases(clusters, clues, min_freq=min_freq, top_n=top_n)
    config.CATEGORY_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.CATEGORY_TOKENS_PATH, index=False)
    applicable = df[df["n_qualifying_phrases"] > 0]["cluster_id"].nunique()
    print(f"Wrote {len(df):,} rows for {df['cluster_id'].nunique()} clusters "
          f"({applicable} with qualifying phrases) -> {config.CATEGORY_TOKENS_PATH}")

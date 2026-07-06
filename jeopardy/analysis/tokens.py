"""Most-common proper-noun phrases per cluster-type."""
import re

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

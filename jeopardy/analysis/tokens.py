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
_NUM = r"(?:[IVX]+|\d+)"
_CONNECT = r"(?:of|the|and|de|la|von|van)"
# Head cap-word, then continuations: cap-words / numerals, optionally preceded by
# lowercase connector words ("of the"). Maximal munch keeps "Richard III" whole.
_PHRASE_RE = re.compile(
    rf"\b{_WORD}(?:\s+(?:{_CONNECT}\s+)*(?:{_WORD}|{_NUM}))*"
)


_BARE_NUM = re.compile(r"^\d+$")


def _strip_leading_stopwords(phrase):
    tokens = phrase.split()
    # Drop leading stopwords, and any leading bare digit run (e.g. a year that
    # got glued on after a sentence-initial stopword, as in "In 1483 Richard III").
    # A genuine entity never starts with a bare number; roman numerals like
    # "III" only ever trail a name, so they're untouched.
    while tokens and (tokens[0] in _STOPWORDS or _BARE_NUM.match(tokens[0])):
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

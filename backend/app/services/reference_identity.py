"""Whether a fetched reference article is about the taxon it would be shown under.

A summary that merely mentions a scientific name is not about that taxon: a
mite's article lists its hosts, a predator's its prey. The subject of an
article is what its title names and what its opening sentence defines, so
identity is read from those two places only. A mismatch is rejected, and the
record then shows no description rather than a wrong one.
"""

from __future__ import annotations

import re
import unicodedata

_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|[。！？]")
# The longest word before a full stop that is read as an initial or abbreviation ("L.", "St.").
_ABBREVIATION_LENGTH = 2


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def lead_sentence(extract: str | None) -> str:
    """The opening sentence of a summary: the one that says what the article is about."""
    text = str(extract or "").strip()
    for match in _SENTENCE_END.finditer(text):
        if match.group() == ".":
            word = re.search(r"[^\s(]*$", text[: match.start()])
            if word and 0 < len(word.group()) <= _ABBREVIATION_LENGTH and word.group().isalpha():
                continue
        return text[: match.end()]
    return text


def article_describes_taxon(article: dict, scientific_name: str | None) -> bool:
    """True when the article's title is the scientific name or its lead sentence names it whole."""
    identity = _normalise(scientific_name)
    if not identity or article.get("type") == "disambiguation":
        return False
    if _normalise(article.get("title")) == identity:
        return True
    lead = _normalise(lead_sentence(article.get("extract")))
    return re.search(rf"(?<!\w){re.escape(identity)}(?!\w)", lead) is not None

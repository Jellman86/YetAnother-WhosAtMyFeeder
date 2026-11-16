"""Whether a fetched reference article is about the taxon it would be shown under.

A summary that mentions a scientific name is not about that taxon: a mite's
article names its host, a hawk's its prey, a genus its species, and all of them
can do so in the opening sentence. An article is about a taxon when the taxon
is its subject, which shows in two places only:

- the title is the scientific name; or
- the opening sentence presents the name as what the article defines. It opens
  with the name, or carries it in the parenthetical that follows the article's
  own subject ("The common starling (Sturnus vulgaris) is ...").

Anything else is a mention. A mismatch is rejected, and the record then shows
no description rather than a wrong one. A renamed taxon is recognised through
synonyms the caller trusts, each held to the same rule.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|[。！？]")
# The longest word before a full stop that is read as an initial or abbreviation ("L.", "St.").
_ABBREVIATION_LENGTH = 2
# A label before the name inside the parenthetical: "lat.", "Latin:", "学名：", "nom scientifique :".
_LABEL_WORDS = 2
_LABEL_END = (".", ":")
# How far into the sentence the subject's parenthetical may open when the article has no title.
_UNTITLED_SUBJECT_WORDS = 8
_LEADING_ARTICLE = re.compile(r"^(the|a|an|der|die|das|le|la|les|l|el|los|las|il|lo|i|gli|o|os|as)\s+")


def _fold(value: object) -> str:
    """Case and width folded text with its punctuation kept, for reading sentence structure."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).casefold()).strip()


def _words(value: object) -> str:
    """Folded text reduced to its words, for comparing names."""
    text = re.sub(r"[_\-]+", " ", _fold(value))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)).strip()


def _contains(text: str, name: str) -> re.Match[str] | None:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text)


def lead_sentence(extract: str | None) -> str:
    """The opening sentence of a summary: the one that says what the article is about."""
    text = str(extract or "").strip()
    for match in _SENTENCE_END.finditer(text):
        before = text[: match.start()]
        # A stop inside an open parenthetical ("(лат. Sturnus vulgaris)") does not end the sentence.
        if len(re.findall(r"[(（]", before)) > len(re.findall(r"[)）]", before)):
            continue
        if match.group() == ".":
            word = re.search(r"[^\s(]*$", before)
            if word and 0 < len(word.group()) <= _ABBREVIATION_LENGTH and word.group().isalpha():
                continue
        return text[: match.end()]
    return text


def _title_subject(title: object) -> str:
    """The article's own subject as its title words, without a disambiguator such as "(bird)"."""
    return _words(re.sub(r"\s*\([^()]*\)\s*$", "", str(title or "")))


def _opens_with(lead: str, name: str) -> bool:
    opening = _LEADING_ARTICLE.sub("", _words(lead), count=1)
    return opening == name or opening.startswith(f"{name} ")


def _named_beside_the_subject(lead: str, name: str, title: str) -> bool:
    """The name stands in the parenthetical that follows the article's own subject."""
    opened = lead.find("(")
    if opened == -1:
        return False
    closed = lead.find(")", opened)
    inside = lead[opened + 1 : closed if closed != -1 else len(lead)]
    # Compared as words, so "Sturnus  vulgaris" and odd spacing still match, but the position
    # is read from text that keeps its punctuation, which is what tells a label from a clause.
    found = _contains(inside, name)
    if not found:
        return False
    label = inside[: found.start()].strip()
    if label and not (label.endswith(_LABEL_END) and len(_words(label).split()) <= _LABEL_WORDS):
        return False
    before = _words(lead[:opened])
    if title:
        return _contains(before, title) is not None
    return len(before.split()) <= _UNTITLED_SUBJECT_WORDS


def _is_subject(article: dict, name: str) -> bool:
    title = _title_subject(article.get("title"))
    if title == name:
        return True
    lead = _fold(lead_sentence(article.get("extract")))
    return _opens_with(lead, name) or _named_beside_the_subject(lead, name, title)


def article_describes_taxon(article: dict, scientific_name: str | None, aliases: Iterable[str] = ()) -> bool:
    """True when the taxon, under its name or a trusted synonym, is the article's subject."""
    if article.get("type") == "disambiguation":
        return False
    names = [_words(name) for name in (scientific_name, *aliases)]
    return bool(names[0]) and any(_is_subject(article, name) for name in names if name)


def linked_article_names_taxon(article: dict, scientific_name: str | None) -> bool:
    """For a page reached through the taxon's own identity link: it only has to name the taxon.

    iNaturalist's record of a taxon links to its Wikipedia page. That link is the identity, so
    the page is not asked to make the taxon the subject of its opening sentence (a family page
    often opens with the common name). It must still name the taxon somewhere in its summary,
    which catches a link that has rotted onto another subject.
    """
    name = _words(scientific_name)
    if not name or article.get("type") == "disambiguation":
        return False
    text = _words(" ".join(str(article.get(key) or "") for key in ("title", "description", "extract")))
    return _contains(text, name) is not None


def cached_reference_describes_taxon(
    *,
    title: str | None,
    extract: str | None,
    summary_source: str | None,
    cached_scientific_name: str | None,
    scientific_name: str | None,
    aliases: Iterable[str] = (),
) -> bool:
    """Whether a cached reference may be shown for the taxon now being asked about.

    Entries cached before identity was checked can hold another subject's text, so a cached
    entry is held to the rule a fresh one is. A Wikipedia summary must have the taxon as its
    subject; a summary from a taxon record (iNaturalist, eBird) must be that taxon's, by its
    name or a trusted synonym. With no summary, or no known taxon to check against, there is
    nothing to refuse.
    """
    name = _words(scientific_name)
    if not name or not extract:
        return True
    if (summary_source or "").casefold() == "wikipedia":
        return article_describes_taxon({"title": title, "extract": extract}, scientific_name, aliases)
    cached = _words(cached_scientific_name)
    if not cached:
        return True
    return cached == name or cached in {_words(alias) for alias in aliases}

"""Whether a fetched reference article is about the taxon it would be shown under.

A summary that mentions a scientific name is not about that taxon: a mite's
article names its host, a hawk's its prey, a genus its species, and all of them
can do so in the opening sentence. An article is about a taxon when the taxon
is its subject, which is established in one of three ways. The last two read the text and are
the fallback for a taxon whose record links no article:

- the article is the one the taxon's own record links to (iNaturalist's `wikipedia_url`). That
  link is a structured identity and needs no reading of the text, which matters because
  Wikipedia's REST summary leaves the scientific-name parenthetical out of its extract; or
- the title is the scientific name; or
- the opening sentence presents the name as what the article defines. It opens
  with the name, or carries it in the parenthetical that comes straight after the
  article's own subject, before any verb ("The common starling (Sturnus vulgaris)
  is ...").

The name is compared whole. An authority may follow it ("Linnaeus, 1758"); one
more epithet makes it a subspecies, which is another taxon.

Anything else is a mention. A mismatch is rejected, and the record then shows
no description rather than a wrong one. A renamed taxon is recognised through
synonyms the caller trusts, each held to the same rule.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import unquote, urlparse

_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|[。！？]")
# The longest word before a full stop that is read as an initial or abbreviation ("L.", "St.").
_ABBREVIATION_LENGTH = 2
# A label before the name inside the parenthetical: "lat.", "Latin:", "学名：", "nom scientifique :".
_LABEL_WORDS = 2
_LABEL_END = (".", ":")
# How far into the sentence the subject's parenthetical may open when the article has no title.
_UNTITLED_SUBJECT_WORDS = 4
_LEADING_ARTICLE = re.compile(
    r"^(?:(?:the|a|an|der|die|das|le|la|les|el|los|las|il|lo|i|gli|o|os|as)\s+|l['’]\s*)", re.IGNORECASE
)
# A lower-case Latin word straight after a scientific name is one more epithet ("Troglodytes
# troglodytes hirtensis"), which makes it a different taxon, unless it is one of these.
_AFTER_AN_OPENING_NAME = frozenset(
    "is are was were or and ist sind war oder und es son fue est sont ou et è sono e é são".split()
)
_AUTHORITY_PARTICLES = frozenset("de del di da du von van den der".split())
_LOWER_CASE_LATIN_WORD = re.compile(r"[a-zß-öø-ÿ]+")
_OTHER_NAME_JOINERS = "or|oder|ou|o|u|или"
# The article's other names for its subject, between its title and the parenthetical: "or wild
# duck", ", rock pigeon, or common pigeon". Each is short, and the last is joined by "or".
_OTHER_NAME = r"[^\s,;:()]+(?: [^\s,;:()]+){0,3}"
_OTHER_NAMES = re.compile(rf"(?:, {_OTHER_NAME})*,? (?:{_OTHER_NAME_JOINERS}) {_OTHER_NAME}", re.IGNORECASE)


def _text(value: object) -> str:
    """Width folded text with its case and punctuation kept, for reading sentence structure."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def _fold(value: object) -> str:
    return _text(value).casefold()


def _words(value: object) -> str:
    """Folded text reduced to its words, for comparing names."""
    text = re.sub(r"[_\-]+", " ", _fold(value))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)).strip()


def _contains(text: str, name: str) -> re.Match[str] | None:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text)


def _find_name(text: str, name: str) -> re.Match[str] | None:
    """The name's words in text that keeps its case and punctuation."""
    spelled = r"[\s_\-]+".join(re.escape(word) for word in name.split())
    return re.search(rf"(?<!\w){spelled}(?!\w)", text, flags=re.IGNORECASE)


def _is_the_complete_name(after: str, allowed_words: frozenset[str]) -> bool:
    """Nothing after the name extends it into another taxon's name.

    An authority may follow ("(Linnaeus, 1758)", "Linnaeus, 1758", "L."): it is punctuation,
    a year or a capitalised word. One more lower-case epithet may not.
    """
    word = re.match(r"\s*([^\W\d_]+)", after)
    if not word or not _LOWER_CASE_LATIN_WORD.fullmatch(word.group(1)):
        return True
    return word.group(1) in allowed_words


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
    opening = _LEADING_ARTICLE.sub("", lead, count=1)
    found = _find_name(opening, name)
    return bool(found) and found.start() == 0 and _is_the_complete_name(opening[found.end() :], _AFTER_AN_OPENING_NAME)


def _is_the_subject_phrase(before: str, title: str) -> bool:
    """The text before the parenthetical is the article's subject and nothing more.

    A verb or a clause between the subject and the parenthetical ("The sparrowhawk hunts the
    house sparrow (Passer domesticus)") means the parenthetical names something else. Verbs are
    not recognised as such: only the title, alone or followed by the subject's other names, is.
    """
    phrase = _LEADING_ARTICLE.sub("", before.strip(), count=1)
    if not title:
        return 0 < len(_words(phrase).split()) <= _UNTITLED_SUBJECT_WORDS and not re.search(r"[,;:]", phrase)
    words = title.split()
    opening = re.match(r"[\W_]*" + r"[\W_]+".join(re.escape(word) for word in words), phrase, flags=re.IGNORECASE)
    if not opening:
        return False
    rest = phrase[opening.end() :]
    return not rest.strip() or _OTHER_NAMES.fullmatch(rest.rstrip()) is not None


def _named_beside_the_subject(lead: str, name: str, title: str) -> bool:
    """The name stands, complete, in the parenthetical that directly follows the article's own subject."""
    opened = lead.find("(")
    if opened == -1:
        return False
    closed = lead.find(")", opened)
    inside = lead[opened + 1 : closed if closed != -1 else len(lead)]
    found = _find_name(inside, name)
    if not found or not _is_the_complete_name(inside[found.end() :], _AUTHORITY_PARTICLES):
        return False
    # The position is read from text that keeps its punctuation, which tells a label from a clause.
    label = inside[: found.start()].strip()
    if label and not (label.endswith(_LABEL_END) and len(_words(label).split()) <= _LABEL_WORDS):
        return False
    return _is_the_subject_phrase(lead[:opened], title)


def _is_subject(article: dict, name: str) -> bool:
    title = _title_subject(article.get("title"))
    if title == name:
        return True
    lead = _text(lead_sentence(article.get("extract")))
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


def linked_article(wikipedia_url: str | None) -> tuple[str, str] | None:
    """The language and title of the article a taxon's record links to, or None for anything else."""
    parsed = urlparse(str(wikipedia_url or "").strip())
    host = (parsed.hostname or "").casefold()
    if parsed.scheme not in ("http", "https") or not host.endswith(".wikipedia.org") or "/wiki/" not in parsed.path:
        return None
    language = host.split(".")[0]
    title = unquote(parsed.path.split("/wiki/", 1)[1]).replace("_", " ").strip()
    if not title or not re.fullmatch(r"[a-z][a-z\-]{1,11}", language):
        return None
    return language, title


def linked_article_is_still_the_taxon(
    requested_title: str,
    article: dict,
    scientific_name: str | None,
    known_names: Iterable[str] = (),
    aliases: Iterable[str] = (),
) -> bool:
    """Whether the article that answered for a taxon's linked title is still that taxon's.

    The link is the identity only while the linked title is what answers. Wikipedia follows its
    own redirects, and a redirect can point anywhere: a renamed article, but also a merged one, a
    genus, a host. When another title answers, it is the same taxon only if that title is a name
    the caller already knows for the taxon (a recorded common name or synonym), or the article
    has the exact scientific name as its subject. Otherwise the link has not been verified.
    """
    answered = _title_subject(article.get("title"))
    if not answered or answered == _title_subject(requested_title):
        return bool(answered)
    if answered in {_words(name) for name in known_names if name}:
        return True
    return article_describes_taxon(article, scientific_name, aliases)


def cached_reference_describes_taxon(
    *,
    extract: str | None,
    summary_source: str | None,
    cached_scientific_name: str | None,
    scientific_name: str | None,
    aliases: Iterable[str] = (),
    identity_checked: bool = False,
) -> bool:
    """Whether a cached reference may be shown for the taxon now being asked about.

    A Wikipedia summary's text rarely names its taxon, so its identity is established when it is
    fetched (the article the taxon's record links to) and kept with the row as
    `identity_checked`. Only such a row, saved for this name or a trusted synonym, is served. A
    row from before that was recorded is looked up again, whatever its text says, and saved with
    its refreshed identity. A summary from a taxon record (iNaturalist, eBird) must be that
    taxon's by name. With no summary, or no known taxon to check against, there is nothing to
    refuse.
    """
    name = _words(scientific_name)
    if not name or not extract:
        return True
    cached = _words(cached_scientific_name)
    same_taxon = bool(cached) and (cached == name or cached in {_words(alias) for alias in aliases})
    if (summary_source or "").casefold() == "wikipedia":
        return identity_checked and same_taxon
    return same_taxon or not cached

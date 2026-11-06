"""Normalize provider reference fragments to text without rendering their HTML."""

from html import unescape
from html.parser import HTMLParser
import re


class _ReferenceText(HTMLParser):
    _HIDDEN = {"script", "style", "template", "iframe", "object", "noscript", "svg", "math"}
    _BLOCKS = {"p", "div", "section", "article", "blockquote", "ul", "ol", "h1", "h2", "h3", "h4", "table", "tr"}
    _VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.hidden or tag in self._HIDDEN:
            if tag not in self._VOID:
                self.hidden.append(tag)
        elif tag in self._BLOCKS:
            self.parts.append("\n\n")
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n• ")

    def handle_endtag(self, tag: str) -> None:
        if self.hidden:
            if tag in self.hidden:
                index = len(self.hidden) - 1 - self.hidden[::-1].index(tag)
                del self.hidden[index:]
        elif tag in self._BLOCKS:
            self.parts.append("\n\n")
        elif tag == "li":
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.hidden and tag not in self._HIDDEN:
            self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def reference_plain_text(value: str | None) -> str | None:
    if value is None:
        return None
    # Some cached provider fragments escape the entire HTML document, including
    # its entities. Decode before parsing so these are not shown as literal tags.
    for _ in range(4):
        decoded = unescape(value)
        if decoded == value:
            break
        value = decoded
    parser = _ReferenceText()
    parser.feed(value)
    parser.close()
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text or None

"""No locale file holds a control character where punctuation was meant.

A control character is invisible in an editor and reaches the reader as a box or as nothing. The
server's messages and the Home Assistant integration's strings are held to the same rule as the
web interface's (apps/ui/src/lib/i18n/locales.control-characters.test.ts).
"""

import json
import re
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[3]
LOCALE_FILES = sorted(
    [
        *(REPOSITORY / "backend" / "locales").glob("*.json"),
        *(REPOSITORY / "custom_components" / "yawamf" / "translations").glob("*.json"),
        REPOSITORY / "custom_components" / "yawamf" / "strings.json",
    ]
)
# C0 and C1 controls and DEL. Tab and newline are the two a string may legitimately hold.
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _control_characters(value: object, path: str) -> list[str]:
    if isinstance(value, str):
        found = CONTROL.search(value)
        return [f"{path}: U+{ord(found.group()):04X} in {value!r}"] if found else []
    if isinstance(value, dict):
        return [
            finding
            for key, child in value.items()
            for finding in (
                *([f"{path}.{key}: a control character in the key"] if CONTROL.search(key) else []),
                *_control_characters(child, f"{path}.{key}" if path else key),
            )
        ]
    if isinstance(value, list):
        return [
            finding for index, child in enumerate(value) for finding in _control_characters(child, f"{path}[{index}]")
        ]
    return []


def test_the_server_has_a_locale_file_for_each_of_the_nine_languages():
    server = {path.stem for path in LOCALE_FILES if path.parent.name == "locales"}
    assert server == {"de", "en", "es", "fr", "it", "ja", "pt", "ru", "zh"}


@pytest.mark.parametrize("path", LOCALE_FILES, ids=lambda path: str(path.relative_to(REPOSITORY)))
def test_locale_file_holds_no_control_character(path: Path):
    text = path.read_text(encoding="utf-8")
    # Written raw or as a \u escape, the character ends up in the parsed string either way.
    assert _control_characters(json.loads(text), "") == []
    # Outside the strings, only the file's own tabs and newlines belong.
    assert CONTROL.search(text) is None


def test_a_control_character_is_reported_with_its_code_point_and_place():
    assert _control_characters({"errors": {"retry": "Réessayez \x01 si cela continue"}}, "") == [
        "errors.retry: U+0001 in 'Réessayez \\x01 si cela continue'"
    ]
    assert _control_characters({"note": "one\ttwo\nthree"}, "") == []

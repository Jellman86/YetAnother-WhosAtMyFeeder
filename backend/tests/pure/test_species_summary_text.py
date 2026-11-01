"""Reference summaries are readable text, including previously cached HTML."""

import pytest

from app.models import SpeciesInfo


@pytest.mark.parametrize(
    ("raw", "plain"),
    [
        ("<p>The <b>dog</b> (<i>Canis familiaris</i>) is an animal.</p>", "The dog (Canis familiaris) is an animal."),
        (
            "<p>Dogs &amp; cats&nbsp;live here.</p><p>A second paragraph.</p>",
            "Dogs & cats live here.\n\nA second paragraph.",
        ),
        (
            "<p>A <a href='https://example.com' onclick='bad()'>fox</a>.</p><script>bad()</script><style>body{display:none}</style>",
            "A fox.",
        ),
        ("<p>One<br>Two</p>", "One\nTwo"),
        ("<p>Fox<!-- hidden comment -->es.</p>", "Foxes."),
        ("&lt;p&gt;The dog &amp;amp; the fox.&lt;/p&gt;", "The dog & the fox."),
        ("A score < 0.7 is below 0.9; 3 > 2.", "A score < 0.7 is below 0.9; 3 > 2."),
        ("<script>bad()</script>", None),
        ("   ", None),
        (None, None),
    ],
)
def test_reference_text_removes_markup_without_running_or_rendering_it(raw, plain):
    info = SpeciesInfo(title="Dog", extract=raw, description=raw)
    assert info.extract == info.description == plain
    assert SpeciesInfo.model_validate(info.model_dump()).model_dump() == info.model_dump()

"""A fetched description is about the taxon it is shown under, or it is not shown.

The Garden record of an Eastern Gray Squirrel carried the Wikipedia summary of
*Androlaelaps fahrenholzi*, a mite: the article lists the squirrel among its
hosts, and any mention of the scientific name anywhere in the summary used to
count as identity. An article is about a taxon when its title is the taxon's
name, or its opening sentence, the one that defines the subject, names it.
"""

import pytest

from app.services.reference_identity import article_describes_taxon, lead_sentence

SQUIRREL = {
    "title": "Eastern gray squirrel",
    "description": "Species of mammal",
    "extract": (
        "The eastern gray squirrel (Sciurus carolinensis), also known, particularly outside of North America, "
        "as simply the grey squirrel, is a tree squirrel in the genus Sciurus. It is native to eastern North America."
    ),
}
MITE = {
    "title": "Androlaelaps fahrenholzi",
    "description": "Species of mite",
    "extract": (
        "Androlaelaps fahrenholzi is a species of mite in the genus Androlaelaps of the family Laelapidae. "
        "It occurs throughout the contiguous United States, where it has been recorded on the following mammals: "
        "Blarina brevicauda, Sciurus carolinensis, Tamias striatus."
    ),
}


def test_the_squirrels_own_article_describes_the_squirrel():
    assert article_describes_taxon(SQUIRREL, "Sciurus carolinensis")


def test_a_mite_that_lists_the_squirrel_as_a_host_does_not_describe_the_squirrel():
    assert not article_describes_taxon(MITE, "Sciurus carolinensis")


def test_an_article_titled_with_the_scientific_name_describes_that_taxon():
    assert article_describes_taxon(MITE, "Androlaelaps fahrenholzi")
    assert article_describes_taxon(
        {"title": "Sturnus vulgaris", "extract": "Der Star ist ein Singvogel."}, "Sturnus vulgaris"
    )


def test_a_short_description_that_only_mentions_the_name_is_not_identity():
    article = {"title": "Squirrel louse", "description": "Parasite of Sciurus carolinensis", "extract": "A louse."}
    assert not article_describes_taxon(article, "Sciurus carolinensis")


@pytest.mark.parametrize("text", ["XSciurus carolinensis", "Sciurus carolinensisX", "Sciurus niger carolinensis"])
def test_the_name_must_be_complete(text):
    assert not article_describes_taxon(
        {"title": "Squirrel", "extract": f"The squirrel ({text}) is a rodent."}, "Sciurus carolinensis"
    )


def test_a_disambiguation_page_or_a_missing_name_describes_nothing():
    assert not article_describes_taxon(
        {"type": "disambiguation", "title": "Sciurus carolinensis"}, "Sciurus carolinensis"
    )
    assert not article_describes_taxon(SQUIRREL, None)
    assert not article_describes_taxon(SQUIRREL, "  ")
    assert not article_describes_taxon({}, "Sciurus carolinensis")


@pytest.mark.parametrize(
    ("extract", "lead"),
    [
        (
            "The dog (Canis familiaris) is a domesticated descendant of the wolf. It was bred.",
            "The dog (Canis familiaris) is a domesticated descendant of the wolf.",
        ),
        # An authority or an initial is not the end of the sentence.
        (
            "The common starling (Sturnus vulgaris L.) is a passerine. It is noisy.",
            "The common starling (Sturnus vulgaris L.) is a passerine.",
        ),
        (
            "St. Kilda wren (Troglodytes troglodytes hirtensis) is a small bird. It lives on St Kilda.",
            "St. Kilda wren (Troglodytes troglodytes hirtensis) is a small bird.",
        ),
        (
            "ハイイロリス（学名：Sciurus carolinensis）は、リス科の動物である。北アメリカ原産。",
            "ハイイロリス（学名：Sciurus carolinensis）は、リス科の動物である。",
        ),
        ("One sentence with no end", "One sentence with no end"),
        ("", ""),
    ],
)
def test_the_lead_is_the_first_sentence(extract, lead):
    assert lead_sentence(extract) == lead

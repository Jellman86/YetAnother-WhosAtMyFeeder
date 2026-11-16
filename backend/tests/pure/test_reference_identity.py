"""A fetched description is about the taxon it is shown under, or it is not shown.

The Garden record of an Eastern Gray Squirrel carried the Wikipedia summary of
*Androlaelaps fahrenholzi*, a mite: the article lists the squirrel among its
hosts, and any mention of the scientific name anywhere in the summary used to
count as identity. An article is about a taxon when its title is the taxon's
name, or its opening sentence, the one that defines the subject, names it.
"""

import pytest

from app.services.reference_identity import (
    article_describes_taxon,
    cached_reference_describes_taxon,
    lead_sentence,
)

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


def article(title: str, extract: str) -> dict:
    return {"title": title, "extract": extract}


@pytest.mark.parametrize(
    ("title", "extract", "taxon"),
    [
        # A parasite whose opening sentence names its host.
        (
            "Androlaelaps fahrenholzi",
            "Androlaelaps fahrenholzi is a mite that parasitises Sciurus carolinensis.",
            "Sciurus carolinensis",
        ),
        # The host tucked into a parenthetical of the opening sentence.
        (
            "Brueelia nebulosa",
            "Brueelia nebulosa is a chewing louse (found on Sturnus vulgaris) of passerine birds.",
            "Sturnus vulgaris",
        ),
        ("Brueelia nebulosa", "Brueelia nebulosa (a parasite of Sturnus vulgaris) is a louse.", "Sturnus vulgaris"),
        # A predator whose opening sentence names its prey.
        (
            "Eurasian sparrowhawk",
            "The Eurasian sparrowhawk (Accipiter nisus) is a small bird of prey that hunts Passer domesticus.",
            "Passer domesticus",
        ),
        # A genus, or a place, that mentions a species in passing.
        ("Sciurus", "Sciurus is a genus of tree squirrels that includes Sciurus carolinensis.", "Sciurus carolinensis"),
    ],
)
def test_a_mention_in_the_opening_sentence_is_not_the_subject(title, extract, taxon):
    assert not article_describes_taxon(article(title, extract), taxon)


@pytest.mark.parametrize(
    ("title", "extract", "taxon"),
    [
        (
            "Eastern gray squirrel",
            "The eastern gray squirrel (Sciurus carolinensis), also known as the grey squirrel, is a tree squirrel.",
            "Sciurus carolinensis",
        ),
        (
            "Common starling",
            "The common starling (Sturnus vulgaris L.) is a medium-sized passerine.",
            "Sturnus vulgaris",
        ),
        # Several names before the parenthetical, the title among them.
        (
            "Rock dove",
            "The rock dove, rock pigeon, or common pigeon (Columba livia) is a member of the bird family Columbidae.",
            "Columba livia",
        ),
        # The sentence opens with the scientific name itself.
        (
            "Eastern gray squirrel",
            "Sciurus carolinensis, the eastern gray squirrel, is a tree squirrel.",
            "Sciurus carolinensis",
        ),
        # Other languages label the name inside the parenthetical.
        (
            "Обыкновенный скворец",
            "Обыкновенный скворец (лат. Sturnus vulgaris) — певчая птица семейства скворцовых.",
            "Sturnus vulgaris",
        ),
        (
            "ホシムクドリ",
            "ホシムクドリ（星椋鳥、学名：Sturnus vulgaris）は、スズメ目ムクドリ科の鳥である。",
            "Sturnus vulgaris",
        ),
        ("Star (Art)", "Der Star (Sturnus vulgaris) ist eine Vogelart aus der Familie der Stare.", "Sturnus vulgaris"),
        (
            "Étourneau sansonnet",
            "L'Étourneau sansonnet (nom scientifique : Sturnus vulgaris) est une espèce de passereaux.",
            "Sturnus vulgaris",
        ),
    ],
)
def test_the_taxon_named_as_the_subject_of_the_opening_sentence_is_described(title, extract, taxon):
    assert article_describes_taxon(article(title, extract), taxon)


def test_a_renamed_taxon_is_recognised_through_a_trusted_synonym_only():
    jackdaw = article(
        "Western jackdaw", "The western jackdaw (Coloeus monedula) is a passerine bird in the crow family."
    )

    assert not article_describes_taxon(jackdaw, "Corvus monedula")
    assert article_describes_taxon(jackdaw, "Corvus monedula", aliases=["Coloeus monedula"])
    # A synonym is held to the same rule: a mention is still only a mention.
    louse = article("Brueelia varia", "Brueelia varia is a louse that lives on Coloeus monedula.")
    assert not article_describes_taxon(louse, "Corvus monedula", aliases=["Coloeus monedula"])


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


def cached(**overrides) -> dict:
    return {
        "title": "Common starling",
        "extract": "The common starling (Sturnus vulgaris) is a passerine.",
        "summary_source": "Wikipedia",
        "cached_scientific_name": "Sturnus vulgaris",
        "scientific_name": "Sturnus vulgaris",
        **overrides,
    }


def test_a_cached_wikipedia_summary_is_held_to_the_subject_rule():
    assert cached_reference_describes_taxon(**cached())
    louse = cached(title="Brueelia nebulosa", extract="Brueelia nebulosa is a louse. Its host is Sturnus vulgaris.")
    assert not cached_reference_describes_taxon(**louse)


def test_a_cached_taxon_record_summary_must_be_that_taxons():
    other = cached(
        summary_source="iNaturalist", extract="A starling of Iberia.", cached_scientific_name="Sturnus unicolor"
    )
    assert not cached_reference_describes_taxon(**other)
    assert cached_reference_describes_taxon(**{**other, "cached_scientific_name": "Sturnus vulgaris"})
    assert cached_reference_describes_taxon(**{**other, "aliases": ["Sturnus unicolor"]})


def test_nothing_is_refused_without_a_summary_or_a_taxon_to_check_against():
    assert cached_reference_describes_taxon(**cached(extract=None, title="Anything"))
    assert cached_reference_describes_taxon(**cached(scientific_name=None, title="Brueelia nebulosa"))

import pytest

from app.config import settings
from app.utils.owner_confirmation import is_owner_confirmed, owner_confirmed_sql


@pytest.mark.parametrize(
    "display_name,category_name,expected",
    [
        ("Turdus merula", "Turdus merula", True),
        ("  Eurasian Blackbird ", None, True),
        ("Unknown Bird", "Unknown Bird", False),
        ("unknown bird", "Turdus merula", False),
        ("", "Turdus merula", False),
        (None, None, False),
        ("Background", "background", False),
        ("Turdus merula", "background", False),
        ("Thrushes and allies", "Turdidae", False),
        ("Life", "Life", False),
    ],
)
def test_a_person_confirms_only_a_named_species(display_name, category_name, expected):
    assert is_owner_confirmed(True, display_name, category_name) is expected


def test_a_model_label_without_an_owner_pick_is_not_a_confirmation():
    assert is_owner_confirmed(False, "Turdus merula", "Turdus merula") is False
    assert is_owner_confirmed(None, "Turdus merula", "Turdus merula") is False


def test_configured_unknown_labels_never_confirm(monkeypatch):
    monkeypatch.setattr(settings.classification, "unknown_bird_labels", ["Nothing here"])
    assert is_owner_confirmed(True, "Nothing here", "Nothing here") is False
    clause, params = owner_confirmed_sql("v")
    assert "nothing here" in params
    assert "v.manual_tagged = 1" in clause
    assert "d." not in clause

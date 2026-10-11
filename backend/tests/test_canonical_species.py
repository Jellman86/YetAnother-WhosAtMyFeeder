from app.utils.canonical_species import should_hide_species_label, unknown_species_labels


def test_should_hide_species_label_treats_abstention_labels_as_unknown():
    for label in (
        "Unknown",
        "Unknown Bird",
        "No detection",
        "No detections",
        "No data",
        "No result",
        "No results",
        "No classification",
        "No classifications",
        "No bird",
        "Not a bird",
        "Unclassified",
        "Unidentified",
        "Unidentified bird",
        "N/A",
        "None",
        "Null",
    ):
        assert should_hide_species_label(label), label


def test_unknown_species_labels_keeps_abstention_labels_deduplicated():
    labels = unknown_species_labels(extra_labels=["Unknown", "No data"])
    normalized = [label.casefold() for label in labels]

    assert normalized.count("unknown") == 1
    assert normalized.count("no data") == 1


def test_unknown_label_lookup_reuses_normalized_labels_without_caching_results(monkeypatch):
    from app.config import settings
    from app.utils import canonical_species

    monkeypatch.setattr(settings.classification, "unknown_bird_labels", ["Custom  Abstention"])
    assert canonical_species.is_unknown_species_label("custom abstention")
    normalize = canonical_species._normalize_label_key
    calls = []

    def record_normalization(value):
        calls.append(value)
        return normalize(value)

    monkeypatch.setattr(canonical_species, "_normalize_label_key", record_normalization)
    assert not canonical_species.is_unknown_species_label("Robin")
    assert calls == ["Robin"]


def test_unknown_label_cache_observes_config_replacement_and_in_place_mutation(monkeypatch):
    from app.config import settings
    from app.utils.canonical_species import is_unknown_species_label

    monkeypatch.setattr(settings.classification, "unknown_bird_labels", ["Custom label"])
    assert is_unknown_species_label("custom label")
    settings.classification.unknown_bird_labels.append("Another label")
    assert is_unknown_species_label("another label")
    settings.classification.unknown_bird_labels.remove("Custom label")
    assert not is_unknown_species_label("custom label")
    settings.classification.unknown_bird_labels = ["Replacement"]
    assert is_unknown_species_label("replacement")
    assert not is_unknown_species_label("another label")


def test_unknown_label_cache_preserves_generator_extras_unicode_and_public_list(monkeypatch):
    from app.config import settings
    from app.utils.canonical_species import is_unknown_species_label

    monkeypatch.setattr(settings.classification, "unknown_bird_labels", ["  Straße  ", "No  Data", "", " "])
    expected = unknown_species_labels()
    assert expected[-1] == "Straße"
    assert is_unknown_species_label("STRASSE")
    assert is_unknown_species_label("no\tdata")
    assert not is_unknown_species_label(None)
    assert not is_unknown_species_label(" ")
    extras = (value for value in ["  Extra   Label ", "extra label", "", " "])
    assert is_unknown_species_label("extra\tlabel", extra_labels=extras)
    assert not is_unknown_species_label("extra label", extra_labels=extras)
    assert not is_unknown_species_label("extra label")
    changed = unknown_species_labels()
    changed.append("Should not leak")
    assert unknown_species_labels() == expected
    assert not is_unknown_species_label("Should not leak")


def test_unknown_label_cache_is_bounded_and_immutable():
    from app.utils.canonical_species import _unknown_species_label_keys

    _unknown_species_label_keys.cache_clear()
    first = _unknown_species_label_keys(("first",), ())
    assert isinstance(first, frozenset)
    assert _unknown_species_label_keys(("first",), ()) is first
    for index in range(150):
        _unknown_species_label_keys((f"custom {index}",), ())
    info = _unknown_species_label_keys.cache_info()
    assert info.maxsize == 128
    assert info.currsize == 128
    assert info.hits == 1
    assert _unknown_species_label_keys(("first",), ()) == first
    assert _unknown_species_label_keys.cache_info().misses == info.misses + 1

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

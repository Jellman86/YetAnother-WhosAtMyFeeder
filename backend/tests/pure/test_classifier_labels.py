from app.utils.classifier_labels import normalize_classifier_label


def test_normalize_classifier_label_keeps_plain_labels_intact():
    assert normalize_classifier_label("Parus major") == "Parus major"
    assert normalize_classifier_label("Great Tit") == "Great Tit"


def test_normalize_classifier_label_extracts_scientific_name_from_birder_taxonomy_path():
    raw = "04853_Animalia_Chordata_Aves_Piciformes_Picidae_Picus_viridis_European_Green_Woodpecker"

    assert normalize_classifier_label(raw) == "Picus viridis"


def test_normalize_classifier_label_extracts_scientific_name_from_compact_taxonomy_label():
    raw = "00824_Pica_pica_Eurasian_Magpie"

    assert normalize_classifier_label(raw) == "Pica pica"

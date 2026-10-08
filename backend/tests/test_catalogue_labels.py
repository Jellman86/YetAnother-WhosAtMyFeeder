"""Reading a model's labels from the catalogue instead of its label file.

`labels.txt` is verified when a model is downloaded and never again, and every
inference since has trusted it. The catalogue now holds a row per output index
carrying the model's own label, taken from a file that was proven at install
time, so the labels can come from there instead.

Verified before writing this: on a live install the catalogue reproduces all ten
installed label files byte for byte.

It is deliberately conservative. Labels come from the catalogue only when it
holds a complete, contiguous set matching the model's declared output width, and
anything short of that falls back to the file, so a model the catalogue does not
know behaves exactly as it does today.
"""

import sqlite3
import hashlib
from unittest.mock import MagicMock, Mock

import pytest

from app.services.catalogue_labels import catalogue_labels_for_model, published_model_sha256


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "species_catalog.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE model_artifacts (id INTEGER PRIMARY KEY, registry_id TEXT, model_sha256 TEXT,
            mapping_set_sha256 TEXT, output_width INTEGER, runtime TEXT, model_version TEXT, state TEXT);
        CREATE TABLE model_output_taxa (model_artifact_id INTEGER, output_index INTEGER, class_kind TEXT,
            species_id INTEGER, source_label TEXT, PRIMARY KEY (model_artifact_id, output_index));
        INSERT INTO model_artifacts VALUES (1,'complete','sha-complete',NULL,3,'onnx',NULL,'installed');
        INSERT INTO model_output_taxa VALUES (1,0,'species',1,'Prunella modularis');
        INSERT INTO model_output_taxa VALUES (1,1,'species',2,'Erithacus rubecula');
        INSERT INTO model_output_taxa VALUES (1,2,'unknown',NULL,'Nothing resolved this');
        INSERT INTO model_artifacts VALUES (2,'short','sha-short',NULL,4,'onnx',NULL,'installed');
        INSERT INTO model_output_taxa VALUES (2,0,'species',1,'One');
        INSERT INTO model_output_taxa VALUES (2,1,'species',2,'Two');
        INSERT INTO model_artifacts VALUES (3,'gappy','sha-gappy',NULL,3,'onnx',NULL,'installed');
        INSERT INTO model_output_taxa VALUES (3,0,'species',1,'Zero');
        INSERT INTO model_output_taxa VALUES (3,2,'species',2,'Two');
        """
    )
    connection.commit()
    connection.close()
    return path


def test_labels_come_back_in_output_order(catalogue):
    assert catalogue_labels_for_model("sha-complete", catalog_path=catalogue) == [
        "Prunella modularis",
        "Erithacus rubecula",
        "Nothing resolved this",
    ]


def test_an_output_with_no_identity_still_contributes_its_label(catalogue):
    """The label is what inference needs; the identity is a separate question."""
    labels = catalogue_labels_for_model("sha-complete", catalog_path=catalogue)
    assert labels[2] == "Nothing resolved this"


def test_a_short_mapping_is_refused_so_the_file_is_used(catalogue):
    """Fewer rows than the model's width would silently truncate its classes."""
    assert catalogue_labels_for_model("sha-short", catalog_path=catalogue) is None


def test_a_gap_in_the_indices_is_refused(catalogue):
    """A missing index would shift every label after it onto the wrong class."""
    assert catalogue_labels_for_model("sha-gappy", catalog_path=catalogue) is None


def test_an_unregistered_model_is_refused(catalogue):
    assert catalogue_labels_for_model("sha-nobody-knows", catalog_path=catalogue) is None


@pytest.mark.parametrize("value", [None, "", "   "])
def test_no_checksum_is_refused(catalogue, value):
    assert catalogue_labels_for_model(value, catalog_path=catalogue) is None


def test_a_missing_catalogue_never_raises(tmp_path):
    assert catalogue_labels_for_model("sha-complete", catalog_path=tmp_path / "absent.db") is None


def test_the_registry_checksum_is_resolved_for_a_plain_model():
    assert published_model_sha256("rope_vit_b14_inat21")


def test_the_registry_checksum_is_resolved_for_a_region_variant():
    """A variant hangs off its parent and has no id of its own."""
    eu = published_model_sha256("small_birds", region="eu")
    na = published_model_sha256("small_birds", region="na")
    assert eu and na and eu != na


def test_an_unknown_model_has_no_registry_checksum():
    assert published_model_sha256("not_a_model") is None


def test_the_loader_prefers_the_catalogue_and_says_which_source_it_used(monkeypatch, tmp_path):
    """The label file stays as the fallback, not the default."""
    from app.services import classifier_service as module

    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("From the file\nSecond\n", encoding="utf-8")

    monkeypatch.setattr(
        module, "catalogue_labels_for_model", lambda _sha: ["From the catalogue", "Second"], raising=False
    )
    monkeypatch.setattr(
        "app.services.catalogue_labels.catalogue_labels_for_model",
        lambda _sha: ["From the catalogue", "Second"],
    )

    labels, _grouped, source = module._resolve_model_labels(
        str(labels_file), {}, model_sha256="sha-known", context="test"
    )
    assert source == "catalogue"
    assert labels[0] == "From the catalogue"


def test_the_loader_falls_back_to_the_file_when_the_catalogue_declines(monkeypatch, tmp_path):
    from app.services import classifier_service as module

    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("From the file\n", encoding="utf-8")
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda _sha: None)

    labels, _grouped, source = module._resolve_model_labels(
        str(labels_file), {}, model_sha256="sha-unknown", context="test"
    )
    assert source == "label_file"
    assert labels == ["From the file"]


def test_a_loader_with_no_checksum_reads_the_file(tmp_path):
    """Every caller that has not been given a checksum behaves as before."""
    from app.services import classifier_service as module

    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("From the file\n", encoding="utf-8")

    labels, _grouped, source = module._resolve_model_labels(str(labels_file), {}, context="test")
    assert source == "label_file"
    assert labels == ["From the file"]


def test_a_catalogue_that_raises_never_stops_a_model_loading(monkeypatch, tmp_path):
    from app.services import classifier_service as module

    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("From the file\n", encoding="utf-8")

    def explode(_sha):
        raise RuntimeError("catalogue on fire")

    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", explode)

    labels, _grouped, source = module._resolve_model_labels(
        str(labels_file), {}, model_sha256="sha-known", context="test"
    )
    assert source == "label_file"
    assert labels == ["From the file"]


@pytest.fixture(params=["ModelInstance", "ONNXModelInstance", "OpenVINOModelInstance"])
def native_loader(request, monkeypatch, tmp_path):
    from app.services import classifier_service as module

    monkeypatch.setattr(module, "tflite", MagicMock())
    monkeypatch.setattr(module, "ONNX_AVAILABLE", True)
    runtime = MagicMock()
    runtime.InferenceSession.return_value.get_providers.return_value = ["CPUExecutionProvider"]
    monkeypatch.setattr(module, "ort", runtime)
    monkeypatch.setattr(module, "OPENVINO_AVAILABLE", True)
    monkeypatch.setattr(module, "OpenVINOCore", MagicMock())
    monkeypatch.setattr(module, "resolve_openvino_cache_dir", lambda: str(tmp_path / "cache"))
    return getattr(module, request.param)


@pytest.mark.parametrize("file_present", [False, True])
@pytest.mark.parametrize("declared_checksum", [None, "different-selected-model"])
def test_native_load_uses_its_own_weights_for_catalogue_labels(
    native_loader, catalogue, monkeypatch, tmp_path, file_present, declared_checksum
):
    """Startup and fallback loaders need no caller-supplied checksum or label file."""
    from app.services import classifier_service as module

    weights = tmp_path / "weights"
    weights.write_bytes(b"actual fallback weights")
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    with sqlite3.connect(catalogue) as connection:
        connection.execute("UPDATE model_artifacts SET model_sha256=? WHERE id=1", (digest,))
    lookup = Mock(side_effect=lambda sha: catalogue_labels_for_model(sha, catalog_path=catalogue))
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lookup)
    hash_weights = Mock(wraps=module.artifact_digest)
    monkeypatch.setattr(module, "artifact_digest", hash_weights)
    labels = tmp_path / "labels.txt"
    if file_present:
        labels.write_text("Altered after installation\n", encoding="utf-8")

    model = native_loader("bird", str(weights), str(labels), model_sha256=declared_checksum)
    assert model.load() is True
    assert model.labels == ["Prunella modularis", "Erithacus rubecula", "Nothing resolved this"]
    lookup.assert_called_once_with(digest)
    assert model.load() is True
    hash_weights.assert_called_once_with(str(weights))
    model.cleanup()


def test_native_load_retains_file_fallback_for_incomplete_catalogue(native_loader, catalogue, monkeypatch, tmp_path):
    weights = tmp_path / "weights"
    weights.write_bytes(b"incompletely mapped model")
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    with sqlite3.connect(catalogue) as connection:
        connection.execute("UPDATE model_artifacts SET model_sha256=? WHERE id=2", (digest,))
    monkeypatch.setattr(
        "app.services.catalogue_labels.catalogue_labels_for_model",
        lambda sha: catalogue_labels_for_model(sha, catalog_path=catalogue),
    )
    labels = tmp_path / "labels.txt"
    labels.write_text("First\nSecond\nThird\nFourth\n", encoding="utf-8")
    model = native_loader("bird", str(weights), str(labels))
    assert model.load() is True
    assert model.labels == ["First", "Second", "Third", "Fourth"]
    model.cleanup()

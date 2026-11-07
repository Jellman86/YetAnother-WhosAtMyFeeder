"""Catalogue-backed classifiers must install and report ready without label files."""

import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest

from app.models.ai_models import DownloadProgress
from app.services import model_manager as module


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "MODELS_DIR", str(tmp_path))
    return module.ModelManager()


def test_catalogue_mapping_replaces_required_label_file(manager, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: ["Bird"])
    (tmp_path / "model.onnx").write_bytes(b"model")
    meta = {"id": "known", "runtime": "onnx", "sha256": hashlib.sha256(b"model").hexdigest()}
    assert manager._model_install_status(meta, str(tmp_path)) == (True, "ready")
    manager._validate_download_payload(meta, str(tmp_path), "model.onnx")


def test_missing_catalogue_and_label_file_remain_incomplete(manager, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: None)
    (tmp_path / "model.onnx").write_bytes(b"model")
    assert manager._model_install_status({"runtime": "onnx", "sha256": "missing"}, str(tmp_path)) == (
        False,
        "labels_missing",
    )


@pytest.mark.asyncio
async def test_download_skips_labels_when_catalogue_is_complete(manager, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: ["Bird"])
    requested = []

    def respond(request):
        requested.append(request.url.path)
        assert request.url.path == "/model.onnx"
        return httpx.Response(200, content=b"model")

    meta = {
        "id": "known",
        "runtime": "onnx",
        "download_url": "https://models.test/model.onnx",
        "labels_url": "https://models.test/labels.txt",
        "sha256": hashlib.sha256(b"model").hexdigest(),
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await manager._download_payload_to_dir(
            client=client,
            model_meta=meta,
            staged_dir=str(tmp_path),
            progress=DownloadProgress(model_id="known", status="downloading", progress=0),
            progress_model_id="known",
            progress_start=0,
            progress_end=100,
        )
    assert requested == ["/model.onnx"]
    assert not (tmp_path / "labels.txt").exists()


@pytest.mark.asyncio
async def test_catalogue_only_model_refuses_download_before_network_when_mapping_is_absent(
    manager, tmp_path, monkeypatch
):
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: None)
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="catalogue"):
        await manager._download_payload_to_dir(
            client=client,
            model_meta={
                "id": "new",
                "runtime": "onnx",
                "download_url": "https://models.test/model.onnx",
                "sha256": "new",
            },
            staged_dir=str(tmp_path),
            progress=DownloadProgress(model_id="new", status="downloading", progress=0),
            progress_model_id="new",
            progress_start=0,
            progress_end=100,
        )
    client.stream.assert_not_called()


def test_catalogue_mapping_cannot_be_bound_to_sidecar_replacement_weights(manager, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: ["Bird"])
    (tmp_path / "model.onnx").write_bytes(b"replacement")
    (tmp_path / "model_config.json").write_text('{"sha256": "' + hashlib.sha256(b"replacement").hexdigest() + '"}')
    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        manager._validate_download_payload(
            {"runtime": "onnx", "sha256": hashlib.sha256(b"original").hexdigest()}, str(tmp_path), "model.onnx"
        )


@pytest.mark.asyncio
async def test_split_weights_are_reassembled_and_each_part_is_verified(manager, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: ["Bird"])
    payloads = {"/model": b"graph", "/part1": b"first", "/part2": b"second"}

    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    meta = {
        "id": "large",
        "runtime": "onnx",
        "sha256": digest(b"graph"),
        "download_url": "https://models.test/model",
        "weights_url": "https://models.test/part1",
        "weights_sha256": digest(b"firstsecond"),
        "weights_parts": [
            {"url": "https://models.test/part1", "sha256": digest(b"first")},
            {"url": "https://models.test/part2", "sha256": digest(b"second")},
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payloads[request.url.path]))
    ) as client:
        await manager._download_payload_to_dir(
            client=client,
            model_meta=meta,
            staged_dir=str(tmp_path),
            progress=DownloadProgress(model_id="large", status="downloading", progress=0),
            progress_model_id="large",
            progress_start=0,
            progress_end=100,
        )
    assert (tmp_path / "model.onnx.data").read_bytes() == b"firstsecond"


@pytest.mark.asyncio
async def test_bad_weight_part_is_rejected_even_with_other_valid_files(manager, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: ["Bird"])
    meta = {
        "id": "large",
        "runtime": "onnx",
        "download_url": "https://models.test/model",
        "weights_url": "https://models.test/part",
        "sha256": hashlib.sha256(b"graph").hexdigest(),
        "weights_parts": [{"url": "https://models.test/part", "sha256": hashlib.sha256(b"expected").hexdigest()}],
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"graph" if request.url.path == "/model" else b"bad")
        )
    ) as client:
        with pytest.raises(RuntimeError, match="Checksum mismatch"):
            await manager._download_payload_to_dir(
                client=client,
                model_meta=meta,
                staged_dir=str(tmp_path),
                progress=DownloadProgress(model_id="large", status="downloading", progress=0),
                progress_model_id="large",
                progress_start=0,
                progress_end=100,
            )


def _install_family_variant(root, family_id, region, *, labels=False, config=True):
    variant_dir = root / family_id / region
    variant_dir.mkdir(parents=True)
    (variant_dir / "model.onnx").write_bytes(b"model")
    if labels:
        (variant_dir / "labels.txt").write_text("Bird\n")
    if config:
        (variant_dir / "model_config.json").write_text("{}")
    return variant_dir


@pytest.fixture
def catalogue_knows_every_artifact(monkeypatch):
    monkeypatch.setattr(
        "app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: ["Bird"] if sha else None
    )


@pytest.fixture
def selections(manager, monkeypatch):
    saved = []
    monkeypatch.setattr(manager, "_save_active_model_id", saved.append)
    return saved


@pytest.mark.parametrize("family_id", ["small_birds", "medium_birds"])
@pytest.mark.parametrize("region", ["eu", "na"])
def test_fresh_family_download_without_label_file_activates(
    manager, tmp_path, catalogue_knows_every_artifact, selections, family_id, region
):
    _install_family_variant(tmp_path, family_id, region)

    assert manager._activate_model_sync(family_id) is True
    assert selections == [family_id]


def test_family_install_from_before_its_sidecar_still_activates(
    manager, tmp_path, catalogue_knows_every_artifact, selections
):
    """Startup repairs a missing sidecar in the background; it must not block selection meanwhile."""
    _install_family_variant(tmp_path, "small_birds", "eu", labels=True, config=False)

    assert manager._activate_model_sync("small_birds") is True
    assert selections == ["small_birds"]


def test_family_variant_with_no_labels_anywhere_stays_inactive(manager, tmp_path, monkeypatch, selections):
    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: None)
    _install_family_variant(tmp_path, "small_birds", "eu")

    assert manager._activate_model_sync("small_birds") is False
    assert selections == []


@pytest.mark.asyncio
async def test_family_listing_reports_the_installed_variant_status(manager, tmp_path, monkeypatch):
    """The listing and activation must agree, or validation starts on a model activation will refuse."""
    _install_family_variant(tmp_path, "small_birds", "eu")

    monkeypatch.setattr(
        "app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: ["Bird"] if sha else None
    )
    ready = next(model for model in await manager.list_installed_models() if model.id == "small_birds")
    assert (ready.ready, ready.reason) == (True, "ready")

    monkeypatch.setattr("app.services.catalogue_labels.catalogue_labels_for_model", lambda sha: None)
    incomplete = next(model for model in await manager.list_installed_models() if model.id == "small_birds")
    assert (incomplete.ready, incomplete.reason) == (False, "labels_missing")

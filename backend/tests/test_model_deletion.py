"""Removing an installed model from disk.

Models are the largest thing YA-WAMF writes to `/data`: 3.8 GB across seven of
them on the reference deployment, with a single unused model at 1.2 GB. There
was no way to remove one. The only route was emptying the directory and
re-downloading whatever was still wanted.

Deleting is irreversible and the files are large, so the guards matter more than
the delete: never remove the model the classifier is using, never race a
download, and never let a model id escape the models directory.
"""

import os

import pytest

from app.services.model_manager import ModelDeletionError, model_manager


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    root = tmp_path / "models"
    root.mkdir()
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(root))
    return root


def _install(root, model_id: str, *, size_bytes: int = 1024) -> None:
    directory = root / model_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model.onnx").write_bytes(b"x" * size_bytes)
    (directory / "labels.txt").write_text("a\nb\n")


def test_deleting_a_model_removes_its_files(models_dir):
    _install(models_dir, "spare_model")
    freed = model_manager.delete_installed_model("spare_model", active_model_id="other")
    assert not (models_dir / "spare_model").exists()
    assert freed > 0


def test_the_active_model_is_never_deleted(models_dir):
    _install(models_dir, "in_use")
    with pytest.raises(ModelDeletionError, match="active"):
        model_manager.delete_installed_model("in_use", active_model_id="in_use")
    assert (models_dir / "in_use" / "model.onnx").exists()


def test_a_model_being_downloaded_is_never_deleted(models_dir, monkeypatch):
    _install(models_dir, "arriving")
    monkeypatch.setattr(model_manager, "get_download_status", lambda _id: object())
    with pytest.raises(ModelDeletionError, match="download"):
        model_manager.delete_installed_model("arriving", active_model_id="other")
    assert (models_dir / "arriving" / "model.onnx").exists()


def test_a_model_that_is_not_installed_reports_that_rather_than_succeeding(models_dir):
    with pytest.raises(ModelDeletionError, match="not installed"):
        model_manager.delete_installed_model("never_here", active_model_id="other")


@pytest.mark.parametrize(
    "model_id",
    [
        pytest.param("../escape", id="parent"),
        pytest.param("../../etc", id="parent_twice"),
        pytest.param("/etc", id="absolute"),
        pytest.param("nested/../../escape", id="sneaky"),
        pytest.param("", id="empty"),
        pytest.param(".", id="dot"),
    ],
)
def test_a_model_id_can_never_escape_the_models_directory(models_dir, model_id):
    with pytest.raises(ModelDeletionError):
        model_manager.delete_installed_model(model_id, active_model_id="other")


def test_a_region_variant_nested_under_its_family_can_be_deleted(models_dir):
    """Region variants live at `family/region`, so nesting must stay allowed."""
    _install(models_dir, "medium_birds/eu")
    _install(models_dir, "medium_birds/na")
    model_manager.delete_installed_model("medium_birds/eu", active_model_id="other")
    assert not (models_dir / "medium_birds" / "eu").exists()
    assert (models_dir / "medium_birds" / "na" / "model.onnx").exists()


def test_deleting_reports_how_much_space_it_reclaimed(models_dir):
    _install(models_dir, "chunky", size_bytes=50_000)
    freed = model_manager.delete_installed_model("chunky", active_model_id="other")
    assert freed >= 50_000


def test_an_empty_family_directory_is_tidied_up_after_its_last_variant_goes(models_dir):
    _install(models_dir, "small_birds/eu")
    model_manager.delete_installed_model("small_birds/eu", active_model_id="other")
    assert not (models_dir / "small_birds").exists()


def test_a_family_directory_survives_while_another_variant_remains(models_dir):
    _install(models_dir, "small_birds/eu")
    _install(models_dir, "small_birds/na")
    model_manager.delete_installed_model("small_birds/eu", active_model_id="other")
    assert (models_dir / "small_birds").exists()


def test_the_active_model_marker_is_not_treated_as_a_model(models_dir):
    (models_dir / "active_model.json").write_text("{}")
    with pytest.raises(ModelDeletionError, match="not installed"):
        model_manager.delete_installed_model("active_model.json", active_model_id="other")
    assert (models_dir / "active_model.json").exists()


def test_deleting_is_idempotent_enough_to_report_the_second_attempt_honestly(models_dir):
    _install(models_dir, "gone_twice")
    model_manager.delete_installed_model("gone_twice", active_model_id="other")
    with pytest.raises(ModelDeletionError, match="not installed"):
        model_manager.delete_installed_model("gone_twice", active_model_id="other")


def test_a_file_outside_the_models_directory_is_never_followed(models_dir, tmp_path):
    """A symlinked model directory must not delete the target it points at."""
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("important")
    os.symlink(outside, models_dir / "linked_model")
    with pytest.raises(ModelDeletionError):
        model_manager.delete_installed_model("linked_model", active_model_id="other")
    assert (outside / "keep.txt").exists()


@pytest.mark.asyncio
async def test_the_api_deletes_a_spare_model_and_reports_the_space(models_dir, monkeypatch):
    import httpx

    from app.main import app

    _install(models_dir, "spare_model", size_bytes=20_000)
    monkeypatch.setattr(model_manager, "active_model_id", "something_else")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/models/spare_model")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "deleted"
    assert body["bytes_freed"] >= 20_000
    assert "again" in body["message"].lower()
    assert not (models_dir / "spare_model").exists()


@pytest.mark.asyncio
async def test_the_api_refuses_to_delete_the_active_model(models_dir, monkeypatch):
    import httpx

    from app.main import app

    _install(models_dir, "in_use")
    monkeypatch.setattr(model_manager, "active_model_id", "in_use")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/models/in_use")

    assert response.status_code == 409
    assert "active" in response.json()["detail"].lower()
    assert (models_dir / "in_use" / "model.onnx").exists()


@pytest.mark.asyncio
async def test_the_api_reports_an_unknown_model_as_not_found(models_dir, monkeypatch):
    import httpx

    from app.main import app

    monkeypatch.setattr(model_manager, "active_model_id", "something_else")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/models/never_installed")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_the_api_addresses_a_nested_region_variant(models_dir, monkeypatch):
    import httpx

    from app.main import app

    _install(models_dir, "medium_birds/eu")
    _install(models_dir, "medium_birds/na")
    monkeypatch.setattr(model_manager, "active_model_id", "something_else")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/models/medium_birds/eu")

    assert response.status_code == 200
    assert not (models_dir / "medium_birds" / "eu").exists()
    assert (models_dir / "medium_birds" / "na" / "model.onnx").exists()

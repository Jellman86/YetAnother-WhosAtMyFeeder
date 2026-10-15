"""An advisory photo check preserves uncertainty and never makes review decisions."""

import math

import pytest

from app.services.garden_visitors import Taxon


def taxonomy():
    return [
        Taxon("generic-bird", "bird", ("aves", "", "", "", "")),
        Taxon("robin", "European robin", ("aves", "passeriformes", "muscicapidae", "erithacus", "rubecula")),
        Taxon("squirrel", "eastern gray squirrel", ("mammalia", "rodentia", "sciuridae", "sciurus", "carolinensis")),
        Taxon("human", "human", ("mammalia", "primates", "hominidae", "homo", "sapiens")),
        Taxon("blank", "blank", ("", "", "", "", "")),
        Taxon("vehicle", "vehicle", ("", "", "", "", "")),
        Taxon("animal", "animal", ("", "", "", "", "")),
    ]


def assess(scores, outputs=None):
    from app.services.garden_visitors import coarse_prediction_mass

    return coarse_prediction_mass(scores, outputs or taxonomy(), expected_width=7)


@pytest.mark.parametrize("output_index,group", [(59, "mammal"), (345, "bird"), (1473, "bird"), (1953, "bird")])
def test_shipped_output_mapping_preserves_taxa_without_english_common_names(output_index, group):
    import json

    from app.repositories.garden_catalog import read_shipped_package
    from app.services.garden_visitors import coarse_prediction_mass

    package = json.loads(read_shipped_package()[0])
    outputs = [Taxon(item["id"], item["name"], tuple(item["ranks"])) for item in package["outputs"]]
    assert outputs[output_index].name == ""
    scores = [0.0] * len(outputs)
    scores[output_index] = 1.0

    result = coarse_prediction_mass(scores, outputs)

    assert result.suggestion == group
    assert result.mass[group] == 1.0
    assert sum(result.mass.values()) == 1.0


def test_human_taxonomic_ranks_withhold_advice_without_a_common_name():
    outputs = taxonomy()
    outputs[3] = Taxon("human", "", ("mammalia", "primates", "hominidae", "homo", "sapiens"))

    result = assess([0.01, 0.01, 0.87, 0.1, 0.005, 0.003, 0.002], outputs)

    assert result.suggestion == "human_rejected"
    assert result.mass["human"] == 0.1
    assert result.mass["mammal"] == 0.87


def test_unnamed_unresolved_output_preserves_other_mass_without_claiming_presence():
    outputs = taxonomy()
    outputs[5] = Taxon("unresolved", "", ("", "", "", "", ""))

    result = assess([0.01, 0.01, 0.01, 0.001, 0.005, 0.961, 0.003], outputs)

    assert result.suggestion == "uncertain"
    assert result.mass["other"] == pytest.approx(0.964)


def test_non_string_common_name_remains_invalid():
    outputs = taxonomy()
    outputs[1] = Taxon("robin", None, outputs[1].ranks)
    with pytest.raises(ValueError):
        assess([0.5, 0.35, 0.04, 0.001, 0.1, 0.004, 0.005], outputs)


def test_bird_outputs_contribute_once_and_scores_keep_complete_mass():
    result = assess([0.5, 0.35, 0.04, 0.001, 0.1, 0.004, 0.005])
    assert result.suggestion == "bird"
    assert result.mass == pytest.approx({"bird": 0.85, "mammal": 0.04, "human": 0.001, "blank": 0.1, "other": 0.009})
    assert sum(result.mass.values()) == pytest.approx(1)


def test_human_output_is_not_counted_as_a_nonhuman_mammal():
    result = assess([0.01, 0.01, 0.87, 0.1, 0.005, 0.003, 0.002])
    assert result.suggestion == "human_rejected"
    assert result.mass["mammal"] == 0.87
    assert result.mass["human"] == 0.1


def test_human_winner_vetoes_even_below_significant_human_threshold():
    outputs = [Taxon(str(i), "other", ("", "", "", "", "")) for i in range(20)]
    outputs[0] = taxonomy()[3]
    from app.services.garden_visitors import coarse_prediction_mass

    result = coarse_prediction_mass([0.09] + [0.91 / 19] * 19, outputs, expected_width=20)
    assert result.suggestion == "human_rejected"


def test_blank_mass_is_not_renormalized_out_of_bird_uncertainty():
    result = assess([0.6, 0.1545, 0.05, 0.001, 0.1884, 0.003, 0.0031])
    assert result.suggestion == "uncertain"
    assert result.mass["bird"] == pytest.approx(0.7545)
    assert result.mass["blank"] == pytest.approx(0.1884)


def test_blank_or_unresolved_winner_does_not_claim_animal_absence():
    result = assess([0.01, 0.01, 0.01, 0.001, 0.95, 0.009, 0.01])
    assert result.suggestion == "uncertain"
    assert result.mass["blank"] == 0.95


def test_nonhuman_mammal_remains_only_a_model_suggestion():
    result = assess([0.005, 0.005, 0.98, 0.001, 0.004, 0.002, 0.003])
    assert result.suggestion == "mammal"


@pytest.mark.parametrize(
    "scores",
    [
        [0.5] * 7,
        [0] * 7,
        [0.5, 0.5],
        [1, 0, 0, 0, 0, 0, math.nan],
        [1, 0, 0, 0, 0, 0, math.inf],
        [1.1, -0.1, 0, 0, 0, 0, 0],
        [True, 0, 0, 0, 0, 0, 0],
    ],
)
def test_invalid_or_incomplete_probabilities_never_produce_a_favourable_suggestion(scores):
    with pytest.raises(ValueError):
        assess(scores)


def test_duplicate_output_identity_cannot_double_count_a_class():
    outputs = taxonomy()
    outputs[1] = outputs[0]
    with pytest.raises(ValueError):
        assess([0.5, 0.35, 0.04, 0.001, 0.1, 0.004, 0.005], outputs)


def test_incomplete_taxonomy_never_normalizes_only_the_known_outputs():
    with pytest.raises(ValueError):
        assess([0.5, 0.35, 0.04, 0.001, 0.1, 0.004, 0.005], taxonomy()[:-1])


@pytest.mark.parametrize(
    "output_index,suggestion", [(345, "bird"), (59, "mammal"), (916, "human_rejected"), (2246, "uncertain")]
)
def test_preview_worker_uses_the_real_shipped_taxonomy(tmp_path, monkeypatch, output_index, suggestion):
    import json
    from types import SimpleNamespace

    import numpy as np
    from PIL import Image

    from app.repositories.garden_catalog import read_shipped_package
    from app.services import garden_worker as worker

    encoded, package_sha = read_shipped_package()
    package = json.loads(encoded)
    model_sha = package["model_sha256"]["4.0.3a"]
    model = tmp_path / "model.onnx"
    model.write_bytes(b"runtime boundary fixture")
    image = tmp_path / "photo.jpg"
    Image.new("RGB", (10, 10), "blue").save(image)
    monkeypatch.setattr(worker, "digest", lambda path: model_sha)

    class Native:
        actual = ["CPUExecutionProvider"]

        def __init__(self, path, provider):
            assert path == model and provider == "cpu"
            self.session = SimpleNamespace(
                get_inputs=lambda: [SimpleNamespace(shape=[1, 480, 480, 3], type="tensor(float)")]
            )

        def infer(self, value):
            assert value.shape == (1, 480, 480, 3)
            logits = np.full((1, 2498), -100.0, dtype=np.float32)
            logits[0, output_index] = 10.0
            return logits

    monkeypatch.setattr(worker, "Runtime", Native)
    result = worker.identify(
        dict(
            model=str(model),
            model_sha256=model_sha,
            image=str(image),
            variant="4.0.3a",
            provider="cpu",
            box=[0, 0, 1, 1],
            mode="preview",
            package_sha256=package_sha,
        )
    )

    assert result["preview"]["suggestion"] == suggestion
    assert result["package_sha256"] == package_sha
    assert sum(result["preview"]["mass"].values()) == pytest.approx(1)


@pytest.mark.parametrize("variant", ["4.0.3b", "4.0.3a"])
def test_native_preview_is_an_explicit_checksum_bound_crop_mode(tmp_path, monkeypatch, variant):
    import hashlib
    import json
    import numpy as np
    from PIL import Image
    from app.services import garden_worker as worker
    from types import SimpleNamespace

    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    image = tmp_path / "photo.jpg"
    Image.new("RGB", (10, 10), "blue").save(image)
    outputs = [dict(id=str(i), name="other", ranks=["", "", "", "", ""]) for i in range(2498)]
    outputs[0] = dict(id="bird", name="bird", ranks=["aves", "", "", "", ""])
    package = dict(outputs=outputs, model_sha256={"4.0.3a": hashlib.sha256(b"model").hexdigest()})
    raw = json.dumps(package).encode()
    package_sha = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(worker, "read_shipped_package", lambda: (raw, package_sha), raising=False)

    class Native:
        actual = ["CPUExecutionProvider"]

        def __init__(self, path, provider):
            assert path == model and provider == "cpu"
            self.session = SimpleNamespace(
                get_inputs=lambda: [SimpleNamespace(shape=[1, 480, 480, 3], type="tensor(float)")]
            )

        def infer(self, value):
            assert value.shape == (1, 480, 480, 3)
            logits = np.full((1, 2498), -20.0, dtype=np.float32)
            logits[0, 0] = 2.0
            return logits

    monkeypatch.setattr(worker, "Runtime", Native)
    request = dict(
        model=str(model),
        model_sha256=package["model_sha256"]["4.0.3a"],
        image=str(image),
        variant=variant,
        provider="cpu",
        box=[0, 0, 1, 1],
        mode="preview",
        package_sha256=package_sha,
    )
    if variant == "4.0.3b":
        with pytest.raises(ValueError):
            worker.identify(request)
    else:
        result = worker.identify(request)
        assert "predictions" not in result
        assert result["preview"]["suggestion"] == "bird"
        assert result["preview"]["mass"]["bird"] > 0.99
        assert result["package_sha256"] == package_sha
        assert result["devices"] == ["CPUExecutionProvider"]
        request["package_sha256"] = "0" * 64
        with pytest.raises(ValueError):
            worker.identify(request)


def test_ordinary_native_identification_retains_its_existing_response(tmp_path, monkeypatch):
    import hashlib
    import numpy as np
    from PIL import Image
    from app.services import garden_worker as worker
    from types import SimpleNamespace

    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    image = tmp_path / "photo.jpg"
    Image.new("RGB", (10, 10), "blue").save(image)

    class Native:
        actual = ["CPUExecutionProvider"]

        def __init__(self, path, provider):
            self.session = SimpleNamespace(
                get_inputs=lambda: [SimpleNamespace(shape=[1, 480, 480, 3], type="tensor(float)")]
            )

        def infer(self, value):
            return np.arange(2498, dtype=np.float32)[None]

    monkeypatch.setattr(worker, "Runtime", Native)
    result = worker.identify(
        dict(
            model=str(model),
            model_sha256=hashlib.sha256(b"model").hexdigest(),
            image=str(image),
            variant="4.0.3b",
            provider="cpu",
            box=None,
        )
    )
    assert set(result) == {"predictions", "devices", "frame_size"}
    assert len(result["predictions"]) == 5
    assert result["predictions"][0][0] == 2497


@pytest.fixture
def check_context(tmp_path, monkeypatch):
    """A read-only boundary double refuses every repository mutation."""
    import hashlib
    import json
    from dataclasses import replace
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.config import settings
    from app.models.garden_motion import MotionSource
    from app.repositories.garden_repository import GardenCapture
    from app.services import garden_identification as module

    service = module.GardenIdentificationService()
    service.models = tmp_path
    service.model_path("4.0.3a").write_bytes(b"model")
    source = MotionSource(
        camera="patio",
        clip_start=100.0,
        clip_end=110.0,
        frame_index=1,
        frame_offset=1.0,
        clip_sha256="a" * 64,
        image_sha256=hashlib.sha256(b"photo").hexdigest(),
        detector_sha256="b" * 64,
        detector_score=0.8,
        box_xywh=(0.1, 0.2, 0.3, 0.4),
    )
    capture = GardenCapture(
        "c" * 32, None, "patio", "animal", "2026-10-15T12:00:00", "pending", True, None, motion_source=source
    )
    state = SimpleNamespace(capture=capture, image=b"photo", change=None)
    get = AsyncMock(side_effect=lambda _: state.capture)
    snapshot = AsyncMock(side_effect=lambda _: state.image)
    monkeypatch.setattr(module.garden_capture_service, "get", get)
    monkeypatch.setattr(module.garden_capture_service, "snapshot", snapshot)
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    monkeypatch.setattr(settings.location, "country", "Unknown country")
    monkeypatch.setattr(module, "garden_inference_pressure", lambda: {"live": {}, "background": {}})
    bundle = {"model_sha256": {"4.0.3a": hashlib.sha256(b"model").hexdigest()}, "package_sha256": "d" * 64}
    monkeypatch.setattr(service.catalog, "load", lambda: bundle)
    native = {
        "preview": {
            "suggestion": "bird",
            "human_winner": False,
            "mass": {"bird": 0.85, "mammal": 0.04, "human": 0.001, "blank": 0.1, "other": 0.009},
        },
        "devices": ["CPUExecutionProvider"],
        "frame_size": [640, 360],
        "package_sha256": bundle["package_sha256"],
    }
    process = AsyncMock()
    process.returncode = 0

    async def response(payload):
        request = json.loads(payload)
        assert request["mode"] == "preview" and request["variant"] == "4.0.3a"
        assert request["box"] == list(source.box_xywh) and request["package_sha256"] == bundle["package_sha256"]
        from pathlib import Path

        assert Path(request["image"]).read_bytes() == b"photo"
        if state.change:
            state.change()
        return b"GARDEN_RESULT:" + json.dumps(native).encode(), b""

    process.communicate = AsyncMock(side_effect=response)
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", launch)

    def no_repository():
        raise AssertionError("A photo check must not write/review repository state")

    monkeypatch.setattr(module, "get_db", no_repository)
    return SimpleNamespace(
        service=service, state=state, source=source, native=native, launch=launch, module=module, replace=replace
    )


@pytest.mark.asyncio
async def test_pending_photo_check_is_country_independent_advisory_without_repository_writes(check_context):
    from app.models.garden import GardenPhotoCheckRequest

    c = check_context
    result = await c.service.check_photo(
        c.state.capture.id, GardenPhotoCheckRequest(image_sha256=c.source.image_sha256)
    )
    assert result.suggestion == "bird"
    assert result.capture_id == c.state.capture.id and result.image_sha256 == c.source.image_sha256
    assert result.box_xywh == c.source.box_xywh and result.mass.bird == 0.85
    assert c.state.capture.status == "pending" and c.state.capture.identification is None
    assert not c.service.busy
    c.launch.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", ["confirmed", "dismissed", "photo", "camera", "model", "event", "hash", "bird", "busy"]
)
async def test_unsafe_or_unavailable_photo_check_does_not_launch_inference(check_context, monkeypatch, reason):
    from fastapi import HTTPException
    from app.config import settings
    from app.models.garden import GardenPhotoCheckRequest

    c = check_context
    image_hash = c.source.image_sha256
    if reason in ["confirmed", "dismissed"]:
        c.state.capture = c.replace(c.state.capture, status=reason)
    elif reason == "photo":
        c.state.capture = c.replace(c.state.capture, has_snapshot=False)
    elif reason == "camera":
        monkeypatch.setattr(settings.frigate, "garden_cameras", [])
    elif reason == "model":
        c.service.model_path("4.0.3a").unlink()
    elif reason == "event":
        c.state.capture = c.replace(c.state.capture, motion_source=None)
    elif reason == "hash":
        image_hash = "0" * 64
    elif reason == "bird":
        monkeypatch.setattr(c.module, "garden_inference_pressure", lambda: {"live": {"queued": 1}, "background": {}})
    else:
        c.service.busy = True
    with pytest.raises(HTTPException) as failure:
        await c.service.check_photo(c.state.capture.id, GardenPhotoCheckRequest(image_sha256=image_hash))
    assert failure.value.status_code in [404, 409]
    c.launch.assert_not_awaited()
    assert c.service.busy == (reason == "busy")


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["review", "restore_cycle", "privacy", "camera", "photo", "crop", "expiry"])
async def test_changed_context_discards_inflight_photo_check(check_context, monkeypatch, change):
    from fastapi import HTTPException
    from app.config import settings
    from app.models.garden import GardenPhotoCheckRequest
    from app.services import garden_motion_privacy

    c = check_context

    def mutate():
        if change == "review":
            c.state.capture = c.replace(c.state.capture, status="confirmed")
        elif change == "restore_cycle":
            c.service.invalidate_photo_checks()
        elif change == "privacy":
            garden_motion_privacy.invalidate()
        elif change == "camera":
            monkeypatch.setattr(settings.frigate, "garden_cameras", [])
        elif change == "photo":
            c.state.image = b"changed"
        elif change == "crop":
            c.state.capture = c.replace(
                c.state.capture, motion_source=c.source.model_copy(update={"box_xywh": (0.2, 0.2, 0.3, 0.4)})
            )
        else:
            c.state.capture = c.replace(c.state.capture, has_snapshot=False)

    c.state.change = mutate
    with pytest.raises(HTTPException) as failure:
        await c.service.check_photo(c.state.capture.id, GardenPhotoCheckRequest(image_sha256=c.source.image_sha256))
    assert failure.value.status_code in [404, 409]
    assert not c.service.busy


@pytest.mark.asyncio
async def test_human_advisory_returns_no_suggestion_without_blocking_the_capture(check_context):
    from app.models.garden import GardenPhotoCheckRequest

    c = check_context
    c.native["preview"] = {
        "suggestion": "human_rejected",
        "human_winner": True,
        "mass": {"bird": 0.01, "mammal": 0.08, "human": 0.9, "blank": 0.005, "other": 0.005},
    }
    result = await c.service.check_photo(
        c.state.capture.id, GardenPhotoCheckRequest(image_sha256=c.source.image_sha256)
    )
    assert result.suggestion == "unavailable" and result.mass is None
    assert c.state.capture.status == "pending"


@pytest.mark.asyncio
async def test_preview_and_identification_share_the_same_native_busy_state(check_context):
    from fastapi import HTTPException
    from app.models.garden import GardenIdentifyRequest, GardenPhotoCheckRequest

    c = check_context

    async def competing(payload):
        assert c.service.busy
        with pytest.raises(HTTPException) as failure:
            await c.service.identify(c.state.capture.id, GardenIdentifyRequest())
        assert failure.value.status_code == 409
        import json

        return b"GARDEN_RESULT:" + json.dumps(c.native).encode(), b""

    c.launch.return_value.communicate.side_effect = competing
    await c.service.check_photo(c.state.capture.id, GardenPhotoCheckRequest(image_sha256=c.source.image_sha256))
    assert not c.service.busy
    c.launch.assert_awaited_once()


def test_human_tied_for_top_probability_is_conservatively_unavailable():
    from app.services.garden_visitors import coarse_prediction_mass

    outputs = [Taxon(str(i), "other", ("", "", "", "", "")) for i in range(20)]
    outputs[1] = taxonomy()[3]
    result = coarse_prediction_mass([0.09, 0.09] + [0.82 / 18] * 18, outputs, expected_width=20)
    assert result.suggestion == "human_rejected"


def test_malformed_ranks_are_rejected_as_invalid_taxonomy():
    outputs = taxonomy()
    outputs[0] = Taxon("invalid", "invalid", None)
    with pytest.raises(ValueError):
        assess([0.5, 0.35, 0.04, 0.001, 0.1, 0.004, 0.005], outputs)


@pytest.mark.asyncio
@pytest.mark.parametrize("top_human", [False, True])
async def test_service_suppresses_human_evidence_independently_of_worker_suggestion(check_context, top_human):
    from app.models.garden import GardenPhotoCheckRequest

    c = check_context
    c.native["preview"] = {
        "suggestion": "uncertain",
        "human_winner": top_human,
        "mass": {"bird": 0.01, "mammal": 0.08, "human": 0.9, "blank": 0.005, "other": 0.005}
        if not top_human
        else {"bird": 0.4, "mammal": 0.3, "human": 0.09, "blank": 0.1, "other": 0.11},
    }
    result = await c.service.check_photo(
        c.state.capture.id, GardenPhotoCheckRequest(image_sha256=c.source.image_sha256)
    )
    assert result.suggestion == "unavailable" and result.mass is None


@pytest.mark.asyncio
async def test_unreaped_worker_quarantine_survives_a_second_temporary_cleanup_error(
    check_context, monkeypatch, tmp_path
):
    from app.models.garden import GardenPhotoCheckRequest
    from fastapi import HTTPException
    from unittest.mock import AsyncMock
    import shutil

    c = check_context
    temporary = tmp_path / "temporary-photo"
    temporary.mkdir()
    monkeypatch.setattr(c.module.tempfile, "mkdtemp", lambda **kwargs: str(temporary))
    monkeypatch.setattr(
        c.module, "supervise_worker", AsyncMock(side_effect=c.module.GardenCleanupFailed("worker did not stop"))
    )
    remove = shutil.rmtree

    def failed(*args, **kwargs):
        raise OSError("temporary cleanup failed")

    try:
        with monkeypatch.context() as scope:
            scope.setattr(shutil, "rmtree", failed)
            with pytest.raises(HTTPException) as failure:
                await c.service.check_photo(
                    c.state.capture.id, GardenPhotoCheckRequest(image_sha256=c.source.image_sha256)
                )
        assert failure.value.status_code == 503 and c.service.error
        with pytest.raises(HTTPException) as blocked:
            await c.service.check_photo(c.state.capture.id, GardenPhotoCheckRequest(image_sha256=c.source.image_sha256))
        assert blocked.value.status_code == 503
        assert c.launch.await_count == 1
    finally:
        remove(temporary)


def test_list_ranks_cannot_turn_a_human_into_a_nonhuman_mammal():
    outputs = taxonomy()
    outputs[3] = Taxon("human", "different common name", ["mammalia", "primates", "hominidae", "homo", "sapiens"])
    with pytest.raises(ValueError):
        assess([0.01, 0.01, 0.87, 0.1, 0.005, 0.003, 0.002], outputs)

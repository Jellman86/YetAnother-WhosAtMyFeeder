import asyncio
from pathlib import Path

from PIL import Image

from backend.scripts import eval_feeder_model_harness as harness


def test_load_manifest_reads_required_species_and_optional_context(tmp_path: Path) -> None:
    image_path = tmp_path / "snap.jpg"
    image_path.write_bytes(b"fake")
    manifest_path = tmp_path / "manifest.csv"
    manifest_path.write_text(
        "image_path,expected_common_name,expected_scientific_name,taxa_id,camera_name,source_kind,tags,notes\n"
        "snap.jpg,Blue Tit,Cyanistes caeruleus,14600,feeder,frigate_snapshot,\"small,side\",clear view\n",
        encoding="utf-8",
    )

    cases = harness.load_manifest(manifest_path)

    assert cases == [
        harness.FeederEvalCase(
            case_id="1",
            image_path=image_path,
            expected_common_name="Blue Tit",
            expected_scientific_name="Cyanistes caeruleus",
            taxa_id=14600,
            camera_name="feeder",
            source_kind="frigate_snapshot",
            tags=["small", "side"],
            notes="clear view",
        )
    ]


def test_score_predictions_flags_high_confidence_unknown_as_distinct_failure() -> None:
    case = harness.FeederEvalCase(
        case_id="case-1",
        image_path=Path("frame.jpg"),
        expected_common_name="Blue Tit",
    )

    scored = harness.score_predictions(
        case,
        predictions=[
            {"label": "Unknown Bird", "score": 0.97},
            {"label": "Blue Tit", "score": 0.42},
        ],
        high_confidence_unknown_threshold=0.90,
    )

    assert scored.top1_label == "Unknown Bird"
    assert scored.top1_score == 0.97
    assert scored.top1_correct is False
    assert scored.top3_correct is True
    assert scored.unknown_top1 is True
    assert scored.high_confidence_unknown is True
    assert scored.failure_kind == "high_confidence_unknown"


def test_aggregate_results_reports_accuracy_and_unknown_bug_counts() -> None:
    rows = [
        harness.FeederEvalResult(
            case_id="1",
            model_id="medium_birds",
            crop_mode="default",
            image_path="a.jpg",
            expected_label="Blue Tit",
            top1_label="Blue Tit",
            top1_score=0.91,
            top3_labels=["Blue Tit"],
            top1_correct=True,
            top3_correct=True,
            unknown_top1=False,
            high_confidence_unknown=False,
            failure_kind="",
            inference_ms=50.0,
            crop_diagnostics={},
        ),
        harness.FeederEvalResult(
            case_id="2",
            model_id="medium_birds",
            crop_mode="default",
            image_path="b.jpg",
            expected_label="Great Tit",
            top1_label="Unknown Bird",
            top1_score=0.96,
            top3_labels=["Unknown Bird", "Great Tit"],
            top1_correct=False,
            top3_correct=True,
            unknown_top1=True,
            high_confidence_unknown=True,
            failure_kind="high_confidence_unknown",
            inference_ms=70.0,
            crop_diagnostics={},
        ),
    ]

    summary = harness.aggregate_results(rows)

    model_summary = summary["models"]["medium_birds"]["crop_modes"]["default"]
    assert model_summary["total"] == 2
    assert model_summary["top1_accuracy"] == 0.5
    assert model_summary["top3_accuracy"] == 1.0
    assert model_summary["unknown_top1_rate"] == 0.5
    assert model_summary["high_confidence_unknown_count"] == 1


def test_settings_restored_after_evaluation_failure(monkeypatch) -> None:
    class _Settings:
        class classification:
            crop_model_overrides = {"medium_birds": "on"}
            crop_source_overrides = {"medium_birds": "high_quality"}

    class _Manager:
        active_model_id = "medium_birds"

        async def activate_model(self, model_id: str) -> bool:
            self.active_model_id = model_id
            return True

    settings = _Settings()
    manager = _Manager()

    async def _boom():
        async with harness.temporary_model_settings(
            model_manager=manager,
            settings=settings,
            model_id="small_birds",
            crop_mode="off",
            source_mode="standard",
        ):
            assert manager.active_model_id == "small_birds"
            assert settings.classification.crop_model_overrides["small_birds"] == "off"
            raise RuntimeError("stop")

    try:
        asyncio.run(_boom())
    except RuntimeError:
        pass

    assert manager.active_model_id == "medium_birds"
    assert settings.classification.crop_model_overrides == {"medium_birds": "on"}
    assert settings.classification.crop_source_overrides == {"medium_birds": "high_quality"}


def test_evaluate_case_uses_classifier_service_and_includes_crop_diagnostics(tmp_path: Path) -> None:
    image_path = tmp_path / "snap.jpg"
    Image.new("RGB", (8, 8), color="blue").save(image_path)
    case = harness.FeederEvalCase(
        case_id="case-1",
        image_path=image_path,
        expected_common_name="Blue Tit",
        camera_name="feeder",
        source_kind="unit_test",
    )

    class _Classifier:
        def _resolve_bird_classification_image(self, image, input_context=None):
            return image, {"crop_attempted": True, "crop_applied": False, "crop_reason": "no_candidate"}

        def classify(self, image, camera_name=None, model_id=None, input_context=None):
            return [{"label": "Blue Tit", "score": 0.88}]

    result = harness.evaluate_case(
        case,
        classifier=_Classifier(),
        model_id="medium_birds",
        crop_mode="default",
        high_confidence_unknown_threshold=0.9,
    )

    assert result.top1_correct is True
    assert result.crop_diagnostics["crop_reason"] == "no_candidate"

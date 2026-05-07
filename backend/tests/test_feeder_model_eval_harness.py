import asyncio
import csv
import sqlite3
from pathlib import Path

from PIL import Image

try:
    from backend.scripts import eval_feeder_model_harness as harness
except ModuleNotFoundError:
    from scripts import eval_feeder_model_harness as harness


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
            expected_aliases=[],
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


def test_score_predictions_reports_abstentions_beyond_top1() -> None:
    case = harness.FeederEvalCase(
        case_id="case-1",
        image_path=Path("frame.jpg"),
        expected_common_name="Blue Tit",
    )

    scored = harness.score_predictions(
        case,
        predictions=[
            {"label": "Great Tit", "score": 0.87},
            {"label": "No data", "score": 0.80},
            {"label": "Blue Tit", "score": 0.71},
        ],
        high_confidence_unknown_threshold=0.90,
    )

    assert scored.top1_correct is False
    assert scored.top3_correct is True
    assert scored.abstention_topk_count == 1
    assert scored.abstention_labels == ["No data"]
    assert scored.failure_kind == "wrong_species"


def test_score_predictions_matches_common_qualifier_variants_and_aliases() -> None:
    blue_tit = harness.FeederEvalCase(
        case_id="blue-tit",
        image_path=Path("frame.jpg"),
        expected_common_name="Blue Tit",
    )
    chaffinch = harness.FeederEvalCase(
        case_id="chaffinch",
        image_path=Path("frame.jpg"),
        expected_common_name="Chaffinch",
        expected_aliases=["Fringilla coelebs"],
    )

    assert harness.score_predictions(
        blue_tit,
        predictions=[{"label": "Eurasian blue tit", "score": 0.85}],
        high_confidence_unknown_threshold=0.9,
    ).top1_correct is True
    assert harness.score_predictions(
        chaffinch,
        predictions=[{"label": "Common chaffinch", "score": 0.89}],
        high_confidence_unknown_threshold=0.9,
    ).top1_correct is True


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
            abstention_topk_count=0,
            abstention_labels=[],
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
            abstention_topk_count=1,
            abstention_labels=["Unknown Bird"],
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
    assert model_summary["abstention_topk_count"] == 1
    assert model_summary["abstention_topk_rate"] == 0.5


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


def _create_detection_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE detections (
                id INTEGER PRIMARY KEY,
                detection_time TEXT NOT NULL,
                score REAL,
                display_name TEXT,
                category_name TEXT,
                frigate_event TEXT,
                camera_name TEXT,
                is_hidden INTEGER DEFAULT 0,
                manual_tagged INTEGER DEFAULT 0,
                scientific_name TEXT,
                common_name TEXT,
                taxa_id INTEGER
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _insert_detection(db_path: Path, **overrides) -> None:
    row = {
        "id": 1,
        "detection_time": "2026-05-07T08:00:00Z",
        "score": 0.91,
        "display_name": "Blue Tit",
        "category_name": "bird",
        "frigate_event": "event-1",
        "camera_name": "feeder",
        "is_hidden": 0,
        "manual_tagged": 1,
        "scientific_name": "Cyanistes caeruleus",
        "common_name": "Blue Tit",
        "taxa_id": 14600,
    }
    row.update(overrides)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO detections (
                id, detection_time, score, display_name, category_name, frigate_event,
                camera_name, is_hidden, manual_tagged, scientific_name, common_name, taxa_id
            ) VALUES (
                :id, :detection_time, :score, :display_name, :category_name, :frigate_event,
                :camera_name, :is_hidden, :manual_tagged, :scientific_name, :common_name, :taxa_id
            )
            """,
            row,
        )
        conn.commit()
    finally:
        conn.close()


def test_cached_snapshot_path_matches_media_cache_sanitizing(tmp_path: Path) -> None:
    cache_dir = tmp_path / "media_cache"
    snapshot_path = cache_dir / "snapshots" / "event..abc-123.jpg"
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(b"fake")

    assert harness.cached_snapshot_path(cache_dir, "event/../abc-123") == snapshot_path
    assert harness.cached_snapshot_path(cache_dir / "snapshots", "event/../abc-123") == snapshot_path
    assert harness.cached_snapshot_path(cache_dir, "../bad") is None


def test_generate_manifest_from_detections_writes_cached_verified_snapshots(tmp_path: Path) -> None:
    db_path = tmp_path / "speciesid.db"
    cache_dir = tmp_path / "media_cache"
    snapshot_path = cache_dir / "snapshots" / "event-1.jpg"
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(b"fake")
    _create_detection_db(db_path)
    _insert_detection(db_path)
    manifest_path = tmp_path / "manifest.csv"

    stats = harness.generate_manifest_from_detections(
        db_path=db_path,
        media_cache_dir=cache_dir,
        output_manifest=manifest_path,
        min_confidence=0.8,
        manual_only=True,
        limit=10,
    )

    assert stats == {"written": 1, "scanned": 1, "skipped_missing_snapshot": 0, "skipped_unlabeled": 0}
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "case_id": "event-1",
            "image_path": str(snapshot_path),
            "expected_common_name": "Blue Tit",
            "expected_scientific_name": "Cyanistes caeruleus",
            "expected_aliases": "",
            "taxa_id": "14600",
            "camera_name": "feeder",
            "source_kind": "cached_snapshot",
            "tags": "manual_tagged,score:0.910",
            "notes": "detection_time=2026-05-07T08:00:00Z;frigate_event=event-1",
        }
    ]


def test_generate_manifest_skips_unknown_and_missing_snapshots_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "speciesid.db"
    cache_dir = tmp_path / "media_cache"
    (cache_dir / "snapshots").mkdir(parents=True)
    (cache_dir / "snapshots" / "event-unknown.jpg").write_bytes(b"fake")
    _create_detection_db(db_path)
    _insert_detection(db_path, id=1, frigate_event="event-unknown", common_name="Unknown Bird", display_name="Unknown Bird")
    _insert_detection(db_path, id=2, frigate_event="event-missing", common_name="Great Tit", display_name="Great Tit")
    manifest_path = tmp_path / "manifest.csv"

    stats = harness.generate_manifest_from_detections(
        db_path=db_path,
        media_cache_dir=cache_dir,
        output_manifest=manifest_path,
        limit=10,
    )

    assert stats == {"written": 0, "scanned": 2, "skipped_missing_snapshot": 1, "skipped_unlabeled": 1}
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == []

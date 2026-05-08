"""Model evaluation harness — orchestrates a single eval run end to end.

Loads the species panel, fetches labeled images, then for every installed
classifier model: activates the model via ModelManager, runs the live
ClassifierService pipeline against each image, records latency / accuracy /
provider info, and writes summary / runtime / confusion / per-image artifacts
to disk. Image cache is removed at the end of the run.

Only one run is allowed at a time. State for the active run is held in the
service singleton; finished runs are read back off disk on request so history
survives a process restart.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import structlog
from PIL import Image

from app.config import settings
from app.services.broadcaster import broadcaster
from app.services.eval import sanity_checks
from app.services.eval.image_fetcher import (
    cleanup_image_dir,
    fetch_panel_images,
)
from app.services.eval.species_panel import (
    SpeciesEntry,
    build_panel,
)
from app.utils.canonical_species import is_unknown_species_label

log = structlog.get_logger()


def _eval_runs_root() -> Path:
    base = os.environ.get("YAWAMF_EVAL_RUNS_DIR", "/config/yawamf-eval")
    return Path(base)


SUMMARY_FILENAME = "summary.json"
RUNTIME_FILENAME = "runtime.json"
RESULTS_FILENAME = "results.jsonl"
CONFUSIONS_FILENAME = "confusions.csv"
IMAGES_SUBDIR = "images"


class ModelEvalAlreadyRunning(RuntimeError):
    pass


class ModelEvalRunner:
    """Single-run orchestrator. Module-level singleton ``model_eval_runner``."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._active_status: Optional[dict[str, Any]] = None

    # ---- Lifecycle ----

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def cancel(self) -> bool:
        """Cancel the active run, if any. Returns True if a run was cancelled."""
        task = self._task
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return True

    def active_status(self) -> Optional[dict[str, Any]]:
        return dict(self._active_status) if self._active_status else None

    async def start(
        self,
        *,
        include_per_image: bool = False,
        region_override: Optional[str] = None,
    ) -> str:
        if self.is_running():
            raise ModelEvalAlreadyRunning("a model evaluation run is already in progress")

        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_dir = _eval_runs_root() / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._active_status = {
            "run_id": run_id,
            "phase": "starting",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "progress": {"done": 0, "total": 0, "label": "starting"},
        }
        self._task = asyncio.create_task(
            self._run_async(
                run_id=run_id,
                run_dir=run_dir,
                include_per_image=include_per_image,
                region_override=region_override,
            ),
            name=f"model_eval:{run_id}",
        )
        return run_id

    # ---- Run history ----

    def list_runs(self) -> list[dict[str, Any]]:
        root = _eval_runs_root()
        if not root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for entry in sorted(root.iterdir(), reverse=True):
            if not entry.is_dir():
                continue
            summary_path = entry / SUMMARY_FILENAME
            row = {"run_id": entry.name, "status": "in_progress" if entry.name == (self._active_status or {}).get("run_id") and self.is_running() else "complete"}
            if summary_path.is_file():
                try:
                    row.update(_summary_brief(json.loads(summary_path.read_text())))
                except (OSError, json.JSONDecodeError):
                    pass
            rows.append(row)
        return rows[:20]

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        run_dir = _eval_runs_root() / _safe_run_id(run_id)
        summary_path = run_dir / SUMMARY_FILENAME
        if not summary_path.is_file():
            if self.is_running() and (self._active_status or {}).get("run_id") == run_id:
                # In-progress run that hasn't written its first partial
                # summary yet. Return a minimal envelope shaped like the
                # final summary so the frontend can render uniformly.
                status = self.active_status() or {}
                return {
                    "run_id": run_id,
                    "started_at": status.get("started_at"),
                    "finished_at": None,
                    "models": [],
                    "in_progress": True,
                    "active_status": status,
                }
            return None
        try:
            summary = json.loads(summary_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        runtime_path = run_dir / RUNTIME_FILENAME
        if runtime_path.is_file():
            try:
                summary["runtime"] = json.loads(runtime_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass
        return summary

    def artifact_path(self, run_id: str, filename: str) -> Optional[Path]:
        if filename not in {SUMMARY_FILENAME, RUNTIME_FILENAME, RESULTS_FILENAME, CONFUSIONS_FILENAME}:
            return None
        candidate = _eval_runs_root() / _safe_run_id(run_id) / filename
        return candidate if candidate.is_file() else None

    def delete_run(self, run_id: str) -> bool:
        run_dir = _eval_runs_root() / _safe_run_id(run_id)
        if not run_dir.is_dir():
            return False
        if self.is_running() and (self._active_status or {}).get("run_id") == run_id:
            return False
        shutil.rmtree(run_dir, ignore_errors=True)
        return True

    # ---- Internal: progress ----

    async def _emit(self, run_id: str, **fields: Any) -> None:
        payload = {"type": "model_eval_progress", "run_id": run_id}
        payload.update(fields)
        if self._active_status and self._active_status.get("run_id") == run_id:
            self._active_status.update({k: v for k, v in fields.items() if k != "type"})
        try:
            await broadcaster.broadcast(payload)
        except Exception as e:
            log.warning("model_eval_broadcast_failed", error=str(e))

    # ---- Internal: orchestration ----

    async def _run_async(
        self,
        *,
        run_id: str,
        run_dir: Path,
        include_per_image: bool,
        region_override: Optional[str],
    ) -> None:
        async with self._lock:
            try:
                await self._do_run(
                    run_id=run_id,
                    run_dir=run_dir,
                    include_per_image=include_per_image,
                    region_override=region_override,
                )
            except asyncio.CancelledError:
                log.info("model_eval_run_cancelled", run_id=run_id)
                await self._emit(run_id, phase="cancelled")
                raise
            except Exception as e:
                log.exception("model_eval_run_failed", run_id=run_id, error=str(e))
                await self._emit(run_id, phase="error", error=str(e))
                # Stamp a partial summary so the UI can see the failure.
                err_summary = {
                    "run_id": run_id,
                    "started_at": (self._active_status or {}).get("started_at"),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                    "models": [],
                }
                try:
                    (run_dir / SUMMARY_FILENAME).write_text(json.dumps(err_summary, indent=2))
                except OSError:
                    pass
            finally:
                self._task = None

    async def _do_run(
        self,
        *,
        run_id: str,
        run_dir: Path,
        include_per_image: bool,
        region_override: Optional[str],
    ) -> None:
        from app.services.classifier_service import get_classifier
        from app.services.model_manager import model_manager

        classifier_service = get_classifier()

        started_at = datetime.now(timezone.utc)
        await self._emit(run_id, phase="building_panel", progress={"done": 0, "total": 0, "label": "building species panel"})

        latitude = settings.location.latitude
        longitude = settings.location.longitude
        region_label = region_override or _region_label_from_settings()

        async with httpx.AsyncClient(timeout=30.0) as http:
            panel: list[SpeciesEntry] = await build_panel(
                latitude=latitude,
                longitude=longitude,
                client=http,
            )

        if not panel:
            raise RuntimeError("species panel is empty — taxonomy service unreachable?")

        # Fetch images
        images_root = run_dir / IMAGES_SUBDIR
        await self._emit(run_id, phase="fetching_images", progress={"done": 0, "total": len(panel), "label": "fetching images"})

        def _img_progress(done: int, total: int) -> None:
            asyncio.create_task(self._emit(run_id, phase="fetching_images", progress={"done": done, "total": total, "label": "fetching images"}))

        species_dicts = [{
            "taxa_id": e.taxa_id,
            "scientific_name": e.scientific_name,
            "common_name": e.common_name,
        } for e in panel]
        images_by_taxa = await fetch_panel_images(
            species=species_dicts,
            dest_root=images_root,
            max_per_species=3,
            concurrency=5,
            progress_cb=_img_progress,
        )

        usable_panel = [e for e in panel if images_by_taxa.get(e.taxa_id)]
        total_images = sum(len(images_by_taxa.get(e.taxa_id, [])) for e in usable_panel)
        image_sources_count = {"inat": 0, "wikimedia": 0}
        for items in images_by_taxa.values():
            for img in items:
                image_sources_count[img.source] = image_sources_count.get(img.source, 0) + 1

        if not usable_panel:
            raise RuntimeError("no species had any retrievable images; aborting")

        # Discover classifier models
        installed = await model_manager.list_installed_models()
        classifiers = [
            m for m in installed
            if m.ready and (
                m.metadata is None or (m.metadata.artifact_kind or "classifier") == "classifier"
            )
        ]
        if not classifiers:
            raise RuntimeError("no installed classifier models found")

        original_active = model_manager.active_model_id

        # Open per-image jsonl writer once if requested
        results_fp: Optional[io.TextIOWrapper] = None
        if include_per_image:
            results_fp = open(run_dir / RESULTS_FILENAME, "w", encoding="utf-8")

        runtime_payload: dict[str, dict[str, Any]] = {}
        model_summaries: list[dict[str, Any]] = []

        # Pre-build a panel label → taxa_id map. Lets us resolve predictions
        # without an iNat round-trip when the predicted label matches a
        # species that's already in our test set — which is the common case
        # since we only test on panel species.
        panel_label_to_taxa: dict[str, int] = {}
        for entry in usable_panel:
            for label in (entry.scientific_name, entry.common_name):
                norm = (label or "").strip().lower()
                if norm and norm not in panel_label_to_taxa:
                    panel_label_to_taxa[norm] = entry.taxa_id

        try:
            for model_idx, model in enumerate(classifiers):
                await self._emit(
                    run_id,
                    phase="evaluating",
                    progress={
                        "done": model_idx,
                        "total": len(classifiers),
                        "label": f"activating {model.id}",
                    },
                )
                activated = await model_manager.activate_model(model.id)
                if not activated:
                    log.warning("model_eval_activation_failed", model_id=model.id)
                    continue
                # Reload classifier_service to pick up the new active model.
                try:
                    if hasattr(classifier_service, "reload_bird_model"):
                        await classifier_service.reload_bird_model()
                except Exception as e:
                    log.warning("model_eval_reload_failed", model_id=model.id, error=str(e))
                    continue

                # Per-model state
                latencies: list[float] = []
                top1_hits = top3_hits = top5_hits = 0
                shared_core_top1 = shared_core_total = 0
                regional_top1 = regional_total = 0
                abstention_count = 0
                high_conf_unknown_count = 0
                processed = 0
                taxa_cache: dict[str, Optional[int]] = {}
                confusions: dict[tuple[int, int], dict[str, Any]] = {}

                for entry in usable_panel:
                    images = images_by_taxa.get(entry.taxa_id) or []
                    for fetched in images:
                        try:
                            with Image.open(fetched.local_path) as raw:
                                img = raw.convert("RGB")
                        except Exception as e:
                            log.warning("model_eval_image_open_failed", path=fetched.local_path, error=str(e))
                            continue

                        t0 = time.monotonic()
                        try:
                            results = await classifier_service.classify_async(img)
                        except Exception as e:
                            log.warning(
                                "model_eval_classify_failed",
                                model_id=model.id,
                                taxa_id=entry.taxa_id,
                                error=str(e),
                            )
                            continue
                        latency_ms = (time.monotonic() - t0) * 1000.0
                        latencies.append(latency_ms)

                        top5 = list(results or [])[:5]
                        # Resolve labels → taxa_ids using the offline panel
                        # map. Predictions that don't match any panel species
                        # keep taxa_id=None: they were never going to count
                        # toward an accuracy hit (we only score panel species)
                        # and the iNat round-trips per non-matching prediction
                        # were the dominant runtime cost in v1.
                        for r in top5:
                            label = (r.get("label") or "").strip()
                            r["taxa_id"] = (
                                _resolve_label_taxa(label, panel_label_to_taxa, taxa_cache)
                                if label else None
                            )

                        top1 = top5[0] if top5 else None
                        is_top1_unknown = bool(top1 and is_unknown_species_label(top1.get("label") or ""))
                        if is_top1_unknown:
                            abstention_count += 1
                            if float(top1.get("score") or 0.0) >= 0.90:
                                high_conf_unknown_count += 1

                        ids = [r.get("taxa_id") for r in top5]
                        if ids and ids[0] == entry.taxa_id:
                            top1_hits += 1
                        if entry.taxa_id in ids[:3]:
                            top3_hits += 1
                        if entry.taxa_id in ids[:5]:
                            top5_hits += 1
                        if entry.panel == "shared_core":
                            shared_core_total += 1
                            if ids and ids[0] == entry.taxa_id:
                                shared_core_top1 += 1
                        else:
                            regional_total += 1
                            if ids and ids[0] == entry.taxa_id:
                                regional_top1 += 1

                        # Confusion: only when top-1 was wrong and resolved
                        if top1 and ids and ids[0] != entry.taxa_id and ids[0] is not None and not is_top1_unknown:
                            key = (entry.taxa_id, ids[0])
                            cur = confusions.get(key)
                            if cur is None:
                                confusions[key] = {
                                    "expected_taxa": entry.taxa_id,
                                    "expected_common": entry.common_name,
                                    "predicted_taxa": ids[0],
                                    "predicted_common": top1.get("label") or "",
                                    "count": 1,
                                    "score_sum": float(top1.get("score") or 0.0),
                                }
                            else:
                                cur["count"] += 1
                                cur["score_sum"] += float(top1.get("score") or 0.0)

                        processed += 1

                        if results_fp is not None:
                            results_fp.write(json.dumps({
                                "model_id": model.id,
                                "taxa_id": entry.taxa_id,
                                "expected_common": entry.common_name,
                                "expected_scientific": entry.scientific_name,
                                "panel": entry.panel,
                                "image_path": fetched.local_path,
                                "image_source": fetched.source,
                                "image_url": fetched.source_url,
                                "top5": [
                                    {
                                        "label": r.get("label"),
                                        "score": float(r.get("score") or 0.0),
                                        "taxa_id": r.get("taxa_id"),
                                    } for r in top5
                                ],
                                "latency_ms": round(latency_ms, 2),
                                "correct_top1": ids[0] == entry.taxa_id if ids else False,
                            }) + "\n")

                # Per-model summary
                status = _classifier_status_snapshot(classifier_service)
                provider_info = _provider_summary(status)
                health_snapshot = _inference_health_for(status)
                summary = {
                    "model_id": model.id,
                    "active_provider": provider_info.get("active_provider"),
                    "requested_provider": provider_info.get("requested_provider"),
                    "device": provider_info.get("device"),
                    "ready": model.ready,
                    "ready_reason": model.reason,
                    "labels_file_present": _labels_file_present(model),
                    "model_config_present": _model_config_present(model),
                    "images_evaluated": processed,
                    "top1_accuracy": _safe_div(top1_hits, processed),
                    "top3_accuracy": _safe_div(top3_hits, processed),
                    "top5_accuracy": _safe_div(top5_hits, processed),
                    "abstention_rate": _safe_div(abstention_count, processed),
                    "high_confidence_unknown_rate": _safe_div(high_conf_unknown_count, processed),
                    "mean_latency_ms": round(statistics.fmean(latencies), 2) if latencies else None,
                    "p50_latency_ms": round(_percentile(latencies, 50), 2) if latencies else None,
                    "p95_latency_ms": round(_percentile(latencies, 95), 2) if latencies else None,
                    "startup_benchmark_ms": provider_info.get("startup_benchmark_ms"),
                    "latency_drift_ratio": _drift_ratio(latencies, provider_info.get("startup_benchmark_ms")),
                    "shared_core_top1": _safe_div(shared_core_top1, shared_core_total),
                    "regional_top1": _safe_div(regional_top1, regional_total),
                    "inference_health_verdict": health_snapshot.get("verdict"),
                    "warnings": [],
                }
                summary["warnings"] = sanity_checks.collect(summary, region_label=region_label)
                model_summaries.append(summary)

                runtime_payload[model.id] = {
                    **provider_info,
                    "measured_mean_ms": summary["mean_latency_ms"],
                    "measured_p95_ms": summary["p95_latency_ms"],
                    "drift_factor": summary["latency_drift_ratio"],
                    "inference_health": health_snapshot,
                    "ready": model.ready,
                    "ready_reason": model.reason,
                    "warnings": summary["warnings"],
                }

                # Confusion CSV — append per model so partial runs leave usable data
                _append_confusions_csv(run_dir / CONFUSIONS_FILENAME, model.id, confusions)
                # Persist partial summary after each model
                _write_summary(run_dir, _build_summary_envelope(
                    run_id=run_id,
                    started_at=started_at,
                    finished_at=None,
                    panel=usable_panel,
                    total_images=total_images,
                    image_sources=image_sources_count,
                    region_label=region_label,
                    models=model_summaries,
                ))
                _write_runtime(run_dir, runtime_payload)
        finally:
            if results_fp is not None:
                results_fp.close()
            # Restore original active model
            if original_active and original_active != model_manager.active_model_id:
                try:
                    await model_manager.activate_model(original_active)
                    if hasattr(classifier_service, "reload_bird_model"):
                        await classifier_service.reload_bird_model()
                except Exception as e:
                    log.warning("model_eval_restore_failed", model_id=original_active, error=str(e))
            # Cleanup image cache
            try:
                cleanup_image_dir(images_root)
            except Exception as e:
                log.warning("model_eval_cleanup_failed", error=str(e))

        finished_at = datetime.now(timezone.utc)
        envelope = _build_summary_envelope(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            panel=usable_panel,
            total_images=total_images,
            image_sources=image_sources_count,
            region_label=region_label,
            models=model_summaries,
        )
        _write_summary(run_dir, envelope)
        _write_runtime(run_dir, runtime_payload)
        await self._emit(run_id, phase="complete", progress={
            "done": len(classifiers),
            "total": len(classifiers),
            "label": "complete",
        })


# ---------- helpers ----------

def _safe_div(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator, 4)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(round((pct / 100.0) * (len(s) - 1)))
    return s[max(0, min(idx, len(s) - 1))]


def _drift_ratio(latencies: list[float], baseline_ms: Any) -> Optional[float]:
    try:
        baseline = float(baseline_ms or 0.0)
    except (TypeError, ValueError):
        return None
    if not latencies or baseline <= 0:
        return None
    return round(statistics.fmean(latencies) / baseline, 3)


def _safe_run_id(run_id: str) -> str:
    cleaned = "".join(c for c in str(run_id or "") if c.isalnum() or c in "-_")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"invalid run id: {run_id!r}")
    return cleaned


def _summary_brief(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "started_at": summary.get("started_at"),
        "finished_at": summary.get("finished_at"),
        "duration_seconds": summary.get("duration_seconds"),
        "model_count": len(summary.get("models") or []),
        "total_species": (summary.get("test_set") or {}).get("total_species"),
        "total_images": (summary.get("test_set") or {}).get("total_images"),
        "region": (summary.get("test_set") or {}).get("region"),
        "error": summary.get("error"),
    }


def _build_summary_envelope(
    *,
    run_id: str,
    started_at: datetime,
    finished_at: Optional[datetime],
    panel: list[SpeciesEntry],
    total_images: int,
    image_sources: dict[str, int],
    region_label: Optional[str],
    models: list[dict[str, Any]],
) -> dict[str, Any]:
    shared_core = sum(1 for e in panel if e.panel == "shared_core")
    return {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat() if finished_at else None,
        "duration_seconds": round((finished_at - started_at).total_seconds(), 2) if finished_at else None,
        "test_set": {
            "shared_core_species": shared_core,
            "regional_species": len(panel) - shared_core,
            "total_species": len(panel),
            "images_per_species": 3,
            "total_images": total_images,
            "region": region_label,
            "image_sources": image_sources,
        },
        "models": models,
        "config_snapshot": {
            "min_confidence": getattr(settings.classification, "min_confidence", None),
            "trust_frigate_sublabel": getattr(settings.classification, "trust_frigate_sublabel", None),
            "personalized_rerank_enabled": getattr(settings.classification, "personalized_rerank_enabled", None),
        },
    }


def _write_summary(run_dir: Path, payload: dict[str, Any]) -> None:
    (run_dir / SUMMARY_FILENAME).write_text(json.dumps(payload, indent=2, default=str))


def _write_runtime(run_dir: Path, payload: dict[str, dict[str, Any]]) -> None:
    (run_dir / RUNTIME_FILENAME).write_text(json.dumps(payload, indent=2, default=str))


def _append_confusions_csv(
    path: Path,
    model_id: str,
    confusions: dict[tuple[int, int], dict[str, Any]],
) -> None:
    if not confusions:
        return
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "model_id", "expected_taxa", "expected_common",
                "predicted_taxa", "predicted_common", "count", "mean_score",
            ])
        ordered = sorted(confusions.values(), key=lambda r: r["count"], reverse=True)
        for row in ordered[:50]:
            mean_score = row["score_sum"] / row["count"] if row["count"] else 0.0
            writer.writerow([
                model_id,
                row["expected_taxa"],
                row["expected_common"],
                row["predicted_taxa"],
                row["predicted_common"],
                row["count"],
                f"{mean_score:.3f}",
            ])


def _resolve_label_taxa(
    label: str,
    panel_label_to_taxa: dict[str, int],
    taxa_cache: dict[str, Optional[int]],
) -> Optional[int]:
    """Resolve a classifier label to a taxa_id using cheap, offline matches.

    Tries: cached lookup, panel exact match, panel match after stripping
    a trailing parenthetical (handles labels like "Cassin's Finch (Adult Male)").
    Returns None if nothing matched — caller can then fall back to iNat.
    """
    if label in taxa_cache:
        return taxa_cache[label]
    norm = label.strip().lower()
    if norm in panel_label_to_taxa:
        return panel_label_to_taxa[norm]
    if "(" in label:
        head = label.split("(", 1)[0].strip().lower()
        if head and head in panel_label_to_taxa:
            return panel_label_to_taxa[head]
    return None


def _classifier_status_snapshot(classifier_service: Any) -> dict[str, Any]:
    """Capture a single classifier-service status snapshot. Empty dict on failure."""
    try:
        getter = getattr(classifier_service, "get_status", None)
        if callable(getter):
            snap = getter()
            if isinstance(snap, dict):
                return snap
    except Exception as e:
        log.warning("model_eval_status_failed", error=str(e))
    return {}


def _provider_summary(status: dict[str, Any]) -> dict[str, Any]:
    """Pull provider/device/benchmark info out of a classifier_service.get_status()."""
    active_provider = status.get("active_provider")
    backend = status.get("inference_backend")
    requested = status.get("selected_provider")
    benchmarks = status.get("runtime_benchmarks") or {}
    benchmark_key = f"{str(backend or 'unknown').strip().lower()}/{str(active_provider or 'unknown').strip().lower()}"
    bench = benchmarks.get(benchmark_key) if isinstance(benchmarks, dict) else None
    candidate_seconds = None
    if isinstance(bench, dict):
        cand = bench.get("candidate_latency_seconds")
        if isinstance(cand, (int, float)) and cand > 0:
            candidate_seconds = float(cand)
    return {
        "active_provider": active_provider,
        "requested_provider": requested,
        "inference_backend": backend,
        "device": status.get("openvino_model_compile_device"),
        "fallback_reason": status.get("fallback_reason"),
        "startup_benchmark_ms": round(candidate_seconds * 1000.0, 2) if candidate_seconds else None,
    }


def _inference_health_for(status: dict[str, Any]) -> dict[str, Any]:
    """Pull the inference_health snapshot out of get_status() with sane defaults."""
    snap = status.get("inference_health") or {}
    return {
        "verdict": snap.get("verdict") or "unknown",
        "runtimes": snap.get("runtimes") or {},
    }


def _labels_file_present(model: Any) -> bool:
    try:
        return Path(getattr(model, "labels_path", "") or "").is_file()
    except Exception:
        return False


def _model_config_present(model: Any) -> bool:
    try:
        path = Path(getattr(model, "path", "") or "")
        if not path.is_file():
            return False
        return (path.parent / "model_config.json").is_file()
    except Exception:
        return False


def _region_label_from_settings() -> Optional[str]:
    # eBird settings carry a region code if configured.
    region = getattr(getattr(settings, "ebird", None), "region", None)
    return str(region) if region else None


model_eval_runner = ModelEvalRunner()

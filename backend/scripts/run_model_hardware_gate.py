"""Local-only, fail-closed model/provider validation with disposable native children.

Uses installed read-only weights and production inference/preprocessing. Never
changes active application settings, detection history or provider eligibility.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
PROVIDERS = ("cpu", "intel_cpu", "intel_npu", "intel_gpu", "cuda")


def discover_models(root: Path, registry: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    models = {}
    for entry in registry:
        model_id = entry["id"]
        variants = entry.get("region_variants") or {None: {}}
        for region, variant in variants.items():
            artifact = f"{model_id}/{region}" if region else model_id
            folder = root / artifact
            if any((folder / filename).is_file() for filename in ("model.onnx", "model.tflite")):
                models[artifact] = entry | variant
    return models


def validate_report(report: dict[str, Any], *, image_count: int, crop: bool) -> bool:
    if image_count < 1:
        return False
    if not report.get("compile", {}).get("ok") or report.get("runtime_error"):
        return False
    summary = report.get("output_summary") or {}
    count = summary.get("element_count", 0)
    if not count or summary.get("finite_count") != count:
        return False
    if any(summary.get(key) for key in ("nan_count", "pos_inf_count", "neg_inf_count")):
        return False
    if crop:
        rows = report.get("per_image_detections") or []
        return bool(
            report.get("real_images_evaluated") == image_count
            and report.get("negative_images_evaluated") == 3
            and len(rows) == image_count + 3
            and len({row["image"] for row in rows}) == len(rows)
        )
    rows = report.get("per_image_top_indices") or []
    minimum, maximum = summary.get("finite_min"), summary.get("finite_max")
    return bool(
        minimum is not None
        and maximum is not None
        and 0 <= minimum <= maximum <= 1
        and len(rows) == image_count
        and all(rows)
    )


def compare_reports(baseline: dict[str, Any], report: dict[str, Any], *, crop: bool) -> dict[str, Any]:
    if crop:
        from app.services.model_validation import _compare_crop_detections

        return _compare_crop_detections(baseline["per_image_detections"], report["per_image_detections"])
    expected = baseline.get("per_image_top_indices") or []
    actual = report.get("per_image_top_indices") or []
    complete = bool(expected and len(expected) == len(actual) and all(expected) and all(actual))
    matches = sum(left[0] == right[0] for left, right in zip(expected, actual) if left and right)
    overlaps = [len(set(left) & set(right)) for left, right in zip(expected, actual)]
    stable_top = complete and all(overlap >= min(4, len(left)) for overlap, left in zip(overlaps, expected))
    same_output_size = baseline.get("output_summary", {}).get("element_count") == report.get("output_summary", {}).get(
        "element_count"
    )
    return {
        "agrees": bool(stable_top and same_output_size and matches == len(expected)),
        "images": len(expected),
        "top1_matches": matches,
        "top5_overlaps": overlaps,
    }


def run_child(command: list[str], output: Path, *, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {"status": "spawn_failed", "exit_code": None}
    try:
        with (output / "process.log").open("w") as log:
            process = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name == "posix"
            )
            try:
                result["exit_code"] = process.wait(timeout=timeout)
                result["status"] = "completed" if process.returncode == 0 else "crashed"
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                if process.poll() is None:
                    try:
                        if os.name == "posix":
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass
                process.wait()
                result.update(
                    status="timeout" if isinstance(exc, subprocess.TimeoutExpired) else "interrupted",
                    exit_code=process.returncode,
                )
        if result["status"] == "completed":
            try:
                result["report"] = json.loads((output / "probe.json").read_text())
                if not isinstance(result["report"], dict):
                    result["status"] = "invalid_report"
            except FileNotFoundError:
                result["status"] = "missing_report"
            except (ValueError, OSError):
                result["status"] = "invalid_report"
    except OSError as exc:
        result["error"] = str(exc)
    result["seconds"] = round(time.monotonic() - started, 3)
    (output / "result.json").write_text(json.dumps(result, indent=2))
    return result


def isolated_environment(root: Path) -> None:
    preserved = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LD_LIBRARY_PATH", "SYSTEMROOT", "WINDIR", "LANG", "HOME"}
    }
    os.environ.clear()
    os.environ.update(preserved)
    for key in ("DATA_DIR", "CONFIG_DIR", "MODEL_DIR", "MEDIA_CACHE_DIR", "OPENVINO_CACHE_DIR", "TMPDIR"):
        path = root / key.lower()
        path.mkdir()
        os.environ[key] = str(path)
    os.environ.update(
        CONFIG_FILE=str(root / "config.json"),
        DB_PATH=str(root / "detections.db"),
        SPECIES_CATALOG_PATH=str(root / "catalog.db"),
        PYTHONPATH=str(BACKEND),
        SYSTEM__TRUSTED_PROXY_HOSTS='["127.0.0.1"]',
        OMP_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        TF_NUM_INTRAOP_THREADS="2",
        TF_NUM_INTEROP_THREADS="1",
        TF_CPP_MIN_LOG_LEVEL="2",
    )
    sys.path.insert(0, str(BACKEND))


def probe_exact_artifact(root: Path, models: Path, artifact: str, provider: str, images: list[str]) -> dict[str, Any]:
    source = models / artifact
    target = Path(os.environ["MODEL_DIR"]) / artifact
    target.mkdir(parents=True)
    for item in source.iterdir():
        if item.is_file():
            if item.suffix in {".json", ".txt"}:
                shutil.copyfile(item, target / item.name)
            elif item.name in {"model.onnx", "model.onnx.data", "model.tflite"}:
                (target / item.name).symlink_to(item.resolve())
    model_id, _, region = artifact.partition("/")
    (Path(os.environ["MODEL_DIR"]) / "active_model.json").write_text(json.dumps({"model_id": model_id}))
    (root / "config.json").write_text(
        json.dumps(
            {
                "classification": {
                    "model": model_id,
                    "inference_provider": provider,
                    "regional_model_override": region or "auto",
                }
            }
        )
    )
    from app.services.model_manager import model_manager

    model_manager.active_model_id = model_id
    if model_id.startswith("bird_crop_detector"):
        from scripts.probe_crop_model_provider import probe_provider

        return probe_provider(provider, model_id, images)
    from scripts.probe_bird_model_provider import probe_provider

    original = model_manager.get_active_model_spec

    def exact_spec() -> dict[str, Any]:
        spec = original(override=region or "auto")
        spec["model_path"] = str(Path(spec["model_path"]).resolve())
        if Path(spec["model_path"]).parent != source.resolve():
            raise ValueError("Selected model does not resolve to the requested artifact")
        return spec

    model_manager.get_active_model_spec = exact_spec
    return probe_provider(provider, images, expected_model_id=model_id)


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_images(paths: list[str]) -> None:
    from PIL import Image

    # The exploratory probe substitutes a synthetic image if none decode. A
    # release gate must reject that rather than count it as a real-image pass.
    for path in paths:
        with Image.open(path) as source:
            source.convert("RGB").load()


def gate_passed(results: list[dict[str, Any]], requested: list[str]) -> bool:
    exercised = {row["provider"] for row in results if row["status"] == "passed"}
    return bool(
        results
        and set(requested) <= exercised
        and all(row["status"] in {"passed", "not_applicable"} for row in results)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", required=True, type=Path)
    parser.add_argument(
        "--output", required=True, type=Path, help="New directory; existing evidence is never overwritten"
    )
    parser.add_argument("--provider", action="append", choices=PROVIDERS)
    parser.add_argument("--model", action="append", help="Exact installed artifact, e.g. medium_birds/eu")
    parser.add_argument("--image", action="append", type=Path)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scratch-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    models = args.models_dir.resolve(strict=True)
    images = (
        args.image
        if args.image is not None
        else sorted((BACKEND / "tests/fixtures/crop_detector_images").rglob("*.jpg"))
    )
    if not images or args.repeat < 1 or args.timeout <= 0:
        parser.error("Real images, positive repeat count and positive timeout are required")
    image_paths = [str(path.resolve(strict=True)) for path in images]
    if len(set(image_paths)) != len(image_paths):
        parser.error("Duplicate image inputs are not allowed")
    validate_images(image_paths)
    output = args.output.resolve()
    if not args.child:
        output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="yawamf-hardware-", dir=args.scratch_root) as directory:
        root = Path(directory)
        isolated_environment(root)
        from app.services.model_manager import REMOTE_REGISTRY

        installed = discover_models(models, REMOTE_REGISTRY)
        selected = args.model or sorted(installed)
        if not selected or any(artifact not in installed for artifact in selected):
            parser.error("No matching installed registry artifacts; unknown/retired models cannot validate a fallback")
        if args.child:
            report = probe_exact_artifact(root, models, selected[0], args.provider[0], image_paths)
            (output / "probe.json").write_text(json.dumps(report, indent=2))
            return 0
        packages = {}
        for name in ("openvino", "onnxruntime", "onnxruntime-gpu", "numpy"):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                pass
        manifest: dict[str, Any] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": packages,
            "images": [{"name": Path(path).name, "sha256": file_hash(Path(path))} for path in image_paths],
            "results": [],
            "artifacts": {},
        }
        providers = list(dict.fromkeys(["cpu", *(args.provider or ["cpu"])]))
        for artifact in selected:
            manifest["artifacts"][artifact] = {
                path.name: file_hash(path)
                for path in sorted((models / artifact).iterdir())
                if path.is_file()
                and path.name in {"model.onnx", "model.onnx.data", "model.tflite", "model_config.json", "labels.txt"}
            }
            entry = installed[artifact]
            supported = set(entry.get("supported_inference_providers") or ["cpu"])
            candidates = set(entry.get("candidate_inference_providers") or [])
            crop = artifact.startswith("bird_crop_detector")
            baseline = None
            for provider in providers:
                if provider != "cpu" and provider not in supported | candidates:
                    manifest["results"].append(
                        {
                            "artifact": artifact,
                            "provider": provider,
                            "status": "not_applicable",
                            "reason": "Provider absent from model registry contract",
                        }
                    )
                    continue
                for repeat in range(args.repeat):
                    run_dir = output / f"{artifact.replace('/', '--')}-{provider}-{repeat}"
                    run_dir.mkdir()
                    command = [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--child",
                        "--models-dir",
                        str(models),
                        "--output",
                        str(run_dir),
                        "--model",
                        artifact,
                        "--provider",
                        provider,
                    ]
                    for path in image_paths:
                        command.extend(["--image", path])
                    command.extend(["--scratch-root", str(root)])
                    result = run_child(command, run_dir, timeout=args.timeout)
                    report = result.get("report") or {}
                    result.update(
                        artifact=artifact, provider=provider, repeat=repeat, declared_support=provider in supported
                    )
                    if result["status"] == "completed":
                        try:
                            valid = validate_report(report, image_count=len(image_paths), crop=crop)
                            if valid and baseline is None and provider == "cpu":
                                baseline = report
                            result["comparison"] = (
                                compare_reports(baseline, report, crop=crop)
                                if valid and baseline
                                else {"agrees": False}
                            )
                        except (TypeError, ValueError, KeyError, AttributeError) as exc:
                            valid = False
                            result["comparison"] = {"agrees": False}
                            result["error"] = f"Malformed probe: {exc}"
                        result["status"] = "passed" if valid and result["comparison"]["agrees"] else "failed"
                    manifest["results"].append(result)
                    (run_dir / "result.json").write_text(json.dumps(result, indent=2))
                    (output / "summary.json").write_text(json.dumps(manifest, indent=2))
                    print(
                        json.dumps({key: result[key] for key in ("artifact", "provider", "repeat", "status")}),
                        flush=True,
                    )
                    if result["status"] == "interrupted":
                        return 130
        (output / "summary.json").write_text(json.dumps(manifest, indent=2))
        results = manifest["results"]
        return 0 if gate_passed(results, providers) else 1


if __name__ == "__main__":
    raise SystemExit(main())

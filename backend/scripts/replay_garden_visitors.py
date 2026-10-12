"""Offline Garden animals prototype (#641); never connects to the application.

Consumes local retained media and checksum-bound JSON taxonomy/model metadata.
The new private output directory is a diagnostic report, not production history.
Native inference must run under an external process/resource watchdog.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterator

import numpy as np
from PIL import Image

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from app.services.garden_visitors import GardenPolicy, Taxon, decide_prediction, route_event  # noqa: E402
from app.services.garden_model_runtime import digest, preprocess, execution_devices, Runtime  # noqa: E402,F401


def media_path(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Media must be a regular file within the input folder")
    return path


def unique_inputs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not 1 <= len(records) <= 256:
        raise ValueError("Replay requires 1 to 256 inputs")
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        identity = record.get("id", "")
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", identity):
            raise ValueError("Invalid replay input identifier")
        if identity in unique and unique[identity] != record:
            raise ValueError("Conflicting metadata for duplicate input identifier")
        if not isinstance(record.get("camera"), str) or not isinstance(record.get("label"), str):
            raise ValueError("Every input requires a camera and label")
        if record.get("mode", "event") not in {"event", "scan"}:
            raise ValueError("Unknown replay mode")
        unique[identity] = record
    return list(unique.values())


def write_report(path: Path, report: dict[str, Any]) -> None:
    encoded = json.dumps(report, indent=2, allow_nan=False).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(encoded)


def sample_positions(duration: float, count: int) -> list[float]:
    if not math.isfinite(duration) or not 0 < duration <= 3600 or not 1 <= count <= 16:
        raise ValueError("Video needs a finite duration up to one hour and 1 to 16 samples")
    return np.linspace(0, max(0, duration - 0.1), count).tolist()


def frames(path: Path, count: int) -> Iterator[tuple[int, Image.Image]]:
    if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        with Image.open(path) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError("Image exceeds prototype pixel limit")
            yield 0, image.convert("RGB")
        return
    if path.suffix.lower() not in {".mp4", ".mkv", ".mov", ".avi", ".webm"}:
        raise ValueError("Unsupported local recording format")
    import cv2

    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            raise ValueError("Recording has no valid frame rate")
        duration = capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps
        for position in sample_positions(duration, count):
            capture.set(cv2.CAP_PROP_POS_MSEC, position * 1000)
            ok, pixels = capture.read()
            if not ok:
                raise ValueError("Could not decode a requested recording frame")
            if pixels.shape[0] * pixels.shape[1] > 16_000_000:
                raise ValueError("Recording exceeds prototype pixel limit")
            decoded_position = capture.get(cv2.CAP_PROP_POS_FRAMES)
            if not math.isfinite(decoded_position) or decoded_position < 1:
                raise ValueError("Decoder did not identify the returned frame")
            yield int(decoded_position) - 1, Image.fromarray(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
    finally:
        capture.release()


def decode_detector(output: np.ndarray, size: int, threshold: float = 0.4) -> list[tuple[str, float, tuple]]:
    import cv2

    if output.ndim != 3 or output.shape[0:2] != (1, 7) or not np.isfinite(output).all():
        raise ValueError("Expected a finite raw three-class MegaDetector head")
    raw = output[0].T
    if np.any(raw[:, 4:] < 0) or np.any(raw[:, 4:] > 1):
        raise ValueError("Detector class scores must be probabilities")
    candidates = []
    for category, label in enumerate(("animal", "person", "vehicle")):
        selected = raw[raw[:, 4 + category] >= threshold]
        if not len(selected):
            continue
        boxes = np.column_stack(
            (selected[:, 0] - selected[:, 2] / 2, selected[:, 1] - selected[:, 3] / 2, selected[:, 2:4])
        )
        scores = selected[:, 4 + category]
        keep = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), threshold, 0.45)
        for index in np.asarray(keep).reshape(-1):
            x, y, w, h = boxes[index] / size
            left, top, right, bottom = (
                max(0.0, float(x)),
                max(0.0, float(y)),
                min(1.0, float(x + w)),
                min(1.0, float(y + h)),
            )
            if right > left and bottom > top:
                candidates.append((label, float(scores[index]), (left, top, right - left, bottom - top)))
    return sorted(candidates, key=lambda item: -item[1])


def load_taxon(value: dict[str, Any]) -> Taxon:
    ranks = tuple(value["ranks"])
    if len(ranks) != 5 or not all(isinstance(part, str) for part in ranks):
        raise ValueError("Taxonomy needs five ordered ranks")
    return Taxon(value["id"], value["name"], ranks)


def replay(
    records: list[dict[str, Any]],
    inputs: Path,
    policy: GardenPolicy,
    country: str,
    bundle: dict[str, Any],
    classifier: Runtime,
    detector: Runtime | None,
    *,
    variant: str,
    detector_size: int,
    video_frames: int,
) -> dict[str, Any]:
    outputs = [load_taxon(value) for value in bundle["outputs"]]
    taxonomy = [load_taxon(value) for value in bundle["taxonomy"]]
    counts: Counter[str] = Counter()
    observations = []
    processed = 0
    for record in unique_inputs(records):
        mode = record.get("mode", "event")
        route = route_event(record["camera"], record["label"], policy)
        if route != "garden":
            counts[route] += 1
            continue
        path = media_path(inputs, record["path"])
        local = []
        media_hash = None
        human = False
        for frame_index, image in frames(path, video_frames):
            processed += 1
            if mode == "scan":
                if detector is None:
                    raise ValueError("Offline scan requires an isolated detector")
                import cv2

                value = cv2.resize(np.asarray(image), (detector_size, detector_size))
                value = np.ascontiguousarray(value.transpose(2, 0, 1)[None].astype(np.float32) / 255)
                boxes = decode_detector(detector.infer(value), detector_size)
                if any(label == "person" for label, _, _ in boxes):
                    human = True
                    break
                crops = [box for label, _, box in boxes if label == "animal"][:4]
                if not crops:
                    counts["no_animal_detected"] += 1
            else:
                crops = [tuple(record["box"]) if record.get("box") else None]
            for box in crops:
                logits = classifier.infer(preprocess(image, variant, box)).reshape(-1)
                if len(logits) != len(outputs):
                    raise ValueError("Model output width differs from its bound taxonomy")
                probabilities = np.exp(logits.astype(np.float64) - float(logits.max()))
                probabilities /= probabilities.sum()
                indices = np.argsort(-probabilities)[:5]
                decision = decide_prediction(
                    [(outputs[index], float(probabilities[index])) for index in indices],
                    policy,
                    country=country,
                    taxonomy=taxonomy,
                    geofence=bundle["geofence"],
                )
                if decision.reason == "human_rejected":
                    human = True
                    break
                counts[decision.reason] += 1
                if decision.taxon:
                    media_hash = media_hash or digest(path)
                    cropped = variant == "4.0.3a" and box is not None
                    local.append(
                        {
                            "input_id": record["id"],
                            "camera": record["camera"],
                            "frame_index": frame_index,
                            "source": "offline_scan" if mode == "scan" else "retained_event",
                            "media_sha256": media_hash,
                            "frame_sha256": hashlib.sha256(np.asarray(image).tobytes()).hexdigest(),
                            "detector_box_xywh": box,
                            "classification_input": {
                                "kind": "tracked_crop" if cropped else "whole_image",
                                "box_xywh": box if cropped else None,
                                "frame_size": [image.width, image.height],
                            },
                            **asdict(decision),
                        }
                    )
            if human:
                break
        if human:
            # Revoke earlier frames too; reports retain no human identity, input
            # identifier, image, bounding box or rejected classifier candidates.
            counts["human_rejected"] += 1
            counts["garden"] -= len(local)
        else:
            supporting_frames = Counter((item["taxon"]["id"], item["frame_index"]) for item in local)
            counts_by_taxon = Counter(identity for identity, _ in supporting_frames)
            for item in local:
                item["needs_review"] = True
                item["supporting_frames"] = counts_by_taxon[item["taxon"]["id"]]
                item["review_reasons"] = ["prototype_accuracy_not_validated"]
                if variant == "4.0.3a" and item["classification_input"]["kind"] == "whole_image":
                    item["review_reasons"].append("whole_image_fallback")
                if item["supporting_frames"] < 2:
                    item["review_reasons"].append("single_frame_only")
            observations.extend(local)
    return {
        "prototype": True,
        "navigation_label": "Garden animals",
        "country": country,
        "frames_evaluated": processed,
        "outcomes": dict(counts),
        "observations": observations,
        "accuracy_measured": False,
        "production_writes": 0,
        "limitations": [
            "offline sampled frames; no MQTT or live tracker",
            "observations are not visit counts",
            "no mammal accuracy claim without reviewed ground truth",
            "human rejection is model-dependent",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--provider", choices=("cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"), required=True)
    parser.add_argument("--variant", choices=("4.0.3a", "4.0.3b"), default="4.0.3a")
    parser.add_argument("--camera", action="append", required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--country", required=True, help="ISO-3 country, e.g. GBR; never coordinates")
    parser.add_argument("--detector-size", type=int, choices=(640, 1280), default=640)
    parser.add_argument("--video-frames", type=int, choices=range(1, 17), default=3)
    args = parser.parse_args()
    os.umask(0o077)
    args.root.mkdir(mode=0o700)
    bundle = json.loads((args.models / "speciesnet.json").read_text())
    if args.country not in bundle["countries"]:
        raise ValueError("Country is not in the model bundle's ISO-3 registry")
    records = unique_inputs(json.loads((args.inputs / "manifest.json").read_text()))
    model = args.models / (args.variant + ".onnx")
    if digest(model) != bundle["model_sha256"][args.variant]:
        raise ValueError("Classifier checksum mismatch")
    policy = GardenPolicy(
        enabled=True, cameras=frozenset(args.camera), labels=frozenset(v.strip().lower() for v in args.label)
    )
    classifier = Runtime(model, args.provider)
    detector = None
    detector_hash = None
    if any(
        record.get("mode") == "scan" and route_event(record["camera"], record["label"], policy) == "garden"
        for record in records
    ):
        detector_path = args.models / f"mdv6-compact-{args.detector_size}.onnx"
        detector_hash = digest(detector_path)
        if detector_hash != bundle["detector_sha256"][str(args.detector_size)]:
            raise ValueError("Detector checksum mismatch")
        detector = Runtime(detector_path, args.provider)
    report = replay(
        records,
        args.inputs,
        policy,
        args.country,
        bundle,
        classifier,
        detector,
        variant=args.variant,
        detector_size=args.detector_size,
        video_frames=args.video_frames,
    )
    report.update(
        model_variant=args.variant,
        model_sha256=digest(model),
        taxonomy_sha256=digest(args.models / "speciesnet.json"),
        detector_sha256=detector_hash,
        requested_provider=args.provider,
        classifier_devices=classifier.actual,
        detector_devices=detector.actual if detector else [],
        classifier_seconds=classifier.timings,
        detector_seconds=detector.timings,
    )
    write_report(args.root / "report.json", report)


if __name__ == "__main__":
    main()

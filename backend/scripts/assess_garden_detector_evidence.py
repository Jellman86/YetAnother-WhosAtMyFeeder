"""Compare frozen Garden inference evidence without running or selecting models.

Research only. All three samples and both model identities must be present.
The report cannot change capture, privacy settings, reviews or bird history.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any


Box = tuple[float, float, float, float]
Candidate = tuple[str, float, Box]
Annotation = tuple[str, Box]
INPUT_CONTRACT = "rgb-f32-nchw-640-letterbox114"
POLICY = {"animal_confidence": 0.63, "person_confidence": 0.2, "bird_confidence": 0.8, "match_iou": 0.5}


@dataclass(frozen=True)
class Sample:
    ordinal: int
    frame_index: int
    rgb_sha256: str
    tensor_sha256: str
    baseline: tuple[Candidate, ...]
    alternative: tuple[Candidate, ...]
    annotations: tuple[Annotation, ...]
    annotations_complete: bool


def object_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Evidence must contain objects")
    return value


def sequence(value: Any, maximum: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("Evidence list missing or exceeds its bound")
    return value


def text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("Evidence identity missing or invalid")
    return value


def checksum(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Evidence requires a SHA256 checksum")
    return value


def number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Expected a finite normalized score or coordinate")
    return float(value)


def box(value: Any) -> Box:
    coordinates = sequence(value, 4)
    if len(coordinates) != 4:
        raise ValueError("Expected normalized xywh geometry")
    x, y, width, height = map(number, coordinates)
    if width <= 0 or height <= 0 or x + width > 1.000001 or y + height > 1.000001:
        raise ValueError("Candidate geometry leaves the image")
    return x, y, width, height


def iou(left: Box, right: Box) -> float:
    intersection = intersection_area(left, right)
    return intersection / (left[2] * left[3] + right[2] * right[3] - intersection)


def intersection_area(left: Box, right: Box) -> float:
    x, y, width, height = left
    xx, yy, ww, hh = right
    return max(0.0, min(x + width, xx + ww) - max(x, xx)) * max(0.0, min(y + height, yy + hh) - max(y, yy))


def model(value: Any, baseline: bool) -> dict[str, Any]:
    result = object_value(value)
    checksum(result.get("sha256"))
    if result.get("provider") not in {"cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"}:
        raise ValueError("Unrecognized reported provider")
    if result.get("input_contract") != INPUT_CONTRACT:
        raise ValueError("This comparison requires the shared qualified square RGB input contract")
    labels = [text(label) for label in sequence(result.get("labels"), 100)]
    groups = object_value(result.get("groups"))
    if len(set(labels)) != len(labels) or set(labels) != set(groups):
        raise ValueError("Output mapping must preserve every ordered model label once")
    if result.get("head_contract") != "raw-bcn-classwise-nms-0.45":
        raise ValueError("Evidence requires the classwise raw head extraction contract")
    if baseline:
        if labels != ["animal", "person", "vehicle"] or groups != dict(zip(labels, labels)):
            raise ValueError("Baseline must retain the current three-class contract")
    elif not {"person", "bird", "mammal"} <= set(groups.values()) or not set(groups.values()) <= {
        "person",
        "bird",
        "mammal",
        "vehicle",
    }:
        raise ValueError("Alternative output groups must identify person, bird and mammal")
    floors = object_value(result.get("score_floors"))
    limits = {
        "animal": POLICY["animal_confidence"],
        "person": POLICY["person_confidence"],
        "bird": POLICY["bird_confidence"],
        "mammal": POLICY["person_confidence"],
        "vehicle": 0.4,
    }
    if set(floors) != set(labels) or any(number(floors[label]) > limits[groups[label]] for label in labels):
        raise ValueError("Extraction must cover every class at the policy's required score floor")
    return result


def detections(value: Any, expected: dict[str, Any], source: str, rgb: str, tensor: str) -> tuple[Candidate, ...]:
    result = object_value(value)
    if (
        checksum(result.get("model_sha256")) != expected["sha256"]
        or checksum(result.get("source_sha256")) != source
        or result.get("provider") != expected["provider"]
        or checksum(result.get("rgb_sha256")) != rgb
        or checksum(result.get("tensor_sha256")) != tensor
    ):
        raise ValueError("Paired model output does not bind the same model, RGB and tensor evidence")
    candidates = []
    for item in sequence(result.get("detections"), 1000):
        parts = sequence(item, 3)
        if len(parts) != 3 or parts[0] not in expected["groups"]:
            raise ValueError("Candidate label differs from frozen output mapping")
        candidates.append((expected["groups"][parts[0]], number(parts[1]), box(parts[2])))
    return tuple(candidates)


def sample(value: Any, models: dict[str, dict[str, Any]], source: str) -> Sample:
    row = object_value(value)
    ordinal, index = row.get("ordinal"), row.get("frame_index")
    if type(ordinal) is not int or ordinal not in (0, 1, 2) or type(index) is not int or not 0 <= index <= 72_000:
        raise ValueError("Sample must identify its ordinal and source frame")
    if checksum(row.get("source_sha256")) != source:
        raise ValueError("Sample source differs from its recording window")
    rgb, tensor = checksum(row.get("rgb_sha256")), checksum(row.get("tensor_sha256"))
    annotations, complete = [], False
    if row.get("annotations") is not None:
        reviewed = object_value(row["annotations"])
        if checksum(reviewed.get("rgb_sha256")) != rgb or type(reviewed.get("complete")) is not bool:
            raise ValueError("Annotations must bind reviewed RGB and explicit completeness")
        complete = reviewed["complete"]
        for item in sequence(reviewed.get("boxes"), 1000):
            annotation = object_value(item)
            if annotation.get("label") not in {"bird", "mammal", "person", "background"}:
                raise ValueError("Unrecognized reviewed annotation")
            annotations.append((annotation["label"], box(annotation.get("box_xywh"))))
    return Sample(
        ordinal,
        index,
        rgb,
        tensor,
        detections(row.get("baseline"), models["baseline"], source, rgb, tensor),
        detections(row.get("alternative"), models["alternative"], source, rgb, tensor),
        tuple(annotations),
        complete,
    )


def truth(candidate: Box, frame: Sample) -> tuple[str, float]:
    matches = [(label, iou(candidate, annotated)) for label, annotated in frame.annotations]
    labels = {label for label, overlap in matches if overlap >= POLICY["match_iou"]}
    overlap = max((overlap for _, overlap in matches), default=0.0)
    if len(labels) > 1:
        return "ambiguous", overlap
    if labels:
        if any(
            label not in labels and intersection_area(candidate, geometry) > 0 for label, geometry in frame.annotations
        ):
            return "ambiguous", overlap
        return labels.pop(), overlap
    if overlap > 0 and frame.annotations_complete:
        return "ambiguous", overlap
    return ("background" if frame.annotations_complete else "unknown"), overlap


def matched_bird(candidate: Box, frame: Sample) -> bool:
    birds = [box for label, score, box in frame.alternative if label == "bird" and score >= POLICY["bird_confidence"]]
    mammals = [
        box for label, score, box in frame.alternative if label == "mammal" and score >= POLICY["person_confidence"]
    ]
    return any(iou(candidate, value) >= POLICY["match_iou"] for value in birds) and not any(
        intersection_area(candidate, value) > 0 for value in mammals
    )


def evaluate(samples: list[Sample], *, alternative_person: bool, bird_gate: bool) -> dict[str, Any]:
    person = any(
        label == "person" and score >= POLICY["person_confidence"]
        for frame in samples
        for label, score, _ in (frame.alternative if alternative_person else frame.baseline)
    )
    animals = [
        (frame, score, geometry)
        for frame in samples
        for label, score, geometry in frame.baseline
        if label == "animal" and score >= POLICY["animal_confidence"]
    ]
    localized = any(truth(geometry, frame)[0] == "mammal" for frame, _, geometry in animals)
    suppressed = [
        (frame, score, geometry) for frame, score, geometry in animals if bird_gate and matched_bird(geometry, frame)
    ]
    eligible = [
        (frame, score, geometry)
        for frame, score, geometry in animals
        if not bird_gate or not matched_bird(geometry, frame)
    ]
    selected = None
    if not person and eligible:
        # Python's max retains first occurrence, matching the worker's strict > update.
        frame, score, geometry = max(eligible, key=lambda item: item[1])
        label, overlap = truth(geometry, frame)
        selected = {
            "sample_ordinal": frame.ordinal,
            "frame_index": frame.frame_index,
            "rgb_sha256": frame.rgb_sha256,
            "tensor_sha256": frame.tensor_sha256,
            "score": score,
            "box_xywh": list(geometry),
            "truth": label,
            "annotation_iou": overlap,
        }
    suppressed_truth = (
        Counter(truth(geometry, frame)[0] for frame, _, geometry in suppressed) if not person else Counter()
    )
    return {
        "outcome": "person_rejected" if person else "candidate" if selected else "no_candidate",
        "selected": selected,
        "any_mammal_localized": localized,
        "suppressed_candidates": len(suppressed) if not person else 0,
        "suppressed_truth": dict(suppressed_truth),
        "lost_mammal_candidate": suppressed_truth["mammal"] > 0,
        "lost_all_localized_mammals": not person
        and localized
        and not any(truth(g, f)[0] == "mammal" for f, _, g in eligible),
        "known_person_admitted": not person
        and selected is not None
        and any(label == "person" for frame in samples for label, _ in frame.annotations),
        "person_annotations_complete": all(frame.annotations_complete for frame in samples),
    }


def assess(value: Any) -> dict[str, Any]:
    document = object_value(value)
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ValueError("Unsupported paired evidence schema")
    raw_models = object_value(document.get("models"))
    models = {key: model(raw_models.get(key), key == "baseline") for key in ("baseline", "alternative")}
    windows, visits, identities = [], {}, set()
    physical_windows, physical_frames, rgb_splits = set(), {}, {}
    complete = 0
    for raw in sequence(document.get("windows"), 1000):
        window = object_value(raw)
        identity, visit = text(window.get("id")), text(window.get("visit_id"))
        split = window.get("split")
        if identity in identities or split not in {"development", "holdout"}:
            raise ValueError("Windows require unique identities and an explicit evaluation split")
        if visit in visits and visits[visit] != split:
            raise ValueError("A visit group cannot cross development and holdout splits")
        identities.add(identity)
        visits[visit] = split
        source = checksum(window.get("source_sha256"))
        frames = sorted(
            (sample(item, models, source) for item in sequence(window.get("samples"), 3)), key=lambda f: f.ordinal
        )
        if [frame.ordinal for frame in frames] != [0, 1, 2]:
            raise ValueError("Every window requires all three distinct sampled frames")
        indices = tuple(frame.frame_index for frame in frames)
        if list(indices) != sorted(indices):
            raise ValueError("Sample frame indices must be chronological")
        physical_window = (source, indices)
        if physical_window in physical_windows:
            raise ValueError("Duplicate physical recording window")
        physical_windows.add(physical_window)
        for frame in frames:
            key = (source, frame.frame_index)
            previous = physical_frames.get(key)
            if previous is not None and previous != (frame.rgb_sha256, frame.tensor_sha256, split):
                raise ValueError("Physical frame identity conflicts or crosses evaluation splits")
            if frame.rgb_sha256 in rgb_splits and rgb_splits[frame.rgb_sha256] != split:
                raise ValueError("Identical RGB evidence cannot cross evaluation splits")
            physical_frames[key] = (frame.rgb_sha256, frame.tensor_sha256, split)
            rgb_splits[frame.rgb_sha256] = split
        complete += sum(frame.annotations_complete for frame in frames)
        windows.append(
            {
                "id": identity,
                "visit_id": visit,
                "split": split,
                "source_sha256": source,
                "policies": {
                    "baseline": evaluate(frames, alternative_person=False, bird_gate=False),
                    "person_comparison": evaluate(frames, alternative_person=True, bird_gate=False),
                    "bird_gate_experiment": evaluate(frames, alternative_person=True, bird_gate=True),
                },
            }
        )
    return {
        "schema_version": 1,
        "scope": "offline policy comparison; no production or hardware qualification",
        "bird_gate_mammal_abstention": "any positive box intersection with a mammal score at least 0.2",
        "provider_evidence": "reported by producer; actual execution requires separate native receipts",
        "models": models,
        "policy": dict(POLICY),
        "windows": windows,
        "summary": {
            "windows": len(windows),
            "samples": 3 * len(windows),
            "visit_groups": len(visits),
            "fully_annotated_samples": complete,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.evidence.open("rb") as stream:
        encoded = stream.read(16 * 1024 * 1024 + 1)
    if len(encoded) > 16 * 1024 * 1024:
        parser.error("Paired evidence must fit within 16 MiB")
    result = assess(json.loads(encoded))
    result["evidence_sha256"] = hashlib.sha256(encoded).hexdigest()
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()

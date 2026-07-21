#!/usr/bin/env python3
"""Build a private, visit-grouped crop-detector panel from cached HQ frames.

The script does not fetch camera media and never copies positive frames. It joins
persisted full-frame and Frigate-hint candidates by event + frame index, which is
the only safe way to use a moving event box as a localisation reference.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image


_NON_IDENTITY_LABELS = {"", "bird", "birds", "unknown", "unknown bird", "background"}


def _identity_labels(*values: object) -> list[str]:
    return list(
        dict.fromkeys(
            str(value).strip() for value in values if str(value or "").strip().casefold() not in _NON_IDENTITY_LABELS
        )
    )


def _intersection_area(left: list[int], right: list[int]) -> int:
    return max(0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0, min(left[3], right[3]) - max(left[1], right[1])
    )


def _negative_region(width: int, height: int, bird_box: list[int]) -> list[int]:
    """Choose the half-frame corner with least overlap with the known bird box."""
    half_width = max(1, width // 2)
    half_height = max(1, height // 2)
    candidates = [
        [0, 0, half_width, half_height],
        [width - half_width, 0, width, half_height],
        [0, height - half_height, half_width, height],
        [width - half_width, height - half_height, width, height],
    ]
    return min(candidates, key=lambda region: _intersection_area(region, bird_box))


def _round_robin_groups(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[(str(item["distance"]), str(item["species"]))].append(item)
    selected: list[dict[str, Any]] = []
    while len(selected) < limit:
        added = False
        for key in sorted(groups):
            if groups[key]:
                selected.append(groups[key].pop(0))
                added = True
            if len(selected) >= limit:
                break
        if not added:
            break
    return selected


def _load_frame_pairs(database: Path, snapshot_dir: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT f.frigate_event, f.frame_index, f.image_ref,
                   h.crop_box_json, h.classifier_label, h.classifier_score,
                   d.detection_time, COALESCE(d.common_name, d.display_name) AS species,
                   d.common_name, d.display_name, d.scientific_name, d.category_name,
                   d.manual_tagged
              FROM snapshot_candidates f
              JOIN snapshot_candidates h
                ON h.frigate_event = f.frigate_event
               AND h.frame_index = f.frame_index
              LEFT JOIN detections d ON d.frigate_event = f.frigate_event
             WHERE f.source_mode = 'full_frame'
               AND h.source_mode = 'frigate_hint_crop'
               AND h.crop_box_json IS NOT NULL
             ORDER BY f.created_at DESC
            """
        ).fetchall()
    finally:
        connection.close()

    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        image_path = snapshot_dir / f"{row['image_ref']}.jpg"
        if not image_path.is_file():
            continue
        try:
            box = [int(value) for value in json.loads(row["crop_box_json"])]
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if len(box) != 4:
            continue
        by_event[str(row["frigate_event"])].append(
            {
                "event_id": str(row["frigate_event"]),
                "frame_index": int(row["frame_index"]),
                "image_path": image_path,
                "box": box,
                "species": str(row["species"] or row["classifier_label"] or "Unknown Bird"),
                "expected_labels": _identity_labels(
                    row["common_name"],
                    row["display_name"],
                    row["scientific_name"],
                    row["category_name"],
                ),
                "manual": bool(row["manual_tagged"]),
                "hint_classifier_label": str(row["classifier_label"] or "") or None,
                "hint_classifier_score": float(row["classifier_score"] or 0.0),
                "detection_time": str(row["detection_time"] or ""),
            }
        )

    items: list[dict[str, Any]] = []
    for event_rows in by_event.values():
        item = max(event_rows, key=lambda value: value["hint_classifier_score"])
        try:
            with Image.open(item["image_path"]) as image:
                width, height = image.size
        except Exception:
            continue
        box = item["box"]
        if width <= 0 or height <= 0 or box[2] <= box[0] or box[3] <= box[1]:
            continue
        area_ratio = ((box[2] - box[0]) * (box[3] - box[1])) / float(width * height)
        distance = "distant" if area_ratio < 0.015 else ("near" if area_ratio >= 0.08 else "mid_distance")
        edge = box[0] < width * 0.04 or box[1] < height * 0.04 or box[2] > width * 0.96 or box[3] > height * 0.96
        item.update(
            {
                "width": width,
                "height": height,
                "area_ratio": area_ratio,
                "distance": distance,
                "edge": edge,
            }
        )
        items.append(item)
    return sorted(items, key=lambda value: value["detection_time"], reverse=True)


def build_manifest(
    *,
    database: Path,
    snapshot_dir: Path,
    output_dir: Path,
    positive_limit: int = 30,
    negative_limit: int = 10,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    negative_dir = output_dir / "hard-negatives"
    negative_dir.mkdir(parents=True, exist_ok=True)
    selected = _round_robin_groups(_load_frame_pairs(database, snapshot_dir), max(1, positive_limit))

    cases: list[dict[str, Any]] = []
    for index, item in enumerate(selected, 1):
        tags = [
            item["distance"],
            "small_subject" if item["area_ratio"] < 0.025 else "large_subject",
            "full_frame",
            "frame_specific_frigate_hint",
        ]
        if item["edge"]:
            tags.append("edge_of_frame")
        cases.append(
            {
                "id": f"quark_visit_{index:02d}",
                "visit_id": item["event_id"],
                "bucket": "quark_feeder_real",
                "source": "cached_hq_full_frame_with_frame_specific_frigate_hint",
                "image_path": str(item["image_path"]),
                "boxes": [item["box"]],
                "frame_index": item["frame_index"],
                "expected_labels": item["expected_labels"] if item["manual"] else [],
                "label_source": "owner_manual" if item["manual"] else "automatic_context_only",
                "frigate_baseline": {
                    "box": item["box"],
                    "classifier_label": item["hint_classifier_label"],
                    "classifier_score": item["hint_classifier_score"],
                },
                "tags": tags,
                "notes": (
                    f"event={item['event_id']}; frame={item['frame_index']}; "
                    f"label={item['species']}; manual={item['manual']}; "
                    f"hint_classifier_score={item['hint_classifier_score']}"
                ),
            }
        )

    for index, item in enumerate(selected[: max(0, negative_limit)], 1):
        region = _negative_region(item["width"], item["height"], item["box"])
        if _intersection_area(region, item["box"]):
            continue
        with Image.open(item["image_path"]) as source:
            negative = source.convert("RGB").crop(tuple(region))
        output_path = negative_dir / f"negative_{index:02d}.jpg"
        negative.save(output_path, quality=94)
        cases.append(
            {
                "id": f"quark_negative_{index:02d}",
                "visit_id": f"negative-{item['event_id']}",
                "bucket": "quark_hard_negative",
                "source": "real_frame_region_excluding_frame_specific_hint",
                "image_path": str(output_path),
                "boxes": [],
                "tags": ["hard_negative", "feeder_clutter", "foliage_or_hardware"],
                "notes": (
                    f"Non-overlapping frame region from event {item['event_id']}; "
                    "this is not a full-scene absence claim."
                ),
            }
        )

    payload = {
        "version": "3",
        "private": True,
        "method": (
            "One independent cached HQ full frame per event with its exact same-frame Frigate hint box and "
            "structured downstream baseline. Owner-confirmed labels are promotion evidence; automatic labels are "
            "context only. Hard negatives are non-overlapping real-frame regions."
        ),
        "cases": cases,
    }
    (output_dir / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("/data/speciesid.db"))
    parser.add_argument("--snapshot-dir", type=Path, default=Path("/config/media_cache/snapshots"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--positive-limit", type=int, default=30)
    parser.add_argument("--negative-limit", type=int, default=10)
    args = parser.parse_args()
    payload = build_manifest(
        database=args.database,
        snapshot_dir=args.snapshot_dir,
        output_dir=args.output_dir,
        positive_limit=args.positive_limit,
        negative_limit=args.negative_limit,
    )
    positives = sum(1 for case in payload["cases"] if case["boxes"])
    negatives = sum(1 for case in payload["cases"] if not case["boxes"])
    print(
        json.dumps({"manifest": str(args.output_dir / "manifest.json"), "positives": positives, "negatives": negatives})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

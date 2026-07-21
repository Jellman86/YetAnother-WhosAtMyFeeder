from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PIL import Image

from scripts.build_crop_field_manifest import (
    _intersection_area,
    _negative_region,
    _round_robin_groups,
    build_manifest,
)


def test_negative_region_does_not_overlap_small_edge_subject():
    bird_box = [900, 700, 980, 790]
    region = _negative_region(1000, 800, bird_box)

    assert _intersection_area(region, bird_box) == 0


def test_round_robin_prevents_one_species_group_from_dominating():
    items = [{"distance": "distant", "species": "pigeon", "id": index} for index in range(4)] + [
        {"distance": "distant", "species": "robin", "id": 10},
        {"distance": "near", "species": "blackbird", "id": 20},
    ]

    selected = _round_robin_groups(items, 4)

    assert [item["id"] for item in selected[:3]] == [0, 10, 20]


def test_build_manifest_joins_full_frame_to_same_frame_hint(tmp_path: Path):
    database = tmp_path / "speciesid.db"
    snapshots = tmp_path / "snapshots"
    output = tmp_path / "output"
    snapshots.mkdir()
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE snapshot_candidates (
            frigate_event TEXT, frame_index INTEGER, image_ref TEXT,
            source_mode TEXT, crop_box_json TEXT, classifier_label TEXT,
            classifier_score REAL, created_at TEXT
        );
        CREATE TABLE detections (
            frigate_event TEXT, detection_time TEXT, common_name TEXT,
            display_name TEXT, manual_tagged INTEGER
        );
        """
    )
    connection.execute(
        "INSERT INTO detections VALUES (?, ?, ?, ?, ?)",
        ("event-1", "2026-07-21T12:00:00", "Robin", "Robin", 1),
    )
    for frame, score, box in ((2, 0.2, [10, 10, 60, 60]), (8, 0.9, [180, 120, 240, 190])):
        image_ref = f"event-1__full_frame__f{frame}__image"
        Image.new("RGB", (320, 240), "green").save(snapshots / f"{image_ref}.jpg")
        connection.execute(
            "INSERT INTO snapshot_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("event-1", frame, image_ref, "full_frame", None, None, None, f"2026-07-21T12:00:0{frame}"),
        )
        connection.execute(
            "INSERT INTO snapshot_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "event-1",
                frame,
                f"hint-{frame}",
                "frigate_hint_crop",
                json.dumps(box),
                "Robin",
                score,
                f"2026-07-21T12:00:0{frame}",
            ),
        )
    connection.commit()
    connection.close()

    manifest = build_manifest(
        database=database,
        snapshot_dir=snapshots,
        output_dir=output,
        positive_limit=1,
        negative_limit=1,
    )

    positive = next(case for case in manifest["cases"] if case["boxes"])
    negative = next(case for case in manifest["cases"] if not case["boxes"])
    assert "__f8__" in positive["image_path"]
    assert positive["boxes"] == [[180, 120, 240, 190]]
    assert Path(negative["image_path"]).is_file()
    assert json.loads((output / "manifest.json").read_text()) == manifest

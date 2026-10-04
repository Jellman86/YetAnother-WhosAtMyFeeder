"""Bounded exact RGB scenes shared through one request-owned lossless artifact."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, BinaryIO

from PIL import Image


MAX_SCENES = 2
MAX_SCENE_BYTES = 64 * 1024 * 1024
# Pillow RGB scenes use four bytes per pixel internally.
SceneKey = tuple[int, int, int, float | None]


def _scene_key(evidence: dict[str, Any]) -> SceneKey | None:
    values = [evidence.get(name) for name in ("frame_index", "frame_width", "frame_height")]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return None
    frame, width, height = values
    if frame < 0 or width <= 0 or height <= 0 or width * height * 4 > MAX_SCENE_BYTES:
        return None
    offset = evidence.get("frame_offset_seconds")
    if offset is not None and (
        isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset) or offset < 0
    ):
        return None
    return frame, width, height, offset


def _clip_identity(clip: Path) -> dict[str, int]:
    stat = clip.stat()
    return {"device": stat.st_dev, "inode": stat.st_ino, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _digest(stream: BinaryIO) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(256 * 1024), b""):
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


class VideoSceneCache:
    def __init__(
        self,
        *,
        max_scenes: int = MAX_SCENES,
        max_bytes: int = MAX_SCENE_BYTES,
        clip_path: Path | None = None,
        clip_variant: str | None = None,
    ) -> None:
        self._max_scenes = min(MAX_SCENES, max(0, max_scenes))
        self._max_bytes = min(MAX_SCENE_BYTES, max(0, max_bytes))
        self._scenes: dict[SceneKey, tuple[float, Image.Image]] = {}
        self._identity: dict[str, int] | None = None
        self._variant = clip_variant
        self._clip_bound = clip_path is not None
        if clip_path is not None:
            try:
                self._identity = _clip_identity(clip_path)
            except OSError:
                pass

    @property
    def retained_count(self) -> int:
        return len(self._scenes)

    @property
    def retained_bytes(self) -> int:
        return sum(key[1] * key[2] * 4 for key in self._scenes)

    def retain(self, evidence: dict[str, Any], image: Image.Image) -> None:
        key = _scene_key(evidence)
        score = evidence.get("score")
        if (
            key is None
            or image.mode != "RGB"
            or image.size != key[1:3]
            or key[1] * key[2] * 4 > self._max_bytes
            or not self._max_scenes
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            return
        if key in self._scenes:
            previous, retained = self._scenes[key]
            self._scenes[key] = (max(score, previous), retained)
            return
        # Retain the strongest scenes, but never discard their evidence. A
        # consensus/reranked winner outside this cache uses the normal decoder.
        while self._scenes and (
            len(self._scenes) >= self._max_scenes or self.retained_bytes + key[1] * key[2] * 4 > self._max_bytes
        ):
            weakest = min(self._scenes, key=lambda item: self._scenes[item][0])
            if self._scenes[weakest][0] > score:
                return
            del self._scenes[weakest]
        self._scenes[key] = (float(score), image.copy())

    def retained_scene(self, evidence: dict[str, Any]) -> Image.Image | None:
        entry = self._scenes.get(_scene_key(evidence))
        return entry[1] if entry is not None else None

    def write(self, directory: Path, clip: Path, variant: str, evidence: dict[str, Any]) -> bool:
        scene = self.retained_scene(evidence)
        key = _scene_key(evidence)
        if scene is None or key is None:
            return False
        try:
            # Never mkdir: a cancelled owner has removed this directory. Late
            # in-process work cannot resurrect artifacts after cleanup.
            identity = _clip_identity(clip)
            if self._clip_bound and (identity != self._identity or variant != self._variant):
                return False
            fd = os.open(directory / "scene.bmp", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w+b") as stream:
                scene.save(stream, format="BMP")
                stream.flush()
                digest = _digest(stream)
            manifest = {"clip": identity, "variant": variant, "key": key, "sha256": digest}
            fd = os.open(directory / "scene.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(manifest, stream)
            return True
        except (OSError, ValueError):
            return False

    def load(self, directory: Path, clip: Path, variant: str) -> bool:
        try:
            fd = os.open(directory / "scene.json", os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                if os.fstat(stream.fileno()).st_size > 4096:
                    return False
                manifest = json.load(stream)
            if not isinstance(manifest, dict) or manifest.get("clip") != _clip_identity(clip):
                return False
            raw_key = manifest.get("key")
            if manifest.get("variant") != variant or not isinstance(raw_key, list) or len(raw_key) != 4:
                return False
            evidence = dict(zip(("frame_index", "frame_width", "frame_height", "frame_offset_seconds"), raw_key))
            key = _scene_key(evidence)
            if key is None or key[1] * key[2] * 4 > self._max_bytes or not self._max_scenes:
                return False
            fd = os.open(directory / "scene.bmp", os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                if os.fstat(stream.fileno()).st_size > MAX_SCENE_BYTES + 8192:
                    return False
                if _digest(stream) != manifest.get("sha256"):
                    return False
                with Image.open(stream) as image:
                    if image.format != "BMP" or image.mode != "RGB" or image.size != key[1:3]:
                        return False
                    image.load()
                    scene = image.copy()
            self._identity, self._variant = manifest["clip"], variant
            self._scenes = {key: (1.0, scene)}
            return True
        except (OSError, ValueError, TypeError, Image.DecompressionBombError):
            return False

    def scene_for(self, clip: Path, variant: str, evidence: dict[str, Any]) -> Image.Image | None:
        try:
            if self._variant != variant or self._identity != _clip_identity(clip):
                return None
            return self.retained_scene(evidence)
        except OSError:
            return None

    def frame_for(self, clip: Path, variant: str, frame_index: int) -> Image.Image | None:
        key = next((key for key in self._scenes if key[0] == frame_index), None)
        if key is None:
            return None
        return self.scene_for(
            clip,
            variant,
            dict(zip(("frame_index", "frame_width", "frame_height", "frame_offset_seconds"), key)),
        )

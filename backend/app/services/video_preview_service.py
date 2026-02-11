"""Generate timeline preview sprite + cue metadata for video clips."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import ceil
from pathlib import Path

import cv2
import structlog
from PIL import Image

log = structlog.get_logger()


@dataclass
class PreviewCue:
    start: float
    end: float
    x: int
    y: int
    w: int
    h: int


class VideoPreviewService:
    """Builds compact sprite thumbnails and cue metadata for a video clip."""

    def __init__(self, tile_width: int = 160, tile_height: int = 90, min_frames: int = 6, max_frames: int = 14):
        self.tile_width = tile_width
        self.tile_height = tile_height
        self.min_frames = min_frames
        self.max_frames = max_frames

    def _target_frame_count(self, duration_seconds: float) -> int:
        if duration_seconds <= 0:
            return 0
        candidate = int(duration_seconds // 3)
        return max(self.min_frames, min(self.max_frames, candidate))

    def generate(self, clip_path: Path) -> tuple[bytes, list[PreviewCue]]:
        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            raise ValueError(f"Unable to open clip for previews: {clip_path}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = (frame_count / fps) if fps > 0 and frame_count > 0 else 0.0
            target_frames = self._target_frame_count(duration)
            if target_frames <= 0:
                raise ValueError("Clip has no duration metadata")

            timestamps = []
            if target_frames == 1:
                timestamps = [0.0]
            else:
                for i in range(target_frames):
                    t = (duration * i) / (target_frames - 1)
                    timestamps.append(max(0.0, min(duration, t)))

            rgb_frames: list[Image.Image] = []
            accepted_timestamps: list[float] = []

            for t in timestamps:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb).resize((self.tile_width, self.tile_height), Image.Resampling.LANCZOS)
                rgb_frames.append(pil_image)
                accepted_timestamps.append(t)

            if len(rgb_frames) < 2:
                raise ValueError("Not enough frames extracted to build previews")

            cols = min(6, len(rgb_frames))
            rows = ceil(len(rgb_frames) / cols)
            sprite = Image.new("RGB", (cols * self.tile_width, rows * self.tile_height), (0, 0, 0))

            cues: list[PreviewCue] = []
            for idx, frame in enumerate(rgb_frames):
                col = idx % cols
                row = idx // cols
                x = col * self.tile_width
                y = row * self.tile_height
                sprite.paste(frame, (x, y))

                start = accepted_timestamps[idx]
                if idx + 1 < len(accepted_timestamps):
                    end = max(start + 0.1, accepted_timestamps[idx + 1])
                else:
                    end = max(start + 0.5, duration)

                cues.append(PreviewCue(start=start, end=end, x=x, y=y, w=self.tile_width, h=self.tile_height))

            out = BytesIO()
            sprite.save(out, format="JPEG", quality=82, optimize=True)
            return out.getvalue(), cues
        except Exception:
            log.exception("Failed to generate video preview sprite", clip_path=str(clip_path))
            raise
        finally:
            cap.release()


video_preview_service = VideoPreviewService()

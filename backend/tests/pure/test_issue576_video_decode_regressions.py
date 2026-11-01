"""Keep multi-photo extraction on one forward decode pass (#576)."""

from unittest.mock import Mock

import cv2
import numpy as np

from app.services import video_snapshot_service as module


def test_several_photo_crops_share_one_decode_of_each_selected_frame(tmp_path, monkeypatch):
    clip = tmp_path / "photos.avi"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"MJPG"), 2, (80, 60))
    assert writer.isOpened()
    try:
        for color in ((0, 0, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255)):
            writer.write(np.full((60, 80, 3), color, dtype=np.uint8))
    finally:
        writer.release()
    capture = cv2.VideoCapture
    opened = []

    def counted_capture(path):
        wrapped = Mock(wraps=capture(path))
        opened.append(wrapped)
        return wrapped

    monkeypatch.setattr(module.cv2, "VideoCapture", counted_capture)
    evidences = [
        {"frame_index": index, "frame_width": 80, "frame_height": 60, "score": 0.9, "crop_box": box}
        for index, box in ((2, [10, 20, 50, 50]), (2, [20, 20, 60, 50]), (3, [10, 20, 50, 50]))
    ]
    photos = module.extract_video_snapshots(clip, evidences)
    assert len(opened) == 1
    assert opened[0].read.call_count == 4
    opened[0].release.assert_called_once()
    assert len(photos) == 3
    assert all(photo is not None and photo[0].size == (40, 30) for photo in photos)
    assert photos[0][1] is photos[1][1]
    assert photos[0][0].getpixel((20, 15))[1] > 240
    assert photos[2][0].getpixel((20, 15))[0] > 240

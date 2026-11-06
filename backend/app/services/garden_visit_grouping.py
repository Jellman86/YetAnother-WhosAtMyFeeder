"""Pure position comparisons; each stack retains its fixed first proposal."""

from app.models.garden_motion import MotionSource


def same_position(left: MotionSource, right: MotionSource) -> bool:
    if left.camera != right.camera or left.detector_sha256 != right.detector_sha256:
        return False
    a, b = left.box_xywh, right.box_xywh
    width = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    height = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    overlap = width * height
    if overlap / (a[2] * a[3] + b[2] * b[3] - overlap) >= 0.75:
        return True
    small_w, small_h = min(a[2], b[2]), min(a[3], b[3])
    return (
        max(a[2], b[2]) <= 2 * small_w
        and max(a[3], b[3]) <= 2 * small_h
        and abs(a[0] - b[0]) <= 0.15 * small_w
        and abs(a[1] - b[1]) <= 0.15 * small_h
        and width >= 0.8 * small_w
        and height >= 0.8 * small_h
    )

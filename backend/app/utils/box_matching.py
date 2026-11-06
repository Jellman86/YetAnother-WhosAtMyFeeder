"""Pure one-to-one object matching for offline localization and counting checks."""

from collections.abc import Sequence


Box = Sequence[float]


def compute_iou(box_a: Box, box_b: Box) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def matched_box_count(targets: Sequence[Box], candidates: Sequence[Box], threshold: float) -> int:
    """Find maximum matching so a broad proposal cannot steal a bird's only match."""
    edges = [
        [i for i, candidate in enumerate(candidates) if compute_iou(box, candidate) >= threshold] for box in targets
    ]
    target_by_candidate: dict[int, int] = {}

    def augment(target: int, visited: set[int]) -> bool:
        for candidate in edges[target]:
            if candidate in visited:
                continue
            visited.add(candidate)
            previous = target_by_candidate.get(candidate)
            if previous is None or augment(previous, visited):
                target_by_candidate[candidate] = target
                return True
        return False

    for target in range(len(targets)):
        augment(target, set())
    return len(target_by_candidate)

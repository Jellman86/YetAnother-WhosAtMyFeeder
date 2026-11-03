"""Proposals on fixtures that never move are not motion visitors (#641).

Replaying the recordings behind 104 owner-dismissed Garden photos showed the
detector re-proposing the same feeder, lawn patch and patio object every few
minutes, while the pixels inside the box changed no more than their
surroundings. Owner-confirmed blackbirds and a dog changed 1.5 to 6 times more.
"""

import numpy as np
import pytest

from app.services.garden_motion_policy import STILL_PROPOSAL_MOTION_RATIO, box_motion_ratio

BOX = (0.4, 0.4, 0.2, 0.2)


def _frames(count=3, *, noise=0.0, moving=0.0, seed=1):
    rng = np.random.default_rng(seed)
    base = rng.integers(40, 200, size=(100, 100)).astype(np.float32)
    frames = []
    for index in range(count):
        frame = base + rng.normal(0, noise, size=base.shape).astype(np.float32) if noise else base.copy()
        if moving:
            frame[40:60, 40:60] += moving * ((index % 2) * 2 - 1)
        frames.append(np.clip(frame, 0, 255))
    return frames


def test_a_fixture_that_does_not_change_is_still():
    assert box_motion_ratio(_frames(), BOX) == pytest.approx(0.0)


def test_noise_spread_evenly_across_the_scene_is_still():
    ratio = box_motion_ratio(_frames(noise=8.0), BOX)
    assert ratio is not None and ratio < STILL_PROPOSAL_MOTION_RATIO


def test_change_concentrated_in_the_box_is_movement():
    ratio = box_motion_ratio(_frames(noise=4.0, moving=40.0), BOX)
    assert ratio is not None and ratio >= 3 * STILL_PROPOSAL_MOTION_RATIO


@pytest.mark.parametrize(
    "frames, box",
    [
        ([np.zeros((100, 100), np.float32)], BOX),
        (_frames(), (0.4, 0.4, 0.0, 0.2)),
        (_frames(), (1.2, 0.4, 0.2, 0.2)),
        (_frames(), (float("nan"), 0.4, 0.2, 0.2)),
    ],
)
def test_unmeasurable_input_is_not_called_still(frames, box):
    """Without a measurement the proposal stays for owner review rather than being dropped."""
    assert box_motion_ratio(frames, box) is None

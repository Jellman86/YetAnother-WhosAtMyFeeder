"""A slow first boot must not be mistaken for an unhealthy container.

A Raspberry Pi, or an emulated arm64 build, runs every migration and seeds the
species catalogue before it can answer a health check. That was measured at
over a minute on emulated arm64, and a 15 second start period with six retries
declared the container unhealthy at around 75 seconds while it was starting
normally. Docker does not count failures inside the start period, so the only
cost of a generous value is that a genuinely broken first boot takes longer to
be called broken; the steady-state check afterwards is unchanged.
"""

import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"
MINIMUM_START_PERIOD_SECONDS = 180


def test_the_healthcheck_allows_a_slow_first_boot():
    healthcheck = [line for line in DOCKERFILE.read_text().splitlines() if line.startswith("HEALTHCHECK")]
    assert healthcheck, "the image must define a health check"

    match = re.search(r"--start-period=(\d+)s", healthcheck[0])
    assert match, f"health check must state a start period: {healthcheck[0]}"
    assert int(match.group(1)) >= MINIMUM_START_PERIOD_SECONDS, (
        f"start period is {match.group(1)}s; a first boot on a slow host needs at least "
        f"{MINIMUM_START_PERIOD_SECONDS}s before the container may be called unhealthy"
    )

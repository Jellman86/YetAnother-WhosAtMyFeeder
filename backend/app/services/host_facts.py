"""What machine this is running on.

A performance report cannot be sized without it. Two diagnostics bundles and a
browser capture were exchanged on #300 before anyone could say whether the host
was a four core box or a sixteen core one, because nothing recorded it.

Everything here is best effort and returns ``None`` rather than raising: a
missing ``/proc`` entry on an unusual platform must never stop a diagnostics
bundle being generated, and an unknown is reported as unknown rather than
rounded up to a plausible number (CLAUDE.md section 5).
"""

from __future__ import annotations

import os
from typing import Any, Optional

import structlog

log = structlog.get_logger()

CGROUP_V2_CPU_MAX = "/sys/fs/cgroup/cpu.max"
CGROUP_V2_MEMORY_MAX = "/sys/fs/cgroup/memory.max"


def _read_cgroup_cpu_quota() -> Optional[float]:
    """Effective CPU limit in cores, or None when unlimited or unreadable.

    A container capped at two cores on a sixteen core host performs like a two
    core machine, so the raw processor count alone is misleading.
    """
    with open(CGROUP_V2_CPU_MAX, encoding="utf-8") as handle:
        raw = handle.read().strip()
    quota, _, period = raw.partition(" ")
    if quota == "max":
        return None
    return int(quota) / int(period)


def _read_cgroup_memory_limit() -> Optional[int]:
    """Container memory limit in bytes, or None when unlimited or unreadable."""
    with open(CGROUP_V2_MEMORY_MAX, encoding="utf-8") as handle:
        raw = handle.read().strip()
    if raw == "max":
        return None
    return int(raw)


def _total_memory_bytes() -> Optional[int]:
    pages = os.sysconf("SC_PHYS_PAGES")
    page_size = os.sysconf("SC_PAGE_SIZE")
    return int(pages) * int(page_size)


def _usable_cpu_count() -> Optional[int]:
    """Processors this process may actually run on, not the machine's total."""
    affinity = getattr(os, "sched_getaffinity", None)
    if affinity is not None:
        return len(affinity(0))
    return os.cpu_count()


def collect_host_facts() -> dict[str, Any]:
    """The machine, as far as it can be determined from inside the container."""
    facts: dict[str, Any] = {
        "cpu_count": None,
        "cpu_quota": None,
        "memory_total_bytes": None,
        "memory_limit_bytes": None,
    }
    for key, reader in (
        ("cpu_count", _usable_cpu_count),
        ("cpu_quota", _read_cgroup_cpu_quota),
        ("memory_total_bytes", _total_memory_bytes),
        ("memory_limit_bytes", _read_cgroup_memory_limit),
    ):
        try:
            facts[key] = reader()
        except Exception as error:  # noqa: BLE001 - diagnostics must not fail to generate
            log.debug("Host fact unavailable", fact=key, error=str(error))
            facts[key] = None

    # The number that actually governs inference and API contention.
    quota = facts["cpu_quota"]
    count = facts["cpu_count"]
    if quota is not None and count is not None:
        facts["effective_cpus"] = min(float(quota), float(count))
    elif count is not None:
        facts["effective_cpus"] = float(count)
    else:
        facts["effective_cpus"] = None
    return facts

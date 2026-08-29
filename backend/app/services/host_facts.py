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
# Unraid and older Docker/Synology hosts still mount cgroup v1, where the same
# limits live under per-controller directories and "no limit" is a sentinel
# value rather than the word "max".
CGROUP_V1_CPU_QUOTA = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
CGROUP_V1_CPU_PERIOD = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
CGROUP_V1_MEMORY_LIMIT = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
_CGROUP_V1_NO_MEMORY_LIMIT = 1 << 60


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip()


def _read_cgroup_cpu_quota() -> Optional[float]:
    """Effective CPU limit in cores. None means explicitly unlimited.

    A container capped at two cores on a sixteen core host performs like a two
    core machine, so the raw processor count alone is misleading. Raises when
    neither cgroup version is readable: an unknown limit must surface as
    unknown, not as no limit.
    """
    try:
        raw = _read_file(CGROUP_V2_CPU_MAX)
    except OSError:
        quota = int(_read_file(CGROUP_V1_CPU_QUOTA))
        if quota < 0:
            return None
        return quota / int(_read_file(CGROUP_V1_CPU_PERIOD))
    quota_raw, _, period = raw.partition(" ")
    if quota_raw == "max":
        return None
    return int(quota_raw) / int(period)


def _read_cgroup_memory_limit() -> Optional[int]:
    """Container memory limit in bytes. None means explicitly unlimited.

    Raises when neither cgroup version is readable, for the same reason as the
    CPU quota.
    """
    try:
        raw = _read_file(CGROUP_V2_MEMORY_MAX)
    except OSError:
        limit = int(_read_file(CGROUP_V1_MEMORY_LIMIT))
        if limit >= _CGROUP_V1_NO_MEMORY_LIMIT:
            return None
        return limit
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
    unknown: set[str] = set()
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
            unknown.add(key)

    # The number that actually governs inference and API contention. A quota
    # that could not be read at all leaves it unknown: rounding an unknown
    # limit up to the whole machine is the guess this module exists to prevent.
    quota = facts["cpu_quota"]
    count = facts["cpu_count"]
    if count is None or "cpu_quota" in unknown:
        facts["effective_cpus"] = None
    elif quota is not None:
        facts["effective_cpus"] = min(float(quota), float(count))
    else:
        facts["effective_cpus"] = float(count)
    return facts

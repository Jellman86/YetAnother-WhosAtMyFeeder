"""Where this process's memory sits.

Container resident memory grew from 633MiB to 4.8GiB over about a day with no
change of model (#314), and nothing in the process could say what held it.
These readings split a sampled curve into its holders: kernel-visible RSS by
kind, the Python allocator's live block count, and the in-process buffers that
grow with traffic.

Best effort like host_facts: an unreadable value is None, never a guess, and a
missing /proc on an unusual platform must never break a health read.
"""

from __future__ import annotations

import sys
from typing import Any

import structlog

log = structlog.get_logger()

PROC_SELF_STATUS = "/proc/self/status"

_STATUS_FIELDS = {
    "VmRSS": "rss_bytes",
    "RssAnon": "anonymous_bytes",
    "RssFile": "file_bytes",
    "RssShmem": "shmem_bytes",
}


def _read_rss_by_kind() -> dict[str, int]:
    readings: dict[str, int] = {}
    with open(PROC_SELF_STATUS, encoding="utf-8") as handle:
        for line in handle:
            name, _, value = line.partition(":")
            key = _STATUS_FIELDS.get(name)
            if key is not None:
                readings[key] = int(value.strip().split()[0]) * 1024
    return readings


def collect_process_memory() -> dict[str, Any]:
    """The process's memory, split by what holds it."""
    facts: dict[str, Any] = {key: None for key in _STATUS_FIELDS.values()}
    try:
        facts.update(_read_rss_by_kind())
    except Exception as error:  # noqa: BLE001 - a health read must not fail here
        log.debug("Process memory unavailable", error=str(error))

    # The Python allocator's live block count separates heap growth from
    # native runtime growth: a climbing RSS with a flat block count is not
    # Python's doing.
    facts["python_allocated_blocks"] = sys.getallocatedblocks()

    try:
        from app.services.audio.audio_service import audio_service

        facts["audio_buffer_entries"] = audio_service.buffer_size()
    except Exception as error:  # noqa: BLE001 - a health read must not fail here
        log.debug("Audio buffer size unavailable", error=str(error))
        facts["audio_buffer_entries"] = None
    return facts

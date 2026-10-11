"""Serialize each capture's photograph choices across cache and database writes."""

import asyncio
from weakref import WeakValueDictionary


_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def photo_choice_lock(event_id: str) -> asyncio.Lock:
    lock = _locks.get(event_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[event_id] = lock
    return lock

"""A feeder refill, as checked before it is stored and as it is read back (#946)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

RefillSource = Literal["manual", "api", "mqtt"]


@dataclass(frozen=True)
class NewRefill:
    """A checked refill, its time in naive UTC to the second as the history stores times."""

    refilled_at: datetime
    camera_name: str | None
    source: RefillSource
    note: str | None
    source_event_id: str | None


@dataclass(frozen=True)
class StoredRefill:
    id: int
    refilled_at: datetime
    camera_name: str | None
    source: RefillSource
    note: str | None
    source_event_id: str | None
    created_at: datetime

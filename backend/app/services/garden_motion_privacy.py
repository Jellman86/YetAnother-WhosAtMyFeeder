"""Serialize final publication with delayed Frigate privacy vetoes."""

import asyncio

lock = asyncio.Lock()
generation = 0


def invalidate() -> None:
    global generation
    generation += 1

"""Keep downloaded-model tests memory bounded without repeatedly reloading weights."""

from collections import defaultdict
from typing import Any


def group_model_cases(items: list[Any]) -> None:
    positions: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        filename = item.nodeid.split("::", 1)[0].rsplit("/", 1)[-1]
        if filename in {"test_model_smoke.py", "test_model_integration.py"}:
            if "model_id" in getattr(getattr(item, "callspec", None), "params", {}):
                positions[filename].append(index)
    for indexes in positions.values():
        grouped = sorted((items[index] for index in indexes), key=lambda item: str(item.callspec.params["model_id"]))
        for index, item in zip(indexes, grouped):
            items[index] = item

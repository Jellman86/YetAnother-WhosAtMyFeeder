"""Work in progress on a model: the server's account of it, which every tab and page reads.

A model's own report says whether it is installed and running, not that it is being downloaded or
checked on this hardware. The page that started the work used to be the only one that knew, so a
download begun on one page, or in another tab, was invisible elsewhere and could be remembered
after it ended. The server is where the work happens, so it is the authority: this module holds
what is in progress, and `GET /api/models/activity` reports it.
"""

from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Literal

ActivityPhase = Literal["downloading", "validating"]

#: The name Garden's automatic check model is reported under; it is not in the model catalogue.
GARDEN_CHECK_MODEL = "garden-speciesnet-4.0.3a"

_ACTIVE_DOWNLOAD = frozenset({"pending", "downloading"})


class ModelActivity:
    def __init__(self) -> None:
        self._working: Counter[tuple[str, ActivityPhase]] = Counter()

    @contextmanager
    def working(self, model_id: str, phase: ActivityPhase) -> Iterator[None]:
        """Marks the model as being worked on until the block ends, however it ends."""
        key = (model_id, phase)
        self._working[key] += 1
        try:
            yield
        finally:
            self._working[key] -= 1
            if self._working[key] <= 0:
                del self._working[key]

    def phases(self, download_statuses: Mapping[str, str]) -> dict[str, ActivityPhase]:
        """Each model being worked on now, with the model manager's own downloads included.

        A download replaces the files a check would read, so it is the phase said when both run.
        """
        phases: dict[str, ActivityPhase] = {
            model_id: phase for model_id, phase in self._working if phase == "validating"
        }
        phases.update({model_id: phase for model_id, phase in self._working if phase == "downloading"})
        phases.update(
            {model_id: "downloading" for model_id, status in download_statuses.items() if status in _ACTIVE_DOWNLOAD}
        )
        return phases


model_activity = ModelActivity()

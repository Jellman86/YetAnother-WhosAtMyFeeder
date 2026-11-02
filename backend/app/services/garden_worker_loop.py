"""The child side of a warm Garden worker: one JSON request per line, one result line each.

Only its parent supervisor may launch it. The loop ends on end of input; any error writes
the exception type and exits non-zero, so the parent replaces the process.
"""

from collections.abc import Callable, Hashable
import json
import os
import sys
from typing import Any, Generic, TypeVar

REQUEST_LIMIT_BYTES = 8192

Model = TypeVar("Model")


class BoundModel(Generic[Model]):
    """The model loaded for the first request's binding; a request with any other binding is refused."""

    def __init__(self, load: Callable[[dict[str, Any]], Model], binding: Callable[[dict[str, Any]], Hashable]) -> None:
        self._load = load
        self._binding = binding
        self._bound: tuple[Hashable, Model] | None = None

    def get(self, request: dict[str, Any]) -> Model:
        binding = self._binding(request)
        if self._bound is None:
            self._bound = (binding, self._load(request))
        elif self._bound[0] != binding:
            raise ValueError("Garden worker received a request for another model binding")
        return self._bound[1]


def serve(prefix: str, handle: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    # Native libraries may print to stdout; only results may reach the parent's protocol pipe.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    while line := sys.stdin.buffer.readline(REQUEST_LIMIT_BYTES):
        try:
            if not line.endswith(b"\n"):
                raise ValueError("Garden worker request exceeds its limit")
            reply = prefix + json.dumps(handle(json.loads(line)), allow_nan=False) + "\n"
        except Exception as error:
            # No source paths, media, identities or provider stderr enter logs: only the type.
            protocol.write("WORKER_ERROR:" + type(error).__name__ + "\n")
            protocol.flush()
            sys.exit(1)
        protocol.write(reply)
        protocol.flush()

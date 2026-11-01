"""Where pure tests live, and whether a session runs nothing else."""

from pathlib import Path

import pytest

PURE_TESTS_DIR = Path(__file__).resolve().parent / "pure"

# Set once collection finishes: True when every collected test is pure.
PURE_ONLY_SESSION = pytest.StashKey[bool]()


def is_pure_test(path: Path) -> bool:
    return PURE_TESTS_DIR in Path(path).resolve().parents

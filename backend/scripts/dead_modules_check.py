#!/usr/bin/env python3
"""Fail when a module under ``backend/app`` is reachable from nothing that runs.

The class of dead code this catches is the one that survives review: a file that
was superseded — a router nobody mounts, a service nobody imports — and kept
compiling, passing lint, and looking alive. ``ruff`` finds unused *names*; this
finds unused *files*.

Reachability starts from the things that actually execute: ``app.main``, every
script under ``backend/scripts`` and the repository-root ``scripts/``, both Alembic
environments, and any module named in a string literal (the classifier worker is
launched with ``-m``). Tests are
deliberately not roots: a module only a test imports is dead production code
with a test keeping it warm.

Usage:
    python scripts/dead_modules_check.py            # exit 1 and list orphans
"""

from __future__ import annotations

import ast
import sys
from collections import deque
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PACKAGE = "app"


def module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def discover_modules(root: Path) -> dict[str, Path]:
    return {module_name(p, root): p for p in sorted((root / PACKAGE).rglob("*.py"))}


def _resolve_relative(current: str, is_package: bool, level: int, target: str | None) -> str:
    base = current.split(".") if is_package else current.split(".")[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join(base + ([target] if target else []))


def references(path: Path, current: str, known: set[str]) -> set[str]:
    """Every known module this file can cause to be imported."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    is_package = path.name == "__init__.py"
    found: set[str] = set()

    def add(candidate: str) -> None:
        # ``import a.b.c`` imports a and a.b too; ``from a.b import c`` may name a submodule.
        parts = candidate.split(".")
        for i in range(1, len(parts) + 1):
            prefix = ".".join(parts[:i])
            if prefix in known:
                found.add(prefix)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _resolve_relative(current, is_package, node.level, node.module)
            else:
                base = node.module or ""
            if base:
                add(base)
            for alias in node.names:
                if base:
                    add(f"{base}.{alias.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith(PACKAGE + ".") and node.value in known:
                found.add(node.value)
    return found


def roots(root: Path) -> list[Path]:
    # The repository-root ``scripts/`` (soak and replay harnesses run by hand on the
    # reference install) import ``app`` modules just as ``backend/scripts`` do.
    candidates = [
        root / PACKAGE / "main.py",
        root / "migrations" / "env.py",
        root / "migrations_catalog" / "env.py",
        *sorted((root / "scripts").glob("*.py")),
        *sorted((root.parent / "scripts").glob("*.py")),
    ]
    return [p for p in candidates if p.exists()]


def find_orphans(root: Path = BACKEND) -> list[str]:
    modules = discover_modules(root)
    known = set(modules)
    reachable: set[str] = set()
    queue: deque[tuple[Path, str]] = deque()

    for entry in roots(root):
        name = module_name(entry, root) if entry.is_relative_to(root / PACKAGE) else f"__root__.{entry.stem}"
        if name in known:
            reachable.add(name)
        queue.append((entry, name))

    while queue:
        path, current = queue.popleft()
        for target in references(path, current, known):
            if target in reachable:
                continue
            reachable.add(target)
            queue.append((modules[target], target))

    # A package is alive if any module inside it is; ``app`` itself is the root.
    for name in list(reachable):
        parts = name.split(".")
        for i in range(1, len(parts)):
            reachable.add(".".join(parts[:i]))

    return sorted(name for name in known if name not in reachable and name != PACKAGE)


def main() -> int:
    orphans = find_orphans()
    if not orphans:
        print("Every module under backend/app is reachable from something that runs.")
        return 0
    print("Modules reachable from nothing that runs (delete them, or wire them in):")
    for name in orphans:
        print(f"  {name}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

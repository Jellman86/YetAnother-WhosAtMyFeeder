"""Pure tests stay pure: no app, no database, no migrations.

`tests/pure/conftest.py` refuses database connections at run time and, when
only pure tests run, refuses an import of `app.main`. This catches the direct
imports up front, with the file and line, before anything runs.
"""

import ast

from tests.pure_lane import PURE_TESTS_DIR, is_pure_test

APPLICATION_RESOURCES = (
    "aiosqlite",
    "alembic",
    "app.database",
    "app.main",
    "app.repositories",
    "fastapi.testclient",
    "sqlite3",
    "starlette.testclient",
)


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    imported: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.append((node.lineno, node.module))
    return imported


def _uses_application_resource(module: str) -> bool:
    return any(module == resource or module.startswith(f"{resource}.") for resource in APPLICATION_RESOURCES)


def test_pure_tests_import_no_application_resources():
    violations = [
        f"{path.relative_to(PURE_TESTS_DIR)}:{line} imports {module}"
        for path in sorted(PURE_TESTS_DIR.rglob("test_*.py"))
        for line, module in _imported_modules(ast.parse(path.read_text(encoding="utf-8")))
        if _uses_application_resource(module)
    ]
    assert violations == []


def test_the_pure_lane_holds_tests():
    assert len(list(PURE_TESTS_DIR.rglob("test_*.py"))) > 0


def test_a_pure_path_is_recognised_and_an_application_test_is_not():
    assert is_pure_test(PURE_TESTS_DIR / "test_example.py")
    assert is_pure_test(PURE_TESTS_DIR / "nested" / "test_example.py")
    assert not is_pure_test(PURE_TESTS_DIR.parent / "test_example.py")
    assert not is_pure_test(PURE_TESTS_DIR.parent / "pure_neighbour" / "test_example.py")


def test_application_resource_imports_are_recognised():
    tree = ast.parse("import sqlite3\nfrom app.repositories.detection_repository import X\nfrom app.utils import y\n")
    flagged = [module for _line, module in _imported_modules(tree) if _uses_application_resource(module)]
    assert flagged == ["sqlite3", "app.repositories.detection_repository"]

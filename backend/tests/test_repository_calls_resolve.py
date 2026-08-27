"""Every repository method call must name a method that exists.

`repo.delete(...)` in the false-positive handler named a method
`DetectionRepository` has never had. Python only finds that at the moment the
line runs, and that line ran inside a broad `except Exception`, so the failure
was swallowed and logged as an ordinary cleanup error. Nothing in ruff, the type
checker or the test suite caught it, and it stayed that way for seven months.

This walks the whole codebase and resolves each `repo.<method>()` call against
the repository class bound to that name in the same function.
"""

import ast
import importlib
import pathlib

REPOSITORY_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "repositories"
APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"


def _repository_classes() -> dict[str, type]:
    classes: dict[str, type] = {}
    for module_path in sorted(REPOSITORY_DIR.glob("*.py")):
        if module_path.stem == "__init__":
            continue
        module = importlib.import_module(f"app.repositories.{module_path.stem}")
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and name.endswith("Repository"):
                classes[name] = obj
    return classes


def _bindings_in(scope: ast.AST, known: dict[str, type]) -> dict[str, set[str]]:
    """Local names assigned a repository instance, and which classes they can hold."""
    bindings: dict[str, set[str]] = {}
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            class_name = getattr(node.value.func, "id", None)
            if class_name in known:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bindings.setdefault(target.id, set()).add(class_name)
    return bindings


def test_every_repository_method_call_resolves():
    known = _repository_classes()
    assert known, "No repository classes found; the audit would pass vacuously"

    unresolved: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for scope in ast.walk(tree):
            if not isinstance(scope, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            bindings = _bindings_in(scope, known)
            if not bindings:
                continue
            for node in ast.walk(scope):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                receiver = getattr(node.func.value, "id", None)
                if receiver not in bindings:
                    continue
                candidates = bindings[receiver]
                if not any(hasattr(known[name], node.func.attr) for name in candidates):
                    unresolved.append(
                        f"{path.name}:{node.lineno} {receiver}.{node.func.attr}() "
                        f"missing on {'/'.join(sorted(candidates))} (in {scope.name})"
                    )

    assert not unresolved, "Repository calls that will raise AttributeError:\n  " + "\n  ".join(unresolved)

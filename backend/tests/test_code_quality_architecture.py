"""Permanent architecture guards established by the file-by-file quality review."""

from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).parents[1] / "app"
ROUTERS_ROOT = APP_ROOT / "routers"
ROUTE_METHODS = {"get", "post", "put", "patch", "delete"}
PATH_BLOCKING_METHODS = {
    "exists",
    "glob",
    "iterdir",
    "mkdir",
    "read_bytes",
    "read_text",
    "rglob",
    "stat",
    "unlink",
    "write_bytes",
    "write_text",
}


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _route_decorators(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr in ROUTE_METHODS:
                yield node, decorator


def test_every_http_route_declares_a_response_contract() -> None:
    missing: list[str] = []
    for path in _python_files(ROUTERS_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function, decorator in _route_decorators(tree):
            keywords = {keyword.arg for keyword in decorator.keywords}
            if not keywords.intersection({"response_model", "response_class"}):
                missing.append(f"{path.relative_to(APP_ROOT)}:{function.lineno}:{function.name}")
    assert not missing, "Routes without response_model/response_class:\n" + "\n".join(missing)


def test_http_routers_do_not_execute_database_queries() -> None:
    violations: list[str] = []
    for path in _python_files(ROUTERS_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "execute":
                violations.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}")
    assert not violations, "Router-owned database execution:\n" + "\n".join(violations)


def test_repository_functions_have_complete_signatures() -> None:
    violations: list[str] = []
    repositories_root = APP_ROOT / "repositories"
    for path in _python_files(repositories_root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            missing = [
                argument.arg
                for argument in arguments
                if argument.arg not in {"self", "cls"} and argument.annotation is None
            ]
            if node.returns is None or missing:
                detail = f" missing args {missing}" if missing else ""
                violations.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}:{node.name}{detail}")
    assert not violations, "Incomplete repository signatures:\n" + "\n".join(violations)


class _AsyncBlockingVisitor(ast.NodeVisitor):
    """Inspect one async function without descending into its nested sync helpers."""

    def __init__(self) -> None:
        self.violations: list[ast.Call] = []
        self._to_thread_depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        is_to_thread = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
            and node.func.attr == "to_thread"
        )
        if is_to_thread:
            self._to_thread_depth += 1
            self.generic_visit(node)
            self._to_thread_depth -= 1
            return
        if self._to_thread_depth == 0 and self._is_blocking(node):
            self.violations.append(node)
        self.generic_visit(node)

    @staticmethod
    def _is_blocking(node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name):
            return node.func.id == "open"
        if not isinstance(node.func, ast.Attribute):
            return False
        rendered = ast.unparse(node.func)
        if rendered.startswith("aiofiles."):
            return False
        if rendered.startswith(("subprocess.", "requests.")):
            return True
        return node.func.attr in PATH_BLOCKING_METHODS


def test_async_functions_do_not_call_blocking_io_directly() -> None:
    violations: list[str] = []
    for path in _python_files(APP_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            visitor = _AsyncBlockingVisitor()
            for statement in node.body:
                visitor.visit(statement)
            violations.extend(f"{path.relative_to(APP_ROOT)}:{call.lineno}:{node.name}" for call in visitor.violations)
    assert not violations, "Blocking I/O in async functions:\n" + "\n".join(violations)


def test_application_has_no_untracked_todos_or_print_calls() -> None:
    violations: list[str] = []
    for path in _python_files(APP_ROOT):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for line_number, line in enumerate(source.splitlines(), start=1):
            if "TODO" in line or "FIXME" in line:
                violations.append(f"{path.relative_to(APP_ROOT)}:{line_number}:untracked note")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                violations.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}:print")
    assert not violations, "Application hygiene violations:\n" + "\n".join(violations)

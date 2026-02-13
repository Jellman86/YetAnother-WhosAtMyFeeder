#!/usr/bin/env python3
"""Documentation consistency checks.

Checks:
1. Local markdown links in README/docs resolve.
2. docs/api.md documented endpoint snippets map to real backend routes.
3. Detect stale compose service aliases in docs commands.
4. Detect stale Settings navigation labels.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_FILES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
API_DOC = ROOT / "docs" / "api.md"

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ROUTE_RE = re.compile(r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']")
APP_ROUTE_RE = re.compile(r"@app\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']")
ROUTER_PREFIX_RE = re.compile(r"APIRouter\([^\)]*prefix\s*=\s*[\"']([^\"']+)[\"']")
DOC_ENDPOINT_RE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE)\s+(/[^`\s]+)`")


def normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    while "//" in path:
        path = path.replace("//", "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def collect_actual_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()

    routers_dir = ROOT / "backend" / "app" / "routers"
    for py in sorted(routers_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        prefix_match = ROUTER_PREFIX_RE.search(text)
        router_prefix = prefix_match.group(1) if prefix_match else ""

        for method, route_path in ROUTE_RE.findall(text):
            full = normalize_path("/api" + router_prefix + route_path)
            routes.add((method.upper(), full))

    main_py = ROOT / "backend" / "app" / "main.py"
    main_text = main_py.read_text(encoding="utf-8")
    for method, route_path in APP_ROUTE_RE.findall(main_text):
        routes.add((method.upper(), normalize_path(route_path)))

    return routes


def check_local_links() -> list[str]:
    errors: list[str] = []
    for file_path in DOC_FILES:
        text = file_path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            raw_link = match.group(1).strip()
            if raw_link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            rel = raw_link.split("#", 1)[0]
            if not rel:
                continue
            target = (file_path.parent / rel).resolve()
            if not target.exists():
                errors.append(f"Broken local link in {file_path.relative_to(ROOT)}: {raw_link}")
    return errors


def check_documented_endpoints(actual_routes: set[tuple[str, str]]) -> list[str]:
    errors: list[str] = []
    text = API_DOC.read_text(encoding="utf-8")
    documented = DOC_ENDPOINT_RE.findall(text)

    for method, path in documented:
        method = method.upper()
        clean_path = path.split("?", 1)[0]

        # Wildcard support for grouped docs like /api/frigate/*
        if clean_path.endswith("*"):
            prefix = clean_path[:-1]
            if not any(m == method and p.startswith(prefix) for m, p in actual_routes):
                errors.append(
                    f"Documented endpoint pattern not found: {method} {clean_path}"
                )
            continue

        clean_path = normalize_path(clean_path)
        if (method, clean_path) not in actual_routes:
            errors.append(f"Documented endpoint not found: {method} {clean_path}")

    return errors


def check_stale_terms() -> list[str]:
    errors: list[str] = []
    stale_patterns = {
        r"docker compose (exec|logs) backend\b": "Use yawamf-backend service name in docs commands.",
        r"docker compose (exec|logs) frontend\b": "Use yawamf-frontend service name in docs commands.",
        r"Settings\s*>\s*Authentication": "Use Settings > Security (current UI navigation).",
        r"Settings\s*>\s*Public Access": "Use Settings > Security (public access controls live there).",
    }

    for file_path in [ROOT / "README.md", ROOT / "MIGRATION.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        text = file_path.read_text(encoding="utf-8")
        for pattern, message in stale_patterns.items():
            if re.search(pattern, text):
                errors.append(f"Stale docs pattern in {file_path.relative_to(ROOT)}: {message}")

    return errors


def main() -> int:
    errors: list[str] = []

    errors.extend(check_local_links())
    actual_routes = collect_actual_routes()
    errors.extend(check_documented_endpoints(actual_routes))
    errors.extend(check_stale_terms())

    if errors:
        print("Documentation consistency check failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Documentation consistency check passed.")
    print(f"Validated routes: {len(actual_routes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

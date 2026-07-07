#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema to a committed artifact.

The OpenAPI schema is the API contract. Committing it makes contract changes
visible in review and lets CI catch drift between the routers under
``backend/app/routers`` and the published schema.

Usage:
    python scripts/export_openapi.py            # write backend/openapi.json
    python scripts/export_openapi.py --check     # exit non-zero if the artifact is stale
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ARTIFACT = BACKEND_DIR / "openapi.json"
VERSION_FILE = BACKEND_DIR.parent / "VERSION"


def _stable_version() -> str:
    """Return the plain base version.

    The runtime version is ``base-branch+hash`` (git-derived), which would make
    the artifact churn on every commit and differ per environment. The contract
    only cares about the released base version, so read it directly.
    """
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def build_schema() -> dict:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from app.main import app

    schema = app.openapi()
    info = schema.get("info")
    if isinstance(info, dict):
        info["version"] = _stable_version()
    return schema


def serialize(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed artifact is out of date",
    )
    args = parser.parse_args()

    rendered = serialize(build_schema())

    if args.check:
        if not ARTIFACT.exists():
            print(
                f"{ARTIFACT} is missing. Generate it with: python scripts/export_openapi.py",
                file=sys.stderr,
            )
            return 1
        if ARTIFACT.read_text(encoding="utf-8") != rendered:
            print(
                f"{ARTIFACT} is out of date. Regenerate it with "
                "`python scripts/export_openapi.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{ARTIFACT} is up to date.")
        return 0

    ARTIFACT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {ARTIFACT} ({len(rendered.splitlines())} lines).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

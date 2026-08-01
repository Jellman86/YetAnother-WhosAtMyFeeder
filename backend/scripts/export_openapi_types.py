#!/usr/bin/env python3
"""Generate the frontend TypeScript API contract from backend/openapi.json.

The generated file is intentionally small and dependency-free: it exposes the
OpenAPI component schemas plus a path/method map that frontend API modules can
import for request and response typing.

Usage:
    python scripts/export_openapi_types.py
    python scripts/export_openapi_types.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OPENAPI_ARTIFACT = ROOT / "backend" / "openapi.json"
TYPES_ARTIFACT = ROOT / "apps" / "ui" / "src" / "lib" / "api" / "generated" / "openapi.ts"
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _schema_ref_name(ref: str) -> str:
    prefix = "#/components/schemas/"
    if not ref.startswith(prefix):
        return "unknown"
    return _ts_name(ref.removeprefix(prefix))


def _ts_name(name: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", name)
    rendered = "".join(part[:1].upper() + part[1:] for part in parts if part)
    if not rendered:
        return "GeneratedType"
    if rendered[0].isdigit():
        return f"Type{rendered}"
    return rendered


def _literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _ts_type(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "unknown"
    if "$ref" in schema:
        return f"components['schemas']['{_schema_ref_name(schema['$ref'])}']"
    if "const" in schema:
        return _literal(schema["const"])
    if "enum" in schema:
        values = schema.get("enum") or []
        return " | ".join(_literal(value) for value in values) or "unknown"
    if "anyOf" in schema:
        return _union(_ts_type(item) for item in schema["anyOf"])
    if "oneOf" in schema:
        return _union(_ts_type(item) for item in schema["oneOf"])
    if "allOf" in schema:
        return " & ".join(_wrap_intersection(_ts_type(item)) for item in schema["allOf"]) or "unknown"

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return _union(_ts_type({**schema, "type": item}) for item in schema_type)
    if schema_type == "null":
        return "null"
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "array":
        item_type = _ts_type(schema.get("items"))
        return f"Array<{item_type}>"
    if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
        properties = schema.get("properties") or {}
        additional = schema.get("additionalProperties")
        if not properties:
            if isinstance(additional, dict):
                return f"Record<string, {_ts_type(additional)}>"
            return "Record<string, unknown>"

        required = set(schema.get("required") or [])
        lines = ["{"]
        for name, prop_schema in sorted(properties.items()):
            optional = "" if name in required else "?"
            lines.append(f"    {_quote_key(name)}{optional}: {_ts_type(prop_schema)};")
        if isinstance(additional, dict):
            lines.append(f"    [key: string]: {_ts_type(additional)};")
        lines.append("}")
        return "\n".join(lines)

    return "unknown"


def _union(types: Any) -> str:
    unique: list[str] = []
    for ts_type in types:
        if ts_type not in unique:
            unique.append(ts_type)
    return " | ".join(unique) or "unknown"


def _wrap_intersection(ts_type: str) -> str:
    return f"({ts_type})" if "|" in ts_type else ts_type


def _quote_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z_$][0-9A-Za-z_$]*", key):
        return key
    return _literal(key)


def _response_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    responses = operation.get("responses") or {}
    response = responses.get("200") or responses.get("201") or responses.get("202") or responses.get("204")
    if not isinstance(response, dict):
        return None
    content = response.get("content") or {}
    for content_type in ("application/json", "text/event-stream", "text/plain"):
        media = content.get(content_type)
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            return media["schema"]
    return None


def _request_body_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    body = operation.get("requestBody") or {}
    if not isinstance(body, dict):
        return None
    content = body.get("content") or {}
    for content_type in ("application/json", "multipart/form-data", "application/x-www-form-urlencoded"):
        media = content.get(content_type)
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            return media["schema"]
    return None


def _parameters_type(operation: dict[str, Any], location: str) -> str:
    params = [
        param for param in operation.get("parameters", []) if isinstance(param, dict) and param.get("in") == location
    ]
    if not params:
        return "never"
    lines = ["{"]
    for param in sorted(params, key=lambda item: item["name"]):
        name = str(param["name"])
        optional = "" if param.get("required") else "?"
        lines.append(f"    {_quote_key(name)}{optional}: {_ts_type(param.get('schema'))};")
    lines.append("}")
    return "\n".join(lines)


def render(schema: dict[str, Any]) -> str:
    components = schema.get("components", {}).get("schemas", {})
    paths = schema.get("paths", {})

    lines = [
        "/* eslint-disable */",
        "// This file is generated by backend/scripts/export_openapi_types.py.",
        "// Do not edit by hand; run `python backend/scripts/export_openapi_types.py` from the repo root.",
        "",
        "export interface components {",
        "  schemas: {",
    ]

    for name, component_schema in sorted(components.items(), key=lambda item: _ts_name(item[0])):
        lines.append(f"    {_quote_key(_ts_name(name))}: {_ts_type(component_schema)};")
    lines.extend(["  };", "}", "", "export interface paths {"])

    for path, methods in sorted(paths.items()):
        lines.append(f"  {_quote_key(path)}: {{")
        for method in HTTP_METHODS:
            operation = methods.get(method)
            if not isinstance(operation, dict):
                continue
            lines.extend(
                [
                    f"    {method}: {{",
                    f"      operationId: {_literal(operation.get('operationId', ''))};",
                    f"      path: {_parameters_type(operation, 'path')};",
                    f"      query: {_parameters_type(operation, 'query')};",
                    f"      requestBody: {_ts_type(_request_body_schema(operation))};",
                    f"      response: {_ts_type(_response_schema(operation))};",
                    "    };",
                ]
            )
        lines.append("  };")
    lines.extend(["}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit non-zero if generated types are stale")
    args = parser.parse_args()

    schema = json.loads(OPENAPI_ARTIFACT.read_text(encoding="utf-8"))
    rendered = render(schema)

    if args.check:
        if not TYPES_ARTIFACT.exists():
            print(
                f"{TYPES_ARTIFACT} is missing. Generate it with: python scripts/export_openapi_types.py",
                file=sys.stderr,
            )
            return 1
        if TYPES_ARTIFACT.read_text(encoding="utf-8") != rendered:
            print(
                f"{TYPES_ARTIFACT} is out of date. Regenerate it with "
                "`python scripts/export_openapi_types.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{TYPES_ARTIFACT} is up to date.")
        return 0

    TYPES_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    TYPES_ARTIFACT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {TYPES_ARTIFACT} ({len(rendered.splitlines())} lines).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

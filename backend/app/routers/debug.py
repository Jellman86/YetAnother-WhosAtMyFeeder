import asyncio
import platform
import shutil
import sys
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, JsonValue

from app.auth import AuthContext, require_owner
from app.config import settings
from app.database import get_db
from app.repositories.debug_repository import DebugRepository

router = APIRouter()

REDACTED_VALUE = "***REDACTED***"
SENSITIVE_CONFIG_KEYS = frozenset(
    {
        "api_key",
        "frigate_auth_token",
        "mqtt_password",
        "station_token",
        "webhook_url",
        "user_key",
        "api_token",
        "bot_token",
        "chat_id",
        "smtp_password",
        "gmail_client_secret",
        "outlook_client_secret",
        "client_secret",
        "oauth_client_secret",
        "token",
        "password",
    }
)
MODEL_DIRECTORY = Path("/data/models")


class DatabaseStatsResponse(BaseModel):
    detections: int | str
    taxonomy_cache: int | str


class ConnectivityResult(BaseModel):
    status: Literal["ok", "error"]
    version: str | None = None
    error: str | None = None
    code: int | None = None


class ConnectivityResponse(BaseModel):
    frigate: ConnectivityResult
    inaturalist: ConnectivityResult
    telemetry: ConnectivityResult


class ModelFile(BaseModel):
    name: str
    size_bytes: int


class ModelFilesResponse(BaseModel):
    files: list[ModelFile] = Field(default_factory=list)
    error: str | None = None


class SystemDebugResponse(BaseModel):
    platform: str
    python: str
    disk_usage: tuple[int, int, int]


def redact_config(value: JsonValue) -> JsonValue:
    """Return a structurally equivalent copy with non-empty secrets redacted."""
    if isinstance(value, dict):
        return {
            key: REDACTED_VALUE if key in SENSITIVE_CONFIG_KEYS and item else redact_config(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_config(item) for item in value]
    return value


def _list_model_files(model_directory: Path) -> list[ModelFile]:
    return [
        ModelFile(name=entry.name, size_bytes=entry.stat().st_size)
        for entry in model_directory.iterdir()
        if entry.is_file()
    ]


@router.get("/debug/config", response_model=dict[str, JsonValue])
async def debug_config(_auth: AuthContext = Depends(require_owner)) -> dict[str, JsonValue]:
    """Dump current configuration (secrets redacted). Owner only."""
    return redact_config(settings.model_dump(mode="json"))


@router.get("/debug/db/stats", response_model=DatabaseStatsResponse)
async def debug_db_stats(_auth: AuthContext = Depends(require_owner)) -> DatabaseStatsResponse:
    """Get row counts for key tables. Owner only."""
    async with get_db() as db:
        stats = await DebugRepository(db).table_counts()
    return DatabaseStatsResponse.model_validate(stats)


@router.get("/debug/connectivity", response_model=ConnectivityResponse, response_model_exclude_none=True)
async def debug_connectivity(_auth: AuthContext = Depends(require_owner)) -> ConnectivityResponse:
    """Test connectivity to external services. Owner only."""
    results: dict[str, ConnectivityResult] = {}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.frigate.frigate_url}/api/version")
            results["frigate"] = ConnectivityResult(status="ok", version=resp.text.strip())
    except httpx.HTTPError as exc:
        results["frigate"] = ConnectivityResult(status="error", error=str(exc))

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://api.inaturalist.org/v1/taxa?q=Cyanistes%20caeruleus")
            if resp.status_code == 200:
                results["inaturalist"] = ConnectivityResult(status="ok")
            else:
                results["inaturalist"] = ConnectivityResult(status="error", code=resp.status_code)
    except httpx.HTTPError as exc:
        results["inaturalist"] = ConnectivityResult(status="error", error=str(exc))

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(settings.telemetry.url.replace("/heartbeat", "/"))
            if resp.status_code == 200:
                results["telemetry"] = ConnectivityResult(status="ok")
            else:
                results["telemetry"] = ConnectivityResult(status="error", code=resp.status_code)
    except httpx.HTTPError as exc:
        results["telemetry"] = ConnectivityResult(status="error", error=str(exc))

    return ConnectivityResponse.model_validate(results)


@router.get(
    "/debug/fs/models",
    response_model=ModelFilesResponse,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
async def debug_fs_models(_auth: AuthContext = Depends(require_owner)) -> ModelFilesResponse:
    """List files in the model directory. Owner only."""
    if not await asyncio.to_thread(MODEL_DIRECTORY.exists):
        return ModelFilesResponse(error="Model directory does not exist")

    files = await asyncio.to_thread(_list_model_files, MODEL_DIRECTORY)
    return ModelFilesResponse(files=files)


@router.get("/debug/system", response_model=SystemDebugResponse)
async def debug_system(_auth: AuthContext = Depends(require_owner)) -> SystemDebugResponse:
    """Get system info. Owner only."""
    usage = await asyncio.to_thread(shutil.disk_usage, "/data")
    return SystemDebugResponse(platform=platform.platform(), python=sys.version, disk_usage=tuple(usage))

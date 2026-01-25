from fastapi import APIRouter, Depends
from typing import Dict, Any
import shutil
import os
import httpx

from app.config import settings
from app.database import get_db
from app.auth import require_owner, AuthContext

router = APIRouter()

@router.get("/debug/config")
async def debug_config(auth: AuthContext = Depends(require_owner)) -> Dict[str, Any]:
    """Dump current configuration (secrets redacted). Owner only."""
    conf = settings.model_dump()
    # Redact secrets without changing structure.
    sensitive_keys = {
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

    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: ("***" if k in sensitive_keys and v else redact(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    conf = redact(conf)
    return conf

@router.get("/debug/db/stats")
async def debug_db_stats(auth: AuthContext = Depends(require_owner)):
    """Get row counts for key tables. Owner only."""
    stats = {}
    async with get_db() as db:
        for table in ["detections", "taxonomy_cache"]:
            try:
                async with db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                    row = await cursor.fetchone()
                    stats[table] = row[0] if row else 0
            except Exception as e:
                stats[table] = f"Error: {str(e)}"
    return stats

@router.get("/debug/connectivity")
async def debug_connectivity(auth: AuthContext = Depends(require_owner)):
    """Test connectivity to external services. Owner only."""
    results = {}
    
    # Test Frigate
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.frigate.frigate_url}/api/version")
            results["frigate"] = {"status": "ok", "version": resp.text.strip()}
    except Exception as e:
        results["frigate"] = {"status": "error", "error": str(e)}

    # Test iNaturalist (Taxonomy)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://api.inaturalist.org/v1/taxa?q=Cyanistes%20caeruleus")
            if resp.status_code == 200:
                results["inaturalist"] = {"status": "ok"}
            else:
                results["inaturalist"] = {"status": "error", "code": resp.status_code}
    except Exception as e:
        results["inaturalist"] = {"status": "error", "error": str(e)}

    # Test Telemetry
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(settings.telemetry.url.replace("/heartbeat", "/"))
            if resp.status_code == 200:
                results["telemetry"] = {"status": "ok"}
            else:
                results["telemetry"] = {"status": "error", "code": resp.status_code}
    except Exception as e:
        results["telemetry"] = {"status": "error", "error": str(e)}

    return results

@router.get("/debug/fs/models")
async def debug_fs_models(auth: AuthContext = Depends(require_owner)):
    """List files in the model directory. Owner only."""
    model_dir = "/data/models"
    if not os.path.exists(model_dir):
        return {"error": "Model directory does not exist"}
    
    files = []
    for f in os.listdir(model_dir):
        path = os.path.join(model_dir, f)
        if os.path.isfile(path):
            size = os.path.getsize(path)
            files.append({"name": f, "size_bytes": size})
    return {"files": files}

@router.get("/debug/system")
async def debug_system(auth: AuthContext = Depends(require_owner)):
    """Get system info. Owner only."""
    import platform
    import sys
    return {
        "platform": platform.platform(),
        "python": sys.version,
        "disk_usage": shutil.disk_usage("/data")
    }

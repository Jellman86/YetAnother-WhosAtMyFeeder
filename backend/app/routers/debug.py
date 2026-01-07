from fastapi import APIRouter
from typing import Dict, Any
import shutil
import os
import httpx

from app.config import settings
from app.database import get_db

router = APIRouter()

@router.get("/debug/config")
async def debug_config() -> Dict[str, Any]:
    """Dump current configuration (secrets redacted)."""
    conf = settings.model_dump()
    # Redact potential secrets
    if 'frigate' in conf:
        conf['frigate']['frigate_auth_token'] = '***' if conf['frigate']['frigate_auth_token'] else None
        conf['frigate']['mqtt_password'] = '***'
    if 'llm' in conf:
        conf['llm']['api_key'] = '***' if conf['llm']['api_key'] else None
    return conf

@router.get("/debug/db/stats")
async def debug_db_stats():
    """Get row counts for key tables."""
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
async def debug_connectivity():
    """Test connectivity to external services."""
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
async def debug_fs_models():
    """List files in the model directory."""
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
async def debug_system():
    """Get system info."""
    import platform
    import sys
    return {
        "platform": platform.platform(),
        "python": sys.version,
        "disk_usage": shutil.disk_usage("/data")
    }

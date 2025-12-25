from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import asyncio
import os
import subprocess
from datetime import datetime, timedelta

from app.database import init_db, get_db
from app.services.mqtt_service import MQTTService
from app.services.classifier_service import ClassifierService
from app.services.event_processor import EventProcessor
from app.repositories.detection_repository import DetectionRepository
from app.routers import events, stream, proxy, settings as settings_router, species, backfill
from app.config import settings
from contextlib import asynccontextmanager

classifier_service = ClassifierService()
event_processor = EventProcessor(classifier_service)
mqtt_service = MQTTService()
log = structlog.get_logger()

# Version management
BASE_VERSION = "2.0.0"

def get_git_hash() -> str:
    """Get git commit hash from environment or by running git."""
    # First check environment variable (set during Docker build)
    git_hash = os.environ.get('GIT_HASH', '').strip()
    if git_hash:
        return git_hash

    # Try to get from git command (for development)
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return "unknown"

GIT_HASH = get_git_hash()
APP_VERSION = f"{BASE_VERSION}+{GIT_HASH}"

# Cleanup task control
cleanup_task = None
cleanup_running = True

async def cleanup_old_detections():
    """Background task that runs cleanup daily."""
    global cleanup_running
    while cleanup_running:
        try:
            # Wait until next cleanup time (run at 3 AM daily, or every 24 hours)
            await asyncio.sleep(3600)  # Check every hour

            # Only run cleanup once per day around 3 AM
            now = datetime.now()
            if now.hour == 3:
                if settings.maintenance.retention_days > 0 and settings.maintenance.cleanup_enabled:
                    cutoff = now - timedelta(days=settings.maintenance.retention_days)
                    async with get_db() as db:
                        repo = DetectionRepository(db)
                        deleted_count = await repo.delete_older_than(cutoff)
                    if deleted_count > 0:
                        log.info("Automatic cleanup completed",
                                deleted_count=deleted_count,
                                retention_days=settings.maintenance.retention_days,
                                cutoff=cutoff.isoformat())
                # Sleep for 2 hours to avoid running again at 3 AM
                await asyncio.sleep(7200)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Cleanup task error", error=str(e))
            await asyncio.sleep(3600)  # Wait an hour before retrying

@asynccontextmanager
async def lifespan(app: FastAPI):
    global cleanup_task, cleanup_running
    # Startup
    await init_db()
    asyncio.create_task(mqtt_service.start(event_processor.process_mqtt_message))
    cleanup_task = asyncio.create_task(cleanup_old_detections())
    log.info("Background cleanup task started",
             retention_days=settings.maintenance.retention_days,
             enabled=settings.maintenance.cleanup_enabled)
    yield
    # Shutdown
    cleanup_running = False
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    await mqtt_service.stop()

app = FastAPI(title="Yet Another WhosAtMyFeeder API", version=APP_VERSION, lifespan=lifespan)

# Setup structured logging
log = structlog.get_logger()

# CORS configuration - Note: wildcard origins cannot be used with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(proxy.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(species.router, prefix="/api")
app.include_router(backfill.router, prefix="/api", tags=["backfill"])

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ya-wamf-backend", "version": APP_VERSION}

@app.get("/api/version")
async def get_version():
    """Return the application version info."""
    return {
        "version": APP_VERSION,
        "base_version": BASE_VERSION,
        "git_hash": GIT_HASH
    }

@app.get("/api/classifier/status")
async def classifier_status():
    """Return the status of the bird classifier model."""
    return classifier_service.get_status()

@app.get("/api/classifier/labels")
async def classifier_labels():
    """Return the list of species labels from the classifier model."""
    return {"labels": classifier_service.labels}

@app.post("/api/classifier/download")
async def download_default_model():
    """Download the default bird classifier model."""
    import httpx
    from pathlib import Path

    # TFLite bird classifier model URLs - using Google Coral EdgeTPU repo (reliable source)
    # The MobileNet V2 iNaturalist bird model recognizes ~965 bird species
    MODEL_URLS = [
        "https://raw.githubusercontent.com/google-coral/edgetpu/master/test_data/mobilenet_v2_1.0_224_inat_bird_quant.tflite",
    ]
    LABELS_URL = "https://raw.githubusercontent.com/google-coral/edgetpu/master/test_data/inat_bird_labels.txt"

    # Use persistent /data/models directory (volume mounted) for model storage
    # This ensures models survive container updates
    models_dir = Path("/data/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "model.tflite"
    labels_path = models_dir / "labels.txt"

    # Check if model already exists
    if model_path.exists() and labels_path.exists():
        log.info("Model already exists, skipping download", path=str(model_path))
        return {
            "status": "ok",
            "message": "Model already downloaded",
            "path": str(model_path)
        }

    # Headers to mimic a browser request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/octet-stream, */*',
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            # Try each model URL until one works
            model_content = None
            last_error = None

            for model_url in MODEL_URLS:
                try:
                    log.info("Trying to download model", url=model_url)
                    model_response = await client.get(model_url, headers=headers)
                    model_response.raise_for_status()

                    # Validate it's actually a TFLite file (not HTML)
                    content = model_response.content
                    if content[:4] == b'<htm' or content[:4] == b'<!DO' or len(content) < 1000:
                        log.warning("Downloaded content appears to be HTML, trying next URL")
                        continue

                    model_content = content
                    log.info("Model downloaded successfully", size=len(content), url=model_url)
                    break
                except httpx.HTTPStatusError as e:
                    last_error = f"HTTP {e.response.status_code} from {model_url}"
                    log.warning("Model URL failed", url=model_url, status=e.response.status_code)
                    continue

            if model_content is None:
                raise Exception(f"All model download URLs failed. Last error: {last_error}")

            with open(model_path, 'wb') as f:
                f.write(model_content)

            # Download labels
            log.info("Downloading labels...")
            labels_response = await client.get(LABELS_URL, headers=headers)
            labels_response.raise_for_status()
            with open(labels_path, 'wb') as f:
                f.write(labels_response.content)

        # Process labels to extract common names
        with open(labels_path, 'r') as f:
            lines = f.readlines()

        processed_labels = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if '(' in line and ')' in line:
                start = line.rfind('(') + 1
                end = line.rfind(')')
                common_name = line[start:end].strip()
                processed_labels.append(common_name)
            else:
                parts = line.split(' ', 1)
                processed_labels.append(parts[1] if len(parts) > 1 else line)

        with open(labels_path, 'w') as f:
            for label in processed_labels:
                f.write(f"{label}\n")

        # Reload the classifier
        classifier_service._load_model()

        log.info("Model downloaded and loaded successfully")
        return {
            "status": "ok",
            "message": f"Downloaded model with {len(processed_labels)} species",
            "labels_count": len(processed_labels)
        }
    except httpx.HTTPStatusError as e:
        log.error("Failed to download model - HTTP error", status=e.response.status_code, url=str(e.request.url))
        return {"status": "error", "message": f"HTTP {e.response.status_code}: Failed to download from {e.request.url}"}
    except Exception as e:
        log.error("Failed to download model", error=str(e))
        return {"status": "error", "message": str(e)}

@app.get("/metrics")
async def metrics():
    # Placeholder for Prometheus metrics
    return "events_processed_total 0\n"


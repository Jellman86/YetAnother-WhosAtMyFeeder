from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import asyncio

from app.database import init_db
from app.services.mqtt_service import MQTTService
from app.services.classifier_service import ClassifierService
from app.services.event_processor import EventProcessor
from app.routers import events, stream, proxy, settings as settings_router, species
from contextlib import asynccontextmanager

classifier_service = ClassifierService()
event_processor = EventProcessor(classifier_service)
mqtt_service = MQTTService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    asyncio.create_task(mqtt_service.start(event_processor.process_mqtt_message))
    yield
    # Shutdown
    await mqtt_service.stop()

app = FastAPI(title="Yet Another WhosAtMyFeeder API", version="2.0.0", lifespan=lifespan)

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

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ya-wamf-backend"}

@app.get("/api/classifier/status")
async def classifier_status():
    """Return the status of the bird classifier model."""
    return classifier_service.get_status()

@app.post("/api/classifier/download")
async def download_default_model():
    """Download the default bird classifier model."""
    import httpx
    from pathlib import Path

    # TFHub model URL - using the direct tfhub.dev URL which handles redirects properly
    MODEL_URL = "https://tfhub.dev/google/lite-model/aiy/vision/classifier/birds_V1/3?lite-format=tflite"
    LABELS_URL = "https://raw.githubusercontent.com/google-coral/edgetpu/master/test_data/inat_bird_labels.txt"

    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    model_path = assets_dir / "model.tflite"
    labels_path = assets_dir / "labels.txt"

    # Headers to mimic a browser request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            # Download model
            log.info("Downloading bird classifier model...")
            model_response = await client.get(MODEL_URL, headers=headers)
            model_response.raise_for_status()
            with open(model_path, 'wb') as f:
                f.write(model_response.content)
            log.info("Model downloaded", size=len(model_response.content))

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


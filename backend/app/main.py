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

@app.get("/metrics")
async def metrics():
    # Placeholder for Prometheus metrics
    return "events_processed_total 0\n"


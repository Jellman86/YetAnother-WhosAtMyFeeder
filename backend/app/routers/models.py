from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import List, Optional
from app.config import settings
from app.services.model_manager import model_manager
from app.models.ai_models import ModelMetadata, InstalledModel, DownloadProgress
from app.services.classifier_service import get_classifier
from app.auth import require_owner, AuthContext

router = APIRouter()

@router.get("/models/available", response_model=List[ModelMetadata])
async def get_available_models(auth: AuthContext = Depends(require_owner)):
    """List all models available for download. Owner only."""
    return await model_manager.list_available_models()

@router.get("/models/installed", response_model=List[InstalledModel])
async def get_installed_models(auth: AuthContext = Depends(require_owner)):
    """List all currently installed models. Owner only."""
    return await model_manager.list_installed_models()

@router.get("/models/families/resolved")
async def get_resolved_model_families(auth: AuthContext = Depends(require_owner)):
    """Resolve regional bird-model families from settings. Owner only."""
    return await model_manager.get_resolved_bird_model_families(
        country=settings.location.country,
        override=settings.classification.bird_model_region_override,
    )

@router.post("/models/{model_id}/download")
async def download_model(
    model_id: str,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_owner)
):
    """Download and install a specific model. Owner only."""
    # Run in background
    background_tasks.add_task(model_manager.download_model, model_id)
    return {"status": "pending", "message": f"Download started for {model_id}"}

@router.get("/models/download-status/{model_id}", response_model=Optional[DownloadProgress])
async def get_download_status(
    model_id: str,
    auth: AuthContext = Depends(require_owner)
):
    """Get the status of an ongoing model download. Owner only."""
    status = model_manager.get_download_status(model_id)
    if not status:
        return None
    return status

@router.post("/models/{model_id}/activate")
async def activate_model(
    model_id: str,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_owner)
):
    """Set a specific model as the active classifier. Owner only."""
    success = await model_manager.activate_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not installed")

    # Keep settings.classification.model in sync so config.json reflects the active model
    settings.classification.model = model_id
    await settings.save()

    # Reload the classifier in the background to prevent blocking API timeouts
    # when loading heavy models across multiple worker processes.
    classifier = get_classifier()
    background_tasks.add_task(classifier.reload_bird_model)

    return {"status": "success", "message": f"Model {model_id} activated"}

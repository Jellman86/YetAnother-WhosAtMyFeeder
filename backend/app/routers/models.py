from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
from app.services.model_manager import model_manager
from app.models.ai_models import ModelMetadata, InstalledModel, DownloadProgress
from app.services.classifier_service import get_classifier

router = APIRouter()

@router.get("/models/available", response_model=List[ModelMetadata])
async def get_available_models():
    """List all models available for download."""
    return await model_manager.list_available_models()

@router.get("/models/installed", response_model=List[InstalledModel])
async def get_installed_models():
    """List all currently installed models."""
    return await model_manager.list_installed_models()

@router.post("/models/{model_id}/download")
async def download_model(model_id: str, background_tasks: BackgroundTasks):
    """Download and install a specific model."""
    # Run in background
    background_tasks.add_task(model_manager.download_model, model_id)
    return {"status": "pending", "message": f"Download started for {model_id}"}

@router.get("/models/download-status/{model_id}", response_model=Optional[DownloadProgress])
async def get_download_status(model_id: str):
    """Get the status of an ongoing model download."""
    status = model_manager.get_download_status(model_id)
    if not status:
        return None
    return status

@router.post("/models/{model_id}/activate")
async def activate_model(model_id: str):
    """Set a specific model as the active classifier."""
    success = await model_manager.activate_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not installed")
    
    # Reload the classifier
    classifier = get_classifier()
    classifier.reload_bird_model()
    
    return {"status": "success", "message": f"Model {model_id} activated"}

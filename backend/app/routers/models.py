from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List
from app.services.model_manager import model_manager
from app.models.ai_models import ModelMetadata, InstalledModel
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
    # We run this in background as it might take time
    # For simplicity in this iteration, we await it to report immediate success/fail
    # In a real app, use a task queue or status endpoint
    success = await model_manager.download_model(model_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to download model")
    return {"status": "success", "message": f"Model {model_id} downloaded"}

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

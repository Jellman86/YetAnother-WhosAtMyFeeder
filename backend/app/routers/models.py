from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, JsonValue
from typing import List, Optional
from app.config import settings
from app.services.model_manager import model_manager
from app.services.model_validation import run_validation_probe
from app.models.ai_models import ModelMetadata, InstalledModel, DownloadProgress
from app.services.classifier_service import get_classifier
from app.auth import require_owner, AuthContext

router = APIRouter()


class ModelActionResponse(BaseModel):
    status: str
    message: str


class ModelValidateResponse(BaseModel):
    model_id: str
    ok: bool
    provider: str
    reason: str


@router.get("/models/available", response_model=List[ModelMetadata])
async def get_available_models(auth: AuthContext = Depends(require_owner)):
    """List all models available for download. Owner only."""
    return await model_manager.list_available_models()


@router.get("/models/installed", response_model=List[InstalledModel])
async def get_installed_models(auth: AuthContext = Depends(require_owner)):
    """List all currently installed models. Owner only."""
    return await model_manager.list_installed_models()


@router.get("/models/families/resolved", response_model=dict[str, dict[str, JsonValue]])
async def get_resolved_model_families(
    _auth: AuthContext = Depends(require_owner),
) -> dict[str, dict[str, JsonValue]]:
    """Resolve regional bird-model families from settings. Owner only."""
    return await model_manager.get_resolved_bird_model_families(
        country=settings.location.country,
        override=settings.classification.bird_model_region_override,
    )


@router.post("/models/{model_id}/download", response_model=ModelActionResponse)
async def download_model(model_id: str, background_tasks: BackgroundTasks, auth: AuthContext = Depends(require_owner)):
    """Download and install a specific model. Owner only."""
    # Run in background
    background_tasks.add_task(model_manager.download_model, model_id)
    return {"status": "pending", "message": f"Download started for {model_id}"}


@router.get("/models/download-status/{model_id}", response_model=Optional[DownloadProgress])
async def get_download_status(model_id: str, auth: AuthContext = Depends(require_owner)):
    """Get the status of an ongoing model download. Owner only."""
    status = model_manager.get_download_status(model_id)
    if not status:
        return None
    return status


@router.post("/models/{model_id}/validate", response_model=ModelValidateResponse)
async def validate_model(model_id: str, auth: AuthContext = Depends(require_owner)):
    """Validate an installed model on this host: run one frame through it and record
    whether it produced finite output here. Clears the selection gate on success.
    Restores the previously active model afterwards. Owner only.
    """
    installed = await model_manager.list_installed_models()
    target = next((m for m in installed if m.id == model_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Model not installed")
    if not target.ready:
        raise HTTPException(
            status_code=409,
            detail=f"Model install is incomplete ({target.reason}); download it before validating.",
        )

    # The probe trial-activates the candidate and restores the previously active model
    # (persisting it) before returning, so no extra reconciliation is needed here.
    return await run_validation_probe(model_id)


@router.post("/models/{model_id}/activate", response_model=ModelActionResponse)
async def activate_model(model_id: str, background_tasks: BackgroundTasks, auth: AuthContext = Depends(require_owner)):
    """Set a specific model as the active classifier. Owner only.

    Post-install selection gate: a model this host has never validated cannot be
    activated through the API — the caller must run `/validate` first. This guards
    every path (Model Manager, the settings picker, a raw POST), not just the UI.
    """
    installed = await model_manager.list_installed_models()
    target = next((m for m in installed if m.id == model_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Model not installed")
    if not target.validated:
        raise HTTPException(
            status_code=409,
            detail="This model has not been validated on your hardware yet. Run validation before selecting it.",
        )

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

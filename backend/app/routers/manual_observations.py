from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from app.auth import AuthContext, require_owner
from app.repositories.manual_observation_repository import ManualObservationDraft
from app.services.manual_observation_service import manual_observation_service
from app.utils.api_datetime import serialize_api_datetime


router = APIRouter(prefix="/manual-observations", tags=["manual observations"])


class ManualObservationPrediction(BaseModel):
    label: str
    score: float
    model_id: str | None = None
    model_name: str | None = None
    inference_provider: str | None = None
    inference_backend: str | None = None
    input_source: str | None = None
    input_is_cropped: bool | None = None
    scientific_name: str | None = None
    common_name: str | None = None
    taxa_id: int | None = None


class ManualObservationResponse(BaseModel):
    id: str
    status: Literal["queued", "analyzing", "ready", "failed", "saved"]
    media_type: Literal["image", "video"]
    original_filename: str
    content_type: str
    content_sha256: str
    size_bytes: int
    progress_current: int
    progress_total: int
    progress_percent: int
    progress_message: str | None = None
    predictions: list[ManualObservationPrediction] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    saved_event_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_source: Literal["image_metadata", "manual_pin"] | None = None
    preview_url: str
    media_url: str
    created_at: str | None = None
    updated_at: str | None = None


class ManualObservationConfirmRequest(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    camera_name: str = Field(default="Manual upload", max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    observed_at: datetime | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_source: Literal["image_metadata", "manual_pin", "none"] | None = None

    @model_validator(mode="after")
    def validate_location(self) -> "ManualObservationConfirmRequest":
        has_latitude = self.latitude is not None
        has_longitude = self.longitude is not None
        if has_latitude != has_longitude:
            raise ValueError("Latitude and longitude must be supplied together.")
        if self.location_source == "none" and (has_latitude or has_longitude):
            raise ValueError("A removed location cannot include coordinates.")
        if self.location_source == "manual_pin" and not (has_latitude and has_longitude):
            raise ValueError("A manual pin requires latitude and longitude.")
        return self


class ManualObservationSavedResponse(BaseModel):
    status: Literal["saved"]
    event_id: str
    detection_url: str


class ManualObservationDeleteResponse(BaseModel):
    status: Literal["deleted"]
    id: str


def _response(draft: ManualObservationDraft) -> ManualObservationResponse:
    total = max(0, draft.progress_total)
    current = max(0, min(draft.progress_current, total)) if total else 0
    percent = round(current / total * 100) if total else (100 if draft.status in {"ready", "saved"} else 0)
    predictions = []
    for item in draft.results or []:
        label = str(item.get("label") or "").strip()
        if label:
            predictions.append(
                ManualObservationPrediction(
                    label=label,
                    score=float(item.get("score") or 0),
                    **{
                        key: item.get(key)
                        for key in (
                            "model_id",
                            "model_name",
                            "inference_provider",
                            "inference_backend",
                            "input_source",
                            "input_is_cropped",
                            "scientific_name",
                            "common_name",
                            "taxa_id",
                        )
                        if item.get(key) is not None
                    },
                )
            )
    return ManualObservationResponse(
        id=draft.id,
        status=draft.status,
        media_type=draft.media_type,
        original_filename=draft.original_filename,
        content_type=draft.content_type,
        content_sha256=draft.content_sha256,
        size_bytes=draft.size_bytes,
        progress_current=current,
        progress_total=total,
        progress_percent=percent,
        progress_message=draft.progress_message,
        predictions=predictions,
        error_code=draft.error_code,
        error_message=draft.error_message,
        saved_event_id=draft.saved_event_id,
        latitude=draft.latitude,
        longitude=draft.longitude,
        location_source=draft.location_source,
        preview_url=f"/api/manual-observations/{draft.id}/preview",
        media_url=f"/api/manual-observations/{draft.id}/media",
        created_at=serialize_api_datetime(draft.created_at),
        updated_at=serialize_api_datetime(draft.updated_at),
    )


@router.post("", response_model=ManualObservationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_manual_observation(
    media: UploadFile = File(...), _auth: AuthContext = Depends(require_owner)
) -> ManualObservationResponse:
    return _response(await manual_observation_service.create(media))


@router.get("/{draft_id}", response_model=ManualObservationResponse)
async def get_manual_observation(
    draft_id: str, _auth: AuthContext = Depends(require_owner)
) -> ManualObservationResponse:
    return _response(await manual_observation_service.get(draft_id))


@router.post("/{draft_id}/retry", response_model=ManualObservationResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_manual_observation(
    draft_id: str, _auth: AuthContext = Depends(require_owner)
) -> ManualObservationResponse:
    return _response(await manual_observation_service.retry(draft_id))


@router.post("/{draft_id}/confirm", response_model=ManualObservationSavedResponse)
async def confirm_manual_observation(
    draft_id: str, body: ManualObservationConfirmRequest, _auth: AuthContext = Depends(require_owner)
) -> ManualObservationSavedResponse:
    event_id = await manual_observation_service.confirm(
        draft_id,
        label=body.label,
        camera_name=body.camera_name,
        notes=body.notes,
        observed_at=body.observed_at,
        latitude=body.latitude,
        longitude=body.longitude,
        location_source=body.location_source,
    )
    return ManualObservationSavedResponse(status="saved", event_id=event_id, detection_url=f"/events?event={event_id}")


@router.delete("/{draft_id}", response_model=ManualObservationDeleteResponse)
async def delete_manual_observation(
    draft_id: str, _auth: AuthContext = Depends(require_owner)
) -> ManualObservationDeleteResponse:
    await manual_observation_service.delete(draft_id)
    return ManualObservationDeleteResponse(status="deleted", id=draft_id)


@router.get("/{draft_id}/preview", response_class=Response)
async def preview_manual_observation(draft_id: str, _auth: AuthContext = Depends(require_owner)):
    draft = await manual_observation_service.get(draft_id)
    path = manual_observation_service.directory(draft.id) / "preview.jpg"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Preview unavailable.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.get("/{draft_id}/media", response_class=Response)
async def media_manual_observation(draft_id: str, _auth: AuthContext = Depends(require_owner)):
    draft = await manual_observation_service.get(draft_id)
    path = manual_observation_service.directory(draft.id) / draft.source_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Original media unavailable.")
    return FileResponse(path, media_type=draft.content_type, filename=draft.original_filename)

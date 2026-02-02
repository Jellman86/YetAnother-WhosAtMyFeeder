from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import secrets
import structlog
import httpx
from urllib.parse import urlencode

from app.config import settings
from app.auth import require_owner, AuthContext
from app.services.inaturalist_service import inaturalist_service, INAT_AUTHORIZE_URL, INAT_TOKEN_URL
from app.services.i18n_service import i18n_service
from app.utils.language import get_user_language
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

log = structlog.get_logger()
router = APIRouter(prefix="/inaturalist", tags=["inaturalist"])
_oauth_state_cache: dict[str, datetime] = {}
OAUTH_STATE_TTL = timedelta(minutes=10)


class InaturalistDraftRequest(BaseModel):
    event_id: str


class InaturalistDraftResponse(BaseModel):
    event_id: str
    species_guess: str
    taxon_id: Optional[int] = None
    observed_on_string: str
    time_zone: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place_guess: Optional[str] = None
    notes: Optional[str] = None
    snapshot_url: Optional[str] = None


class InaturalistSubmitRequest(BaseModel):
    event_id: str
    notes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place_guess: Optional[str] = None


class InaturalistStatusResponse(BaseModel):
    connected: bool
    user: Optional[str] = None


@router.get("/status", response_model=InaturalistStatusResponse)
async def inaturalist_status(auth: AuthContext = Depends(require_owner)):
    user = await inaturalist_service.refresh_connected_user()
    return InaturalistStatusResponse(connected=bool(user), user=user)


@router.get("/oauth/authorize")
async def inaturalist_authorize(request: Request, auth: AuthContext = Depends(require_owner)):
    lang = get_user_language(request)
    if not settings.inaturalist.enabled:
        raise HTTPException(status_code=400, detail=i18n_service.translate("errors.inat.disabled", lang))
    if not settings.inaturalist.client_id or not settings.inaturalist.client_secret:
        raise HTTPException(status_code=400, detail=i18n_service.translate("errors.inat.not_configured", lang))

    state = secrets.token_urlsafe(32)
    _oauth_state_cache[state] = datetime.utcnow() + OAUTH_STATE_TTL
    redirect_uri = f"{str(request.base_url)}api/inaturalist/oauth/callback"
    params = {
        "client_id": settings.inaturalist.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "write",
        "state": state
    }
    authorization_url = f"{INAT_AUTHORIZE_URL}?{urlencode(params)}"
    return {"authorization_url": authorization_url, "state": state}


@router.get("/oauth/callback")
async def inaturalist_callback(request: Request, code: str = Query(...), state: str = Query(None)):
    lang = get_user_language(request)
    if not state or state not in _oauth_state_cache:
        raise HTTPException(status_code=400, detail=i18n_service.translate("errors.inat.invalid_state", lang))
    expires_at = _oauth_state_cache.get(state)
    if expires_at and expires_at < datetime.utcnow():
        _oauth_state_cache.pop(state, None)
        raise HTTPException(status_code=400, detail=i18n_service.translate("errors.inat.state_expired", lang))
    _oauth_state_cache.pop(state, None)

    redirect_uri = f"{str(request.base_url)}api/inaturalist/oauth/callback"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                INAT_TOKEN_URL,
                data={
                    "client_id": settings.inaturalist.client_id,
                    "client_secret": settings.inaturalist.client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri
                }
            )
            resp.raise_for_status()
            token = resp.json()
    except Exception as e:
        log.error("inat_oauth_token_error", error=str(e))
        raise HTTPException(status_code=500, detail=i18n_service.translate("errors.inat.oauth_failed", lang, error=str(e)))

    access_token = token.get("access_token")
    if not access_token:
        raise HTTPException(status_code=500, detail=i18n_service.translate("errors.inat.oauth_failed", lang, error="missing token"))

    user_login = await inaturalist_service.fetch_user(access_token) or "inaturalist"
    await inaturalist_service.store_token(
        email=user_login,
        access_token=access_token,
        refresh_token=token.get("refresh_token"),
        token_type=token.get("token_type"),
        expires_in=token.get("expires_in"),
        scope=token.get("scope")
    )

    html = "<html><body><h3>iNaturalist connected.</h3><p>You can close this window.</p></body></html>"
    return HTMLResponse(content=html)


@router.delete("/oauth/disconnect")
async def inaturalist_disconnect(auth: AuthContext = Depends(require_owner)):
    deleted = await inaturalist_service.delete_token()
    return {"status": "ok", "deleted": deleted}


@router.post("/draft", response_model=InaturalistDraftResponse)
async def inaturalist_draft(request: Request, draft: InaturalistDraftRequest, auth: AuthContext = Depends(require_owner)):
    lang = get_user_language(request)
    if not settings.inaturalist.enabled:
        raise HTTPException(status_code=400, detail=i18n_service.translate("errors.inat.disabled", lang))

    async with get_db() as db:
        repo = DetectionRepository(db)
        det = await repo.get_by_frigate_event(draft.event_id)
        if not det:
            raise HTTPException(status_code=404, detail=i18n_service.translate("errors.inat.event_missing", lang))

        lat = settings.inaturalist.default_latitude or settings.location.latitude
        lon = settings.inaturalist.default_longitude or settings.location.longitude
        place_guess = settings.inaturalist.default_place_guess

        snapshot_url = f"{str(request.base_url)}api/frigate/{draft.event_id}/thumbnail.jpg"

        return InaturalistDraftResponse(
            event_id=draft.event_id,
            species_guess=det.display_name,
            taxon_id=det.taxa_id,
            observed_on_string=det.detection_time.isoformat(),
            time_zone="UTC",
            latitude=lat,
            longitude=lon,
            place_guess=place_guess,
            notes=None,
            snapshot_url=snapshot_url
        )


@router.post("/submit")
async def inaturalist_submit(request: Request, body: InaturalistSubmitRequest, auth: AuthContext = Depends(require_owner)):
    lang = get_user_language(request)
    if not settings.inaturalist.enabled:
        raise HTTPException(status_code=400, detail=i18n_service.translate("errors.inat.disabled", lang))

    token = await inaturalist_service.get_valid_token()
    if not token:
        raise HTTPException(status_code=400, detail=i18n_service.translate("errors.inat.not_connected", lang))

    async with get_db() as db:
        repo = DetectionRepository(db)
        det = await repo.get_by_frigate_event(body.event_id)
        if not det:
            raise HTTPException(status_code=404, detail=i18n_service.translate("errors.inat.event_missing", lang))

    lat = body.latitude if body.latitude is not None else (settings.inaturalist.default_latitude or settings.location.latitude)
    lon = body.longitude if body.longitude is not None else (settings.inaturalist.default_longitude or settings.location.longitude)
    place_guess = body.place_guess or settings.inaturalist.default_place_guess

    payload = {
        "observation[species_guess]": det.display_name,
        "observation[observed_on_string]": det.detection_time.isoformat(),
        "observation[time_zone]": "UTC",
    }
    if det.taxa_id:
        payload["observation[taxon_id]"] = str(det.taxa_id)
    if lat is not None and lon is not None:
        payload["observation[latitude]"] = str(lat)
        payload["observation[longitude]"] = str(lon)
    if place_guess:
        payload["observation[place_guess]"] = place_guess
    if body.notes:
        payload["observation[description]"] = body.notes

    try:
        obs = await inaturalist_service.create_observation(token["access_token"], payload)
        observation_id = None
        results = obs.get("results", [])
        if results:
            observation_id = results[0].get("id")
        if not observation_id:
            raise RuntimeError("missing observation id")

        image_bytes = await inaturalist_service.get_snapshot_bytes(body.event_id)
        if image_bytes:
            await inaturalist_service.upload_photo(token["access_token"], observation_id, image_bytes)

        return {"status": "ok", "observation_id": observation_id}
    except Exception as e:
        log.error("inat_submit_failed", error=str(e))
        raise HTTPException(status_code=500, detail=i18n_service.translate("errors.inat.submit_failed", lang, error=str(e)))

"""Owner-only, bounded representative-input checks for a quarantined profile."""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.auth import require_owner
from app.services.native_profile_probe import MAX_VIDEO_BYTES, finish_owned_io
from app.services.native_profile_revalidation import (
    RevalidationStatus,
    RevalidationView,
    native_profile_revalidation,
)
from app.utils.image_io import MAX_IMAGE_BYTES

router = APIRouter(
    prefix="/classifier/quarantine/revalidation", tags=["classifier"], dependencies=[Depends(require_owner)]
)
MAX_UPLOAD_BYTES = 3 * MAX_IMAGE_BYTES + MAX_VIDEO_BYTES + 1024 * 1024


class PrepareRevalidationRequest(BaseModel):
    profile_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_id: UUID


@router.get("", response_model=RevalidationView)
async def inspect_revalidation(response: Response) -> RevalidationView:
    response.headers["Cache-Control"] = "no-store"
    return await native_profile_revalidation.inspect()


@router.post("/prepare", response_model=RevalidationStatus)
async def prepare_revalidation(body: PrepareRevalidationRequest, response: Response) -> RevalidationStatus:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await native_profile_revalidation.prepare(body.profile_fingerprint, attempt_id=str(body.attempt_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{attempt_id}/cancel", response_model=RevalidationStatus)
async def cancel_revalidation(attempt_id: UUID, response: Response) -> RevalidationStatus:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await native_profile_revalidation.cancel(str(attempt_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


async def _bounded_stream(request: Request) -> AsyncIterator[bytes]:
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise MultiPartException("upload_limit")
        yield chunk


async def _upload_bytes(upload: UploadFile, limit: int) -> bytes:
    contents = await upload.read(limit + 1)
    if not contents or len(contents) > limit:
        raise HTTPException(413, "Choose nonempty photos up to 25 MiB each and a clip up to 32 MiB.")
    return contents


def _close_spools(parser: MultiPartParser) -> None:
    for file in parser._files_to_close_on_error:
        file.close()


@router.post("/{attempt_id}/inputs", response_model=RevalidationStatus)
async def upload_revalidation(attempt_id: UUID, request: Request, response: Response) -> RevalidationStatus:
    response.headers["Cache-Control"] = "no-store"
    identity = str(attempt_id)
    try:
        native_profile_revalidation.claim_upload(identity)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    parser = MultiPartParser(request.headers, _bounded_stream(request), max_files=4, max_fields=0)
    accepted = False
    try:
        form = await parser.parse()
        photos = form.getlist("images")
        clips = form.getlist("video")
        if (
            len(photos) != 3
            or len(clips) != 1
            or len(form.multi_items()) != 4
            or any(not isinstance(item, UploadFile) for item in [*photos, *clips])
        ):
            raise HTTPException(400, "Choose exactly three distinct bird photos and one short bird clip.")
        images = [await _upload_bytes(item, MAX_IMAGE_BYTES) for item in photos]
        video = await _upload_bytes(clips[0], MAX_VIDEO_BYTES)
        try:
            result = await native_profile_revalidation.start_prepared(identity, images, video)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        accepted = True
        return result
    except MultiPartException as exc:
        raise HTTPException(
            413 if exc.message == "upload_limit" else 400,
            "Diagnostic upload exceeds the total limit."
            if exc.message == "upload_limit"
            else "Invalid diagnostic upload.",
        ) from exc
    finally:
        # Parser cleanup does not cover disconnect/cancellation. Close every
        # private spool even when the client disappears midway through a part.
        try:
            await finish_owned_io(asyncio.create_task(asyncio.to_thread(_close_spools, parser)))
        finally:
            if not accepted:
                await native_profile_revalidation.abandon_upload(identity)

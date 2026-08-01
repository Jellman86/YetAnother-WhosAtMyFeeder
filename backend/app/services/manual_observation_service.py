from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import aiofiles
import aiosqlite
import cv2
import structlog
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import Detection, DetectionRepository
from app.repositories.manual_observation_repository import ManualObservationDraft, ManualObservationRepository
from app.services.classifier_service import get_classifier
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.utils.api_datetime import utc_naive_datetime, utc_naive_now
from app.utils.image_io import load_rgb_image
from app.utils.tasks import create_background_task


log = structlog.get_logger()
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 250 * 1024 * 1024
MAX_IMAGE_PIXELS = 80_000_000
DRAFT_RETENTION_DAYS = 7
ALLOWED_MEDIA = {
    "image/jpeg": ("image", ".jpg"),
    "image/png": ("image", ".png"),
    "image/webp": ("image", ".webp"),
    "video/mp4": ("video", ".mp4"),
    "video/quicktime": ("video", ".mov"),
    "video/webm": ("video", ".webm"),
}


class ManualObservationService:
    def __init__(self) -> None:
        self.base_dir = Path(os.getenv("DATA_DIR", "/data")) / "manual_observations"
        self._tasks: dict[str, asyncio.Task] = {}

    def directory(self, draft_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", draft_id):
            raise HTTPException(status_code=400, detail="Invalid observation ID")
        return self.base_dir / draft_id

    async def create(self, media: UploadFile) -> ManualObservationDraft:
        try:
            await self._purge_expired_drafts()
        except Exception as exc:
            log.warning("Expired manual-observation cleanup failed", error=str(exc))
        content_type = str(media.content_type or "").lower().split(";", 1)[0]
        media_spec = ALLOWED_MEDIA.get(content_type)
        if not media_spec:
            raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, WebP, MP4, MOV, or WebM file.")
        media_type, suffix = media_spec
        draft_id = uuid.uuid4().hex
        draft_dir = self.directory(draft_id)
        await asyncio.to_thread(draft_dir.mkdir, parents=True, exist_ok=False)
        source_filename = f"source{suffix}"
        source_path = draft_dir / source_filename
        size_limit = MAX_IMAGE_BYTES if media_type == "image" else MAX_VIDEO_BYTES
        digest = hashlib.sha256()
        size = 0
        try:
            async with aiofiles.open(source_path, "wb") as output:
                while chunk := await media.read(1024 * 1024):
                    size += len(chunk)
                    if size > size_limit:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{media_type.title()} exceeds the {size_limit // 1024 // 1024} MB limit.",
                        )
                    digest.update(chunk)
                    await output.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail="The uploaded file is empty.")
            await self._validate_and_create_preview(source_path, draft_dir / "preview.jpg", media_type)
            content_sha256 = digest.hexdigest()
            async with get_db() as db:
                repo = ManualObservationRepository(db)
                existing = await repo.get_by_hash(content_sha256)
                if existing:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message": "This media has already been uploaded.",
                            "draft_id": existing.id,
                            "event_id": existing.saved_event_id,
                        },
                    )
                draft = ManualObservationDraft(
                    id=draft_id,
                    status="queued",
                    media_type=media_type,
                    original_filename=Path(media.filename or f"observation{suffix}").name[:255],
                    content_type=content_type,
                    content_sha256=content_sha256,
                    size_bytes=size,
                    source_filename=source_filename,
                )
                try:
                    await repo.create(draft)
                except aiosqlite.IntegrityError as exc:
                    raise HTTPException(status_code=409, detail="This media has already been uploaded.") from exc
            self._start_analysis(draft_id)
            return draft
        except Exception:
            await asyncio.to_thread(shutil.rmtree, draft_dir, True)
            raise
        finally:
            await media.close()

    async def _validate_and_create_preview(self, source: Path, preview: Path, media_type: str) -> None:
        if media_type == "image":

            def validate_image() -> None:
                with Image.open(source) as image:
                    image.load()
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise HTTPException(status_code=413, detail="Image dimensions are too large.")
                    normalized = ImageOps.exif_transpose(image).convert("RGB")
                    normalized.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                    normalized.save(preview, "JPEG", quality=92, optimize=True)

            try:
                await asyncio.to_thread(validate_image)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=422, detail="The image could not be decoded safely.") from exc
            return

        def validate_video() -> None:
            capture = cv2.VideoCapture(str(source))
            try:
                if not capture.isOpened():
                    raise HTTPException(status_code=422, detail="The video could not be decoded safely.")
                frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
                if fps <= 0:
                    raise HTTPException(status_code=422, detail="The video duration could not be validated safely.")
                duration = frame_count / fps if frame_count > 0 else 0
                if duration > 180:
                    raise HTTPException(status_code=413, detail="Video exceeds the 3 minute limit.")
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise HTTPException(status_code=422, detail="The video could not be decoded safely.")
                height, width = frame.shape[:2]
                if width * height > MAX_IMAGE_PIXELS:
                    raise HTTPException(status_code=413, detail="Video dimensions are too large.")
                if frame_count <= 0:
                    decoded_frames = 1
                    maximum_frames = max(1, int(fps * 180))
                    while decoded_frames <= maximum_frames:
                        ok, _frame = capture.read()
                        if not ok:
                            break
                        decoded_frames += 1
                    if decoded_frames > maximum_frames:
                        raise HTTPException(status_code=413, detail="Video exceeds the 3 minute limit.")
                if not cv2.imwrite(str(preview), frame, [cv2.IMWRITE_JPEG_QUALITY, 92]):
                    raise HTTPException(status_code=422, detail="A video preview could not be generated.")
            finally:
                capture.release()

        await asyncio.to_thread(validate_video)

    async def _purge_expired_drafts(self) -> None:
        cutoff = utc_naive_now() - timedelta(days=DRAFT_RETENTION_DAYS)
        async with get_db() as db:
            repo = ManualObservationRepository(db)
            expired_ids = await repo.list_expired_unsaved_ids(cutoff)
            for draft_id in expired_ids:
                task = self._tasks.get(draft_id)
                if task and not task.done():
                    task.cancel()
                await repo.delete(draft_id)
        for draft_id in expired_ids:
            await asyncio.to_thread(shutil.rmtree, self.directory(draft_id), True)

    def _start_analysis(self, draft_id: str) -> None:
        existing = self._tasks.get(draft_id)
        if existing and not existing.done():
            return
        task = create_background_task(self._run_analysis(draft_id), name=f"manual_observation:{draft_id}")
        self._tasks[draft_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(draft_id, None))

    async def retry(self, draft_id: str) -> ManualObservationDraft:
        draft = await self.get(draft_id)
        if draft.status not in {"failed", "queued"}:
            raise HTTPException(status_code=409, detail="Only failed analyses can be retried.")
        async with get_db() as db:
            repo = ManualObservationRepository(db)
            await repo.mark_analyzing(draft_id)
            refreshed = await repo.get(draft_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Manual observation not found.")
        self._start_analysis(draft_id)
        return refreshed

    async def _run_analysis(self, draft_id: str) -> None:
        try:
            async with get_db() as db:
                repo = ManualObservationRepository(db)
                draft = await repo.get(draft_id)
                if not draft or draft.status == "saved":
                    return
                await repo.mark_analyzing(draft_id)
            classifier = get_classifier()
            source_path = self.directory(draft_id) / draft.source_filename
            if draft.media_type == "image":
                image = await asyncio.to_thread(load_rgb_image, source_path)
                results = await asyncio.wait_for(
                    classifier.classify_async_background(
                        image, camera_name="Manual upload", input_context={"is_cropped": False}
                    ),
                    timeout=float(settings.classification.video_classification_timeout_seconds),
                )
            else:

                async def progress_callback(current: int, total: int, *_args, **_kwargs) -> None:
                    async with get_db() as progress_db:
                        await ManualObservationRepository(progress_db).update_progress(
                            draft_id, int(current), int(total), "Choosing the strongest frames"
                        )

                results = await asyncio.wait_for(
                    classifier.classify_video_async(
                        str(source_path),
                        camera_name="Manual upload",
                        progress_callback=progress_callback,
                        input_context={"is_cropped": False},
                        propagate_worker_failure=True,
                    ),
                    timeout=float(settings.classification.video_classification_timeout_seconds),
                )
            if not results:
                raise RuntimeError("The classifier did not return a usable result.")
            async with get_db() as db:
                await ManualObservationRepository(db).mark_ready(draft_id, results[:10])
        except asyncio.CancelledError:
            async with get_db() as db:
                await ManualObservationRepository(db).mark_failed(
                    draft_id, "interrupted", "Analysis was interrupted. You can retry it safely."
                )
            raise
        except Exception as exc:
            log.exception("Manual observation analysis failed", draft_id=draft_id)
            async with get_db() as db:
                await ManualObservationRepository(db).mark_failed(
                    draft_id, "classification_failed", str(exc) or "Classification failed"
                )

    async def get(self, draft_id: str) -> ManualObservationDraft:
        self.directory(draft_id)
        async with get_db() as db:
            repo = ManualObservationRepository(db)
            draft = await repo.get(draft_id)
            task = self._tasks.get(draft_id)
            if draft and draft.status == "analyzing" and (task is None or task.done()):
                await repo.mark_failed(
                    draft_id,
                    "interrupted",
                    "Analysis was interrupted by a restart. The original is safe and can be retried.",
                )
                draft = await repo.get(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Manual observation not found.")
        return draft

    async def confirm(
        self, draft_id: str, *, label: str, camera_name: str, notes: str | None, observed_at: datetime | None
    ) -> str:
        draft = await self.get(draft_id)
        if draft.status == "saved" and draft.saved_event_id:
            return draft.saved_event_id
        if draft.status != "ready":
            raise HTTPException(status_code=409, detail="Finish analysis before saving this observation.")
        normalized_label = " ".join(label.split())[:255]
        if not normalized_label:
            raise HTTPException(status_code=422, detail="Choose or enter a species before saving.")
        taxonomy = await taxonomy_service.get_names(normalized_label)
        top_result = (draft.results or [{}])[0]
        matching = next(
            (
                item
                for item in (draft.results or [])
                if str(item.get("label", "")).casefold() == normalized_label.casefold()
            ),
            None,
        )
        score = float((matching or {}).get("score") or 1.0)
        classifier_score = float(top_result.get("score") or 0.0)
        event_id = f"manual_{draft_id}"
        detection = Detection(
            detection_time=utc_naive_datetime(observed_at) if observed_at else utc_naive_now(),
            detection_index=0,
            score=max(0.0, min(1.0, score)),
            display_name=normalized_label,
            category_name=normalized_label,
            frigate_event=event_id,
            camera_name=(" ".join(camera_name.split()) or "Manual upload")[:100],
            manual_tagged=True,
            scientific_name=taxonomy.get("scientific_name"),
            common_name=taxonomy.get("common_name"),
            taxa_id=taxonomy.get("taxa_id"),
            video_classification_score=classifier_score,
            video_classification_label=str(top_result.get("label") or normalized_label),
            video_classification_status="completed",
            video_classification_provider=top_result.get("inference_provider"),
            video_classification_backend=top_result.get("inference_backend"),
            video_classification_model_id=top_result.get("model_id"),
            video_classification_input_source=top_result.get("input_source"),
        )
        async with get_db() as db:
            detection_repo = DetectionRepository(db)
            if await detection_repo.get_by_frigate_event(event_id) is None:
                await detection_repo.create(detection)
                await detection_repo.update_video_classification(
                    event_id,
                    label=detection.video_classification_label,
                    score=classifier_score,
                    index=0,
                    status="completed",
                    provider=detection.video_classification_provider,
                    backend=detection.video_classification_backend,
                    model_id=detection.video_classification_model_id,
                    input_source=detection.video_classification_input_source,
                )
            await ManualObservationRepository(db).mark_saved(draft_id, event_id, notes)
        return event_id

    async def delete(self, draft_id: str) -> None:
        draft = await self.get(draft_id)
        if draft.status == "saved":
            raise HTTPException(status_code=409, detail="Delete the saved detection from the detections page.")
        task = self._tasks.get(draft_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with get_db() as db:
            await ManualObservationRepository(db).delete(draft_id)
        await asyncio.to_thread(shutil.rmtree, self.directory(draft_id), True)

    async def path_for_event(self, event_id: str, *, preview: bool) -> Path | None:
        if not event_id.startswith("manual_"):
            return None
        async with get_db() as db:
            draft = await ManualObservationRepository(db).get_by_event_id(event_id)
        if not draft:
            return None
        path = self.directory(draft.id) / ("preview.jpg" if preview else draft.source_filename)
        return path if path.is_file() else None

    async def delete_saved_event_media(self, event_id: str) -> None:
        if not event_id.startswith("manual_"):
            return
        async with get_db() as db:
            repo = ManualObservationRepository(db)
            draft = await repo.get_by_event_id(event_id)
            if not draft:
                return
            await repo.delete(draft.id)
        await asyncio.to_thread(shutil.rmtree, self.directory(draft.id), True)


manual_observation_service = ManualObservationService()

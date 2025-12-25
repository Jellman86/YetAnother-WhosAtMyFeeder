from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import structlog

from app.services.backfill_service import BackfillService
from app.services.classifier_service import ClassifierService

router = APIRouter()
log = structlog.get_logger()

# Initialize the classifier and backfill service
classifier = ClassifierService()
backfill_service = BackfillService(classifier)


class BackfillRequest(BaseModel):
    date_range: str = Field(
        default="week",
        description="Date range preset: 'day', 'week', 'month', or 'custom'"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date for custom range (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date for custom range (YYYY-MM-DD)"
    )
    cameras: Optional[List[str]] = Field(
        default=None,
        description="Optional list of cameras to backfill (defaults to configured cameras)"
    )


class BackfillResponse(BaseModel):
    status: str
    processed: int
    new_detections: int
    skipped: int
    errors: int
    message: str


@router.post("/backfill", response_model=BackfillResponse)
async def backfill_detections(request: BackfillRequest):
    """
    Fetch historical bird detections from Frigate and process them.

    This endpoint queries Frigate's event API for past bird detections,
    classifies them using the ML model, and saves new detections to the database.
    Existing detections (by frigate_event ID) are skipped to avoid duplicates.

    Date range options:
    - 'day': Last 24 hours
    - 'week': Last 7 days
    - 'month': Last 30 days
    - 'custom': Use start_date and end_date parameters
    """
    try:
        now = datetime.now()

        # Calculate date range
        if request.date_range == "day":
            start = now - timedelta(days=1)
            end = now
        elif request.date_range == "week":
            start = now - timedelta(weeks=1)
            end = now
        elif request.date_range == "month":
            start = now - timedelta(days=30)
            end = now
        elif request.date_range == "custom":
            if not request.start_date or not request.end_date:
                raise HTTPException(
                    status_code=400,
                    detail="start_date and end_date required for custom date range"
                )
            try:
                start = datetime.strptime(request.start_date, "%Y-%m-%d")
                end = datetime.strptime(request.end_date, "%Y-%m-%d")
                # Set end to end of day
                end = end.replace(hour=23, minute=59, second=59)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date format. Use YYYY-MM-DD"
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date_range: {request.date_range}. Use 'day', 'week', 'month', or 'custom'"
            )

        # Validate date range
        if start > end:
            raise HTTPException(
                status_code=400,
                detail="start_date must be before end_date"
            )

        # Run the backfill
        result = await backfill_service.run_backfill(start, end, request.cameras)

        # Build message
        if result.new_detections > 0:
            message = f"Added {result.new_detections} new detection(s)"
        else:
            message = "No new detections found"

        if result.skipped > 0:
            message += f", {result.skipped} already existed"

        if result.errors > 0:
            message += f", {result.errors} error(s)"

        return BackfillResponse(
            status="completed",
            processed=result.processed,
            new_detections=result.new_detections,
            skipped=result.skipped,
            errors=result.errors,
            message=message
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error("Backfill failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Backfill failed: {str(e)}")


import asyncio
import os
import sys
from datetime import datetime

# Add the app directory to the path
sys.path.append('/config/workspace/YA-WAMF/backend')

from app.services.classifier_service import get_classifier
from app.services.backfill_service import BackfillService

async def main():
    classifier = get_classifier()
    backfill_service = BackfillService(classifier)
    
    start = datetime(2026, 1, 4, 7, 30)
    end = datetime(2026, 1, 4, 7, 45)
    
    print(f"Running backfill from {start} to {end}")
    result = await backfill_service.run_backfill(start, end)
    print(f"Backfill complete: {result}")

if __name__ == "__main__":
    asyncio.run(main())

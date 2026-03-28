import asyncio
import os
import sys


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.database import close_db, init_db
from app.services.canonical_identity_repair_service import canonical_identity_repair_service


async def main() -> None:
    await init_db()
    try:
        summary = await canonical_identity_repair_service.run(batch_size=200)
        print(summary)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())

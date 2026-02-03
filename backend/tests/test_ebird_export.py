import pytest
import aiosqlite
import csv
import io
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.main import app
from fastapi.testclient import TestClient

@pytest.mark.asyncio
async def test_ebird_export_format():
    # We use a real app instance but need to mock the database and settings
    with patch("app.routers.ebird.get_db") as mock_get_db, \
         patch("app.routers.ebird.settings") as mock_settings:
        
        # Mock settings
        mock_settings.ebird.enabled = True
        mock_settings.location.latitude = 51.5074
        mock_settings.location.longitude = -0.1278
        
        # Mock DB
        async def mock_db_context():
            db = await aiosqlite.connect(":memory:")
            await db.execute("""
                CREATE TABLE detections (
                    id INTEGER PRIMARY KEY,
                    display_name TEXT,
                    scientific_name TEXT,
                    detection_time TIMESTAMP,
                    score FLOAT,
                    camera_name TEXT,
                    is_hidden BOOLEAN
                )
            """)
            await db.execute("""
                INSERT INTO detections (display_name, scientific_name, detection_time, score, camera_name, is_hidden)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("Blackbird", "Turdus merula", "2023-01-01 12:00:00", 0.95, "Garden", 0))
            await db.commit()
            return db

        # Set up the async context manager mock
        class AsyncMockContextManager:
            async def __aenter__(self):
                self.db = await mock_db_context()
                return self.db
            async def __aexit__(self, exc_type, exc, tb):
                await self.db.close()

        mock_get_db.return_value = AsyncMockContextManager()

        client = TestClient(app)
        # Mock authentication
        with patch("app.routers.ebird.get_auth_context_with_legacy", return_value=MagicMock(is_owner=True)):
            response = client.get("/api/ebird/export")
        
        assert response.status_code == 200
        content = response.text
        f = io.StringIO(content)
        reader = csv.reader(f)
        rows = list(reader)
        
        assert len(rows) == 1
        row = rows[0]
        
        # Verify 19 columns for eBird Record Format (Extended)
        assert len(row) == 19
        
        # Verify specific columns
        assert row[0] == "Blackbird"        # 1. Common Name
        assert row[1] == "Turdus"           # 2. Genus
        assert row[2] == "merula"           # 3. Species
        assert row[3] == "1"                # 4. Number
        assert "0.95" in row[4]             # 5. Species Comments (Confidence)
        assert "Garden" in row[5]           # 6. Location Name
        assert "51.5074" in row[6]          # 7. Latitude
        assert "-0.1278" in row[7]          # 8. Longitude
        assert row[8] == "01/01/2023"       # 9. Date
        assert row[9] == "12:00"            # 10. Start Time
        assert row[12] == "Incidental"      # 13. Protocol
        assert row[18] == "Exported from YA-WAMF" # 19. Submission Comments

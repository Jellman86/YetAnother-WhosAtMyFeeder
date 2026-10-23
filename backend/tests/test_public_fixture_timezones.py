"""UTC privacy routes must receive UTC-day evidence on every host timezone."""

import os
import time

import httpx
import pytest

from app.config import settings
from app.main import app
from test_audio_public_bounds_and_identity import bounded_audio as bounded_audio
from test_event_bird_summary_api import history as history
from test_guest_privacy_review import private_history as private_history


@pytest.mark.asyncio
@pytest.mark.skipif(not hasattr(time, "tzset"), reason="Host timezone switching requires tzset")
@pytest.mark.parametrize("host_timezone", ["Pacific/Kiritimati", "Etc/GMT+12"])
@pytest.mark.parametrize("fixture_name", ["private_history", "bounded_audio", "history"])
async def test_guest_today_fixtures_match_utc_routes_on_non_utc_hosts(
    monkeypatch, request, host_timezone, fixture_name
):
    previous_timezone = os.environ.get("TZ")
    monkeypatch.setenv("TZ", host_timezone)
    time.tzset()
    try:
        request.getfixturevalue(fixture_name)
        monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
        path = "/api/audio/history" if fixture_name == "bounded_audio" else "/api/events"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
            response = await client.get(path)
        assert response.status_code == 200, response.text
        if fixture_name == "bounded_audio":
            assert response.json()["total"] == 1
            assert response.json()["items"][0]["species"] == "Shared"
        else:
            names = {row["frigate_event"] for row in response.json()}
            if fixture_name == "private_history":
                assert names == {"visible"}
            else:
                assert {"flock", "unprocessed"} <= names
                assert "hidden-parent" not in names
    finally:
        if previous_timezone is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous_timezone
        time.tzset()

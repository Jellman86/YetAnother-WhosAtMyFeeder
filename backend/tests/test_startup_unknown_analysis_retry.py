import pytest


@pytest.mark.asyncio
async def test_scheduled_unknown_analysis_retries_until_frigate_recovers(monkeypatch):
    from app import main

    calls = 0
    sleeps = []

    async def fake_analysis():
        nonlocal calls
        calls += 1
        if calls < 3:
            return {"status": "deferred", "reason": "frigate_unavailable", "accepted": 0}
        return {"status": "queued", "accepted": 2}

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(main.settings.maintenance, "auto_analyze_unknowns", True)
    monkeypatch.setattr(main.settings_router, "_run_analyze_unknowns", fake_analysis)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main, "cleanup_running", True)

    assert await main._run_scheduled_unknown_analysis() is True
    await main._retry_scheduled_unknown_analysis()

    assert calls == 3
    assert sleeps == [main.UNKNOWN_ANALYSIS_RETRY_SECONDS] * 2


@pytest.mark.asyncio
async def test_scheduled_unknown_analysis_retry_is_bounded(monkeypatch):
    from app import main

    calls = 0

    async def fake_analysis():
        nonlocal calls
        calls += 1
        return {"status": "deferred", "reason": "frigate_unavailable", "accepted": 0}

    async def fake_sleep(seconds):
        assert seconds == main.UNKNOWN_ANALYSIS_RETRY_SECONDS

    monkeypatch.setattr(main.settings.maintenance, "auto_analyze_unknowns", True)
    monkeypatch.setattr(main.settings_router, "_run_analyze_unknowns", fake_analysis)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main, "cleanup_running", True)

    await main._retry_scheduled_unknown_analysis()

    assert calls == main.UNKNOWN_ANALYSIS_MAX_RETRIES

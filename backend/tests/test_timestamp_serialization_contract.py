from datetime import datetime, timedelta, timezone


def test_proxy_video_share_link_item_normalizes_aware_timestamps_to_explicit_utc():
    from app.routers import proxy

    item = proxy._build_video_share_link_item(
        (
            5,
            "event-1",
            "owner",
            "label",
            "2026-04-01T12:00:00Z",
            "2026-04-01T13:00:00Z",
            0,
        )
    )

    assert item.created_at == "2026-04-01T12:00:00Z"
    assert item.expires_at == "2026-04-01T13:00:00Z"
    assert item.remaining_seconds >= 0


def test_ai_router_serializer_emits_explicit_utc_for_naive_and_aware_datetimes():
    from app.routers import ai

    assert ai._serialize_timestamp(datetime(2026, 4, 1, 12, 0, 0)) == "2026-04-01T12:00:00Z"
    assert ai._serialize_timestamp(
        datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5)
    ) == "2026-04-01T12:05:00Z"

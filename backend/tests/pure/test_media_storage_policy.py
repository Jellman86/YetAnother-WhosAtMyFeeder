from app.services.media_storage_policy import CachedVisit, select_media_evictions


def visits():
    return [
        CachedVisit("old", "robin", "2026-01-01", 100),
        CachedVisit("new", "robin", "2026-01-03", 100),
        CachedVisit("favorite", "robin", "2026-01-02", 500, True),
        CachedVisit("tit", "tit", "2026-01-01", 100),
    ]


def test_species_cap_keeps_newest_and_exempts_favorites():
    assert select_media_evictions(visits(), per_species_maximum=1, max_bytes=0) == ["old"]


def test_byte_budget_cannot_delete_favorites_even_when_they_exceed_it():
    assert set(select_media_evictions(visits(), per_species_maximum=0, max_bytes=200)) == {"old", "new", "tit"}


def test_active_visit_is_protected_from_eviction():
    assert "old" not in select_media_evictions(
        visits(), per_species_maximum=1, max_bytes=1, protected_event_ids={"old"}
    )


def test_disabled_limits_leave_media_unchanged():
    assert select_media_evictions(visits(), per_species_maximum=0, max_bytes=0) == []

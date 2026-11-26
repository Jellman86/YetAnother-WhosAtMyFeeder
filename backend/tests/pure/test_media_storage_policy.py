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


def test_keep_photo_evicts_non_photo_media_and_skips_when_already_photo_only():
    items = [
        CachedVisit("old-confirmed-photo-only", "tit", "2026-01-01", 80, keep_photo=True, photo_bytes=80),
        CachedVisit("mid-confirmed-with-clip", "tit", "2026-01-02", 500, keep_photo=True, photo_bytes=80),
        CachedVisit("new-ordinary", "tit", "2026-01-03", 500),
    ]
    # Photo-only confirmed visit has nothing left to evict and does not eat a species cap slot.
    assert select_media_evictions(items, per_species_maximum=1, max_bytes=0) == ["mid-confirmed-with-clip"]


def test_byte_budget_subtracts_only_evictable_bytes_for_keep_photo_visits():
    items = [
        CachedVisit("confirmed-old", "tit", "2026-01-01", 500, keep_photo=True, photo_bytes=100),
        CachedVisit("ordinary-mid", "tit", "2026-01-02", 300),
        CachedVisit("ordinary-new", "tit", "2026-01-03", 300),
    ]
    # Total is 1100; budget is 650. Trimming confirmed-old frees 400 (leaving 100 photo),
    # bringing remaining to 700 > 650, so ordinary-mid (300) must also be evicted -> 400 <= 650.
    assert select_media_evictions(items, per_species_maximum=0, max_bytes=650) == ["confirmed-old", "ordinary-mid"]


def test_byte_budget_skips_photo_only_keep_photo_visits_without_evicting_them():
    items = [
        CachedVisit("confirmed-photo-only", "tit", "2026-01-01", 300, keep_photo=True, photo_bytes=300),
        CachedVisit("ordinary-new", "tit", "2026-01-02", 200),
    ]
    assert select_media_evictions(items, per_species_maximum=0, max_bytes=250) == ["ordinary-new"]

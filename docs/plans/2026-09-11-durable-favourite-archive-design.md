# Durable favourite archive and per-species snapshot floor — design

**Roadmap item:** [Durable media archive and retention floors](../../ROADMAP.md) (issue #178).
**Standards applied:** [Engineering standards](../../CLAUDE.md) §1 (data integrity), §2 (test-first), §3
(migrations); [Layout patterns](../standards/layout-patterns.md).
**Status:** Implemented on `dev`; maintained as the behavioural design record. See
[`docs/features/favourites.md`](../features/favourites.md) for the user-facing contract.

## 1. The promise being made

Today a favourite keeps its detection row and whatever happens to be in the media cache out of
retention cleanup. It does not fetch anything, it does not survive a cache clear, and it says
"favourite" the moment the star is pressed, whatever Frigate still holds. #178 asks for two things
and this design gives exactly those:

1. **A favourite is durable.** Favouriting a visit acquires its photograph and, where Frigate still
   has one, its clip into an archive that no cache operation touches. The star says so only once
   that is true, and says so honestly when it is not.
2. **Snapshots have a floor as well as a window.** Cached photographs are kept for an age window
   *and* the newest N per species are kept regardless of age. Clips are never fetched automatically.

## 2. What already exists (reuse, don't rebuild)

- `detection_favorites` (id, detection_id, created_by, created_at) is the favourite; every read joins
  it, so state stored on this row costs nothing extra to surface.
- `media_cache` owns `/config/media_cache/{snapshots,clips,previews}`, atomic writes, cleanup by age
  with a `protected_event_ids` exemption, orphan cleanup, and `clear_all`.
- `frigate_client.get_snapshot_with_error` (crop=1) and `download_clip_to_file` already distinguish
  "not there" (`clip_not_found`, `clip_not_retained`, `snapshot_not_found`) from transport failure.
- `full_visit_clip_service` is the model for a bounded background worker with per-event locks,
  failure cooldowns and a restart-safe reconcile pass.
- `run_cleanup` in `main.py` and `POST /cache/cleanup` both compute the protected set once from
  `get_favorite_frigate_event_ids()`; they gain one more source of protected ids.
- `DetectionRepository._canonical_key_sql` is the one definition of "same bird"; the per-species floor
  partitions by it, so a split or renamed taxon does not break the floor.

## 3. The archive

### 3.1 Location and layout

`ARCHIVE_DIR` (env, default `/config/archive`), a sibling of the media cache on the same persistent
volume, never inside it. One directory per visit:

```
/config/archive/<frigate_event>/
    snapshot.jpg            the photograph as stored at archive time (the crop when one exists)
    snapshot.meta.json      the media cache's metadata for it (source), copied verbatim
    clip.mp4                Frigate's event clip, when Frigate still had it
    recording.mp4           the full-visit recording, only if it was already cached (never fetched)
    manifest.json           what is here, byte sizes, when, and the app version that wrote it
```

Every file is written to a temporary name in the same directory and renamed into place after
`fsync`; `manifest.json` is written last, so a directory without a manifest is an unfinished
archive and is treated as absent. The directory name is the sanitised event id the media cache
already uses, so path containment is the same code.

### 3.2 State, on the favourite row

Migration adds to `detection_favorites`:

| column | values | meaning |
| --- | --- | --- |
| `archive_snapshot_state` | `pending` · `durable` · `unavailable` · `failed` | the photograph |
| `archive_clip_state` | `pending` · `durable` · `unavailable` · `failed` | the clip |
| `archive_bytes` | int, default 0 | total bytes on disk once durable |
| `archive_attempts` | int, default 0 | acquisition attempts so far |
| `archive_error` | text, nullable | the last reason code (`clip_timeout`, `disk_full`, ...) |
| `archived_at` | datetime, nullable | when the archive last became durable |
| `archive_updated_at` | datetime, nullable | last state change |

Existing favourites are migrated as `pending`/`pending` and picked up by the reconcile pass, so
an install's old favourites become durable without anyone pressing anything.

The API reports one derived `archive_state` per detection, alongside `is_favorite`:

- `durable` — snapshot durable, clip durable **or** unavailable (Frigate had no clip to give: that
  is an honest end state, not a failure);
- `unavailable` — neither the cache nor Frigate had anything; the row is still kept;
- `pending` — anything still to do;
- `failed` — an attempt that should have worked did not, and retries are exhausted or waiting;
- `null` — not a favourite.

Detail (`GET /api/events/{id}/archive`) carries both per-asset states, bytes, error, timestamps, and
whether a `recording.mp4` is present.

### 3.3 Acquisition

`archive_service` is a background worker with an in-process queue, one asyncio lock per event and
at most two downloads in flight (clips are large and Frigate is on the same LAN as everything else).

Favouriting enqueues the event. The worker, per event:

1. **Snapshot.** Copy the media cache's stored photograph and its metadata if present; otherwise
   fetch Frigate's cropped snapshot and record `source: frigate_snapshot`. `snapshot_not_found` ⇒
   `unavailable`. Anything else ⇒ `failed` with the reason.
2. **Clip.** Copy the cached event clip if present; otherwise `download_clip_to_file` straight into
   the archive's temporary name. `clip_not_found` / `clip_not_retained` ⇒ `unavailable`. A partial
   download (bytes below the minimum valid size, or the request failed part-way) is deleted and
   ⇒ `failed`.
3. **Recording.** If a full-visit recording is already cached, copy it. Never requested.
4. Write `manifest.json`, then the row: states, bytes, `archived_at`.

Before writing anything the worker checks free space on the archive volume; below a 256 MB
floor it records `failed` / `disk_full` without touching the disk. Failures back off (1, 5, 15, 60
minutes, then hourly) and stop after eight attempts; `POST /api/events/{id}/archive/retry` resets the
count. The worker also runs a reconcile pass at startup and every 30 minutes: every favourite in
`pending`, or `failed` and due, is queued. That is what makes the promise restart-safe.

If the visit is unfavourited while its archive is being written, the worker finishes the asset in
hand, notices the row is gone under the per-event lock, and removes the directory. Favouriting again
while a removal is in flight waits on the same lock, so the two cannot interleave.

### 3.4 What reads the archive

Media routes serve the cache when it has the file (the live photograph as currently chosen), then
the archive, then Frigate: `snapshot.jpg`, `clip.mp4`, `recording-clip.mp4`, and the About reel's
card image. A cleared cache or an expired Frigate event therefore changes nothing for a durable
favourite, which is the whole point. When the photograph is replaced (a candidate applied, or the
HQ pipeline settling at event end), a favourite's photograph state returns to `pending` and it is
archived again, so the archive never shadows a better choice.

A clip Frigate does not have yet is not the same as a clip it never had: while the visit is younger
than 24 hours a 404 leaves the clip `pending` for the next reconcile pass. Under the missing-event
policy's `delete` behaviour a favourite is marked missing instead of deleted.

### 3.5 What deletes it, and nothing else

- **Unfavouriting** removes the archive. The star's confirmation on a durable favourite says so and
  names the size. The visit stays in history.
- **Deleting the visit** removes the archive with it (the existing delete confirmation already says
  media goes too).
- **`Remove all favourites`** in maintenance removes every archive, and its confirmation says so.
- **Database reset** removes the archive along with everything else, and its confirmation says so.
  A reset is not a cache clear, and it is the one action that is meant to leave nothing behind.
- **Orphan sweep**: at startup and in the daily run, an archive directory whose event has no row is
  removed and logged with the reason. This only happens after a reset or a hand-edited database.

Age cleanup, orphan cleanup of the *cache*, `clear_all`, the missing-event policy and the media
integrity scan never touch `ARCHIVE_DIR`; a test proves each one.

## 4. The per-species floor

`media_cache.per_species_minimum` (int, default 0 = off; env `MEDIA_CACHE__PER_SPECIES_MINIMUM`).
When set, the newest N visible detections of each canonical species are protected from **age**
cleanup of both the detection row (`delete_older_than`) and the cached snapshot. Clips are not
protected by the floor; they follow the age window. Hidden detections do not count towards N and
are not protected by it.

The protected set is computed once per cleanup run by a repository query that partitions by
`_canonical_key_sql` and takes `ROW_NUMBER() <= N`, and is passed to the same
`protected_event_ids` argument the favourites use, so the two protections compose and the cleanup
code has one exemption path.

## 5. Storage and visibility

- `GET /api/cache/stats` gains the archive's count, bytes and per-state counts from the favourite
  rows, which record bytes as they are written; the endpoint is polled every minute and must not
  walk the directory tree.
- Settings → Data: the archive line under the media cache usage, the per-species minimum field,
  and the failed-archive count with a retry-all action.
- Detection record: the favourite control shows the archive state (pending, durable with size,
  photo only, failed with retry). The Explorer's favourite marker is unchanged.
- Backup and restore are one paragraph in the feature doc: copy the database and `/config/archive`
  together; the archive is plain files named by event id.

## 6. Implementation outline (test-first)

**Backend, slice 1 — archive**
1. Migration: the seven columns on `detection_favorites`; upgrade/downgrade/upgrade proven.
2. `archive_service`: layout, atomic writes, manifest, disk-pressure check, acquisition, backoff,
   reconcile, removal; tests use a temp `ARCHIVE_DIR` and a stubbed Frigate client, covering: no
   clip in Frigate (unavailable, favourite still durable), partial download (failed, no stray
   file), disk full (failed, nothing written), restart mid-way (manifest missing ⇒ re-acquired),
   unfavourite during acquisition (directory removed, no leak), concurrent favourite/unfavourite.
3. Wire favourite/unfavourite/delete/clear-favourites/reset; `archive_state` on responses and SSE.
4. Media routes prefer the archive; a test clears the cache and still serves the favourite.
5. Cleanup-order tests: age cleanup, orphan cleanup, clear_all, missing-event policy leave the
   archive alone; the orphan sweep removes only rowless directories.

**Backend, slice 2 — floor**
6. `media_cache.per_species_minimum` config, env, settings round-trip; repository floor query with a
   canonical-taxon test (two names, one taxon, one floor); `run_cleanup` and `/cache/cleanup` pass
   the union.

**Frontend, slice 3**
7. `archive_state` in the API types; favourite control states; unfavourite confirmation on a
   durable favourite; Settings fields and usage; nine locales; layout tests.

**Docs, slice 4**
8. `docs/features/favourites.md` (what durable means, states, backup/restore, what deletes it),
   `docs/api.md` endpoints, ROADMAP status, CHANGELOG.

## 7. Acceptance criteria (from the roadmap, made checkable)

- Archive writes are atomic and restart-safe: a manifest-less directory is never served and is
  completed by reconcile.
- A favourite reports `pending` until its requested assets are durable or honestly unavailable.
- Cache clear, age cleanup, orphan cleanup and the missing-event policy cannot remove archived media.
- Storage use is visible; every destructive action names the archive in its confirmation.
- Per-species floors are canonical-taxon based and protect rows as well as cached snapshots.
- Backup/restore is documented.
- Tests cover Frigate expiry, concurrent favourite/unfavourite, partial downloads, cleanup order,
  and disk-pressure failure.

## 8. Out of scope

- Fetching full-visit recordings automatically (the floor and the archive only copy one that is
  already cached).
- A second storage tier or remote/offsite archive.
- Archiving audio detections.

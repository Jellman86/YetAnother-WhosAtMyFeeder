# Favourites

A favourite is a visit you want to keep. Pressing the star on a detection does three things:

1. keeps the detection row out of age-based cleanup;
2. archives the visit's photograph and clip into a place no cache operation touches;
3. tells you, on the record, whether that archive is actually there yet.

## What the star says

Beside the star on a favourite you will see one of:

| State | Meaning |
| --- | --- |
| **Archiving photo and clip** | The archive worker is copying or fetching the assets. |
| **Archived, 3.2 MB** | The photograph and clip are on disk in the archive. |
| **Photo archived, no clip to keep** | The photograph is archived; Frigate had no clip for this visit (it was never recorded, or it had already rotated). This is a finished state, not an error. |
| **Nothing left to archive** | Neither the media cache nor Frigate had anything for this visit. The row is still kept. |
| **Archive failed** | Something that should have worked did not (a timeout, a full disk, a truncated download). The worker retries with backoff; **Try again** retries now. |

A favourite is only reported as archived once its files are written and the archive's manifest is
in place. An archive interrupted by a restart is finished by the worker's reconcile pass, which runs
at startup and every half hour and also picks up favourites made before this feature existed.

## Where the archive lives

`ARCHIVE_DIR` (default `/config/archive`), a sibling of `/config/media_cache` on the same
persistent volume. One directory per visit, named by its event id:

```
/config/archive/<frigate_event>/
    snapshot.jpg          the photograph as stored at the time (the crop, when there is one)
    snapshot.meta.json    where that photograph came from
    clip.mp4              Frigate's event clip, when Frigate still had it
    recording.mp4         the full-visit recording, only if it was already cached
    manifest.json         what is here and when it was written
```

The photograph and clip routes serve the media cache when it has the file, then the archive, then
Frigate, so a favourite looks the same after a cache clear or after Frigate has rotated the event,
and choosing a different photograph for a favourite is archived again behind it.

A visit favourited while it is still happening shows **Archiving photo and clip** until Frigate has
written the clip, which it does after the event ends; the worker checks again on its half-hourly
pass. Under the missing-event policy's *delete* setting a favourite is marked missing instead of
deleted, so a Frigate rotation never removes a favourite or its archive.

## What removes an archive

Only these:

- **Unfavouriting** the visit. The confirmation names the size. The visit stays in history.
- **Deleting** the visit.
- **Remove all favourites** in Settings, and a **database reset**. Both say so.

Age cleanup, orphan cleanup, **Clear cached files**, the media integrity scan and the
missing-event policy never touch the archive.

## Backup and restore

Back up the database file and `/config/archive` together. The archive is plain files named by
event id, so a restore is a copy: put the directory back beside the database and the favourites
are served again. A directory without `manifest.json` is treated as unfinished and re-acquired if
the visit is still a favourite.

## The per-species floor

**Settings → Data → Keep the newest per species** keeps the newest N visits of each species, and
their cached photographs, through age-based cleanup, however old they are. It is off (0) by
default. The floor is counted per canonical species, so a bird under two names has one floor, and
hidden visits neither count towards it nor are held by it. Clips are not held by the floor; they
follow the age window as before. The same setting is `MEDIA_CACHE__PER_SPECIES_MINIMUM`.

## Storage

**Settings → Data** shows archived favourites (count and size) apart from the cache size, and how
many could not be archived. The archive is never cleaned automatically, so its size is a choice
you make one star at a time.

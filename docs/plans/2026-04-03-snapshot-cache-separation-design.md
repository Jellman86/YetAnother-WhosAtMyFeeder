# Snapshot Cache Separation Design

## Problem

YA-WAMF currently treats Frigate `thumbnail.jpg` and `snapshot.jpg` as interchangeable in the backend cache. That is incorrect. The thumbnail route can write a low-resolution thumbnail into the shared snapshot cache, and later `/snapshot.jpg` requests will serve that cached low-resolution image as if it were the full event snapshot.

This is visible on event `1775114887.077327-sq0kd0`, where:

- the cached snapshot file is only `175x175`
- `/thumbnail.jpg` and `/snapshot.jpg` both serve the same `5312`-byte payload
- the full recording clip exists at `2560x1920`, so the event has enough source material for a much better still

## Goals

- Prevent thumbnail requests from poisoning the full snapshot cache
- Keep detection cards fast by preserving a thumbnail-oriented route
- Ensure higher-detail surfaces use the full snapshot contract
- Self-heal already-poisoned cached snapshots when the backend can detect them

## Recommended Approach

1. Separate thumbnail and snapshot cache entries in the backend media cache.
2. Keep `thumbnail.jpg` for explorer/dashboard card imagery.
3. Switch the detection modal media image to `snapshot.jpg`.
4. Add self-heal logic in the snapshot proxy path:
   - if the cached "snapshot" is clearly thumbnail-sized, evict it
   - fetch the true Frigate snapshot or serve the upgraded snapshot path instead

## Why This Approach

This is the smallest change that fixes the actual contract bug instead of hiding it. Disabling thumbnail cache would avoid poisoning but would throw away useful caching and keep the architecture muddled. Separating the cache entries preserves intent:

- thumbnail cache: optimized for card/list views
- snapshot cache: canonical event still, eligible for high-quality upgrade

## Error Handling

- Missing thumbnail cache: fetch Frigate thumbnail and store in thumbnail cache only
- Missing snapshot cache: fetch Frigate snapshot and store in snapshot cache only
- Poisoned cached snapshot: evict and refetch instead of serving low-resolution data forever
- HQ snapshot replacement continues to target the canonical snapshot cache only

## Testing Strategy

- Backend regression: thumbnail requests must not overwrite the snapshot cache
- Backend regression: poisoned cached snapshot gets evicted/refetched on `/snapshot.jpg`
- UI regression: detection modal uses `getSnapshotUrl(...)`, not `getThumbnailUrl(...)`
- Focus verification on proxy/media-cache tests plus the modal layout test

# Canonical Full-Visit Clip Design

**Date:** 2026-04-02

**Problem**

YA-WAMF currently exposes two overlapping playback concepts for the same detection:

- the canonical event clip on `/api/frigate/{event_id}/clip.mp4`
- the persisted full-visit recording on `/api/frigate/{event_id}/recording-clip.mp4`

The backend already promotes persisted full visits in some paths, but the UI still treats the two variants as separate user-facing choices. That creates unreliable player behavior, extra store state, and auth/public inconsistencies.

**Goals**

- Make `/clip.mp4` the only playback URL the UI cares about.
- Keep authenticated and guest/public playback behavior identical.
- Use the short event clip only as a temporary fallback before a full visit exists.
- Once a full visit is fetched or auto-generated, promote it to the canonical clip for that event and remove the user-facing variant choice.
- Preserve a visible UI indicator when the canonical clip is a promoted full visit.

**Non-Goals**

- No change to the fetch/reconcile/auto-generation pipeline itself.
- No change to public-access authorization rules for whether an event is viewable.
- No need to remove the backend `recording-clip` route if it still supports fetch/probe internals.

**Recommended Approach**

Adopt a single canonical playback contract:

1. The UI always plays `/api/frigate/{event_id}/clip.mp4`.
2. Before promotion, `/clip.mp4` resolves to the short Frigate event clip.
3. After manual fetch or automatic generation, `/clip.mp4` resolves to the persisted `{event_id}_recording.mp4` full visit.
4. The UI never offers a clip-vs-full-visit toggle.
5. The UI shows a passive indicator when the currently served canonical clip is a promoted full visit.

**Backend Contract**

- `/api/frigate/{event_id}/clip.mp4` remains the public playback route for all users.
- When a valid persisted recording clip exists, `/clip.mp4` serves it as the canonical asset.
- When it does not exist, `/clip.mp4` falls back to the short event clip.
- The separate `/recording-clip.mp4` route may remain for capability checks, internal fetches, and legacy compatibility, but it is no longer a UI playback concern.
- Authenticated and unauthenticated callers use the same clip-selection logic once they are authorized to see the event.

**UI Contract**

- Remove the client-side “prefer full visit” state and any playback variant switching.
- Keep a single optional action before promotion: `Fetch full clip`.
- Once promotion succeeds, the fetch action disappears because the canonical clip is now the full visit.
- Add a compact visible badge or indicator near the video UI when the canonical clip is a promoted full visit.
- The same indicator appears for authenticated and guest/public viewers whenever the canonical clip is promoted.

**Data / State Impact**

- The `full-visit` store should stop modeling playback preference and instead model capability/readiness only.
- Detection cards and modals should derive:
  - whether a full visit can be fetched
  - whether a full visit has been promoted
- Video source selection should collapse to a single canonical clip URL helper.

**Risks**

- Leaving old toggle code in place would continue to fight the canonical route and create ambiguous state.
- Guest/public pages may still have separate rendering branches that accidentally hide the promoted indicator.
- Tests that assert direct `recording-clip.mp4` usage will need to be rewritten around canonical `/clip.mp4` behavior.

**Acceptance Criteria**

- The player no longer offers a short-clip/full-visit toggle.
- Both authenticated and unauthenticated viewers use the same `/clip.mp4` route.
- When no full visit exists, `/clip.mp4` plays the short event clip.
- When a full visit exists, `/clip.mp4` plays the promoted full visit instead.
- The UI visibly indicates when the canonical clip is a promoted full visit.

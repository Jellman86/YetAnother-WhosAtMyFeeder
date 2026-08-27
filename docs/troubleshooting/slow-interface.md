# The interface is slow, or a page never loads

If the dashboard takes ten or twenty seconds, Settings is slow to populate, live updates keep
dropping, or a page sits loading and never arrives, the usual cause is not a slow query. It is the
server waiting for a database connection that something else is holding.

## What is happening

YA-WAMF keeps a small pool of database connections (five by default) and serves every request from
it. A request is meant to hold one only while it is running statements. If something holds one
while it waits on Frigate, on the weather archive, on iNaturalist, on an AI model or on image
classification, that connection is unavailable to everyone else for as long as that call takes.

With five connections, a handful of those at once leaves nothing for the page you are looking at.
Requests queue, the browser times out, and the live-updates stream drops with them.

## Confirming it

Open **Settings → Diagnostics** and generate a bundle, or read the health endpoint directly:

```bash
curl -fsS http://localhost:8000/health | jq .db_pool
```

The fields that matter:

| Field | What it tells you |
| --- | --- |
| `acquire_wait_max_ms` | How long a request recently waited for a connection. Anything in the seconds means requests are queueing. |
| `hold_ms_max` | The longest a connection was recently held. This is the cause; the wait above is the effect. |
| `slow_hold_last_label` | The module and function that held one too long, for example `app.routers.ai:analyze_event`. |
| `checked_out` | Connections in use right now, out of `pool_size`. |
| `acquire_timeouts` | Requests refused because no connection came free. A non-zero count means the pool ran dry. |
| `longest_active_hold_label` | What is holding a connection at this moment. Useful while a stall is happening. |
| `nested_acquires` | Times a request already holding a connection asked for a second. This is the shape that can deadlock a small pool; `last_nested_acquire_label` names the code. |

Both `acquire_wait_max_ms` and `hold_ms_max` cover the last five minutes, so they fall back to
normal once the problem passes. The `*_lifetime_max` fields keep the all-time peak for context and
do not affect health status.

The backend log carries the same information:

```
Slow DB connection hold   held_ms=12043.2  held_by=app.routers.ai:analyze_event  pool_size=5
```

## What to do

**If `slow_hold_last_label` names a handler**, that handler is holding a connection through work
that does not need one. Report it with the label and the bundle; it is a bug in that handler.

**If `acquire_timeouts` is climbing and requests return 503**, the pool is saturated rather than
blocked by one offender. Consider whether background work is set too high:

- **Settings → Detection → deep video analysis concurrency** defaults to `1`. Raising it lets more
  video jobs run at once, and each one uses the same shared pool. Values well above the pool size
  put background work and the interface in direct competition.
- `DB_POOL_SIZE` raises the pool itself. Each connection carries its own 64 MB page cache, so five
  connections is roughly 320 MB of headroom; raising it costs memory in proportion, and SQLite does
  not write faster with more connections.

**Detections are never refused.** Ingesting a Frigate event or a BirdNET-Go detection always waits
for a connection, however long that takes, because each is delivered once and dropping one would
lose a sighting. A saturated pool can therefore delay a detection appearing, but will not lose it.

**If you would rather wait than be refused**, set `DB_POOL_ACQUIRE_TIMEOUT_SECONDS=0`. Requests then
queue indefinitely instead of returning 503. This makes the stall silent again, so prefer it only
on hardware slow enough that the default sixty seconds is genuinely too short.

## What this is not

- **It is not the size of your history.** Filtering and paging are indexed; a large database is not
  by itself a cause here.
- **It is not the species filter being slow to query.** That was a separate, earlier problem in how
  the filter matched names, fixed in its own right.
- **It is not a corrupted database.** Nothing here damages stored detections; the symptom is
  contention for connections, and it clears when the work holding them completes.

## Known remaining cause

Six read paths still resolve species names while holding a connection, so the first time a species
is displayed in a language it has not been shown in before, that path can hold a connection for up
to ten seconds waiting on iNaturalist. It is bounded to the first sighting per species per language
and clears as the cache fills. `ISSUES.md` lists them. If `slow_hold_last_label` names one of those
and the wait was around ten seconds, that is this, and it will not recur for the same species.

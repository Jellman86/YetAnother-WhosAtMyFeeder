# The interface is slow, or a page never loads

If the dashboard takes ten or twenty seconds, Settings is slow to populate, live updates keep
dropping, or a page sits loading and never arrives, check whether the server is waiting for
database connections before changing worker counts.
Database contention is one possible cause; network outages, a busy inference queue and failed
page requests need separate checks in [Diagnostics](diagnostics.md).

## What is happening

YA-WAMF keeps a small pool of database connections (five by default) and serves every request from
it. A request is meant to hold one only while it is running statements. If something holds one
while it waits on Frigate, on the weather archive, on iNaturalist, on an AI model or on image
classification, that connection is unavailable to everyone else for as long as that call takes.

With five connections, a handful of those at once leaves nothing for the page you are looking at.
Requests queue, the browser times out, and the live-updates stream drops with them.

## Confirming it

Open **Settings → Health** and generate a diagnostics bundle, or read the health endpoint directly:

```bash
curl -fsS http://localhost:9852/health | jq .db_pool
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

- `CLASSIFICATION__BACKGROUND_WORKER_COUNT` controls video concurrency (one when unset, at most
  four). Raising it adds model copies and competing background work; it is not a database fix.
  The legacy `video_classification_max_concurrent` field is ignored. Start with one and compare
  queue waiting ages, memory and database holds before increasing it. See
  [maintenance concurrency](../setup/configuration.md#maintenance-concurrency).
- `DB_POOL_SIZE` raises the pool itself. Each connection carries its own 64 MB page cache, so five
  connections is roughly 320 MB of headroom; raising it costs memory in proportion, and SQLite does
  not write faster with more connections.

Durable ingestion uses an unbounded database-acquisition wait so this pool timeout does not
refuse a sighting. That is not a guarantee against every source of lost events: a network outage,
a stopped process, unavailable snapshots or admission limits can still affect ingestion. A
saturated pool can delay a detection appearing; check MQTT and classifier evidence separately.

**If you would rather wait than be refused**, set `DB_POOL_ACQUIRE_TIMEOUT_SECONDS=0`. Requests then
queue indefinitely instead of returning 503. This makes the stall silent again, so prefer it only
on hardware slow enough that the default sixty seconds is genuinely too short.

## Include the evidence

Report the exact build, `slow_hold_last_label`, recent wait/hold values and a fresh diagnostics
bundle while the stall is happening. Do not assume that one old list of slow handlers identifies
a current regression: name lookups, cache state and background workload can differ between runs.

# Background admission contention and cancellation review

Date: 19 October 2026. Baseline: `c2292cf2` on `dev`.

## Problem and evidence

A bounded operational backfill processed 59 events in 366 seconds: four added,
one updated, 53 skipped and one `background_image_overloaded` error. Two
attempt-level overload diagnostics concerned the same event. The retained
admission trace records other background requests completing around the second
timeout, including another completion about 94 milliseconds after that timeout.
It does not identify the producing caller for each request. No new native crash,
worker restart, retirement or circuit opening was observed. No live Frigate
traffic arrived during the 30-minute observation, so concurrency and sustained
capacity remain unqualified.

A disposable characterization uses the real admission coordinator and backfill
retry wrapper with a controlled event-processing boundary and async runners in
place of network, model and database work. Healthy
work holds the background slot while two short admission attempts expire. The
backfill reports overload, the active work finishes normally, and subsequent work
succeeds. Time budgets are shortened for the fixture. This confirms the bounded
overload contract; it does not establish a scheduler defect or justify changing
production queue limits and deadlines.

Source review identified a separate concrete defect. `submit()` shields its
internal admission future. Cancelling the caller while queued left its work item
in the deque. The request could later run despite having no remaining caller,
retain its inputs, and occupy capacity wanted by useful work. Four regressions
failed on unchanged code: live/background requests cancelled explicitly or by
an enclosing `asyncio.timeout` all remained queued. Cancellation is not established
as the cause of the operational timeout above.

## Requirements and implementation

- A caller cancelled before admission leaves its queue and never runs. Count it
  as rejected with reason `caller_cancelled`, distinct from queue timeout.
- Cancel both unclaimed internal futures for queued work and reconsider pending
  admission immediately, so cancelled live demand cannot retain false pressure.
- Serialize cancellation against admission through the coordinator condition.
  If admission has already won, preserve the runner and its capacity ownership.
- Keep admitted work under its existing completion and lease cleanup. Do not
  reclaim a native slot just because its caller stopped waiting. Consume a later
  unclaimed result exception so it does not become an unhandled-future warning.
- Retain live preference, starvation relief, all capacities, queue/lease budgets,
  backfill retry limits, retirement ordering and crash quarantine.

Tests cover queued cancellation in both lanes and both cancellation modes,
cancellation after admission, cancellation during handoff, later runner failure
and lease expiry without unclaimed exceptions, and bounded healthy background
contention through the backfill retry wrapper.

## Second-order effects and limits

Rejected counters now include cancelled queued submissions. Existing outcome
records identify the cause; no API shape or telemetry schema changes. Running
counts and completed/failed outcomes remain authoritative for admitted work,
even when its caller is gone. A caller cancelled at the admission boundary can
therefore still see its already-admitted work finish.

Queued frames are eligible for release sooner and stop creating avoidable
contention. This does not preempt active inference, add throughput, repair an
unreaped worker, or guarantee every backfill event will acquire capacity.
Existing lease cleanup remains responsible for genuinely stuck admitted work.

No database, settings, model, precision, detection admission policy or deployment
change is included. No new production backfill or synthetic MQTT replay was used
for this investigation. Operational evidence remains private and contains no
photographs or credentials in this document. Issues #712, #490 and #576 retain
their outstanding affected-host and sustained-traffic requirements.

## Verification

The four queued-cancellation cases failed first. The focused admission/backfill
suite passed 33 tests, including existing lease reclamation and stale-result
checks. The final full backend gate passed **5,994 tests, 54 skipped**, with
**79% coverage**, successful process exit and 453.30 seconds for pytest.
Repository-wide Ruff lint/format, documentation consistency (219 routes) and
whitespace checks pass. No frontend or API contract changed.

Independent review approved the implementation with no blocking findings. It
independently reproduced unwanted execution on the baseline and its removal by
the fix, exercised shutdown/cancellation ordering in both directions, repeated
the cancellation/handoff tests eight times, and checked late failure and lease
expiry after a caller leaves. Its optional suggestions were addressed: document
the invariant that condition-protected sections never suspend while holding the
lock, and retain failure/lease-expiry coverage in the committed tests. Deliberately
holding the private condition across an await can defeat synchronous cancellation
cleanup; no current public path does that. A future change adding such an await
must revisit cancellation and queue-timeout cleanup together.

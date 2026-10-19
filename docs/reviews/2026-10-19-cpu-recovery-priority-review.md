# CPU recovery live-priority review

Date: 19 October 2026. Baseline: `0697afc6` on `dev`.
Related reports: [#712](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/712)
and [#490](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/490).

The broader open-issue and recent-work review accompanies
[PR #758](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/pull/758).
This scheduling fix is an independent change into `dev`.

## Reproduced behavior

Accelerator faults route otherwise isolated live, background and video workloads
through one shared same-model CPU recovery worker. Admission used `asyncio.Lock`,
which serves waiters in arrival order. A held background inference, a second
background request and then a live detection consequently ran in that order.
A deterministic fake-worker test failed on unchanged `dev`: the queued background
request reached inference before live work. A long background/video call can
therefore consume a live request's remaining budget even though live work has
priority before entering recovery.

This reproduces a scheduling defect. It does not reproduce a GPU reset or prove
that it caused the original installations' stalls.

## Implemented requirements

Only admission to the existing recovery critical section changes. A pending live
request takes the next free turn before waiting background/video work. Background
and video requests share arrival order with each other. Profile refresh and
shutdown take precedence over new inference, preserving their exclusive access.
The active inference keeps ownership until result or the existing failure/cleanup
path completes; priority does not kill or preempt it.

The lock hands ownership directly to the chosen waiter. A cancelled queued
request is removed. Cancellation after handoff but before acquisition resumes
passes ownership onward, preventing both deadlock and two simultaneous owners.
The lock creates no dispatcher task or worker process.

## Second-order effects

- Live preference can make background/video waits longer under continuous live
  traffic. Their existing whole-request deadlines still apply, including queue
  time; this change promises neither starvation freedom nor more CPU capacity.
- Existing expected-duration admission avoids starting work with too little
  remaining budget. Queue expiry does not establish that CPU inference failed
  and must not disable future workload recovery. Existing regression tests cover
  that distinction.
- Cold model load, artifact/provider verification, finite inference handling,
  quarantine and cleanup ownership are unchanged. Only one native recovery
  worker can be in the critical section; no extra native model is loaded for
  priority or concurrency.
- Shutdown sets the existing closed flag before waiting and takes a control turn
  ahead of pending inference. Waiting inference then fails without new native
  work. Profile refresh remains serialized and cannot clean up a model being used.
- There is no schema, configuration, threshold or API-contract change. No data
  migration or production history writes are needed. Rollback restores FIFO
  admission without changing stored records or crash evidence.

## Further recent-work review

The closing review also read the recent integration/security/UI diffs and their
current regression tests, beyond the retirement/telemetry/export/storage changes
covered by #758:

- **Debug secret redaction (#747):** nested dictionaries/lists are copied and
  current auth/access fields are redacted. Secret-shaped suffixes provide a
  fallback for future settings; the current settings-field regression covers
  the known contract, not every possible future naming convention.
- **Recording delay (#745):** the configured 1–120 second initial wait is bounded,
  later metadata refreshes the paired recording-frame context without resetting
  the timer, and final events are retained for follow-up. The wait intentionally
  adds notification latency; it does not establish additional pipeline capacity.
- **Garden beta/privacy (#742):** disabling collection does not bypass later
  person/false-positive cleanup of saved photos. The API gate, routing and scanner
  camera selection are tested separately, including the privacy path with beta off.
- **Garden fixture-motion filter (#741):** collection compares box motion against
  surroundings across the sampled frames. A stationary animal can be missed;
  tests of this rule do not replace independent mammal/privacy qualification.
- **RF-DETR selection (#740):** the finder remains selectable, with the existing
  default preserved and CUDA fallback rather than an unverified CUDA promotion.
  Multi-bird/fixture counting qualification remains tracked by #734.
- **Settings/toast accessibility (#746):** the source uses container width in rem
  to stack enlarged text and preserves semantic save/close controls. The complete
  frontend unit/layout suite and Svelte checks passed during #758 verification.
  No new manual browser inspection is claimed by this source review.

No further defect was reproduced in these slices. The demonstrated additional
recovery scheduling defect is the one fixed above; this is not an unrestricted
security, dependency or hardware certification.

## Verification

New tests cover request-level overtaking without preemption, cancellation before
handoff, cancellation during handoff, control-operation precedence, and shared
background/video arrival order. Existing CPU recovery and GPU retirement tests
exercise deadlines, cancellation, exact artifacts/providers, cleanup failure and
quarantine.

- Full local backend gate after the review follow-up: **5,952 passed, 54 skipped**,
  **79% coverage**, successful process exit; pytest took 446.80 seconds. The
  earlier published head passed 5,950 tests.
- Targeted recovery suite: **48 passed**. Recovery plus retirement tests also pass.
- Separate cancellation stress: **100 seeded runs / 10,000 mixed-priority tasks**,
  no concurrent owners or leaked locks. These are scheduler tests without native
  inference, not throughput or hardware qualification.
- Repository-wide Ruff lint/format, documentation consistency and whitespace checks
  pass. No frontend or API contract is changed by this branch.
- Temporary integration with #758 merged cleanly. The combined model-validation,
  quarantine, CPU recovery, GPU retirement, diagnostics, supervisor, worker-client
  and worker-liveness suites passed: **227 passed, 1 skipped**, 17.57 seconds.
  The temporary merge was aborted after verification; both PRs remain independent
  changes into `dev`. No combined commit or deployment was created.

## Independent review follow-up

The independent pass found no demonstrated priority-lock defect. It additionally
exercised `asyncio.timeout` during queueing and handoff, 200 handoff/timeout races,
and 3,000 mixed-priority tasks with random cancellation, reporting no leaked or
double-owned lock and no remaining waiters.

The existing request-level queue-timeout test already used the real recovery
runner's `asyncio.timeout` path. It now explicitly verifies that the next live
request succeeds on the same worker and that the lock remains usable. Two added
real-runner regressions verify that shutdown reaps before queued work is rejected,
and that profile refresh completes before queued live inference uses a new
profile. These supplement the raw-lock precedence tests without changing the
scheduling implementation. The focused recovery suite now passes 48 tests.

A second independent review was requested with the original brief and all prior
findings and responses. It terminated with a subscription-quota error before
providing a verdict; independent approval of these follow-up tests is not claimed.

# Open issues and runtime evidence review

Date: 19 October 2026. Baseline: `0697afc6` on `dev`.

This technical review and requirements document covers all eight open upstream
issues at the start of the review, their discussion, the latest reporter bundle
for #712, and the recent retirement, telemetry, export, upload and storage fixes.
It distinguishes reproduced defects, implemented behavior and evidence still
needed. It is not a declaration that every open issue is fixed.

## Evidence and boundaries

The repository contract, documentation standard, existing quality assessment,
classifier recovery review and Garden handover were read first. Shared access
and operational instructions were checked against the current private knowledge
system. Credentials, original photographs, diagnostic bundles and machine access
information are excluded from this document.

Tests use temporary migrated databases and fixtures on the developer SSD.
No production data, saved settings, deployment, driver configuration, thresholds
or inference precision were changed. Existing worktrees were preserved.

## Open issue assessment

### #712: queue still seems to stall

[Issue #712](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/712)
contains distinct reports: native GPU failure, recovery-provider selection,
quarantine handling, telemetry and proposed FP16/shared-memory/driver changes.
These are not one established root cause.

The latest supplied bundle was captured on `950fa24`. It records completed
same-model OpenVINO Intel CPU recovery for background and video work. Its recent
backend activity includes photo-update completion and cached-clip reuse after
Frigate event expiry. In this capture the original retirement fields are null;
`failed_runtime` is unknown. The evidence does not recover a missing OpenCL code
or prove what reset the GPU. Historical failed backfills remain in the bundle
alongside current activity; they do not establish a fresh failure in this epoch.

A reproducible support defect is fixed in this change: the bundle had named
`video_photo_update` as `likely_last_error` and included informational cache
messages as failure candidates. The code previously treated every non-circuit
video event as a failure, then searched only eight recent events. Regression tests
prove both false attribution and loss of older failure evidence.

Acceptance still requires a fresh failure capture containing the original native
incident, per-workload completion/queue age, provider identity and host pressure.
A completed CPU recovery is useful evidence, but does not establish GPU stability
or sustained throughput. Do not change driver boot options, shared-memory size
or precision on the basis of the proposed explanations alone. Worker protocol
traffic uses pipes; no shared-memory exhaustion was reproduced here.

### #490: backfill and live feed fail repeatedly

[Issue #490](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/490)
remains a hardware/workload reproduction question. Existing tests and the
September recovery review establish bounded failure handling and the
three-consecutive-classifier-failure stop, rather than indefinite backfill work.
Recent retirement and Intel CPU recovery fixes address specific failure paths.
The latest #712 report confirms recovery on another installation, not this
reporter's original path.

Required evidence is simultaneous live traffic and bounded backfill with queue
age, admissions, completed/failed work and worker lifecycle records. Preserve
unique event IDs and owner corrections; verify database integrity before and
after a replay using disposable data. No new reproduction of this report's GPU
reset is claimed.

### #722: explicit revalidation of a quarantined profile

[Issue #722](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/722)
contains a confirmed identity defect and a larger owner workflow enhancement.
The identity defect is addressed: sysfs driver binding is recorded even when
`/sys/module/*/version` does not exist. GPU and NPU qualification use their
respective binding category; missing, broken or inaccessible bindings are
unknown. Display connectors are excluded from the device-binding map. Tests switch a synthetic binding from `i915` to `xe`, show that the
identity changes and reject the prior Intel GPU eligibility record. Unchanged
bindings produce unchanged identities.

Changing fingerprint inputs also changes native-quarantine keys. That would
silently release old blocked profiles without a successful diagnostic. The
implementation therefore carries a legacy runtime alias exclusively for matching
negative evidence. It is excluded from the new profile's canonical key. Guards
check both the current profile and the equivalent legacy profile; old files are
neither rewritten nor removed. Tests prove preservation across a new policy
instance, model isolation, and stable new keys with or without the alias. A legacy
fault without recorded binding conservatively remains blocked after a binding
change. This is deliberate; it cannot establish that a new driver cured the fault.

The owner-only explicit revalidation action is **not implemented** by this fix.
Its acceptance contract remains: one bounded diagnostic child for one exact
artifact/runtime/provider profile; coalesced requests; normal work remains
blocked; representative finite, nondegenerate inference; exact profile checked
again before release; failure, cancellation or settings races retain the block;
workers restored through serialized initialization. A ready handshake must never
release a profile. Existing automatic stale-provider revalidation is a different,
once-only mechanism. Its attempt ledger is retained, and startup checks now
skip a quarantined profile before native probing.

### #723: qualify Intel GPU FP16

[Issue #723](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/723)
is qualification work, not a reproduced proof that FP32 caused a reset. FP32 stays
the current policy. There is no measured accuracy or stability result in this
review that authorizes exposing or selecting FP16 for EVA-02 or ConvNeXt Large.

Before any implementation permits selection, precision must enter provider
qualification, launch/quarantine and compilation-cache identity. Require stale,
missing and wrong-precision evidence to fail, including finite but degenerate
output. Freeze top-one agreement, top-five overlap and confidence-difference
limits before comparing representative birds, non-birds and hard negatives to
CPU/FP32. Measure cold compilation, warm latency, peak memory and live/background/
video contention separately for each model with external deadlines and resource
guards. Hardware support alone proves none of the proposed memory or accuracy
claims. The reporter's Arrow Lake host remains a separate qualification target.

### #734: two birds and feeder hardware in a wide frame

[Issue #734](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/734)
already has a selectable RF-DETR finder in `dev`, with guarded CPU fallback on
CUDA and unchanged YOLOX defaults. The retained private panel records were read:
two correlated sets demonstrate substantially better tiled recall. The additional
counting rule was designed after inspecting the second set, so that set is not an
independent holdout for the rule. Classification borrowed from an adjacent bird
cannot prove a second individual.

No further counting-policy promotion is made here. Acceptance still needs new
owner-labelled multi-bird visits and fixture/part negatives, preserving uncertainty
for the obscured bird, plus actual CUDA inference. A bounded SSH reachability
check to the available NVIDIA host timed out in this review; no CUDA result is
claimed. Private photographs remain outside Git.

### #576: repeated video decoding and sustained capacity

[Issue #576](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/576)
records that photo preflight, winning-frame reuse, controlled replay, NVIDIA
checks and a 24-hour observation have already landed. Its remaining requirement
is sustained backfill capacity during heavy natural traffic. The earlier window
crossed deployment epochs and did not establish that workload.

Avoid another speculative decode rewrite. A useful acceptance run needs a fixed
build, stage timings, queue age, throughput, bounded retained frames/artifacts and
live-traffic coexistence. Recheck notification completion, photo identity, manual
selections, cancellation, hidden/deleted visits and storage eviction. The diagnostic
fix here makes successful photo work distinguishable from failure; it is not a
capacity benchmark.

### #696: location-based species rejection

[Issue #696](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/696)
is an enhancement with no current distribution-data contract. The existing
catalogue contains taxonomy, not geographic absence evidence. A regional list's
omission alone must not be represented as positive proof of impossibility.

The scoped implementation needs an opt-in setting, one authoritative source and
an explicit semantic contract for year-round versus seasonal presence. Use exact
catalogue/eBird identities, cache provenance and freshness, fail open on missing
or stale evidence, preserve manual observations/corrections, and expose recoverable
skip reasons for rare birds. Source choice and evidence semantics are still
unresolved; this review does not add guessed range data or silently suppress
observations.

### #641: Garden visitors

[Issue #641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641)
is already an off-by-default beta with collection/review functionality. Its
remaining gap is qualification of the complete path on genuine daytime/infrared
mammals and privacy/hard-negative controls. The owner reported that all 249
reviewed Patio captures from the cited period were false alarms. That is useful
local negative evidence, not mammal recall evidence. Later fixture-motion changes
need evaluation against the retained negatives and new positives; stationary
animals can be lost by that gate.

Preserve person rejection, per-photo review, explicit owner decisions and exclusion
from bird counts, exports and personalization. No privacy threshold, detector or
automatic promotion is relaxed. Synthetic sightings cannot supply the missing
real-animal evidence. The handover's historical grouping report received a
specific follow-up in #714: the discussion records 120 photos in 12 cards,
including the previously split feeder photos. That supersedes the earlier pause
checkpoint for this case; it does not establish capture accuracy.

## Second-order effects of the runtime evidence changes

- **Qualification invalidation:** adding a binding intentionally expires prior
  Intel GPU/NPU positive evidence. CPU, Intel CPU and CUDA provider signatures
  exclude the new binding field, preserving their existing evidence and avoiding
  an unnecessary slow recovery-provider downgrade. Tests also show that a GPU
  binding change does not expire NPU evidence.
- **Old crash evidence:** legacy aliases are negative-only. They cannot validate
  a provider, clear a block or bypass the exact model/artifact/provider fields.
  Older ambiguous driver faults remain conservatively blocking. No crash file is
  deleted, and native recovery still uses the existing cleanup barrier.
- **Identity lifetime:** signatures retain existing process-lifetime caching.
  Rebinding a driver under a running native workload is not supported by this
  change; restart and revalidate through the deployment manager after a host change.
- **Bounded diagnostics:** candidate failures are selected before the eight-event
  activity cap, within the already bounded owner snapshot. Candidate output stays
  capped at five. This improves evidence selection without retaining an unbounded
  history or changing API schema, access control, polling or ingestion.
- **Honest recovery:** successful CPU recovery remains visible as degraded recent
  activity. It is not a failed inference. Warning/error/critical failures remain
  candidates; circuit summaries retain their separate last-error context.
- **Data and rollback:** no schema, data or configuration migration is introduced.
  These changes neither relabel nor remove history. Original legacy crash files
  are retained. An older binary does not understand the new fingerprint, so before
  rollback review any incidents first recorded after this upgrade; their new keys
  alone do not block the older binary. Do not delete evaluation or quarantine
  directories as a rollback procedure.

## Review of recent work

Read the diffs and surrounding paths for #750–#754, #756 and #757, including the
subsequent retirement ordering fixes. Git author names do not establish which
contributor or tool produced a patch, so this review identifies changes by PR.

- **Worker retirement (#751/#754/#756):** the retirement request is validated
  against generation/request/work/lease identity. Replacement owns cleanup before
  quarantine becomes visible, and cancellation retains that ownership. The caller
  waits for reap; other recovery paths share a bounded cleanup barrier. The
  reviewed regression tests pass. This establishes ordering under those cases,
  not the cause of the reporter's driver reset.
- **Quarantine persistence (#754):** short in-memory locking is separated from
  serialized read/merge/fsync/replace persistence. Concurrent retirement/native
  abort evidence is retained. This review adds compatibility tests because new
  fingerprint inputs would otherwise bypass those older records.
- **GPU telemetry (#752/#754):** per-client baselines prevent joins/exits from
  becoming artificial work; cycle counters and rollback high-water behavior are
  handled separately. Readings are application-scoped and do not establish whole
  device utilization. Existing accounting tests remain part of verification.
- **Bird export (#753/#754):** positive non-bird evidence excludes rows, including
  confirmed unchanged identities; producing evidence is bound to the current
  scientific name, preserving correction behavior. No history is deleted. Missing
  evidence remains unknown rather than guessed non-bird.
- **Upload bounds (#750/#754):** the byte/pixel guards and pre-open ICO/CUR refusal
  address concrete decode risks; they do not claim every image format has been
  independently fuzzed. The shared decoding regression tests are retained.
- **Space used (#757):** the request now permits a slow walk, unavailable is no
  longer rendered as zero, and visit films enter the same accounting. The figure
  is a filesystem measurement, not a retention guarantee. Concurrent slow walks
  and filesystem permissions remain operational concerns, not reproduced new
  regressions in this review.

The confirmed additional findings are the misleading diagnostic failure selection
and the missing driver-binding identity. No new safety defect is claimed in the
recent retirement, export or upload fixes based only on theoretical possibilities.

## Verification

- Full local backend gate after the review corrections: **5,977 passed,
  54 skipped**, coverage **79%**; successful process exit, 447.18 seconds for
  pytest. The earlier published head passed 5,965 tests. An initial invocation
  omitted the virtualenv tools from PATH, so migration subprocesses could not
  find `alembic`. All twelve affected migration fixtures passed with the
  corrected PATH, followed by the complete successful gate above.
- Frontend baseline/recent-work checks: **1,659 passed** across 248 files;
  Svelte check has zero errors/warnings; dead-code check and production build pass.
- Repository-wide Ruff check and format check pass (877 Python files).
- Documentation consistency passes (219 routes); generated OpenAPI JSON and
  frontend API types are current; both Alembic streams have a single head.
- Baseline-source synthetic sysfs replay reproduces unchanged identity after
  `i915` to `xe` without module version files; the fixed identity changes.
  Read-only host enumeration also confirms bound GPU/NPU drivers are discoverable.
- The NVIDIA host SSH check timed out. No native inference or hardware
  qualification is claimed by these synthetic identity and scheduling tests.

A separate recovery-scheduling investigation during this review also reproduced
queued background work overtaking a later live request on the shared CPU worker.
That fix has its own branch, failing request-level regression and validation;
it does not establish the original GPU-reset cause. All eight upstream issues
remain open for the requirements described above. Hardware skips and unavailable
hosts do not establish inference support.


## Independent review follow-up

The first independent pass confirmed additional cases, each reproduced before
its correction:

- Automatic evidence refresh could probe a profile still blocked by a legacy
  crash record. Startup validation now guards the matching current model,
  artifact and configured-provider profile before recording an attempt or
  starting a probe. Blocked records remain untouched; a changed configuration
  marks the request superseded. Unblocked explicit and auto-provider paths are
  covered as controls.
- An older circuit context could override a newer failure. Failure attribution
  now follows newest-first snapshot order while retaining the separate circuit
  record for historical context.
- CPU recovery recorded its pool only inside context. Its producer now also
  emits the top-level pool consumed by focused diagnostics. Tests exercise the
  actual producer for both successful degraded recovery and failed video work.
- A recovered snapshot fallback warning was another successful-recovery path
  mislabelled as failure. It remains recent activity but is excluded from failed
  inference candidates when its recovery flag is explicitly true.

The conservative category-wide device fingerprint is retained deliberately:
changes to another visible card in the same category can expire Intel evidence.
This fails closed rather than guessing device selection. Troubleshooting now
also explains that hidden sysfs information cannot establish a binding change.
The disclosed rollback limitation remains; neither it nor the priority lock was
shown to corrupt data or silently release an existing upgrade-direction block.

The separate priority branch adds real shutdown/profile-refresh ordering tests
and strengthens its existing whole-request queue-timeout regression. The first
pass found no demonstrated defect in the priority lock, including independent
timeout/handoff and mixed cancellation probes. A second independent review was
requested with the original brief, prior findings and responses, but terminated
with a subscription-quota error before providing a verdict. The first pass is
complete; independent approval of the follow-up corrections is not claimed.
Follow-up verification results are recorded after the revised checks.

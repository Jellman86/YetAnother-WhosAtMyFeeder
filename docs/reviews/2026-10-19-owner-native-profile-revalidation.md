# Owner-controlled native profile revalidation

## Problem and outcome

A retained native crash blocks the exact classifier launch configuration across
restarts. That is appropriate negative evidence, but changing a driver or
investigating a transient failure needs a deliberate recovery path (#722).
Settings → Detection now offers **Check quarantined profile** only when a saved
incident blocks the current profile. This does not automatically retry faults.

## Requirements and contract

The owner selects a concrete provider in saved settings and subprocess image
execution on Linux. The installed bird artifact must have an identity. The owner
supplies exactly three distinct photos (25 MiB each maximum) and a short clip
(32 MiB maximum, at least three readable frames), then explicitly acknowledges
that the disposable native process may crash. No detection, feedback, taxonomy,
MQTT, settings or model-eligibility record is written by the diagnostic.

A client-chosen UUID reserves an attempt before uploading. Preparation performs
no native work. The reservation expires after five minutes. A late upload after
cancel, expiry, a profile change or a new incident cannot launch a probe. Retries
of the same prepare UUID observe its existing state. A second distinct attempt
cannot replace active work. Owner authentication runs before multipart parsing;
stream and individual file limits bound spool and input sizes. Filenames never
control a filesystem path. Private probe inputs are removed after child cleanup.

The controller freezes the model, provider, runtime/driver signature, weights,
external weights, labels, preprocessing, crop artifacts and video frame setting.
Earlier profile identities remain negative aliases when the identity expands.
A changed auxiliary artifact invalidates approval. Selecting Auto is refused.

## Execution and approval

One externally monitored process receives private fixed paths. It exercises the
normal photo pipeline, raw outputs from three photos, configured installed crop
and wildlife components, representative video-frame inference and the normal
video pipeline. Exact provider and model identity must remain unchanged; fallback,
nonfinite/uniform outputs, indistinguishable photo outputs, invalid scores or an
empty pipeline result fail. Each installed crop tier is checked directly with
provider fallback disabled, so a failed accurate detector cannot pass by
substituting the fast detector. Video frames may be stationary, so variation across
video outputs is not required. This validates numerical and pipeline operation,
not species accuracy or bounding-box quality.

The parent waits for prior native cleanup and refuses queued/running classification,
active native assignments and ingest pressure. It requires observable memory
headroom, monitors process-group RSS and available memory every 250 ms, and aborts
on live demand or its five-minute execution deadline. The memory budget is four
times installed bird weights, clamped to 1–8 GiB, with 512 MiB reserve. This is a
sampled watchdog, not a kernel memory ceiling; a sudden allocation can exceed it
between samples. Large auxiliary models or busy hosts may legitimately fail.

The child disables core dumps and uses Linux parent-death protection. The parent
kills and reaps the entire owned process group on every exit, including success
and cancellation, before releasing inputs or authority. Repeated cancellation
cannot abandon cleanup. Failed reaping retains private inputs, keeps quarantine
and disables further checks until an application restart. No automatic restart is
performed. Retained private inputs are not automatically purged on restart;
the owner must inspect and clean them after confirming the old child is gone.
Leaving Settings does not cancel an already accepted bounded check;
returning to Settings restores its status and offers explicit cancellation.

After a passing report and confirmed reaping, the parent restores worker state
while quarantine still applies. It persists a sanitized diagnostic audit, checks
the current profile and incident revision again, then grants process-local
permission. Permission travels only through the trusted isolated worker launch;
a child checks exact identity and unchanged saved evidence before adopting it.
New faults revoke it immediately, including faults that cannot be persisted.
Approval never authorizes native fallback in the API process. No crash file is
removed, rewritten or globally reset, and application restart requires another
explicit check. The durable audit records a passing probe, not durable approval.

## Second-order effects and limits

- Native fault containment protects the API, but GPU/driver failure can affect
  other processes sharing hardware. The owner action, idle checks and abort
  watchdog reduce exposure; they cannot prove driver isolation.
- Live work wins: pressure can stop a diagnostic, leaving the incident blocked.
  Brief competition is possible between watchdog samples. This is not evidence
  of live/backfill throughput or a fix for an earlier admission timeout.
- Restoring workers does not reset recovery history, saved fault evidence or
  unrelated circuit breakers. The exact checked profile alone gains authority.
- Upload disconnects close private spools and abandon only pending uploads.
  They cannot cancel an independently accepted attempt through a failed duplicate
  upload. Owners retain the known attempt ID for explicit cancel/status recovery.
- Audit files contain bounded status/identity metadata, never photos, clip bytes,
  credential values or raw native stderr. Audits survive restart; approvals do not.
- No schema migration is involved. Container recreation discards approval but
  preserves configured persistent incident evidence. Windows owner revalidation
  remains unavailable because equivalent monitoring is not implemented.

## Verification

Tests cover exact and inherited authority, retained legacy evidence, new incidents,
profile changes, cancellation during spawn and cleanup, upload reservation races,
owner access, body limits, memory refusal, real disposable process-group reaping,
probe numerical/pipeline failures, audit failure and cleanup lockout. Browser
fixtures exercise upload cancellation and terminal success/failure/superseded UI.
No native probe has been run on production, no owner media used, and no real job
has been cancelled. Full gate results are recorded in the pull request.

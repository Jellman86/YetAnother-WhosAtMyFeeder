# GPU usage report #778: validation and diagnostic coverage

## Reported behavior and evidence

The report describes reduced GPU chart activity followed by CPU activity and slower
processing on dev e43686dd. Its screenshot shows an unavailable GPU value, not a
measured zero, while live, background and video workers are marked Intel GPU loaded.
The accompanying bundle reports worker-sourced Intel GPU/OpenVINO runtime for all
three pools, zero worker restarts, no open circuits, zero recovery attempts and
successful recent inference. It also includes older browser-retained incidents;
those must not be treated as failures of the current startup.

The bundle does not establish a GPU crash, classifier CPU fallback, hardware video
decoding fallback or the cause of the slowdown. It omits the System chart history,
so the exact interval and counter behavior cannot be checked. No affected-host
native fault has been reproduced. The issue remains open.

## Implemented behavior

An unmeasured accelerator sample now says **Not measured**, explains the limit,
and directs the owner to worker runtime attribution. A measured zero remains 0.0%.
Owner workspace and server bundle responses add optional typed `system_telemetry`
from the existing bounded history. Browser bundles retain that evidence at top
level and in raw evidence. Older servers remain compatible through the optional
field. Missing samples remain null.

## Effects and boundaries

- No provider selection, inference, recovery, quarantine, decoding, settings or
  history-writing behavior changes. No migration is required.
- Export reads the existing snapshot; it starts no native work or new sampling.
  The snapshot is normally at most 360 points, so payload growth is bounded. It
  follows the existing owner-only access boundary and contains private operational
  process/host metadata already present in the owner System history response.
- Loaded-provider attribution is not utilization or kernel execution proof. A
  missing counter must not trigger a restart or invent an idle/CPU state.
- Existing graph gaps remain gaps; genuine fallback/restart diagnostics remain
  available. Historical browser incidents and current startup must be separated.
- Reverting removes the additional evidence and wording without changing user
  data or inference behavior.

## Validation and next evidence

Regression tests cover export of a measured GPU value followed by a null gap with
GPU worker attribution, absence of live sampling, owner/guest access, browser
bundle retention, and distinct unmeasured versus measured-idle rendering. Full
verification results are recorded in the implementation pull request.

An affected-host export captured while the symptom is visible is still needed to
correlate chart counters, worker runtime, successful inference latency and workload
phases. It must precede any claim that the original slowdown is repaired.

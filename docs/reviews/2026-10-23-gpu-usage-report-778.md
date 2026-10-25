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


## Follow-up evidence, 25 October

The reporter supplied a new bundle on `99e1128` in
[the latest issue comment](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/778#issuecomment-6400927719).
Its 360-point window covers 17:07:50 to 17:37:50 UTC. There are 258 measured GPU
samples, reaching 95.2%, followed by 102 null samples. The last measured point is
17:29:18.673 UTC; the first null is 17:29:23.682 UTC (13:29:23 in the reporter's
America/Detroit timezone).

The two retained DRM samples explain a telemetry discontinuity. All 30 cycle
observations across six clients report `counter_regressed`. Their retained total
clock baseline is about 68,706,428,536, just below `2^36` (68,719,476,736), while the
current clocks advance from about 9,711,283,593 to 9,807,446,444 over 5.0097 seconds.
That implies about 19.207 MHz and places the rollover near 17:29:19 UTC, matching
the start of the gap. Busy counters remain cumulative or flat. There are no client
arrivals/departures or permission denials in those samples, with one other read
error per sample. The prior bundle from 24 October contains 360 null GPU points
but no retained DRM samples; it cannot independently establish the same cause.

The collector incorrectly retained a high-water mark for the total-cycle clock as
if it were cumulative client work. It could remain trapped below the old baseline
for almost a full clock period, with only a narrow opportunity to catch up before
the next wrap. This accounts for the sustained chart gap. It does not establish
a native GPU failure, CPU fallback or the cause of a processing slowdown.

At export, all worker pools still report Intel GPU/OpenVINO, zero restarts and
closed circuits. Runtime fallback and GPU recovery counters remain zero. The
latest GPU-attributed successful inference is at 17:37:49 UTC, and the finder
records a completed GPU execution at 17:34:25 UTC, both during the gap. Loaded
provider attribution remains separate from hardware execution proof.

### Scoped correction and reproduction

Total-cycle timestamps now replace their baseline after each observation. A
backwards-clock interval stays unmeasured, and the next valid interval can report
an actual percentage or measured zero. Busy-cycle and nanosecond high-water
rules are preserved. No bit width is guessed; there is no wrap arithmetic,
provider change, worker restart or inference recovery change. Standard Xe engine
names are retained through the existing diagnostic allow-list.

On Quark, replaying sanitized reported counters reproduced the persistent null
reading before the change and recovered after it. Tests cover busy work across
the discontinuity, simultaneous busy-counter regression, multiple clients,
multiple Xe engines, repeated rollovers, bounded diagnostics and unknown-name
redaction. Quark's live GPU currently uses `i915`, so this is a reproduction of
the collector using Xe fixtures, not a claim of a native Xe rollover on Quark.
A read-only two-sample check against Quark's running application saw readable
i915 counters and a measured idle second sample, without changing the deployment.
Raw bundles remain outside the repository.

The kernel's [DRM usage-stat specification](https://www.kernel.org/doc/html/latest/gpu/drm-usage-stats.html)
describes total cycles as a timestamp and separately requires preserving cumulative
busy high-water marks. The [Xe query implementation](https://github.com/torvalds/linux/blob/v6.17/drivers/gpu/drm/xe/xe_query.c)
reports a platform-dependent 36- or 64-bit engine clock width. These boundaries
support rebaselining the timestamp without assuming a universal wrap width.

Issue #778 remains open for affected-host confirmation after this correction and
for any remaining slowdown. A passing counter replay does not establish field
runtime stability or resolve the whole report.

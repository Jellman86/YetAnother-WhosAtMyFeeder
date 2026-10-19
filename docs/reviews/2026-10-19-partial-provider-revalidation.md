# Partial accelerator revalidation and CPU recovery routes

## Problem and reproduction

[Issue #712's new report](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/712#issuecomment-6267129013)
compares `dev` and `dev-intel` on revision `0e64c86`: Intel CPU is absent from
the latter's selector. Intel images intentionally package OpenVINO CPU support.
Packaging, detected hardware and validated model execution are separate facts.

A read-only check on Quark reproduces the missing option: OpenVINO detects CPU,
GPU and NPU, while the active model's current validated/selectable list includes
only ONNX CPU and NPU. No inference was triggered by that check. This does not
establish the reporter's host state or the cause of its earlier GPU failure.

A temporary-evidence reproduction using the production policy establishes:

1. A full-image model record validates CPU, Intel CPU and Intel GPU.
2. Switching to the Intel image invalidates the old image-bound evidence.
3. Startup revalidation checks only CPU and the selected accelerator.
4. That passing subset becomes authoritative for the model; Intel CPU disappears
   despite never being tested in the new image.

The result can affect manual selection and CPU recovery eligibility. Simply
showing the packaged route as validated would weaken the runtime safety policy.

## Requirements and implementation

The trigger remains an unused automatic refresh for a previously validated,
selected accelerator whose current qualification expired. Missing CPU evidence
alone does not trigger it. `ProviderRevalidation` must include `intel_cpu` in that sweep
when qualification is missing or expired, the image packages it and the active
model lists it as a candidate or supported provider. Already-current Intel CPU evidence
is retained without another native probe. The sweep's capability filter still requires host
availability. CPU remains the baseline where available. The selected previously
validated accelerator remains the only accelerator this startup flow may test.

The existing probe judges compilation, finite inference and agreement with the
CPU baseline. Only passing results enter current eligibility, so a failed Intel
CPU check cannot enable that route. A failed optional CPU check does not suppress
a separately passing accelerator. The existing model/artifact/runtime/image
bindings remain in force. Passing CPU evidence is published even when the
accelerator fails, without recommending or reloading that failed accelerator.
New failed results supersede older passes for the same provider; current evidence
for providers outside this bounded check is retained. Persistence is verified
before reporting that results were retained.

No data migration, setting, API or UI contract changes. No validation files are
manually edited. No provider is approved from packaging alone, and full-image
proof is not promoted across an image switch. The configured profile's quarantine
guard runs before consuming an automatic attempt. An additional guard runs for
each concrete provider immediately before its native probe; blocked targets are
reported as failed/skipped without spawning that probe or erasing evidence. A
blocked CPU baseline can prevent other providers from qualifying against it.
The once-only attempt identity and ledger are
unchanged, including interruption/failure behavior.

## Acceptance evidence

Test-first regression cases establish:

- Startup's requested sweep includes Intel CPU when model and image permit it;
  the resulting current evidence makes it both selectable and a recovery target.
- A failed Intel CPU result remains ineligible while the passing accelerator is
  applied, and another startup does not repeat the consumed attempt.
- A route excluded by packaging or the model is not added.
- Other candidate accelerators are not automatically added to the sweep.
- A new failed CPU result overrides earlier passing evidence for that route.
- Already-current Intel CPU qualification is retained without an extra probe.
- CPU profile quarantine prevents its native probe and preserves the crash file.
- Passing CPU results survive accelerator failure without reloading that accelerator.

Existing regressions cover model-switch cancellation, persistence, retained
current evidence, superseded configuration and quarantine refusal. The complete
backend regression gate and repository-wide lint/format remain required before
commit; results belong in the pull request rather than being predicted here.

## Second-order effects

**Startup time and host load.** At most one additional sequential probe is
requested. Its existing timeout is 300 seconds. OpenVINO CPU compilation and
inference can consume CPU and RAM while normal service is running, and can delay
the accelerator refresh. This is a bounded cost, not a throughput improvement.
No parallel provider probing or new automatic retry loop is introduced.

**Provider order.** Passing Intel CPU receives the same measured-latency ordering
as other validated routes for the ordinary runtime contract. Native CPU recovery
has a separate existing preference: for ONNX models it tries eligible OpenVINO
CPU before ONNX CPU, subject to quarantine. Restoring eligibility can therefore
change that recovery choice; this change does not prove that choice is faster
on every host. Native-fault recovery still requires isolated worker cleanup
before taking a replacement route.

**Already-consumed checks.** Existing partial records and automatic ledgers are
preserved. Deployment alone will not restore their missing CPU eligibility.
Owners can use the existing compatibility check to obtain fresh evidence; it
can test installed models and temporarily changes the active model. This is a
material limitation, documented in troubleshooting. Replaying automatic checks
would risk retrying a genuinely failed native workload without owner action.

**Evidence limits.** This fixes the reproduced omission mechanism. It neither
establishes an Intel CPU inference defect nor fixes the original GPU crash,
native driver behavior, model numerical accuracy or sustained live/backfill
capacity. Issue #712 should stay open for those separate observations.

The quarantine guard retains existing exact-profile identities. It does not
reinterpret a fault recorded under Auto as proof that a particular concrete
provider failed, or unify Auto and explicit provider selections. A quarantine
arriving during the sweep skips remaining native probes; already-completed
passing CPU evidence can still be retained. These are identity and reporting
limits, not a new quarantine release mechanism.

## Release and rollback

Ship through a reviewed `dev` pull request and the standard image build. Do not
change production settings, start a compatibility/backfill job or deploy as part
of development verification. Rolling back the code needs no database migration:
retained passing evidence uses the existing schema and original binding rules.

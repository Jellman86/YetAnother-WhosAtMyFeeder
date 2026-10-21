# Native quarantine evidence and owner-check failure reports

## Problem and required behavior

The owner diagnostic in #722 expands the launch fingerprint with crop/wildlife
artifacts and the video frame count. That full identity is necessary for positive
approval. Recording a new crash only under that full key, however, let a frame or
auxiliary-weight change bypass negative evidence after restart. Looking up older
pre-expansion keys protected older incidents but did not protect new ones.

An isolated child also discarded both output streams and wrote its result only
on success. The owner could not distinguish an unsuitable input from a provider
mismatch or a recognised GPU device failure. Exposing raw stderr would introduce
credential/path disclosure rather than provide a safe explanation.

## Identity and retained evidence

Negative evidence uses the existing primary launch identity, omitting only
`auxiliary_artifacts` and `video_frames`. Primary model weights, labels,
preprocessing, provider and runtime remain part of that identity. Full fingerprints
still govern the diagnostic, positive approval and inherited worker authority.
Changing an auxiliary configuration keeps the block and requires a distinct
successful explicit check; it cannot reuse an earlier approval. A new in-memory
fault for any such sibling profile revokes approval before disk persistence.
Earlier aliases are derived from the current primary identity. Captured GPU alias
metadata cannot follow a CPU/provider/model override and block a separate valid
recovery route; an independently failed CPU profile still remains blocked.

New incidents retain a full-profile record and a stable-base record. Both preserve
the existing crash/retirement merge behavior. A sibling incident does not overwrite
the original full-profile record. Failed persistence still blocks in memory;
persistence cannot promise survival across restart when the filesystem rejects
all writes.

A bounded compatibility index associates existing full-key files with their base
identity, without rewriting or deleting them. The index checks directory and file
metadata and caches parsed identities. Changed file metadata triggers a re-read,
including in-place updates; new entries cannot be hidden by coarse directory
timestamps. It examines at most 1,024
directory entries and reads at most 64 KiB per incident. Non-regular, malformed,
mismatched, unreadable or excessive records fail closed because their affected
profile cannot be trusted. This can prevent otherwise unrelated fallback profiles
from launching until the saved evidence is verified. Memory-only fault recording
does not wait for the index or persistence locks.

Approval captures incident metadata/revisions and the incident directory identity.
The final grant performs no compatibility scan or await. A changed directory
requires a fresh explicit check, even if its new file concerns a different model;
this conservative refusal can require repeating an otherwise passing diagnostic.
Existing-file changes and new in-memory faults also refuse the grant. Approval
still lasts only in the current process and never permits API-process inference.

## Safe failure reports

Expected checks raise typed reason codes. The child writes a failure envelope and
exits unsuccessfully. The parent reads at most 64 KiB and maps only recognised
codes to fixed explanations and next steps. Recognised device-retirement codes
are retained; exception strings, paths, arbitrary fields and runtime stderr are
excluded. Unexpected exceptions use a generic reason. Native exits or missing,
malformed and oversized reports remain generic failures. A failure envelope cannot
be accepted as success, even with exit code zero.

These messages reach the existing owner status and audit path. No API fields,
settings, database migrations or new UI workflow are added. Existing cleanup,
deadline, pressure and sampled memory checks remain; cleanup failure still retains
private inputs and prevents further checks. No raw-output capture is enabled.

## Operational effects and verification limits

The stricter block can deny a previously permitted auxiliary-change retry. Use a
different validated primary model/provider or the explicit owner check rather than
removing incident files. Existing records are preserved and new base aliases also
remain readable to versions that consult pre-expansion aliases; downgrading still
restores that older version's behavior for records it alone created.

Index metadata work and cold bounded JSON reads add launch/inspection I/O. Owner
inspection performs approval lookup off the event loop; the immediate memory block
remains independent of disk progress. At most two records are written per expanded
incident identity, increasing incident-directory storage. The diagnostic still
writes only its private inputs/results and audit; it does not modify detections,
settings, provider qualification or existing crash evidence.

Regression fixtures cover new and pre-fix incidents, crash/retirement persistence,
sibling changes, stale approval, cache invalidation, unavailable evidence, bounded
reports, safe causes and cleanup. These tests do not reproduce the original native
fault, qualify any GPU/NPU/driver, or demonstrate live inference concurrency.

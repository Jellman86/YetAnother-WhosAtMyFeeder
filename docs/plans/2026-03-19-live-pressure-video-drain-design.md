# Live-Pressure Video Drain Design

## Goal

Make auto video classification strictly yield to live detection work without cancelling already-running video jobs, and expose the throttle reason accurately to operators.

## Decision

- Live pressure means any live classification work is running or queued.
- Auto video classification must stop starting new video jobs while live pressure is active.
- Already-running video jobs should drain normally.
- Queue/status APIs must distinguish live-pressure throttling from MQTT-pressure throttling.

## Rationale

Hard-cancelling in-flight video work would add retry churn, partial-progress edge cases, and more failure-state reconciliation. Draining keeps the scheduler simple and preserves work already consuming scarce GPU/CPU resources, while still giving live work first claim on new slots.

## Implementation Notes

- Use classifier admission status rather than broad classifier status polling.
- Compute a dedicated live-pressure signal from live queued/running counts.
- Keep MQTT throttling semantics intact and additive.
- Update UI blocker/activity messaging so live pressure is not mislabeled as MQTT pressure.
- Correct the changelog wording to match the real behavior: pause new batch video starts under live pressure, not full preemption.

## Testing

- Add backend regression coverage for live queued/running pressure reducing effective video concurrency to zero.
- Add backend regression coverage proving MQTT-only throttle flags remain separate from live-pressure flags.
- Add frontend presenter coverage for live-pressure blocker text.

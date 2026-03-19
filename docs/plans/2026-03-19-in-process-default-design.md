# In-Process Default Design

## Goal

Make `in_process` the default image execution mode for fresh installs and unset configurations, while keeping the tradeoff explicit in Settings.

## Decision

- Backend defaults switch from `subprocess` to `in_process`.
- Existing saved configs remain unchanged.
- UI defaults and unset fallbacks switch to `in_process`.
- Settings copy becomes neutral and explanatory rather than recommending `subprocess`.

## Rationale

For larger models, the subprocess default duplicates model memory across workers and drives RAM use much higher than necessary. Making `in_process` the default gives new installs the lower-memory path by default while still preserving an explicit opt-in to subprocess isolation for users who value crash containment more than memory efficiency.

## Testing

- Update backend default-value tests to assert `in_process`.
- Update UI fallback tests or checks impacted by the new default.
- Run targeted backend config tests and frontend type/test checks.

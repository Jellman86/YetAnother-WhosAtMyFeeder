# Affordable regression gates: September 23, 2026

## Outcome

Strengthen the existing hosted checks and make browser/device-heavy checks repeatable
locally. No new hosted jobs, scheduled runs, paid services or automatic model downloads
were introduced. Existing CI/build usage is not a guarantee about account billing.

## Gaps closed

- **Uncollected tests:** 12 files under root `tests/unit` contained 110 cases outside
  the backend CI command. They now live under `backend/tests/additional`. Obsolete
  APIs, cursor doubles, script paths and a weak video-success assertion were corrected.
  A guard rejects new Python tests placed in the old, uncollected tree.
- **Unequal gates:** PR coverage required 60% while image publication accepted 20%
  and could rescue a killed pytest process after a printed pass summary. Both use
  one fail-closed command, branch measurement and a 70% combined coverage floor.
  Timeout/failure propagation and workflow wiring have regression tests.
- **Telemetry before merge:** the existing PR job now runs the 18 local Worker/D1
  integration tests, not only the dry-run bundle build.
- **Joined ingest:** nine cases exercise real MQTT processing, filtering, migrated
  SQLite, queueing and notification policy together. External model/media/taxonomy/
  weather/channel calls are substituted; no real notifications are sent.
- **Browser behaviour:** five rendered-component cases run across Chromium/WebKit,
  desktop/mobile. They assert geometry, actual interaction, event selection, media
  failure and state transitions, rather than inspecting component source strings.

## Defect found by the stronger tests

The old pre-migration backup used `shutil.copy2` on the main SQLite file. With an
open WAL connection, a committed table and row were absent from the restore point:
the new restore test failed with `no such table: observations`.

The fix uses a read-only source connection and SQLite's backup API in the existing
off-event-loop startup call. A same-directory temporary snapshot is checked, flushed,
closed and atomically published before pruning. Failed/corrupt/locked copies keep
existing restore points. A progress deadline bounds backup lock retries, unique
filenames avoid same-second replacement, and retention always keeps the snapshot just
created even after a clock correction. Uncommitted source writes stay excluded.
This changes no schema or normal inference path. Backup failure retains the existing
non-fatal startup behaviour; it is logged, not reported as a successful restore point.

## Review boundaries

- The browser fixture is not shipped in the production build and never contacts a
  real backend. Its new dependency is development-only, pinned in the lockfile.
- Quark's browser exercised the current fixture at 1280px and 390px, including
  hit-testing the escaped preview and checking record selection and Escape dismissal.
- Quark's 18 backup/pipeline tests ran from disposable source/dependency directories
  and temporary migrated databases. They passed using its installed runtime libraries;
  this is not another hardware-inference or accuracy certification.
- The existing broad-suite database-thread daemon workaround remains explicit debt.
  The new gate does not claim to detect every leaked connection or guarantee exactly-once
  notification delivery after a process crash.
- An npm audit still reports pre-existing UI toolchain advisories (including Browserslist,
  Vitest and the svelte-i18n/esbuild chain). The Playwright addition changes no existing
  package versions and adds no reported advisory. Dependency updates remain a separate
  reviewed change; do not run an unreviewed force upgrade to make the audit green.

## Read-only fleet check

The seven-day active-heartbeat query returned 28 reporting installations: 24 last
reported inference health as `ok`, four did not report that field. Historical health
reports still include unavailable snapshots and classification-stage timeouts across
six installations each. These guide recovery fixtures; they do not prove six current
outages, nor should paired timeout/drop markers be counted as independent incidents.
The aggregate reads wrote zero rows. No raw client identifiers or payloads were retained
in this review.

Issue #490 is still open awaiting reporter confirmation. Dependency-update PRs are
separate from that bug. Latest healthy heartbeat status does not establish that the
original Intel GPU/model failure is resolved on the reporter's installation.

## Verification

- Shared backend gate: **3,188 passed, 49 skipped**, 73% combined statement/branch
  coverage. The skipped model/platform cases are not counted as hardware passes.
- Frontend: **1,133 unit tests**, clean Svelte/TypeScript and dead-code checks,
  production build successful; **20 local browser cases** across four projects.
- Telemetry Worker: **18 integration tests**, local databases only.
- Quark: **18 backup/pipeline tests**, plus remote browser geometry/interaction checks.
  The live container remained healthy with zero restarts and HTTP 200 health/readiness.
- Repository-wide lint, format, documentation consistency and whitespace checks pass.

Run commands and remaining work are in the [testing guide](../development/testing.md)
and [coverage roadmap](../../ROADMAP.md#broader-end-to-end-coverage-).

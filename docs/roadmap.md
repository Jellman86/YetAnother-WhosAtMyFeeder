# Road to 3.0

The prioritised, forward-looking plan for YA-WAMF **3.0**. It is the companion to the two
assessments that define *where we stand*:

- [Gold-Standard Review (2026-07-07)](reviews/2026-07-07-project-quality-and-gold-standard-review.md) — honest quality assessment and the incremental path.
- [Telemetry Health Findings (2026-07-09)](reviews/2026-07-09-telemetry-health-findings.md) — what actually fails across the fleet.

Completed work lives in [`CHANGELOG.md`](../CHANGELOG.md); this file tracks what's **next**.

---

## Major initiatives (3.0)

### 1. First-run setup wizard
A friendly, **skippable** guided setup that configures YA-WAMF end to end, and — crucially —
is **idempotent and re-runnable at any time** from Settings (running a step again is safe and
never clobbers unrelated config). Steps:

- **Model selection with on-hardware validation** — pick a classifier and confirm it actually
  loads and runs on the detected accelerator (reuse the model-eval / device-sweep machinery:
  compile + finite-output + latency check per NPU/GPU/CPU), so the user leaves the step on a
  model proven to work on *their* box.
- **Integrations** — Frigate, BirdNET-Go, media servers, notifications: guided connect + test.
- **Frigate settings** — cameras, recording-retention guidance, and the detection gates that
  drive the Event-Not-Found problem (`min_score` / `min_initialized` / `threshold`).
- **Common quality configs** — HQ snapshots, crop selection, verification gates.

Each step is independently re-runnable; skipping the wizard leaves the current config untouched.

### 2. UI simplification & polish
Make the whole UI clean, coherent, and calm — **especially Settings**, which is currently
bloated with indistinct sections. Approach: *research current UI/UX best practice from
authoritative sources first*, apply it consistently (information architecture, grouping,
progressive disclosure, empty/error states), then **codify the resulting UI standards into
`CLAUDE.md` §5** so future work stays consistent and doesn't re-bloat.

### 3. File-by-file code-quality review
Research the **gold-standard for our stack** (Python/FastAPI + Svelte 5/TypeScript) from
authoritative sources, **codify the code-quality standards into `CLAUDE.md`**, then perform a
**file-by-file** review and refactor: self-documenting, defensive, clean — no dead code,
commented-out blocks, or leftover scaffolding. Sequenced lowest-risk first; every change is
test-first per §2 and preserves the §1 safety model.

### 4. Full translation review
Review every locale against the `en.json` source of truth for completeness, accuracy, and
consistency; fix missing keys, drift, and machine-translation artefacts. Add a CI check that
flags missing/extra keys per locale so translations can't silently rot.

---

## Carry-over (incremental — from the gold-standard review)

Kept because they remain valuable; not blockers for 3.0:

- **Frontend API contract adoption** — migrate the remaining SPA API modules to generated
  path-level request/response types (Gold-Standard Review, Phase 2).
- **Coverage ratchet** — raise the backend coverage floor as low-coverage modules gain focused
  tests.
- **Keep dated reviews current** as significant subsystems change.

## Recently completed (trimmed — see CHANGELOG for detail)

Removed from the active roadmap because they shipped:

- Telemetry-health recommendations (2026-07-09): recording-frame classification fallback,
  in-app Event-Not-Found guidance, and diagnosable telemetry context/severity.
- Pre-3.0 shortlist (OAuth token encryption, logout cleanup, typed `/api/settings`, 365-day
  date-range cap).
- In-app, channel-aware update prompt.

---

*When an initiative here starts, add a dated design note under [`docs/plans/`](plans/) and link
it from the item above; when it ships, move it to the CHANGELOG and strike it here.*

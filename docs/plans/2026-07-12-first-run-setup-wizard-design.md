# First-run setup wizard — design

**Roadmap item:** [The Road to 3.0 §1.2 — First-run setup wizard](../../ROADMAP.md#12-major-initiatives-the-release-defining-work).
**Standards applied:** [UI/UX standard](../standards/ui-ux.md), [Code-quality standard](../standards/code-quality.md).
**Status:** Implemented on `dev`; maintained as the behavioural design record.

A friendly, multi-part wizard that guides a new user through the whole of YA-WAMF's
configuration end to end, **validates their hardware**, and — crucially — can be **re-run at
any point in the application's life**, section by section, without ever clobbering unrelated
config.

> **Implementation hardening note (2026-07-22):** the shipped flow deliberately differs from
> a few early sketches below. The account step seals first run and returns the new owner session
> immediately; review readiness is deterministic configuration/credential completeness rather
> than a live uptime claim; re-run sections return to the review map; the connection step permits
> saved-but-offline services with an explicit warning; and integration setup enables services
> while credentials remain in their focused Settings surfaces. Diagnostics use current form
> values, fail closed on persistence errors, and never overwrite config just to test it.

---

## 1. Goals & principles

Grounded in the researched onboarding gold standards (see [References](#references)):

- **One thing at a time.** A wizard reduces a large, intimidating settings surface to focused,
  ordered steps — users make fewer errors when each screen asks for only what it needs
  (progressive disclosure). (NN/g, *Wizards*.)
- **Always show progress.** A determinate progress indicator (step N of M) is shown on every
  step except a trivial 1–2 step flow — visible progress measurably raises completion
  confidence. (NN/g.)
- **Validate in place, prevent errors.** Each step validates before it lets you continue —
  reuse the existing per-integration *test* endpoints, keep "Continue" disabled until the step
  is valid, and report failures in plain language with the next step to take. (Nielsen
  heuristics 5 & 9.)
- **Skippable and non-destructive.** The whole wizard is skippable, and so is any individual
  step. Skipping a step leaves the current config untouched.
- **Resumable.** The user can leave and come back; because each completed step persists its own
  slice, re-entering reflects saved state. The backend config remains authoritative.
- **Re-runnable for the whole app lifecycle.** The wizard is not a one-time gate. It is
  launchable any time from the owner navigation, in a **non-linear** mode where the user can
  jump straight to the section they want to reconfigure. (NN/g: non-linear steppers suit
  experienced users and independent steps.)
- **Idempotent.** Re-running a step reads current config, pre-fills it, and writes back **only
  that step's slice** through the existing secret-preserving `POST /api/settings`. Running a
  step again is always safe.
- **Accessible (WCAG 2.2 AA).** Keyboard-operable, visible focus, step changes announced via a
  live region / `aria-current`, and no colour-only status — per the [UI/UX standard](../standards/ui-ux.md).

---

## 2. What already exists (reuse, don't rebuild)

- **Legacy first-run screen** — the former language/password page supplied the account policy
  that is now implemented by `WizardShell.svelte` and `AccountStep.svelte`.
- **First-run gate** — `auth.initial_setup_complete` + `POST /api/auth/initial-setup`
  (`auth.py`). Kept as the *first-run* trigger; the re-run entry point is decoupled from it.
- **Config read/write** — `GET`/`POST /api/settings`, secret-preserving via
  `should_update_secret()`. Every step reads/writes through this; merging semantics give us
  idempotency for free.
- **Per-integration test endpoints** (per-step validation): `GET /api/frigate/test`,
  `POST /api/settings/mqtt/test-publish`, `POST /api/settings/birdnet/test`,
  `POST /api/settings/notifications/test`, `POST /api/settings/birdweather/test`,
  `POST /api/settings/llm/test`, `POST /api/email/test`, classifier `POST /api/classifier/test`
  + `/probe`.
- **Hardware validation engine** — the classifier capability probe
  (`cuda_available` / `intel_gpu_available` / `intel_npu_available` / OpenVINO device probe,
  surfaced on classifier status) plus the **model-eval provider sweep**
  (`POST /api/diagnostics/model-eval/runs` with `sweep_devices` / `compat_only`): compile +
  finite-output + real-image CPU-baseline agreement + median latency. The wizard sends the selected
  installed model in `model_ids`; candidates are the running image/host/model intersection,
  including CUDA even when the full image also exposes OpenVINO. This is exactly the "prove the
  model runs on *this* box" machinery the model step needs.
- **Model management** — `GET /api/models/installed` plus classifier validation and activation.
  Crop detectors are separate artifacts: the wizard filters them out and both validation and
  activation APIs reject them as classifier selections.

**Net new backend is small** — mostly a thin state endpoint (§5); the heavy lifting already ships.

---

## 3. Step structure

A linear flow on first run; a jump-anywhere map on re-run. Each step is a self-contained
component with the shape `{ load(currentConfig), validate(), test?(), save(slice) }`.

| # | Step | Config section | Per-step validation |
|---|------|----------------|---------------------|
| 0 | **Welcome & language** | locale | — (existing) |
| 1 | **Admin account & access** | `auth` | password policy; or explicit "skip auth" (existing) |
| 2 | **Frigate & MQTT connection** | `frigate`, `mqtt` | `GET /frigate/test`, `POST /settings/mqtt/test-publish`; tests current form values, saves explicitly, and allows later repair when an endpoint is offline |
| 3 | **Cameras & detection gates** | `frigate` (cameras, `min_score`/`min_initialized`/`threshold`), recording-retention guidance | camera list pulled from Frigate; inline guidance on the Event-Not-Found gates |
| 4 | **Classifier model & hardware** | `classification` (model, provider) | **capability probe → provider sweep** (packaged ∩ detected ∩ model-compatible; isolated compile + finite output + real-image agreement + latency for ONNX CPU/CUDA and OpenVINO CPU/GPU/NPU as applicable); only passing providers remain and the fastest is selected |
| 5 | **Snapshot & crop quality** | `classification` (HQ snapshots and automatic best-image policy) | preview against a recent detection where possible |
| 6 | **Integrations** (opt-in) | `birdnet`, `ebird`, `inaturalist`, `birdweather`, `ai` | enables selected services; BirdNET offers the staged URL → MQTT → durable-ingest diagnostic; credential completion is reported in review |
| 7 | **Import existing detections** (opt-in) | one-shot action | starts a visible background import for retained Frigate events; does not delay setup or imply unavailable BirdNET audio can be recovered |
| 8 | **Anonymous telemetry** | `telemetry` | explicit opt-in; off by default |
| 9 | **Review & finish** | — | localized configuration/credential-completeness summary with jump-to-section actions |

Model, quality, integrations, retained-history import, and telemetry all offer a safe skip or
no-op choice; skipping leaves that section unchanged. Hardware validation is the headline: it
turns "pick a model and hope" into "pick a model and *see it run* on this hardware before leaving
the step."

---

## 4. Two entry modes

**First-run mode** — auto-shown when `auth.initial_setup_complete` is false. Linear, start to
finish with a progress bar. The account step sets the completion flag (and returns an owner token
when auth is enabled) before later owner-only API calls; optional product steps remain skippable.

**Re-run mode** — launched any time from the owner-only **Setup wizard** action in the Settings
navigation.
Opens on a **section map**: every step is listed as configured, needing attention, or optional,
letting the user jump straight to the one section they want to redo. Completing, skipping, or
backing out of that section returns to the map. Because each
step round-trips only its own slice through `POST /api/settings`, re-running "Integrations"
never touches Frigate, models, or anything else. Re-run mode never resets
`initial_setup_complete`.

---

## 5. State & persistence

- **Config truth lives in the backend** (`config.json` via `/api/settings`) — the wizard is a
  guided editor over it, holding no shadow copy.
- **`GET /api/setup/state`** returns cheap, deterministic readiness derived from current config:
  required connection fields, classifier artifact role, and credentials needed by enabled
  integrations. It intentionally does not present live uptime as saved readiness; live checks stay
  in staged diagnostics.
- **First-run completion** — `POST /api/auth/initial-setup` sets
  `auth.initial_setup_complete` in the account step and atomically returns the owner token when
  authentication is enabled. The endpoint is serialized and permanently rejects later takeover
  attempts, including when auth was deliberately skipped.

---

## 6. Implementation outline (test-first, per [code-quality standard](../standards/code-quality.md))

**Backend**
- `GET /api/setup/state` → typed `response_model` (`SetupState` with per-section status enums).
  Pure readiness logic lives in a service and is unit-tested without a live Frigate/MQTT.
- No new config-write endpoints — steps reuse `POST /api/settings` and the existing test/probe/
  device-sweep endpoints.

**Frontend**
- Refactor `FirstRunWizard.svelte` into a `wizard/` shell (`WizardShell.svelte` owning the
  stepper, progress indicator, next/back/skip, and the section map) plus one component per step,
  each implementing the `{ load, validate, test?, save }` contract.
- A `setup_wizard.svelte.ts` store holds current step, per-step status, and the section map from
  `/api/setup/state`. Failed refreshes preserve the last trustworthy summary and expose retry UI.
- The portalled modal traps and restores focus, supports Escape only in re-run mode, announces step
  changes, and uses keyboard/touch-sized controls. Step save failures appear beside the action.
- Hardware validation has a 30-minute client deadline and directs long-running jobs back to
  Diagnostics rather than leaving the wizard in an endless busy state.
- The Settings navigation gains a "Setup wizard" launch action (re-run mode) in its Operations
  group, keeping the guided path discoverable beside the settings it changes without burying it
  among data-maintenance tools or promoting it to a primary application destination.
- All copy through i18n with `{ default }` fallbacks; all API calls through `apps/ui/src/lib/api/`.

**Testing**
- Backend: `GET /api/setup/state` readiness matrix (configured / partial / skipped) as pure
  unit tests; contract test that the endpoint's `response_model` matches.
- Frontend: step validity gating (Continue disabled until valid), skip leaves config untouched,
  re-run of one step doesn't mutate other slices, section-map rendering per status, and a
  keyboard/focus/`aria-current` accessibility test.

---

## 7. Acceptance criteria

- A brand-new install is walked from language → auth → Frigate/MQTT (tested live or saved with an
  explicit repair warning) → cameras &
  gates → **model validated on the detected accelerator** → quality → chosen integrations
  (with staged BirdNET path testing when selected) → optional retained-history import → telemetry
  → finish, with a visible progress indicator throughout.
- Optional configuration steps are skippable; skipping leaves that section's config untouched.
- The wizard is re-launchable from the Settings navigation at any time, opens on a section map, and
  lets the user reconfigure a single section without altering any other.
- Re-running a step is idempotent — it pre-fills from current config and writes back only its
  own slice via the secret-preserving settings write.
- Step 4 refuses to leave the user on a model that fails compile/finite-output/latency on their
  hardware, and always offers a working CPU fallback.
- Meets WCAG 2.2 AA (keyboard, focus, announced step changes); `npm run check` clean; new
  backend behaviour is unit-tested; `CHANGELOG.md` updated.

## 8. Out of scope

- No new inference/model capability — the wizard *orchestrates* the existing probe/sweep, it
  doesn't add detectors.
- No change to the settings pages themselves (that's the separate UI-simplification initiative);
  the wizard reuses their underlying config and test endpoints.
- No telemetry added for wizard steps in this pass.

---

## References

- [NN/g — Wizards: Definition and Design Recommendations](https://www.nngroup.com/articles/wizards/)
- [NN/g — Onboarding and Connecting Smart Devices: 5 Guidelines](https://www.nngroup.com/articles/smart-device-onboarding/)
- [NN/g — Design Guidelines for Complex Applications](https://www.nngroup.com/articles/complex-application-design/)
- [Nielsen's 10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) · [WCAG 2.2](https://www.w3.org/TR/WCAG22/)

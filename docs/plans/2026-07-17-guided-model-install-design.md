# Guided model install & post-install selection gate — design

**Roadmap item:** extends [The Road to 3.0 §1.2 — First-run setup wizard](../../ROADMAP.md#12-major-initiatives-the-release-defining-work)
(the "Model selection with on-hardware validation" bullet) and generalises it into the standalone
Model Manager.
**Standards applied:** [Diagnostics & dialog standard](../standards/diagnostics-and-dialogs.md),
[UI/UX standard](../standards/ui-ux.md), [Code-quality standard](../standards/code-quality.md),
[CLAUDE.md](../../CLAUDE.md) §1 (safety) & §5 (honest UI).
**Status:** Implemented on `dev`.

### Implementation notes (deviations from the original design)

Two things changed once the existing code was read closely:

1. **The gate lives at the API/router boundary, not inside `activate_model()`.** The device sweep
   itself calls `model_manager.activate_model()` to trial-load each model, so gating the core method
   would have deadlocked validation. Gating `POST /api/models/{id}/activate` (409 for unvalidated)
   still blocks every API path — UI, settings picker, raw POST — while leaving internal validation
   free. `InstalledModel.ready` was likewise **not** overloaded for validation state (the sweep
   filters on `ready`); a distinct `validated` / `validation_reason` pair was added instead.
2. **A host-agnostic validate probe was added** (`POST /api/models/{id}/validate`,
   `model_validation.py`). The pre-existing `device_eligibility.json` is written only by the
   OpenVINO sweep, so it is empty on CPU-only and CUDA hosts — gating on it alone would have
   stranded them. The probe trial-loads the model, runs one frame through the live classifier,
   checks for finite output, records the result, and restores the previously active model. Either
   the sweep record **or** the probe record clears the gate; the active model and bundled models are
   grandfathered.

The three-stage download→validate→activate wizard was realised as a two-stage **Validate & enable**
`DiagnosticDialog` launched from the gate (download keeps its existing progress UI). Crop
micro-validation remains out of scope (§5).

A guided, multi-stage flow that runs when a user installs a classifier model: it downloads and
verifies the artifact, validates it **on this host's hardware**, and only then lets the model be
selected. Selection is **gated post-install** — an installed-but-unvalidated model cannot become the
active classifier through any path, enforced server-side, not just hidden in the UI.

---

## 1. Goals & principles

- **One guided shape.** The flow uses the shared `DiagnosticDialog` / `WizardShell` visual language
  ([diagnostics standard](../standards/diagnostics-and-dialogs.md) §1), so a user who has seen the
  first-run wizard or any test dialog already understands it. No hand-rolled modal.
- **Honest, staged progress.** Each stage turns green only when its check actually passed; the
  reveal controls *when* a resolved stage appears, never *whether* it passed (diagnostics standard
  §3). A failure stops the run and states the cause and the next step in plain language.
- **Prove it runs here, not in the abstract.** Registry notes tell us a model *can* misbehave on a
  given accelerator (e.g. RoPE ViT produces NaN on this Intel GPU; EVA-02 crashes it). Validation
  confirms behaviour on *this* box before the model is trusted.
- **Never strand the user.** The gate must never leave the installation with zero usable model. CPU
  is the always-eligible baseline (every registry model is CPU-validated); the gate can restrict
  *provider*, never remove the *only* path to running.
- **Selection is gated, safety is not violated.** Blocking activation of an *unvalidated new
  selection* is error-prevention (Nielsen #5). It must not retroactively deactivate a model that is
  already live and working (§1: a working history is not something we break on a version bump).
- **Non-destructive & idempotent.** Re-running validation re-reads state and overwrites only this
  model's eligibility record. Download integrity, staging, and swap semantics are unchanged.

---

## 2. What already exists (reuse, don't rebuild)

Most of the machinery ships today; the net-new work is **orchestration + a server-side gate**, not
new ML capability.

- **Download + integrity** — `ModelManager.download_model()` → `POST /api/models/{id}/download`
  (background task), progress via `DownloadProgress` polled in `ModelManager.svelte` /
  `model_download_progress.ts`. Includes `_verify_checksum()` (SHA-256) and
  `_validate_download_payload()`, atomic staging + `_swap_model_dirs()`.
- **On-hardware validation** — the model-eval **device sweep** in `compat_only` mode
  (`POST /api/diagnostics/model-eval/runs` with `sweep_devices=true, compat_only=true`,
  `model_eval_service.py:357`): per device, it compiles the model, checks finite output, and takes a
  latency reading — no accuracy scoring. This is exactly the "does it actually run correctly here"
  check, and it already backs the Detection Settings *Run compatibility check* button
  (`DetectionSettings.svelte:93`). It accepts a single model (single-model sweep) or all
  (`sweep_all_models`).
- **Persistent per-host eligibility record** — `/config/yawamf-eval/device_eligibility.json`, keyed
  `model_id → [verified providers]`, surfaced to the UI via
  `classifier_service._host_device_eligibility_summary()` →
  `classifier_status.host_device_eligibility.verified_providers`. **This is the gate's source of
  truth.**
- **Installed-model readiness carrier** — `InstalledModel.ready: bool` + `reason: str` already exist
  (`ai_models.py:73`) and are already populated for incomplete installs. The gate reuses this field
  rather than inventing a new one.
- **Activation** — `ModelManager.activate_model()` → `POST /api/models/{id}/activate`. Currently
  **not** gated on validation — this is the gap this design closes.

---

## 3. The flow (three stages)

Rendered with `DiagnosticDialog`, launched from the Model Manager's install/download action. Stages
are modelled as an ordered `DiagnosticStage[]`, each resolved by a real backend call (diagnostics
standard §4.1 — prefer real sequential checks over one call mapped onto stages).

1. **Download & verify** — kick off `download_model`, stream `DownloadProgress`. Stage passes when
   the artifact is downloaded, checksum-verified, and the payload validates. Failure = network /
   checksum / incomplete payload, reported with the retry path.
2. **Validate on hardware** — run a single-model `compat_only` device sweep for the just-installed
   model. Stage reports, per candidate provider, one of *verified* / *unsupported (reason)* /
   *not present on this host*. Stage passes when **at least one provider** (CPU at minimum) is
   verified. If the user's currently-*selected* provider (`Auto`/CUDA/OpenVINO GPU/…) is **not** in
   the verified set, the stage is a **warning, not a pass-through**: it surfaces "runs on CPU here,
   but your selected Intel GPU produced invalid output" and offers to continue on the verified
   provider. Writes/updates `device_eligibility.json`.
3. **Activate** — call `activate_model`. Because stage 2 has recorded eligibility, the server-side
   gate (§4) now permits activation. Stage passes when the model loads and reports healthy via the
   existing classifier status/health probe. On activation the active provider is pinned to a
   verified one; the wizard shows selected vs active provider honestly (same pattern as
   [ai-models.md](../features/ai-models.md) fallback reporting).

The wizard's `summary` strip shows `Model · target provider`. The whole flow is skippable, but
skipping stage 2/3 leaves the model **installed but unvalidated and unselectable** (§4) — the UI
says exactly that.

---

## 4. The post-install selection gate

The core new behaviour. **A model is selectable iff it has a passing per-host eligibility record for
at least one provider.**

- **Server-side enforcement (authoritative).** `activate_model()` consults
  `device_eligibility.json` for the target model. If there is **no verified provider**, activation is
  rejected with a typed, honest error (`ModelActionResponse` success=false + reason:
  `unvalidated` / `no_compatible_device`), and the currently-active model is left untouched. This
  holds no matter which path calls it — Model Manager, the settings dropdown, the first-run wizard,
  or a raw API call. The gate is not a UI affordance that a direct `POST` can bypass.
- **UI reflects the gate, never fakes it.** In `ModelManager.svelte` and the model picker, an
  unvalidated installed model renders as **selectable-after-validation**, not silently disabled: a
  clear "Validate to enable" affordance that launches stage 2 of the wizard, with the reason shown
  (recognition over recall; never colour-alone; §5). We reuse `InstalledModel.ready=false` +
  `reason="unvalidated"` so the picker's existing not-ready rendering path carries it.
- **Provider downgrade instead of a dead end.** When the selected provider isn't verified but CPU
  (or another provider) is, selection is *allowed on the verified provider* with an explicit
  notice — never a hard block that leaves the user unable to pick any model. This is the §1
  "never strand" rule and matches the existing soft-fallback contract.
- **Grandfathering existing installs (safety-critical).** Models installed before this feature have
  no eligibility record. We must **not** retroactively deactivate a model that is currently active
  and working (§1). Rule:
  - The **currently-active** model is implicitly grandfathered (treated as eligible on its active
    provider) and keeps running; the UI offers a non-blocking "validate now" nudge.
  - The gate applies to **new selections** only. Switching *away* and back to an unvalidated model
    triggers validation first.
- **CPU baseline.** Because every registry model is CPU-validated, a successful CPU compile+finite
  check is always sufficient to clear the gate. The gate constrains *acceleration*, not *existence*.

No database schema change is required — eligibility lives in the existing `device_eligibility.json`
on the config volume, and readiness rides the existing `InstalledModel` DTO. **No Alembic
migration.** (If we later decide to persist eligibility in SQLite for queryability, that becomes a
separate reversible migration per §3 — out of scope here.)

---

## 5. Explicitly out of scope: crop micro-validation

The original idea included a per-install "does this model prefer cropped or full-frame images"
micro-check. **We are not building this**, because it conflicts with an already-implemented, documented
decision:

> [`2026-07-16-model-crop-policy.md`](2026-07-16-model-crop-policy.md) (Status: Implemented): "Image
> preparation is an application responsibility, not a routine owner preference. Each classifier or
> regional family variant has one explicit crop policy in the model registry."

That policy was set from a controlled **144-image / 3,456-classification** shared-panel sweep on
Quark. A per-download micro-sample of a few feeder frames would be statistically far weaker and would
reintroduce exactly the per-install crop preference the project deliberately removed. The wizard's
stage 2 may *display* the registry's crop policy for the model under "technical details" (read-only,
per the crop-policy doc), but it must not measure, choose, or mutate it.

If future work wants a per-host crop confirmation, it belongs in the existing repeatable crop-policy
sweep (`eval_feeder_model_harness.py`) as a **non-authoritative diagnostic** that cannot override the
central registry policy — a separate design, not this one.

---

## 6. Safety, concurrency & failure modes

- **One eval run at a time.** The device sweep shares the model-eval harness, which is single-run
  (409 on concurrent). Stage 2 must handle "a run is already in progress" honestly (queue message,
  not a fake success) and must restore the previously-active model on completion/failure — the
  harness already does the restore; the wizard must not assume it activated the new model until
  stage 3.
- **Don't stall live detections silently.** A full sweep competes with real-time classification.
  `compat_only` is lightweight (compile + one finite check + latency read per device, no image
  panel), but the UI must still warn that validation briefly exercises the classifier, consistent
  with the model-eval "runs flat-out" caveat.
- **Partial failure is legible.** Download-OK / validate-FAIL leaves an installed, unvalidated,
  unselectable model — surfaced truthfully, retryable. Validate-OK-on-CPU / FAIL-on-GPU leaves a
  selectable model pinned to CPU with the reason shown. No stage is ever promoted to green on a
  warning/skip (diagnostics standard §3).
- **Secrets & untrusted input.** No new external input surface; `model_id` is already sanitised on
  the existing routes. No secrets involved.

---

## 7. Work breakdown (TDD, per §2/§6)

Backend:
1. `ModelManager`/eligibility helper: read `device_eligibility.json` → `(verified_providers,
   generated_at)` for a model; unit-tested pure against a temp config dir.
2. Gate in `activate_model()`: reject unvalidated models with typed reason; grandfather the active
   model; allow provider downgrade. Tests: unvalidated rejected, CPU-only allowed, active model
   grandfathered, direct-API bypass blocked.
3. Populate `InstalledModel.ready/reason` from eligibility in `list_installed_models`. Test the DTO
   surfacing.
4. (If needed) a thin `POST /api/models/{id}/validate` convenience that runs the single-model
   `compat_only` sweep and returns the run id — or the wizard calls the existing model-eval endpoint
   directly. Prefer reuse; add the alias only if the wizard wiring is cleaner for it. Document in
   `docs/api.md` if added.

Frontend:
5. `ModelInstallWizard.svelte` (or extend the existing model-step component) built on
   `DiagnosticDialog`, three stages, i18n keys with `{ default }` fallbacks.
6. Gate rendering in `ModelManager.svelte` + the model picker: unvalidated → "Validate to enable";
   selected-provider-unverified → downgrade notice. Guard with a `*.layout.test.ts` asserting the
   dialog is used and the three stages are present (diagnostics standard §4.4).

Cross-cutting: `CHANGELOG.md` (Unreleased); update
[`docs/features/ai-models.md`](../features/ai-models.md) (Model Manager + validation gate) and
[`docs/features/model-evaluation.md`](../features/model-evaluation.md) (compat sweep now also backs
install validation); mark the ROADMAP §1.2 bullet as generalised beyond first-run.

---

## 8. Open questions

1. **Convenience endpoint vs. direct model-eval call** (item 4) — decide once the wizard wiring is
   sketched; default to reuse.
2. **Grandfather scope** — is implicit eligibility for the active model *only*, or for every model
   installed before the feature ships? Proposal: active-model-only, everything else prompts
   validate-on-select. Confirm with owner.
3. **Auto-validate on download completion?** — should stage 2 always run inline after stage 1, or be
   a distinct user-initiated step? Proposal: inline within the guided wizard, but the standalone
   "download" affordance in Model Manager still lands a model in the unvalidated state so the gate is
   meaningful for non-wizard installs.

## References

- [Diagnostics & dialog standard](../standards/diagnostics-and-dialogs.md)
- [First-run setup wizard design](2026-07-12-first-run-setup-wizard-design.md) — sibling flow, shared
  visual language and hardware-validation engine.
- [Automatic model crop policy](2026-07-16-model-crop-policy.md) — why crop micro-validation is out
  of scope.
- [Model evaluation feature](../features/model-evaluation.md) — the device sweep this reuses.
- [AI Models & Performance](../features/ai-models.md) — Model Manager and provider fallback contract.

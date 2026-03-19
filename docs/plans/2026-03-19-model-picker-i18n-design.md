# Model Picker Localization and Changelog Design

## Goal
Localize the new tiered model picker and adjacent settings UX, and document the completed model-lineup/taxonomy work in the unreleased changelog without broadening into a whole-app translation project.

## Scope
- Update `CHANGELOG.md` with concise unreleased entries for the tiered model lineup, downloadable small/medium models, global model-download progress, Birder label normalization, and stronger taxonomy/manual-label backfill behavior.
- Replace hard-coded English in the model manager and related detection-settings guidance with translation keys.
- Localize adjacent user-visible strings in the same model/settings workflow where we recently added behavior.
- Add locale coverage tests for the new keys across all supported UI locales.

## Approach
Use the existing `settings.detection` namespace for settings-facing copy and add a small `settings.detection.model_manager_*` group for the model picker strings. Keep existing behavior intact; this is a copy and i18n pass, not a layout or feature redesign. Validate via locale-coverage tests plus `vitest` and `svelte-check`.

## Error Handling
- Keep existing runtime behavior for model download/activation failures.
- Ensure all newly referenced translation keys exist in every bundled locale to avoid raw-key fallback in production.

## Testing
- Add a locale coverage test covering the new keys in all locale JSON files.
- Run the new locale test directly.
- Run `npm --prefix apps/ui run check` after wiring the new keys.

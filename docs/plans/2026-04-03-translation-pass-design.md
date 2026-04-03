# Full Translation Pass Design

## Goal

Do a real multi-locale translation pass across the YA-WAMF UI, not just a token locale-file sync. The pass should improve coverage, reduce reliance on inline English fallbacks, and normalize terminology across all supported locales:

- English (`en`)
- German (`de`)
- Spanish (`es`)
- French (`fr`)
- Italian (`it`)
- Japanese (`ja`)
- Portuguese (`pt`)
- Russian (`ru`)
- Chinese (`zh`)

## Current State

The translation system is healthy enough to ship, but not yet disciplined enough to call “complete”:

- all non-English locale files are only missing two keys relative to `en.json`
- active UI code still contains hundreds of inline English fallback/default strings
- some strings are localized only through code-level defaults rather than locale data
- terminology consistency has drifted across jobs/errors/settings/model-management surfaces

This means locale JSON coverage alone would be misleading. The real work is split across locale files and component source.

## Recommended Approach

### 1. Close locale-file gaps first

Add the two missing About-page keys to every non-English locale and strengthen locale audit coverage so missing keys fail fast in CI.

### 2. Clean up the highest-visibility code surfaces

Focus on the UI areas most likely to be seen by users and most likely to still leak English through inline defaults:

- Dashboard / Events / Detection modal
- Species / Leaderboard
- Jobs / Errors / Global progress
- Video player / reclassification overlays
- top-level settings panels with many default strings

This pass should prefer existing translation keys where possible and add new keys only when necessary.

### 3. Do a terminology consistency pass

Normalize how core product concepts are rendered across locales, especially:

- full visit
- leaderboard / species leaderboard
- batch analysis
- circuit breaker
- auto video / reclassification
- jobs / queue / stale / pending / active

The goal is not literary perfection; it is product consistency and obvious UX meaning.

## Constraints

- Do not try to remove every single code-level `default:` fallback in one pass.
- Do not introduce a huge taxonomy of new keys unless the UI genuinely needs them.
- Preserve stable existing keys where translations are already good enough.
- Prefer visible UX quality over exhaustive theoretical coverage.

## Testing Strategy

- Expand locale audit coverage for newly touched keys
- Run existing locale tests
- Run focused UI tests for touched components
- Run `svelte-check`

## Success Criteria

- no locale files missing keys relative to `en.json`
- high-visibility active UI no longer depends on obvious English fallbacks for the touched surfaces
- terminology is more consistent across all locales
- tests and `svelte-check` pass

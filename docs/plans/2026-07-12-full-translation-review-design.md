# Full Translation Review Design

**Status:** In progress
**Roadmap:** 3.0 major initiative, P1/M
**Source of truth:** `apps/ui/src/lib/i18n/locales/en.json`

## Problem

YA-WAMF supports eight non-English locales, but completeness has been checked only for selected
high-risk strings. All eight currently trail the English locale by the same 67 keys. New English
copy can therefore reach `dev` without an explicit translation decision, and obsolete locale keys
can remain unnoticed.

## Delivery sequence

1. **Contract gate:** compare every scalar leaf path with `en.json` and reject missing or extra
   keys through the existing Vitest job. Complete: the temporary baseline has been removed.
2. **Completeness batches:** translate the shared UI/navigation keys, update and telemetry copy,
   then the Audio History surface. Complete for all eight non-English locales.
3. **Language review:** review each complete locale for terminology, placeholders, punctuation,
   and machine-translation artefacts. Product names, protocol names, and interpolation tokens stay
   unchanged. **Status:** a measured sweep found ≈0 full English sentences surviving in any locale
   (the byte-identical strings that remain are brands, URL/host placeholders, and legitimate
   cross-language cognates). The residual is therefore a subjective, per-language native editorial
   polish (idiom, terminology, locale typography) with low defect density — best done per language
   by a native reviewer, not by bulk machine edits.
4. **Close the gate:** remove the temporary missing-key baseline. Every locale must then have
   exactly the same leaf-key set as `en.json`. **Done.**
5. **Anti-rot ratchet:** freeze the current set of byte-identical-to-English strings per locale in
   `locales.identical-baseline.json`; `locales.untranslated-regression.test.ts` fails CI if any
   *new* translatable string lands identical to English, so future untranslated copy can't slip in
   silently. Genuine new brands/cognates are added to the baseline in the same change. **Done.**

## Contract rules

- Nested object order does not matter; scalar leaf paths define the contract.
- A locale may not add keys absent from English.
- A newly missing key is always a CI failure.
- Every localized string must preserve the English interpolation-token set.
- Empty strings and selected English copies continue to be rejected by the existing semantic
  locale audit.
- Translation batches must preserve interpolation variables and product/integration names.

## Acceptance

- All eight non-English locales have exactly the English leaf-key set. ✅
- The structural audit has no allowlist and runs under `npm test` in CI. ✅
- A ratchet guards against new untranslated strings landing identical to English. ✅
- A language-quality pass is recorded for every locale (residual: native editorial polish; see step 3).
- `npm run check`, `npm test`, and `npm run build` pass. ✅

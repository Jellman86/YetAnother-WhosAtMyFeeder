# Translation editorial review — 2026-07-20

## Outcome

YA-WAMF's English source catalog and all eight translated catalogs contain the same 1,977 scalar
leaf keys. Every interpolation token matches its English source, no new user-facing string is
silently copied from English, and the application-wide editorial checks pass.

This review covers `en`, `de`, `es`, `fr`, `it`, `ja`, `pt`, `ru`, and `zh`. It is a
repository-backed editorial and automated quality pass. It is **not independent native-speaker
certification**, so release notes must preserve that limitation unless native reviewers sign off
before release.

## Review method

The pass checked every catalog in five layers:

1. Exact scalar-key parity with `en.json`, with no missing or obsolete keys.
2. Exact preservation of `{interpolation_tokens}` at every matching key.
3. A ratcheted comparison against English to reject newly copied user-facing strings while allowing
   explicit brands, protocols, URLs, technical examples, and genuine cognates.
4. An editorial scan for surrounding whitespace, Unicode replacement/control characters, mojibake,
   ASCII ellipses in prose, and known accent-loss transliterations.
5. Locale-specific checks for French non-breaking spacing before `:`, `;`, `!`, and `?`, plus
   sentence-length Latin-only copy in the Japanese, Russian, and Chinese catalogs.

The permanent coverage lives in:

- `locales.audit.test.ts` for structure, required active keys, high-risk localization, and tokens;
- `locales.untranslated-regression.test.ts` and `locales.identical-baseline.json` for English-copy
  regression control;
- `locales.editorial-quality.test.ts` for encoding, whitespace, typography, accent-loss, and script
  checks.

## Findings corrected

- Added the missing localized deployment-refresh message used by stale tabs after an update.
- Replaced copied English enrichment fallback guidance in Spanish, French, Italian, Japanese,
  Portuguese, Russian, and Chinese, while preserving the eBird-to-iNaturalist fallback meaning.
- Corrected accent-stripped text in recently added German, Spanish, French, Italian, and Portuguese
  notification, public-access, and video-player surfaces.
- Reworded Russian `open-source NVR` copy in natural Russian and separated the embedded
  `Server-Sent Events` term correctly in Japanese.
- Removed trailing whitespace from the English keyboard-shortcut hint.
- Replaced three-dot loading/search prose with the typographic ellipsis in every catalog; literal
  webhook and bot-token examples intentionally retain three dots.
- Applied narrow non-breaking spaces before French double punctuation so labels and questions do
  not wrap incorrectly.

## Residual limitation

Automated checks can prove catalog structure, token safety, encoding, selected terminology rules,
and many common editorial failures. They cannot prove that every one of roughly 15,800 translated
strings is idiomatic to a native speaker in every context.

No known structural or automated editorial defect remains after this pass. The generic `pt`
catalog has historically accumulated a mixture of European and Brazilian terminology; choosing one
regional convention is a product decision that should accompany native review rather than an
unreviewed bulk rewrite. Native reviewers may also prefer different idioms for retained technical
terms such as snapshot, pipeline, dashboard, and fallback.

For the 3.0 exit criterion, choose one of these honest paths:

1. obtain independent native-speaker review for each locale presented as fully supported; or
2. state in the release notes that the catalogs passed comprehensive structural/editorial review
   but have not received independent native-speaker certification.

## Verification

Run the frontend quality gates from `apps/ui`:

```bash
npm run check
npm test
npm run build
```

The repository documentation consistency check and `git diff --check` must also pass before merge.

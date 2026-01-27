# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

- **Fixed:** Enforced guest access checks for Frigate media proxies to prevent access to hidden or out-of-range events.
- **Fixed:** Added guest rate limiting to classifier status/label endpoints.
- **Fixed:** Added security headers to frontend Nginx responses.
- **Changed:** Disabled frontend production sourcemaps by default.
- **Fixed:** Added FastAPI request args to rate-limited classifier endpoints to satisfy SlowAPI.

## [2.6.6] - 2026-01-25

- **Added:** Standardized AI Naturalist responses to structured Markdown headings (`Appearance`, `Behavior`, `Naturalist Note`, `Seasonal Context`).
- **Added:** AI analysis can prefer clip frames (`use_clip`, `frame_count`) and falls back to snapshots.
- **Added:** Leaderboard hero now shows species blurb and “Read more” link (Wikipedia/iNaturalist).
- **Added:** Guest mode documentation in README and docs, plus About page feature entry.
- **Added:** BirdNET status exposed to guests so the Recent Audio panel can show in public view.
- **Changed:** Leaderboard chart now uses fixed dimensions to avoid NaN sizing/overlap issues.
- **Fixed:** `docker-compose.dev.yml` restored and aligned with prod/base configuration.
- **Fixed:** Added missing error boundary translation keys across non-English locales.
- **Fixed:** Removed stray `common.edit` key from Chinese locale.

## [2.6.5] - 2026-01-24

- **Changed:** Version bump to 2.6.5.

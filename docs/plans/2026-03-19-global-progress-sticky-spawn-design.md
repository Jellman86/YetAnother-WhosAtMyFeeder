# Global Progress Sticky Spawn Design

**Date:** 2026-03-19

## Problem

The global progress banner was changed to a sticky element under the app header, but its initial appearance left excess whitespace above the banner and did not feel like it pushed the page content down cleanly when jobs started.

## Chosen Behavior

- Render the global progress banner in normal document flow when it first appears.
- Keep a small bottom gap under the banner so page content stays readable when it spawns.
- Switch the wrapper into sticky positioning only after the page has started scrolling.
- Keep the sticky offset aligned with the shared `--app-chrome-height` contract so the banner remains below the header/mobile top bar.

## Rationale

This keeps the initial state visually stable, preserves the natural page push-down effect the user expects, and still provides sticky access to long-running job progress after the user starts moving through the page.

## Validation

- Add a layout test that requires the scroll-gated sticky contract in `App.svelte`.
- Re-run the global progress layout test and an adjacent progress-store test set after implementation.

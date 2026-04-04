# Desktop Nav Simplification Design

## Goal

Remove the desktop horizontal navigation model entirely while preserving the current mobile header menu and mobile navigation behavior.

## Decision

YA-WAMF will support a single desktop navigation model: the left sidebar. The top header will remain for status, account/theme/language controls, notifications, and the existing mobile menu, but it will no longer render route tabs on desktop.

## Why

- The horizontal desktop nav duplicates the sidebar and creates an extra layout branch with little product value.
- The current app shell already treats mobile as a special case and has a strong vertical/sidebar path.
- Eliminating the horizontal mode reduces layout state, settings complexity, and desktop rendering branches without changing mobile UX.

## Scope

### In scope

- Remove the desktop route-tab nav from `Header.svelte`
- Collapse layout state to vertical-only
- Migrate old persisted `layout=horizontal` users safely to `vertical`
- Remove the layout-choice UI from appearance/settings surfaces
- Keep the mobile menu in the header as-is
- Keep desktop sidebar behavior unchanged

### Out of scope

- Reworking the mobile menu interaction model
- Redesigning the sidebar itself
- Reorganizing route structure or permission gating

## Target Behavior

### Desktop

- Sidebar is the only route navigation surface
- Header shows branding, status, public/user badge, language selector, keyboard shortcuts, auth actions, theme toggle, notification center
- No horizontal route nav remains

### Mobile

- Current mobile header menu remains
- Current mobile sidebar behavior remains
- No functional change expected

## Migration

- Any stored `localStorage.layout = "horizontal"` is coerced to `vertical` on load
- The layout store no longer exposes a real horizontal mode
- App shell layout padding/chrome calculations should assume vertical on desktop and mobile top bar behavior on mobile

## Risks

- Removing the desktop header nav without fully removing the horizontal layout branch could leave dead conditional layout logic behind
- Settings UI could still reference removed layout keys and create runtime inconsistency
- Existing tests may encode the old dual-layout contract and need tightening around the new single-layout behavior

## Validation

- Source-level checks for header/nav structure
- Layout-store behavior test for legacy `horizontal` migration
- Settings/appearance checks ensuring layout choice UI is gone
- `svelte-check` green after the refactor

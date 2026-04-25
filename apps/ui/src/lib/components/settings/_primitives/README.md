# Settings primitives

Shared building blocks for the settings page. Every settings tab uses these
instead of rolling its own card chrome, switch markup, or padding scale.

A build-time guard (`settings-style-audit.test.ts`) fails if a migrated tab
reintroduces inline `role="switch"` markup or bypasses the standard chrome —
adding a tab to `MIGRATED_COMPONENTS` is what enrolls it in the guard.

## When to reach for what

| You want… | Use |
|---|---|
| A whole settings panel with title/icon/header tile | `SettingsCard` |
| One row inside a card: label + description + a control on the right | `SettingsRow` |
| The same row but the control sits under the label (sliders, multi-button pickers, segmented controls) | `SettingsRow` with `layout="stacked"` |
| A boolean on/off | `SettingsToggle` (the **only** legal source of `role="switch"` in settings) |
| A `<select>` dropdown | `SettingsSelect` |
| A grid of mutually-exclusive option tiles or cards | `SettingsSegmented` |
| A text / number / url / password / email field | `SettingsInput` |
| A multi-line text field (mono for JSON / templates, sans otherwise) | `SettingsTextarea` |
| Hide power-user knobs behind "Advanced" — collapsed by default, persists per-browser | `AdvancedSection` |
| The page itself: title, refresh, status banner, sticky save bar | `SettingsPage` |

## Conventions baked into the primitives

- **One card chrome**: `card-base rounded-3xl p-6 md:p-8 backdrop-blur-md`. Don't reintroduce per-tab coloured icon tiles — the leading tile is monochrome by design.
- **One inner row chrome**: `rounded-2xl p-4 bg-slate-50 dark:bg-slate-900/50` with a 1px border.
- **One accent colour**: teal. Status colours (amber, red, emerald) signal warning / danger / success only — they aren't decoration.
- **One typography ramp**: card h3 (lg/xl, font-black), row label (sm, font-bold), row description (text-[11px]). Don't add a fourth.
- **One focus ring**: `focus:ring-2 focus:ring-teal-400`.

## Basic vs Advanced taxonomy

The rule we apply when deciding what goes behind `AdvancedSection`:

> If a fresh installer of YA-WAMF will need to touch this control to get a working
> setup *or* to make a single core decision (enable on/off, choose a model, set a
> threshold) — keep it Basic. Otherwise put it behind Advanced.

Concrete examples already applied:

- **Connection**: MQTT port and recording-clip seconds-before/after → Advanced. Frigate URL, MQTT broker, MQTT auth, clips on/off → Basic.
- **AI**: prompt template overrides and pricing JSON registry → Advanced. Provider, API key, model → Basic.
- **Integrations**: per-channel API tunables (eBird radius/days/locale, BirdNET buffer hours / correlation seconds, iNat default lat/lon/place) → Advanced.
- **Data**: maintenance concurrency, HQ snapshot JPEG quality, weather backfill → Advanced. Retention window, manual purge, cache on/off → Basic.
- **Detection**: video classifier delay/retries/concurrency/frames, OpenVINO/CUDA diagnostics, crop overrides → Advanced. Confidence threshold, "Trust Frigate sublabels", auto-video on/off → Basic.
- **Notifications**: Pushover priority + per-device targeting, Email "only on event end" + dashboard URL → Advanced. Channel API keys, recipient addresses, test buttons → Basic.

`AdvancedSection`'s open/closed state is persisted in `localStorage` under
`yawamf:settings:advanced:<id>`, so once a user opens an Advanced section it
stays open across reloads on that browser.

## Adding a new primitive

1. Drop the component in this folder. Use Svelte 5 runes and snippets, no stores.
2. Update `settings-style-audit.test.ts` if the primitive is the new owner of an HTML pattern that should be banned elsewhere (the way `SettingsToggle` owns `role="switch"`).
3. Document it in the table above.
4. Use it in at least one tab in the same PR — primitives without a real consumer tend to drift.

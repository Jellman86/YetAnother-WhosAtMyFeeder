# Settings primitives

Shared building blocks for the settings page. Every settings tab uses these
instead of rolling its own card chrome, switch markup, or padding scale.

A build-time guard (`settings-style-audit.test.ts`) fails if a migrated tab
reintroduces inline `role="switch"` markup or bypasses the standard chrome —
adding a tab to `MIGRATED_COMPONENTS` is what enrolls it in the guard. In every
settings tab it also fails a `<label>` that wraps an `sr-only` radio or checkbox
without `focus-within:ring` classes, because the tile is then the only place
keyboard focus can show.

## When to reach for what

| You want… | Use |
|---|---|
| A whole settings panel with title/icon/header tile | `SettingsCard` |
| One row inside a card: label + description + a control on the right | `SettingsRow` |
| The same row but the control sits under the label (sliders, multi-button pickers, segmented controls) | `SettingsRow` with `layout="stacked"` |
| A boolean on/off | `SettingsToggle` (the **only** legal source of `role="switch"` in settings) |
| A `<select>` dropdown | `SettingsSelect` |
| A grid of mutually-exclusive option tiles or cards | `SettingsSegmented` |
| A compact single choice inside a list row, with options that can be unavailable (camera Off / Birds / Garden animals / Both) | Native radios in a `role="radiogroup"`, as `CameraWatchRow` does: `sr-only` inputs in `min-h-11` labels with `focus-within:ring`, a check mark on the chosen option and a worded reason linked by `aria-describedby` for a disabled one |
| A name for a few rows inside a card (a channel, "Garden animals") | `SettingsSubheading`; its level follows the card it sits in |
| A text / number / url / password / email field | `SettingsInput`; pass `field` (the saved setting's API name) so a refused save marks it and shows the reason under it |
| A multi-line text field (mono for JSON / templates, sans otherwise) | `SettingsTextarea` |
| Hide power-user knobs behind "Show advanced options", collapsed by default; Settings keeps it open for the rest of the visit | `AdvancedSection` |
| The page itself: load failure with retry, and the save bar (count, tabs, Discard changes, Save changes, refused fields) | `SettingsPage` |
| A refused value's reason under a hand-built input | `FieldRefusal`, with the input's `aria-invalid` and `aria-describedby` set from the same refusal |

## Conventions baked into the primitives

- **One card chrome**: a `SettingsCard` is a display-face heading over one raised panel of rows (`card-base settings-section-body`). There is no icon tile, band or box inside it.
- **One inner row chrome**: rows are not boxed. They sit in that panel, separated by hairline dividers (`divide-line-soft`), each with `py-4`.
- **One accent colour**: the `brand` token, which follows the colour theme (teal in Classic). Status colours signal warning / danger / success only; they aren't decoration.
- **One typography ramp**: the open section's `h2` (`text-2xl`, bold, kept in view by `SettingsPage`), a card's `h3` (`text-xl`, display face, semibold; `h4` at `text-lg` when `nested` under More options), a `SettingsSubheading` inside a card (reading face, semibold, one level below its card), the row label (`text-base`, semibold) and the row description (`text-sm`, muted, regular). Values, links and statuses are regular. Don't add another step, and don't write a heading tag by hand: `settings-reading-hierarchy.layout.test.ts` fails on one.
- **Every row and card is findable**: give a `SettingsRow` a static `labelId`, a `SettingsSlider` its `id` and a `SettingsCard` an `id`, and add the entry to `src/lib/settings/settings-search-index.ts`. The index test names what is missing.
- **One focus ring**: the `focus-ring` utility from `app.css` (`ring-focus`, keyboard focus only).
- **Selects draw their own box**: `SettingsSelect` uses `appearance-none`, `min-h-11` and a decorative chevron, because desktop WebKit's native menu list discards padding and height (a 22px control). Below `sm` it uses `pl-2 pr-5` with the chevron at `right-1.5`, so a 320px screen at 200% text still shows part of the value; from `sm` up it uses `pl-4 pr-8`. The option picker stays native.

## Basic vs Advanced taxonomy

The rule we apply when deciding what goes behind `AdvancedSection`:

> If a fresh installer of YA-WAMF will need to touch this control to get a working
> setup *or* to make a single core decision (enable on/off, choose a model, set a
> threshold) — keep it Basic. Otherwise put it behind Advanced.

Concrete examples already applied:

- **Connection**: full-visit clip seconds before/after → Advanced. Frigate URL, MQTT address and port, MQTT auth → Basic. Fetching video clips sits under the section's **More options**.
- **AI**: prompt template overrides and pricing JSON registry → Advanced. Provider, API key, model → Basic.
- **Integrations**: per-channel API tunables (eBird radius/days/locale, BirdNET buffer hours / correlation seconds, iNat default lat/lon/place) → Advanced.
- **Data**: maintenance concurrency, HQ snapshot JPEG quality, weather backfill → Advanced. Retention window, manual purge, storage limit → Basic.
- **Detection**: video classifier delay/retries/concurrency/frames, OpenVINO/CUDA diagnostics, crop overrides → Advanced. Naming threshold and minimum confidence floor → Basic. "Trust Frigate sublabels" and auto video analysis sit under the section's **More options**.
- **Notifications**: Pushover priority + per-device targeting, Email "only on event end" + dashboard URL → Advanced. Channel API keys, recipient addresses, test buttons → Basic.

`AdvancedSection`'s open/closed state is not stored. Inside Settings the page
keeps it by its `id` for the rest of the visit, so it stays open while
you move between sections, and a reload closes it again.

## Adding a new primitive

1. Drop the component in this folder. Use Svelte 5 runes and snippets, no stores.
2. Update `settings-style-audit.test.ts` if the primitive is the new owner of an HTML pattern that should be banned elsewhere (the way `SettingsToggle` owns `role="switch"`).
3. Document it in the table above.
4. Use it in at least one tab in the same PR — primitives without a real consumer tend to drift.

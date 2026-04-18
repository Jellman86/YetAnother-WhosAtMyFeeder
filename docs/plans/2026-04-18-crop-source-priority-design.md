# Crop Source Priority Configuration Design

## Goal

Add one global configuration setting that controls whether Frigate hints or the configured crop model are preferred for bird cropping, while preserving the existing crop detector tier setting and polishing the crop controls UI.

## Current Behavior

- The crop detector tier defaults to `fast`.
- Normal classification prefers Frigate hints first, then falls back to the configured crop model.
- High-quality snapshot generation also prefers Frigate hints first, then falls back to the crop model.
- This source order is hard-coded and not configurable.
- The crop tier UI uses a basic standalone select rather than the more polished dropdown style used elsewhere in the settings/model UI.

## Requirements

- One global setting, not separate classification vs HQ settings.
- The configured crop model tier must still be respected whenever the model path is used.
- Existing installs should keep current behavior by default.
- UI should present crop tier and crop source priority consistently.

## Options Considered

### 1. Global source-priority setting

Add `bird_crop_source_priority` under classification settings with values:
- `frigate_hints_first`
- `crop_model_first`
- `crop_model_only`
- `frigate_hints_only`

Pros:
- Clean mental model
- Minimal settings surface
- Works for both classification and HQ snapshot flows

Cons:
- No separate tuning for classification vs HQ

### 2. Separate settings for classification and HQ

Pros:
- More control

Cons:
- More complexity than requested
- Easy to confuse with crop tier and model-specific overrides

## Chosen Design

Use option 1.

Keep the current crop detector tier setting and add one global source-priority setting. Source priority decides the order of crop sources. Crop tier decides which model is used when the crop model source is involved.

Default value: `frigate_hints_first`

## Behavior

### Classification

- `frigate_hints_first`: hints -> configured crop model
- `crop_model_first`: configured crop model -> hints
- `crop_model_only`: configured crop model only
- `frigate_hints_only`: hints only

### High-quality snapshots

Use the same global order as classification.

### Respect the configured model

When the crop model source is selected, it must use the currently configured crop detector tier (`fast` or `accurate`), including its fallback behavior.

## UI

In Detection Settings:
- keep crop controls together in one card
- style the crop tier control like the main models dropdown
- add a second matching dropdown for crop source priority
- keep short help text under both controls

## Testing

- Classification tests for each priority mode
- HQ snapshot tests for each priority mode
- Settings schema/API tests for the new field
- UI layout test ensuring the new control exists and uses the styled dropdown pattern

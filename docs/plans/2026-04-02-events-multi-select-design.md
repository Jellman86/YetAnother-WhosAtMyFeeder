# Events Multi-Select Card Design

**Date:** 2026-04-02

**Problem**

The current multi-select affordance in the Events explorer uses a text pill inside the card image area. That creates three problems:

- it overlaps snapshot content and existing badges
- it duplicates wording already shown in the bulk action bar
- it makes selected cards feel visually disconnected from the cyan selection styling used elsewhere in the page

**Goals**

- Make selected cards visually obvious with a stronger cyan/blue border treatment.
- Remove `Select` / `Selected` words from individual cards.
- Use a simpler icon-only control that implies “select this card”.
- Keep the selector from covering snapshot badges or bird imagery.
- Preserve clear behavior in selection mode for both selected and unselected cards.

**Non-Goals**

- No change to bulk-tagging behavior or selection state logic.
- No change to non-selection card interactions outside `selectionMode`.
- No new modal or bulk action flows.

**Recommended Approach**

Adopt an edge-mounted circular selector:

1. In selection mode, each card shows a circular selector straddling the top-left card edge.
2. Unselected state uses a neutral outlined circle.
3. Selected state uses a filled cyan circle with a checkmark icon.
4. Selected cards also get a stronger cyan border/ring so the whole card reads as active.
5. The control is icon-only; explanatory text remains in the bulk action bar above the grid.

**Interaction Model**

- The selector is only visible in `selectionMode`.
- Clicking the card still toggles selection through the existing page wiring.
- The selector is decorative/affirming rather than a separate interaction target, so it does not need extra text on the card surface.
- The affordance should feel aligned with the existing cyan multi-select button and bulk action panel.

**Visual Direction**

- Reuse the same cyan family already used in the Events selection UI.
- Keep the selector visually crisp and compact with a white/light neutral unselected state.
- Mount it partly outside the card frame so the snapshot remains unobstructed.
- Use a slightly stronger ring/border on selected cards than the current subtle state.

**Risks**

- If the edge-mounted control is positioned too far outside the card, it can clip in dense grids.
- If the selected card border is too strong, it can compete with hidden/favorite/reclassification states.
- If the control becomes interactive separately from the card, focus/keyboard behavior can drift from the current simple selection model.

**Acceptance Criteria**

- Selected cards have a clearly stronger cyan border/ring.
- The in-card `Select` / `Selected` text is gone.
- The selector no longer overlaps the main snapshot badges/content.
- The control is icon-only and clearly communicates selected vs unselected state.
- Existing selection mode behavior still works without regressions.

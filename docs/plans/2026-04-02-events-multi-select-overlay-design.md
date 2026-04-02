# Events Multi-Select Overlay Design

**Date:** 2026-04-02

**Problem**

The first pass at the Events multi-select redesign removed the text pill, but the remaining corner-only selector still feels too weak. From a grid view, selection does not read strongly enough, and the card frame still does too little of the work.

**Goals**

- Make selected cards immediately obvious at a glance.
- Keep snapshot content readable while giving selected cards a clear visual state.
- Avoid relying on `Select` / `Selected` words inside each card.
- Use the card surface itself as the main signal, with the selector icon as confirmation.

**Recommended Approach**

Use a full selected-card treatment rather than a corner-only one:

1. Keep a selector icon, but demote it to a supporting role.
2. Add a subtle cyan-tinted blurred overlay across the image area for selected cards.
3. Strengthen the selected border/ring noticeably so it reads from a distance.
4. Keep unselected cards unchanged during selection mode.

**Interaction Model**

- Only selected cards get the cyan veil and stronger frame.
- Unselected cards remain neutral, so the selected subset is visually prominent without dimming the entire grid.
- The selector stays icon-only and anchored near the top edge, but the overlay becomes the primary state cue.

**Visual Direction**

- Use a frosted cyan veil over the media area, not an opaque block.
- Add a stronger cyan outer ring and border than the current implementation.
- Keep the overlay below the existing badges and controls so favorite/full-visit/media status remain readable.
- Use a cleaner selected icon disc that feels integrated with the overlay instead of floating weakly at the corner.

**Risks**

- Too much tint can reduce snapshot readability.
- Too much blur or too strong a ring can make selected cards feel disabled instead of active.
- If the overlay sits above badges or action controls, it will reintroduce the same visual collisions we just removed.

**Acceptance Criteria**

- Selected cards are clearly identifiable in a dense grid from a quick scan.
- The selected border/ring is materially stronger than the unselected state.
- The selected treatment looks intentional and cohesive rather than like a small badge added on top.
- The selector no longer feels like the only signal carrying the state.

# Events Multi-Select Overlay Design

**Date:** 2026-04-02

**Problem**

The current selected state is still too weak. The corner-led selector is not carrying enough visual weight, the selected frame still competes with inner card layers, and the selected state does not clearly obscure the normal card content the way a proper multi-select state should.

**Goals**

- Make selected cards immediately obvious at a glance.
- Make the card border itself carry the selected state cleanly and visibly.
- Obscure normal card content on selected cards with a strong frosted cyan-blue veil.
- Use a single centered checkmark as the selected symbol.
- Avoid relying on `Select` / `Selected` words or corner controls inside each card.

**Recommended Approach**

Use a full-card selected veil:

1. Remove the top-left selector entirely.
2. Put the strong selected state on the real card border so it matches the card shape exactly.
3. Add a heavier cyan-blue frosted overlay above the card content, not below it.
4. Place a large centered checkmark above that veil as the only in-card selection symbol.
5. Keep unselected cards unchanged during selection mode.

**Interaction Model**

- Only selected cards get the cyan veil and stronger card border.
- The overlay sits above existing badges, labels, and actions so selected cards look intentionally masked.
- The centered checkmark confirms the selected state without adding any text or extra control chrome.
- Unselected cards remain neutral, so the chosen subset pops by contrast.

**Visual Direction**

- Use a frosted cyan-blue veil across the whole card, not just the image area.
- Match the tint to the existing multi-select cyan/blue used in the explorer toolbar.
- Put a strong cyan state directly on the card border so it aligns perfectly with the card shape.
- Use a large standalone checkmark in the center, not a small chip or circle.

**Risks**

- Too much tint or blur can make selected cards feel disabled instead of intentionally selected.
- A selected border that is too thin will still disappear visually in the grid.
- The centered checkmark needs enough contrast to read through the stronger veil.

**Acceptance Criteria**

- Selected cards are clearly identifiable in a dense grid from a quick scan.
- The cyan selected border is clearly visible on the real card itself.
- The selected veil sits above all normal card content and intentionally obscures it.
- The top-left corner selector is gone.
- A large centered checkmark is the only in-card selected symbol.

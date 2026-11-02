/**
 * Where a taxon card goes: inside its container (the family-tree dialog, else the window) and
 * never over the name it describes. Below the name, else above, else beside it on the roomier
 * side, else on the roomier of above and below with its own scroll.
 */
export interface Box {
    left: number;
    top: number;
    right: number;
    bottom: number;
}

export interface Placement {
    left: number;
    top: number;
    /** The most the card may be tall here; past it, the card scrolls inside. */
    maxHeight: number;
}

export function placeCard(
    anchor: Box,
    card: { width: number; height: number },
    bounds: Box,
    gap = 8,
    margin = 8
): Placement {
    const inner = { left: bounds.left + margin, top: bounds.top + margin, right: bounds.right - margin, bottom: bounds.bottom - margin };
    const centred = Math.max(inner.left, Math.min((anchor.left + anchor.right) / 2 - card.width / 2, inner.right - card.width));
    const below = inner.bottom - anchor.bottom - gap;
    const above = anchor.top - gap - inner.top;
    if (card.height <= below) return { left: centred, top: anchor.bottom + gap, maxHeight: below };
    if (card.height <= above) return { left: centred, top: anchor.top - gap - card.height, maxHeight: above };

    const right = inner.right - anchor.right - gap;
    const left = anchor.left - gap - inner.left;
    if (Math.max(left, right) >= card.width) {
        const top = Math.max(inner.top, Math.min((anchor.top + anchor.bottom) / 2 - card.height / 2, inner.bottom - card.height));
        return {
            left: right >= left ? anchor.right + gap : anchor.left - gap - card.width,
            top,
            maxHeight: inner.bottom - top
        };
    }
    return below >= above
        ? { left: centred, top: anchor.bottom + gap, maxHeight: below }
        : { left: centred, top: Math.max(inner.top, anchor.top - gap - card.height), maxHeight: above };
}

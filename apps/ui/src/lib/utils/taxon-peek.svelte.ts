import type { Taxon } from '../api/taxonomy';

/**
 * Which taxon's card is open, and where it points. One per surface, shared by every trigger on
 * it, so moving between names moves the one card rather than stacking several.
 *
 * It follows the hover pop-out contract in docs/standards/layout-patterns.md §4: a hovering
 * pointer or keyboard focus opens it, a tap opens it by its click and pins it, the pointer may
 * travel into the card within a short grace, and Escape closes it.
 */
export interface PeekAnchor {
    taxon: Taxon;
    current: boolean;
    /** The name the card points at; read again as the page scrolls so the card follows it. */
    element: Element;
    pinned: boolean;
}

// Long enough that sweeping the pointer across a tree does not open a card, and fetch a
// picture, for every name it passes.
const OPEN_DELAY_MS = 150;
// A pointer travelling from the name to the card crosses a gap (WCAG 2.2 SC 1.4.13).
const CLOSE_GRACE_MS = 120;

export class TaxonPeek {
    anchor = $state<PeekAnchor | null>(null);
    private openTimer: ReturnType<typeof setTimeout> | null = null;
    private closeTimer: ReturnType<typeof setTimeout> | null = null;

    isOpen(taxonId: number): boolean {
        return this.anchor?.taxon.taxon_id === taxonId;
    }

    private clearTimers(): void {
        if (this.openTimer) clearTimeout(this.openTimer);
        if (this.closeTimer) clearTimeout(this.closeTimer);
        this.openTimer = null;
        this.closeTimer = null;
    }

    private place(taxon: Taxon, current: boolean, element: Element, pinned: boolean): void {
        this.anchor = { taxon, current, pinned, element };
    }

    /** A hovering pointer: opens after a moment, unless a tapped card is pinned open. */
    hover(taxon: Taxon, current: boolean, element: Element): void {
        if (this.anchor?.pinned) return;
        this.clearTimers();
        this.openTimer = setTimeout(() => this.place(taxon, current, element, false), OPEN_DELAY_MS);
    }

    /** Keyboard focus: opens at once. */
    focus(taxon: Taxon, current: boolean, element: Element): void {
        this.clearTimers();
        this.place(taxon, current, element, false);
    }

    /** A click or tap: opens and pins the card, or closes it if this taxon's card is pinned. */
    toggle(taxon: Taxon, current: boolean, element: Element): void {
        this.clearTimers();
        if (this.anchor?.pinned && this.isOpen(taxon.taxon_id)) {
            this.anchor = null;
            return;
        }
        this.place(taxon, current, element, true);
    }

    /** The pointer left a name or the card: close after the grace, unless pinned. */
    leave(): void {
        if (this.openTimer) clearTimeout(this.openTimer);
        this.openTimer = null;
        if (this.anchor?.pinned) return;
        if (this.closeTimer) clearTimeout(this.closeTimer);
        this.closeTimer = setTimeout(() => {
            this.anchor = null;
            this.closeTimer = null;
        }, CLOSE_GRACE_MS);
    }

    /** The pointer reached the card. */
    stay(): void {
        if (this.closeTimer) clearTimeout(this.closeTimer);
        this.closeTimer = null;
    }

    close(): void {
        this.clearTimers();
        this.anchor = null;
    }
}

/** Hover is for a hovering pointer: a touch browser replays a tap as pointerenter first. */
export function isHoverPointer(event: PointerEvent): boolean {
    return event.pointerType !== 'touch';
}

/** Keyboard focus, not the focus a tap or click gives a button. */
export function isKeyboardFocus(target: EventTarget | null): boolean {
    if (!(target instanceof Element)) return true;
    try {
        return target.matches(':focus-visible');
    } catch {
        return true;
    }
}

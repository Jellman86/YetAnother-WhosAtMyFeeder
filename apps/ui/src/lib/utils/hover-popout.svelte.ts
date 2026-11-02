/**
 * The hover pop-out contract (docs/standards/layout-patterns.md §4), shared by every small
 * capture that opens a larger preview: birds (`DetectionPreview`) and Garden animals
 * (`GardenCapturePreview`). The panel itself is `HoverPopoutPanel`.
 */

/**
 * A pointer travelling from a thumbnail to its panel crosses a gap; closing on the first
 * mouseleave would put the panel out of reach (WCAG 2.2 SC 1.4.13, "hoverable").
 */
export const POPOUT_CLOSE_GRACE_MS = 120;

const GAP = 8;
const VIEWPORT_MARGIN = 8;

export interface PopoutAnchor {
    x: number;
    y: number;
    above: boolean;
}

interface PopoutSize {
    width: number;
    estimatedHeight: number;
}

type TriggerRect = Pick<DOMRectReadOnly, 'top' | 'bottom' | 'left' | 'width'>;

/**
 * Where the panel sits, in viewport coordinates. A thumbnail near the foot of the window has no
 * space beneath it, so the panel flips above rather than running off the screen, and it is
 * clamped so neither edge leaves the window.
 */
export function popoutAnchor(rect: TriggerRect, viewport: { width: number; height: number }, panel: PopoutSize): PopoutAnchor {
    const above = rect.bottom + GAP + panel.estimatedHeight > viewport.height;
    const half = panel.width / 2;
    const centre = Math.min(
        Math.max(rect.left + rect.width / 2, half + VIEWPORT_MARGIN),
        viewport.width - half - VIEWPORT_MARGIN
    );
    return { x: centre, y: above ? rect.top - GAP : rect.bottom + GAP, above };
}

/**
 * A touch browser replays a tap as mouseenter and, on Chrome, focus before the click; a pop-out
 * that opened on either would swallow the tap (iOS) or sit under the record (Chrome). Hover is
 * for a hovering pointer and focus is for the keyboard; a tap opens by its click.
 */
function isKeyboardFocus(target: EventTarget | null): boolean {
    if (!(target instanceof Element)) return true;
    try {
        return target.matches(':focus-visible');
    } catch {
        return true;
    }
}

/**
 * One component's pop-outs, one per trigger index, at most one open. Construct it during
 * component initialisation, with the component's `$props.id()`: it follows its trigger while the
 * page scrolls, clears its timer when the component goes away, and names each panel so its
 * trigger can point at it.
 */
export class HoverPopout {
    openIndex = $state<number | null>(null);
    anchor = $state<PopoutAnchor | null>(null);
    /** The wrapper that owns the triggers; focus moving within it keeps the panel open. */
    root = $state<HTMLElement | null>(null);
    triggers = $state<HTMLElement[]>([]);
    #closeTimer: ReturnType<typeof setTimeout> | null = null;
    readonly #id: string;
    readonly #size: PopoutSize;

    constructor(id: string, size: PopoutSize = { width: 240, estimatedHeight: 220 }) {
        this.#id = id;
        this.#size = size;
        $effect(() => () => this.#clearTimer());
        // Placed in viewport coordinates, so the panel follows its trigger as the page moves.
        // Closing on the first scroll broke the keyboard path: focusing a trigger below the fold
        // scrolls it into view, and that scroll landed right after the panel opened. A trigger
        // scrolled out of sight still closes it; a panel pointing at nothing is honest to no one.
        $effect(() => {
            const index = this.openIndex;
            if (index === null) return;
            let pending: number | null = null;
            const follow = () => {
                if (pending !== null) return;
                pending = requestAnimationFrame(() => {
                    pending = null;
                    const rect = this.triggers[index]?.getBoundingClientRect();
                    if (!rect || rect.bottom < 0 || rect.top > window.innerHeight) {
                        this.hide(true);
                        return;
                    }
                    this.#place(index);
                });
            };
            window.addEventListener('scroll', follow, true);
            window.addEventListener('resize', follow);
            return () => {
                if (pending !== null) cancelAnimationFrame(pending);
                window.removeEventListener('scroll', follow, true);
                window.removeEventListener('resize', follow);
            };
        });
    }

    #clearTimer(): void {
        if (this.#closeTimer) clearTimeout(this.#closeTimer);
        this.#closeTimer = null;
    }

    #place(index: number): void {
        const trigger = this.triggers[index];
        if (!trigger) return;
        this.anchor = popoutAnchor(trigger.getBoundingClientRect(), { width: window.innerWidth, height: window.innerHeight }, this.#size);
    }

    panelId(index = 0): string {
        return `${this.#id}-popout-${index}`;
    }

    /**
     * The trigger's `aria-describedby`: the open panel, so a screen reader reads its name, score,
     * state and camera after the trigger's own label. Absent while closed, as there is nothing to read.
     */
    describedBy(index = 0): string | undefined {
        return this.openIndex === index && this.anchor ? this.panelId(index) : undefined;
    }

    show(index = 0): void {
        this.#clearTimer();
        this.#place(index);
        this.openIndex = index;
    }

    hide(immediate = false): void {
        this.#clearTimer();
        if (immediate) {
            this.openIndex = null;
            return;
        }
        this.#closeTimer = setTimeout(() => {
            this.openIndex = null;
            this.#closeTimer = null;
        }, POPOUT_CLOSE_GRACE_MS);
    }

    cancelScheduledClose = (): void => this.#clearTimer();

    pointerEnter = (event: PointerEvent, index = 0): void => {
        if (event.pointerType !== 'touch') this.show(index);
    };

    focusIn = (event: FocusEvent, index = 0): void => {
        if (isKeyboardFocus(event.target)) this.show(index);
    };

    focusOut = (event: FocusEvent): void => {
        const next = event.relatedTarget;
        if (next instanceof Node && this.root?.contains(next)) return;
        this.hide(true);
    };

    keydown = (event: KeyboardEvent): void => {
        if (event.key === 'Escape' && this.openIndex !== null) {
            event.preventDefault();
            event.stopPropagation();
            this.hide(true);
        }
    };
}

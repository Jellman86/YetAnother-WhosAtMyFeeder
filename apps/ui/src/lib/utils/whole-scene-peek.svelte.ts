import { wholeSceneOutline, type OutlineBox } from './frame-moments';

/**
 * A pointer crossing the photograph on its way to Play or Close is not a request to see the
 * whole scene, and the whole frame is a large fetch. Hover waits this long for intent; focus
 * and touch do not.
 */
export const PEEK_INTENT_MS = 250;

/**
 * The whole scene is a look, not a mode (#256).
 *
 * The photograph is always the crop. Hover or focus peeks at the whole scene with the crop
 * outlined; a click pins the peek so a control can be offered on it; Escape or a second click
 * returns to the crop. One controller carries that for every surface that shows a photograph,
 * so the detection record and the review queue behave the same way.
 */
export class WholeScenePeek {
    private view = $state<'crop' | 'whole'>('crop');
    pinned = $state(false);
    outline = $state<OutlineBox | null>(null);
    private intentTimer: ReturnType<typeof setTimeout> | null = null;

    /** `canPeek` is read live: it usually depends on which frame is the photograph now. */
    constructor(
        private readonly canPeek: () => boolean,
        private readonly intentMs: number = PEEK_INTENT_MS
    ) {}

    /** True while the whole scene is what should be drawn. */
    get showing(): boolean {
        return this.view === 'whole' && this.canPeek();
    }

    private clearIntent(): void {
        if (this.intentTimer) {
            clearTimeout(this.intentTimer);
            this.intentTimer = null;
        }
    }

    /** Pointer arrives: peek after a moment of intent. */
    enter = (): void => {
        if (!this.canPeek() || this.intentTimer) return;
        this.intentTimer = setTimeout(() => {
            this.intentTimer = null;
            this.show();
        }, this.intentMs);
    };

    /** Focus or touch: peek at once. */
    show = (): void => {
        this.clearIntent();
        if (!this.canPeek()) return;
        this.view = 'whole';
    };

    /** Pointer or focus leaves: back to the crop unless the peek is pinned. */
    leave = (): void => {
        this.clearIntent();
        if (this.pinned) return;
        this.view = 'crop';
    };

    /** Click: pin the whole scene, or unpin it and return to the crop. */
    toggle = (): void => {
        if (!this.canPeek()) return;
        if (this.pinned) {
            this.reset();
            return;
        }
        this.pinned = true;
        this.view = 'whole';
    };

    /** Back to the crop, unpinned. Also the state a new subject starts in. */
    reset = (): void => {
        this.clearIntent();
        this.view = 'crop';
        this.pinned = false;
        this.outline = null;
    };

    /**
     * Where the crop sits on the drawn whole scene. A DOM measurement, because the drawn
     * size of a `contain`ed image is not knowable from state; call it once the whole
     * scene has loaded and again when the window changes size.
     */
    measure = (image: HTMLImageElement | null, cropBox: ReadonlyArray<number> | null | undefined): void => {
        if (!image || this.view !== 'whole') {
            this.outline = null;
            return;
        }
        this.outline = wholeSceneOutline(
            cropBox,
            { width: image.naturalWidth, height: image.naturalHeight },
            { width: image.clientWidth, height: image.clientHeight }
        );
    };

    destroy = (): void => {
        this.clearIntent();
    };
}

/**
 * CLAUDE.md §5: media degrades silently and never shifts layout. A picture that fails to load is
 * marked here, and `app.css` keeps its box while hiding what the browser would otherwise draw in it:
 * the alt text, cut across whatever sits on top, and the broken-image glyph. The ground behind it
 * (each media box has one) is the placeholder. A component that can say something useful about the
 * missing picture still swaps in its own words; this is the floor for every other image.
 *
 * Error and load events do not bubble, so they are caught on the way down. A later successful load
 * of the same element, after its address changes, clears the mark.
 */
/** A picture, told by its tag rather than its class so the check holds in any realm. */
function isPicture(target: EventTarget | null): target is HTMLImageElement {
    if (typeof target !== 'object' || target === null) return false;
    const element = target as { tagName?: unknown; toggleAttribute?: unknown };
    return element.tagName === 'IMG' && typeof element.toggleAttribute === 'function';
}

export function installMediaFallback(root: Pick<Document, 'addEventListener' | 'removeEventListener'>): () => void {
    const mark = (event: Event): void => {
        const image = event.target;
        if (!isPicture(image)) return;
        image.toggleAttribute('data-media-failed', event.type === 'error');
    };
    // The options object rather than a bare `true`: some EventTarget implementations match a
    // removal only by the same form, and the cleanup must always find its listeners.
    const capture = { capture: true };
    root.addEventListener('error', mark, capture);
    root.addEventListener('load', mark, capture);
    return () => {
        root.removeEventListener('error', mark, capture);
        root.removeEventListener('load', mark, capture);
    };
}

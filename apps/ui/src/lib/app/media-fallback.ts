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
export function installMediaFallback(root: Document): () => void {
    const mark = (event: Event): void => {
        const image = event.target;
        if (!(image instanceof HTMLImageElement)) return;
        image.toggleAttribute('data-media-failed', event.type === 'error');
    };
    root.addEventListener('error', mark, true);
    root.addEventListener('load', mark, true);
    return () => {
        root.removeEventListener('error', mark, true);
        root.removeEventListener('load', mark, true);
    };
}

/**
 * Holds the page still beneath a full-screen dialog and returns the release.
 *
 * `overflow: hidden` alone does not stop iOS scrolling the page, so the body is pinned at its
 * scrolled offset and the position is put back on release. A pinned page also loses its
 * scrollbars; WebKit otherwise shrinks `position: fixed` backdrops by their width, leaving a strip
 * of page beside and below the dialog. Same technique as the detection record's own lock.
 */
export function lockDocumentScroll(): () => void {
    const { body, documentElement: html } = document;
    const left = window.scrollX;
    const top = window.scrollY;
    const previous = {
        position: body.style.position,
        top: body.style.top,
        width: body.style.width,
        bodyOverflow: body.style.overflow,
        htmlOverflow: html.style.overflow
    };
    body.style.position = 'fixed';
    body.style.top = `-${top}px`;
    body.style.width = '100%';
    body.style.overflow = 'hidden';
    html.style.overflow = 'hidden';

    let released = false;
    return () => {
        if (released) return;
        released = true;
        body.style.position = previous.position;
        body.style.top = previous.top;
        body.style.width = previous.width;
        body.style.overflow = previous.bodyOverflow;
        html.style.overflow = previous.htmlOverflow;
        window.scrollTo(left, top);
    };
}

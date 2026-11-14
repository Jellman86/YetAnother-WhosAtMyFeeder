/**
 * Runs `onNear` once, the first time the node comes within `margin` of the viewport. Work that only
 * matters once something is on screen (a row's reference image, a chart) waits for this instead of
 * running for a whole page at load. A node that is not laid out (`display: none`) never comes near.
 */
const NEAR_VIEWPORT_MARGIN = '300px';

export function whenNearViewport(
    node: Element,
    onNear: () => void,
    margin: string = NEAR_VIEWPORT_MARGIN
): { destroy(): void } {
    if (typeof IntersectionObserver === 'undefined') {
        onNear();
        return { destroy() {} };
    }
    let ran = false;
    const observer = new IntersectionObserver(
        (entries) => {
            if (ran || !entries.some((entry) => entry.isIntersecting)) return;
            ran = true;
            observer.disconnect();
            onNear();
        },
        { rootMargin: margin }
    );
    observer.observe(node);
    return {
        destroy() {
            observer.disconnect();
        }
    };
}

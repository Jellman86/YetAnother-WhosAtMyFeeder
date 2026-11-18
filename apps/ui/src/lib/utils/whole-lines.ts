/**
 * The height that shows only whole lines, given where each line ends (px from the top of the content)
 * and the height there is room for: the end of the last line that fits, or null when every line fits.
 * Never less than the first line. A line overhanging by less than a pixel still fits, so a browser's
 * rounding of fractional heights does not cost a line.
 */
export function wholeLinesHeight(lineEnds: readonly number[], available: number): number | null {
    const ends = [...lineEnds].sort((a, b) => a - b);
    if (ends.length === 0 || ends[ends.length - 1] <= available + 1) return null;
    const fitting = ends.filter((end) => end <= available + 1);
    return Math.floor(fitting.length > 0 ? fitting[fitting.length - 1] : ends[0]);
}

/**
 * Keeps `node`, a scrolling list of lines, to whole lines at rest: when its lines do not all fit, its
 * height ends after the last line that does, so no line is ever shown cut through its letters. `lines`
 * names the elements that are lines. Measured again whenever the node, its lines or `container` (whose
 * size decides the room there is) change size, and whenever a line arrives.
 */
export function snapToWholeLines(node: HTMLElement, { lines, container }: { lines: string; container: string }): { destroy: () => void } {
    const measure = (): void => {
        node.style.maxHeight = '';
        node.style.minHeight = '';
        const top = node.getBoundingClientRect().top - node.scrollTop;
        const ends = [...node.querySelectorAll<HTMLElement>(lines)].map((line) => line.getBoundingClientRect().bottom - top);
        const height = wholeLinesHeight(ends, node.clientHeight);
        if (height === null) return;
        // The snapped height overrides any floor the node has (the readings keep 3rem), which would
        // otherwise hold it taller than its last whole line and show the next one in part.
        node.style.maxHeight = `${height}px`;
        node.style.minHeight = '0px';
    };
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    const room = node.closest(container);
    if (room) observer.observe(room);
    const observeLines = (): void => {
        for (const line of node.querySelectorAll(lines)) observer.observe(line);
    };
    observeLines();
    // Lines arrive after the node does (a reading, an update notice), and each is measured from then on.
    const arrivals = new MutationObserver(() => {
        observeLines();
        measure();
    });
    arrivals.observe(node, { childList: true, subtree: true });
    return {
        destroy: () => {
            observer.disconnect();
            arrivals.disconnect();
        }
    };
}

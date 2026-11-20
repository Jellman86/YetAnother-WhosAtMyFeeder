/**
 * The height that shows only whole lines, given where each line ends (px from the top of the content)
 * and the height there is room for: the end of the last line that fits, or null when every line fits.
 * Never less than `floor`, the end of the last line that must always show (by default the first line).
 * A line overhanging by less than a pixel still fits, so a browser's rounding of fractional heights
 * does not cost a line.
 */
export function wholeLinesHeight(lineEnds: readonly number[], available: number, floor = 0): number | null {
    const ends = [...lineEnds].sort((a, b) => a - b);
    if (ends.length === 0 || ends[ends.length - 1] <= available + 1) return null;
    const fitting = ends.filter((end) => end <= available + 1);
    return Math.floor(Math.max(fitting.length > 0 ? fitting[fitting.length - 1] : ends[0], floor));
}

/** All of the lines; whole lines down to the floor, `height` px of them; or none, the holder gone. */
export type WholeLinesFit = { show: 'all' } | { show: 'some'; height: number } | { show: 'none' };

/**
 * How much of a list of lines to show in the room its holder has. `room` is the height the holder may
 * take without its container scrolling, negative when the container scrolls anyway because what stands
 * before the holder does not fit; `chrome` is the holder's height besides the lines (its frame, and a
 * link at its foot). Where the holder cannot show even its floor whole it shows nothing, never a
 * sliver; but where the container scrolls anyway the holder follows in full, below what does not fit.
 */
export function wholeLinesFit({ lineEnds, floor, room, chrome }: { lineEnds: readonly number[]; floor: number; room: number; chrome: number }): WholeLinesFit {
    if (room < 0) return { show: 'all' };
    const available = room - chrome;
    const height = wholeLinesHeight(lineEnds, available, floor);
    if (height === null) return available >= -1 ? { show: 'all' } : { show: 'none' };
    return height <= available + 1 ? { show: 'some', height } : { show: 'none' };
}

/**
 * Keeps `node`, a scrolling list of lines, to whole lines at rest, in the room left for it in
 * `container`, a scrolling column: when its lines do not all fit, its height ends after the last line
 * that does, and never before the end of the first `floor` line. `lines` names the elements that are
 * lines. The node's holder, its ancestor that stands in the column's own flow, is marked
 * `data-whole-lines` with the fit (all, some or none), so its page can take it out of view at none.
 * The room is worked out from the column's height and its other children, not from what the browser
 * left the holder, so the holder always lays out whole. Measured again whenever any of those, the
 * node or its lines change size, and whenever a line arrives.
 */
export function snapToWholeLines(node: HTMLElement, { lines, floor, container }: { lines: string; floor: string; container: string }): { destroy: () => void } {
    const column = node.closest<HTMLElement>(container);
    let holder: HTMLElement = node;
    while (column && holder.parentElement && holder.parentElement !== column) holder = holder.parentElement;
    const height = (element: Element): number => element.getBoundingClientRect().height;

    const measure = (): void => {
        if (!column) return;
        const top = node.getBoundingClientRect().top - node.scrollTop;
        const lineEnds = [...node.querySelectorAll<HTMLElement>(lines)].map((line) => line.getBoundingClientRect().bottom - top);
        const floorLine = node.querySelector<HTMLElement>(floor);
        const others = [...column.children].filter((child) => child !== holder).reduce((sum, child) => sum + height(child), 0);
        const fit = wholeLinesFit({
            lineEnds,
            floor: floorLine ? floorLine.getBoundingClientRect().bottom - top : 0,
            room: column.clientHeight - others,
            chrome: height(holder) - height(node)
        });
        node.style.maxHeight = fit.show === 'some' ? `${fit.height}px` : '';
        holder.dataset.wholeLines = fit.show;
    };
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    if (column) {
        observer.observe(column);
        for (const child of column.children) observer.observe(child);
    }
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
            // The holder outlives the node (the icon rail reuses it), and must not stay out of view.
            delete holder.dataset.wholeLines;
        }
    };
}

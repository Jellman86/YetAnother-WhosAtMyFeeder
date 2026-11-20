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
 * A group with nothing that can give way: all of it where its whole height fits the room, and none of
 * it otherwise, never cut. A sub-pixel shortfall still fits, as for a line.
 */
export function wholeOrNone(room: number, height: number): 'all' | 'none' {
    return height <= room + 1 ? 'all' : 'none';
}

/** The node's ancestor that stands in the column's own flow (or the node itself). */
function holderIn(node: HTMLElement, column: HTMLElement | null): HTMLElement {
    let holder = node;
    while (column && holder.parentElement && holder.parentElement !== column) holder = holder.parentElement;
    return holder;
}

const heightOf = (element: Element): number => element.getBoundingClientRect().height;

/**
 * The height the holder may take without the column scrolling: the column's height less its other
 * children. Worked out, not read from what the browser left the holder, so the holder always lays out
 * whole and the answer does not depend on whether it is shown.
 */
function roomFor(holder: HTMLElement, column: HTMLElement): number {
    const others = [...column.children].filter((child) => child !== holder).reduce((sum, child) => sum + heightOf(child), 0);
    return column.clientHeight - others;
}

/**
 * Measures again whenever the node, the column or anything in it changes size. The holder is marked
 * `data-fit` with the answer (all, some or none), so its page can take it out of view at none; the mark
 * is removed with the action, since the holder may outlive the node.
 */
function fitInColumn(node: HTMLElement, container: string, measure: (holder: HTMLElement, column: HTMLElement) => string): { holder: HTMLElement; observer: ResizeObserver; measure: () => void; release: () => void } {
    const column = node.closest<HTMLElement>(container);
    const holder = holderIn(node, column);
    const run = (): void => {
        if (column) holder.dataset.fit = measure(holder, column);
    };
    const observer = new ResizeObserver(run);
    observer.observe(node);
    if (column) {
        observer.observe(column);
        for (const child of column.children) observer.observe(child);
    }
    return {
        holder,
        observer,
        measure: run,
        release: () => {
            observer.disconnect();
            delete holder.dataset.fit;
        }
    };
}

/**
 * Keeps `node`, a scrolling list of lines, to whole lines at rest, in the room left for it in
 * `container`, a scrolling column: when its lines do not all fit, its height ends after the last line
 * that does, and never before the end of the first `floor` line. `lines` names the elements that are
 * lines. Where not even the floor fits, the holder is marked none (see fitInColumn). Measured again
 * whenever a line changes size or arrives, too.
 */
export function snapToWholeLines(node: HTMLElement, { lines, floor, container }: { lines: string; floor: string; container: string }): { destroy: () => void } {
    const fit = fitInColumn(node, container, (holder, column) => {
        const top = node.getBoundingClientRect().top - node.scrollTop;
        const lineEnds = [...node.querySelectorAll<HTMLElement>(lines)].map((line) => line.getBoundingClientRect().bottom - top);
        const floorLine = node.querySelector<HTMLElement>(floor);
        const answer = wholeLinesFit({
            lineEnds,
            floor: floorLine ? floorLine.getBoundingClientRect().bottom - top : 0,
            room: roomFor(holder, column),
            chrome: heightOf(holder) - heightOf(node)
        });
        node.style.maxHeight = answer.show === 'some' ? `${answer.height}px` : '';
        return answer.show;
    });
    const observeLines = (): void => {
        for (const line of node.querySelectorAll(lines)) fit.observer.observe(line);
    };
    observeLines();
    // Lines arrive after the node does (a reading, an update notice), and each is measured from then on.
    const arrivals = new MutationObserver(() => {
        observeLines();
        fit.measure();
    });
    arrivals.observe(node, { childList: true, subtree: true });
    return {
        destroy: () => {
            fit.release();
            arrivals.disconnect();
        }
    };
}

/**
 * Shows `node`'s holder in `container`, a scrolling column, only where it fits there whole without the
 * column scrolling: a group with nothing that can give way is whole and in view, or marked none.
 */
export function showWholeOrNone(node: HTMLElement, { container }: { container: string }): { destroy: () => void } {
    const fit = fitInColumn(node, container, (holder, column) => wholeOrNone(roomFor(holder, column), heightOf(holder)));
    return { destroy: fit.release };
}

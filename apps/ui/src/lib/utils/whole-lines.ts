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
 * A line overhanging by under a pixel still counts as whole, but the lines are then cut to the room:
 * the holder is never taller than the room, since a column a pixel too tall grows a classic scrollbar,
 * which narrows the lines, rewraps one and takes the scrollbar away again, round and round.
 */
export function wholeLinesFit({ lineEnds, floor, room, chrome }: { lineEnds: readonly number[]; floor: number; room: number; chrome: number }): WholeLinesFit {
    if (room < 0) return { show: 'all' };
    const available = Math.floor(room - chrome);
    const height = wholeLinesHeight(lineEnds, available, floor);
    if (height === null) {
        if (available < 0) return { show: 'none' };
        return Math.max(0, ...lineEnds) <= available ? { show: 'all' } : { show: 'some', height: available };
    }
    return height <= available + 1 ? { show: 'some', height: Math.min(height, available) } : { show: 'none' };
}

/**
 * A group with nothing that can give way: all of it where its whole height fits the room, and none of
 * it otherwise, never cut. Never past the room, by any fraction of a pixel (see wholeLinesFit).
 */
export function wholeOrNone(room: number, height: number): 'all' | 'none' {
    return height <= room ? 'all' : 'none';
}

/** The full status card, the one-line summary that stands in for it, or the card pushed `push` px down. */
export type StatusTier = { tier: 'full'; readings: number | null; push: number } | { tier: 'summary' };

const WHOLE_CARD: StatusTier = { tier: 'full', readings: null, push: 0 };

/**
 * Which form of the status shows in `room`, the height under the places. `frame` is the holder's own
 * height besides the form; `full` and `summary` are the two forms' heights; `lines` are the full
 * form's readings, where they can give way (the icon rail's group has none). The full card where its
 * floor fits, in whole lines; else the one-line summary where that fits; else the whole card pushed
 * just past the foot of the column, so nothing of it shows at rest. Where the places themselves do
 * not fit, the whole card simply follows them.
 */
export function statusTier({ room, frame, full, summary, lines }: {
    room: number;
    frame: number;
    full: number;
    summary: number;
    lines?: { lineEnds: readonly number[]; floor: number; readings: number };
}): StatusTier {
    if (room < 0) return WHOLE_CARD;
    if (lines) {
        const fit = wholeLinesFit({ lineEnds: lines.lineEnds, floor: lines.floor, room, chrome: frame + full - lines.readings });
        if (fit.show === 'all') return WHOLE_CARD;
        if (fit.show === 'some') return { tier: 'full', readings: fit.height, push: 0 };
    } else if (wholeOrNone(room, frame + full) === 'all') {
        return WHOLE_CARD;
    }
    if (wholeOrNone(room, frame + summary) === 'all') return { tier: 'summary' };
    return { tier: 'full', readings: null, push: Math.ceil(room) };
}

const heightOf = (element: Element): number => element.getBoundingClientRect().height;

/** An element's height with its margins, as it takes room in a column. */
function outerHeightOf(element: Element): number {
    const style = getComputedStyle(element);
    return heightOf(element) + (parseFloat(style.marginTop) || 0) + (parseFloat(style.marginBottom) || 0);
}

/**
 * The height the holder may take without the column scrolling: the column's height less its other
 * children and their margins. Worked out, not read from what the browser left the holder, so the
 * holder always lays out whole and the answer does not depend on which form it shows. The column's
 * height is the lesser of its rounded and its exact height, so rounding never adds room.
 */
function roomFor(holder: HTMLElement, column: HTMLElement): number {
    const others = [...column.children].filter((child) => child !== holder).reduce((sum, child) => sum + outerHeightOf(child), 0);
    return Math.min(column.clientHeight, heightOf(column)) - others;
}

/**
 * Shows the sidebar status in the tier its room allows. `holder` stands in `container`, a scrolling
 * column, and holds two forms, `[data-status-form="full"]` and `[data-status-form="summary"]`; it is
 * marked `data-fit` with the form chosen, so its page can take the other out of view while it stays
 * laid out for the next measure. `readings` names the full form's scrolling lines (`lines`, never
 * shorter than the `floor` line), which are kept to whole lines at rest. Keyboard focus in the form
 * taken away moves to the same control in the other (its link), or else to `fallbackFocus`, never
 * staying on something unseen. Measured again whenever the column, anything in it, a form or a line
 * changes size, and whenever a form or a line arrives.
 */
export function fitStatus(holder: HTMLElement, options: {
    container: string;
    readings?: string;
    lines?: string;
    floor?: string;
    fallbackFocus?: () => HTMLElement | null | undefined;
}): { destroy: () => void } {
    const column = holder.closest<HTMLElement>(options.container);
    const form = (name: 'full' | 'summary'): HTMLElement | null => holder.querySelector<HTMLElement>(`[data-status-form="${name}"]`);
    const readingsOf = (full: HTMLElement): HTMLElement | null => (options.readings ? full.querySelector<HTMLElement>(options.readings) : null);

    const measure = (): void => {
        const full = form('full');
        const summary = form('summary');
        const forms = full?.parentElement;
        if (!column || !full || !summary || !forms) return;
        const readings = readingsOf(full);
        let lines: { lineEnds: number[]; floor: number; readings: number } | undefined;
        if (readings && options.lines) {
            const top = readings.getBoundingClientRect().top - readings.scrollTop;
            const floorLine = options.floor ? readings.querySelector<HTMLElement>(options.floor) : null;
            lines = {
                lineEnds: [...readings.querySelectorAll<HTMLElement>(options.lines)].map((line) => line.getBoundingClientRect().bottom - top),
                floor: floorLine ? floorLine.getBoundingClientRect().bottom - top : 0,
                readings: heightOf(readings)
            };
        }
        const answer = statusTier({
            room: roomFor(holder, column),
            frame: heightOf(holder) - heightOf(forms),
            full: heightOf(full),
            summary: heightOf(summary),
            lines
        });
        if (readings) readings.style.maxHeight = answer.tier === 'full' && answer.readings !== null ? `${answer.readings}px` : '';
        holder.style.marginTop = answer.tier === 'full' && answer.push > 0 ? `${answer.push}px` : '';
        const leaving = answer.tier === 'summary' ? full : summary;
        const arriving = answer.tier === 'summary' ? summary : full;
        const focusLeaves = holder.dataset.fit !== answer.tier && leaving.contains(document.activeElement);
        holder.dataset.fit = answer.tier;
        if (focusLeaves) {
            // On the next frame, once the new form is styled as shown: Chromium does not move focus from
            // inside a ResizeObserver callback onto an element its style still hides.
            const tier = answer.tier;
            requestAnimationFrame(() => {
                if (holder.dataset.fit !== tier) return;
                (arriving.querySelector<HTMLElement>('a[href]') ?? arriving.querySelector<HTMLElement>('[tabindex="0"]') ?? options.fallbackFocus?.())?.focus();
            });
        }
    };

    const observer = new ResizeObserver(measure);
    const observeAll = (): void => {
        observer.observe(holder);
        if (column) {
            observer.observe(column);
            for (const child of column.children) observer.observe(child);
        }
        for (const name of ['full', 'summary'] as const) {
            const element = form(name);
            if (element) observer.observe(element);
        }
        const full = form('full');
        const readings = full ? readingsOf(full) : null;
        if (readings && options.lines) for (const line of readings.querySelectorAll(options.lines)) observer.observe(line);
    };
    observeAll();
    // Forms and lines arrive after the holder does (a reading, an update notice, the icon rail's forms
    // when the sidebar collapses), and each is measured from then on.
    const arrivals = new MutationObserver(() => {
        observeAll();
        measure();
    });
    arrivals.observe(holder, { childList: true, subtree: true });
    return {
        destroy: () => {
            observer.disconnect();
            arrivals.disconnect();
            delete holder.dataset.fit;
            holder.style.marginTop = '';
        }
    };
}

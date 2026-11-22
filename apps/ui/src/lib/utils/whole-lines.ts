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
    // Judged on the floor's own end, not its rounded one: rounding first let a floor line overhanging
    // by up to two pixels pass, and the cut to the room then took the foot of its letters.
    return height <= available + 1 && floor <= available + 1 ? { show: 'some', height: Math.min(height, available) } : { show: 'none' };
}

/**
 * A group with nothing that can give way: all of it where its whole height fits the room, and none of
 * it otherwise, never cut. Never past the room, by any fraction of a pixel (see wholeLinesFit).
 */
export function wholeOrNone(room: number, height: number): 'all' | 'none' {
    return height <= room ? 'all' : 'none';
}

/**
 * The full status card (its readings `readings` px tall, or whole, null); the one-line summary; the compact
 * summary; or, with no room for even that, the Health place carrying the status while the whole card
 * waits `push` px down, just past the foot of the column.
 */
export type StatusTier =
    | { tier: 'full'; readings: number | null }
    | { tier: 'summary' }
    | { tier: 'compact' }
    | { tier: 'health'; push: number };

const WHOLE_CARD: StatusTier = { tier: 'full', readings: null };

/**
 * Which form of the status shows in `room`, the height under the places. `frame` is the holder's own
 * height besides the form; `full`, `summary` and `compact` are the forms' heights (the compact one with
 * its negative margins, which eat into the frame); `lines` are the full form's readings, where they can
 * give way (the icon rail's group has none). The full card where its floor fits, in whole lines; else
 * the one-line summary (a full-size target); else the compact summary (a 24 px target); and only
 * where not even that fits, or the places themselves do not, does the Health place carry the status.
 */
export function statusTier({ room, frame, full, summary, compact, lines }: {
    room: number;
    frame: number;
    full: number;
    summary: number;
    compact: number;
    lines?: { lineEnds: readonly number[]; floor: number; readings: number };
}): StatusTier {
    if (room < 0) return { tier: 'health', push: 0 };
    if (lines) {
        const fit = wholeLinesFit({ lineEnds: lines.lineEnds, floor: lines.floor, room, chrome: frame + full - lines.readings });
        if (fit.show === 'all') return WHOLE_CARD;
        if (fit.show === 'some') return { tier: 'full', readings: fit.height };
    } else if (wholeOrNone(room, frame + full) === 'all') {
        return WHOLE_CARD;
    }
    if (wholeOrNone(room, frame + summary) === 'all') return { tier: 'summary' };
    if (wholeOrNone(room, frame + compact) === 'all') return { tier: 'compact' };
    return { tier: 'health', push: Math.ceil(room) };
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

/** Anything keyboard focus can be put on. */
interface Focusable {
    focus(): void;
}

/**
 * Moves keyboard focus to `target()` once that can take it, without ever fighting the reader. A newly
 * shown element does not always take focus at once (Chromium refuses it from inside a ResizeObserver
 * callback, and at times for a frame after), so the move starts in a task of its own and is tried again
 * for up to `attempts` frames, asking `target()` afresh each time, since a resize can pass through other
 * tiers on its way. Before every try it checks focus is still `ours()` (on nothing, in the status, or
 * where this put it): once the reader has moved focus on, it is theirs and is left alone. With no
 * target, or when every try is refused, focus goes to `fallback()` instead of staying on nothing, and
 * `onFallback` hears where. The schedulers are passed in so the timing can be tested.
 */
export function createFocusMover<T extends Focusable>({ target, fallback, ours, active, onFallback, frame, task, cancelFrame, cancelTask, attempts = 5 }: {
    target: () => T | null | undefined;
    fallback: () => T | null | undefined;
    ours: () => boolean;
    active: () => unknown;
    onFallback?: (element: T) => void;
    frame: (run: () => void) => number;
    task: (run: () => void) => number;
    cancelFrame: (id: number) => void;
    cancelTask: (id: number) => void;
    attempts?: number;
}): { move: () => void; cancel: () => void } {
    let taskId: number | null = null;
    let frameId: number | null = null;
    const settle = (): void => {
        taskId = null;
        frameId = null;
    };
    const tryFocus = (attempt: number): void => {
        settle();
        if (!ours()) return;
        const element = target();
        if (element) {
            element.focus();
            if (active() === element) return;
            if (attempt < attempts) {
                frameId = frame(() => tryFocus(attempt + 1));
                return;
            }
        }
        const instead = fallback();
        if (!instead || !ours()) return;
        instead.focus();
        onFallback?.(instead);
    };
    return {
        move: () => {
            if (taskId !== null || frameId !== null) return;
            taskId = task(() => tryFocus(0));
        },
        cancel: () => {
            if (taskId !== null) cancelTask(taskId);
            if (frameId !== null) cancelFrame(frameId);
            settle();
        }
    };
}

type StatusForm = 'full' | 'summary' | 'compact';

/** The form each tier shows: the Health place's tier keeps the whole card, past the fold. */
const FORM_OF: Record<StatusTier['tier'], StatusForm> = { full: 'full', summary: 'summary', compact: 'compact', health: 'full' };

/**
 * Shows the sidebar status in the tier its room allows. `holder` stands in `container`, a scrolling
 * column, and holds three forms, `[data-status-form="full"|"summary"|"compact"]`; it is marked
 * `data-fit` with the tier, so its page can take the other forms out of view while they stay laid out
 * for the next measure, and `onTier` hears each change. `readings` names the full form's scrolling
 * lines (`lines`, never shorter than the `floor` line), which are kept to whole lines at rest. Keyboard
 * focus in a form taken away moves to the same `control` in the new one, or, at the Health place's
 * tier or where the new form has none, to `fallbackFocus`: never staying on something unseen, and
 * never taken back from where the reader has moved it (see createFocusMover). Focus parked there comes
 * back to the status when it shows again. Measured again whenever the column, anything in it, a form
 * or a line changes size, and whenever a form or a line arrives.
 */
export function fitStatus(holder: HTMLElement, options: {
    container: string;
    readings?: string;
    lines?: string;
    floor?: string;
    /** Each form's control that stands for the others (its way to Health), for focus to move between. */
    control?: string;
    /** The summary's words: the compact form is used only while they keep to one or two lines. */
    words?: string;
    fallbackFocus?: () => HTMLElement | null | undefined;
    onTier?: (tier: StatusTier['tier']) => void;
}): { destroy: () => void } {
    const column = holder.closest<HTMLElement>(options.container);
    const form = (name: StatusForm): HTMLElement | null => holder.querySelector<HTMLElement>(`[data-status-form="${name}"]`);
    const readingsOf = (full: HTMLElement): HTMLElement | null => (options.readings ? full.querySelector<HTMLElement>(options.readings) : null);

    // Where focus was put outside the status to wait, and the one listener that forgets it once the
    // reader moves it on.
    let parked: HTMLElement | null = null;
    let parkedListener: AbortController | null = null;
    const park = (element: HTMLElement | null): void => {
        parkedListener?.abort();
        parkedListener = null;
        parked = element;
        if (!element) return;
        parkedListener = new AbortController();
        element.addEventListener('blur', () => park(null), { signal: parkedListener.signal });
    };

    const focusMover = createFocusMover<HTMLElement>({
        target: () => {
            const now = holder.dataset.fit as StatusTier['tier'] | undefined;
            const shown = now && now !== 'health' ? form(FORM_OF[now]) : null;
            return (options.control ? shown?.querySelector<HTMLElement>(options.control) : null) ?? shown?.querySelector<HTMLElement>('[tabindex="0"]');
        },
        fallback: () => options.fallbackFocus?.(),
        ours: () => {
            const active = document.activeElement;
            return active === null || active === document.body || holder.contains(active) || (parked !== null && active === parked);
        },
        active: () => document.activeElement,
        onFallback: park,
        frame: (run) => requestAnimationFrame(run),
        task: (run) => window.setTimeout(run, 0),
        cancelFrame: (id) => cancelAnimationFrame(id),
        cancelTask: (id) => window.clearTimeout(id)
    });

    // The compact form tightens only its padding, so its words must still read as a line or two: a
    // wider face or a longer language that runs them to a third gives the compact form up.
    const wordsWithinTwoLines = (element: HTMLElement): boolean => {
        const words = options.words ? element.querySelector<HTMLElement>(options.words) : null;
        if (!words) return true;
        const line = parseFloat(getComputedStyle(words).lineHeight);
        return !Number.isFinite(line) || heightOf(words) <= 2 * line + 1;
    };

    const measure = (): void => {
        const full = form('full');
        const summary = form('summary');
        const compact = form('compact');
        const forms = full?.parentElement;
        if (!column || !full || !summary || !compact || !forms) return;
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
            summary: outerHeightOf(summary),
            compact: wordsWithinTwoLines(compact) ? outerHeightOf(compact) : Number.POSITIVE_INFINITY,
            lines
        });
        if (readings) readings.style.maxHeight = answer.tier === 'full' && answer.readings !== null ? `${answer.readings}px` : '';
        holder.style.marginTop = answer.tier === 'health' && answer.push > 0 ? `${answer.push}px` : '';
        const tier = answer.tier;
        if (holder.dataset.fit === tier) return;
        const shown = { full, summary, compact }[FORM_OF[tier]];
        // Focus leaves with the form it was in, and at the Health place's tier with the card too, which
        // waits past the fold where focus would only scroll it back. Focus parked outside the status,
        // still where it was put, comes back as soon as the status shows again.
        const active = document.activeElement;
        const focusLeaves = (holder.contains(active) && (tier === 'health' || !shown.contains(active)))
            || (parked !== null && active === parked && tier !== 'health');
        holder.dataset.fit = tier;
        options.onTier?.(tier);
        if (focusLeaves) focusMover.move();
    };

    // Everything measured is observed once; what the icon rail's toggle swapped out is let go.
    const observer = new ResizeObserver(measure);
    const observed = new Set<Element>();
    const watch = (element: Element): void => {
        if (observed.has(element)) return;
        observed.add(element);
        observer.observe(element);
    };
    const observeAll = (): void => {
        for (const element of observed) {
            if (element.isConnected) continue;
            observer.unobserve(element);
            observed.delete(element);
        }
        watch(holder);
        if (column) {
            watch(column);
            for (const child of column.children) watch(child);
        }
        for (const name of ['full', 'summary', 'compact'] as const) {
            const element = form(name);
            if (element) watch(element);
        }
        const full = form('full');
        const readings = full ? readingsOf(full) : null;
        if (readings && options.lines) for (const line of readings.querySelectorAll(options.lines)) watch(line);
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
            focusMover.cancel();
            park(null);
            delete holder.dataset.fit;
            holder.style.marginTop = '';
        }
    };
}

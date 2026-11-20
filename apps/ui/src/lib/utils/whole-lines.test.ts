import { describe, expect, it } from 'vitest';
import { createFocusMover, statusTier, wholeLinesFit, wholeLinesHeight, wholeOrNone } from './whole-lines';

/** Where each line of the status readings ends, from the top of the readings, in px. */
const LINES = [16, 40, 64, 88, 106];

describe('wholeLinesHeight', () => {
    it('leaves the height alone when every line fits', () => {
        expect(wholeLinesHeight(LINES, 106)).toBeNull();
        expect(wholeLinesHeight(LINES, 120)).toBeNull();
    });

    it('ends the visible height at the last line that fits whole, so no line shows in part', () => {
        // 101px would show 13px of the last 18px line; it ends after the line before it instead.
        expect(wholeLinesHeight(LINES, 101)).toBe(88);
        expect(wholeLinesHeight(LINES, 88)).toBe(88);
        expect(wholeLinesHeight(LINES, 70)).toBe(64);
    });

    it('takes line ends in any order, and a sub-pixel overhang does not count as a line that does not fit', () => {
        expect(wholeLinesHeight([88.4, 16, 64, 40], 88)).toBeNull();
        expect(wholeLinesHeight([106.6, 16, 40, 64, 88], 106)).toBeNull();
    });

    it('keeps at least the first line, even in a space too small for it', () => {
        expect(wholeLinesHeight(LINES, 10)).toBe(16);
    });

    it('never ends before the floor line, so a heading keeps the reading under it', () => {
        // Room for the heading alone (16px) still shows the first reading (40px) whole.
        expect(wholeLinesHeight(LINES, 20, 40)).toBe(40);
        expect(wholeLinesHeight(LINES, 10, 40)).toBe(40);
        // Above the floor the snap is the usual one.
        expect(wholeLinesHeight(LINES, 70, 40)).toBe(64);
    });
});

/** The status card: 66px of frame and Health link around readings whose first reading ends at 40px. */
const CARD = { lineEnds: LINES, floor: 40, chrome: 66 };

describe('wholeLinesFit', () => {
    it('shows every line where they all fit', () => {
        expect(wholeLinesFit({ ...CARD, room: 66 + 106 })).toEqual({ show: 'all' });
    });

    it('shows whole lines down to the floor where only some fit', () => {
        expect(wholeLinesFit({ ...CARD, room: 66 + 70 })).toEqual({ show: 'some', height: 64 });
        expect(wholeLinesFit({ ...CARD, room: 66 + 40 })).toEqual({ show: 'some', height: 40 });
    });

    it('shows nothing, not a sliver, where even the floor does not fit beside what comes first', () => {
        expect(wholeLinesFit({ ...CARD, room: 66 + 38 })).toEqual({ show: 'none' });
        expect(wholeLinesFit({ ...CARD, room: 20 })).toEqual({ show: 'none' });
        expect(wholeLinesFit({ ...CARD, room: 0 })).toEqual({ show: 'none' });
    });

    it('shows every line where the container scrolls anyway, since what comes first does not fit', () => {
        expect(wholeLinesFit({ ...CARD, room: -5 })).toEqual({ show: 'all' });
    });

    it('never makes the holder taller than the room, even where a line overhangs by under a pixel', () => {
        // A last line 0.6px past the room still counts as whole, but the readings are cut to the room.
        expect(wholeLinesFit({ lineEnds: [16, 40, 64, 88, 106.6], floor: 40, chrome: 66, room: 66 + 106 })).toEqual({ show: 'some', height: 106 });
        // With a fractional room and frame, every answer leaves the frame plus the lines within the room,
        // so a column with classic scrollbars never overflows by a pixel and flips a scrollbar on and off.
        for (let room = 100; room <= 200; room += 0.25) {
            const fit = wholeLinesFit({ ...CARD, chrome: 66.4, room });
            const height = fit.show === 'all' ? Math.max(...LINES) : fit.show === 'some' ? fit.height : 0;
            expect(66.4 + height, `room ${room}`).toBeLessThanOrEqual(room + (fit.show === 'none' ? Infinity : 0));
        }
    });

    it('treats a holder with no lines yet by its frame alone', () => {
        expect(wholeLinesFit({ lineEnds: [], floor: 0, chrome: 66, room: 80 })).toEqual({ show: 'all' });
        expect(wholeLinesFit({ lineEnds: [], floor: 0, chrome: 66, room: 30 })).toEqual({ show: 'none' });
    });
});

describe('wholeOrNone', () => {
    it('shows a group with nothing that can give way only where all of it fits', () => {
        expect(wholeOrNone(164, 164)).toBe('all');
        expect(wholeOrNone(200, 164)).toBe('all');
        expect(wholeOrNone(120, 164)).toBe('none');
    });

    it('never lets the group pass the room, not even by a sub-pixel', () => {
        expect(wholeOrNone(163.4, 164)).toBe('none');
        expect(wholeOrNone(164.2, 164)).toBe('all');
    });

    it('shows none where what comes first already fills the column', () => {
        expect(wholeOrNone(-18, 164)).toBe('none');
    });
});

/**
 * The sidebar status in its room: a 17px frame around the full card (139px, readings 84px of it, whose
 * first reading ends at 35px), around the one-line summary (27px), or around the compact summary (16px
 * once its negative margins eat into the frame).
 */
const STATUS = { frame: 17, full: 139, summary: 27, compact: 16, lines: { lineEnds: [14, 35, 53, 70, 84], floor: 35, readings: 84 } };

describe('statusTier', () => {
    it('shows the full card whole where it fits', () => {
        expect(statusTier({ ...STATUS, room: 160 })).toEqual({ tier: 'full', readings: null });
    });

    it('shows the full card in whole lines down to its first reading', () => {
        // Frame and card without readings take 72px; 40px left holds the heading and first reading.
        expect(statusTier({ ...STATUS, room: 112 })).toEqual({ tier: 'full', readings: 35 });
    });

    it('gives the summary where the floor of the card does not fit but the summary does', () => {
        expect(statusTier({ ...STATUS, room: 100 })).toEqual({ tier: 'summary' });
        expect(statusTier({ ...STATUS, room: 44 })).toEqual({ tier: 'summary' });
    });

    it('tightens to the compact summary before giving up on a line', () => {
        expect(statusTier({ ...STATUS, room: 43.5 })).toEqual({ tier: 'compact' });
        expect(statusTier({ ...STATUS, room: 33 })).toEqual({ tier: 'compact' });
    });

    it('where not even the compact line fits, hands the status to the Health place, with the card just past the fold', () => {
        expect(statusTier({ ...STATUS, room: 32.5 })).toEqual({ tier: 'health', push: 33 });
        expect(statusTier({ ...STATUS, room: 0 })).toEqual({ tier: 'health', push: 0 });
    });

    it('hands the status to the Health place too when the places themselves do not fit', () => {
        expect(statusTier({ ...STATUS, room: -20 })).toEqual({ tier: 'health', push: 0 });
    });

    it('treats a group with nothing that can give way (the icon rail) as all, one icon, a small icon or the Health place', () => {
        const rail = { frame: 17, full: 147, summary: 39, compact: 15 };
        expect(statusTier({ ...rail, room: 164 })).toEqual({ tier: 'full', readings: null });
        expect(statusTier({ ...rail, room: 163 })).toEqual({ tier: 'summary' });
        expect(statusTier({ ...rail, room: 50 })).toEqual({ tier: 'compact' });
        expect(statusTier({ ...rail, room: 23 })).toEqual({ tier: 'health', push: 23 });
    });
});

/** A stand-in for elements and the page's focus, with frames and tasks run by hand. */
function focusWorld() {
    let active: string | null = 'hidden card link';
    const frames: (() => void)[] = [];
    const tasks: (() => void)[] = [];
    const element = (name: string, takes: () => boolean = () => true) => ({
        name,
        focus: () => { if (takes()) active = name; }
    });
    return {
        get active() { return active; },
        set active(name: string | null) { active = name; },
        element,
        schedule: {
            frame: (run: () => void) => frames.push(run),
            task: (run: () => void) => tasks.push(run),
            cancelFrame: (id: number) => { frames[id - 1] = () => undefined; },
            cancelTask: (id: number) => { tasks[id - 1] = () => undefined; }
        },
        run: () => { while (tasks.length || frames.length) (tasks.shift() ?? frames.shift())?.(); }
    };
}

describe('createFocusMover', () => {
    it('moves focus to the new form once it takes it, trying again for a few frames', () => {
        const world = focusWorld();
        let refusals = 2;
        const summaryLink = world.element('summary link', () => refusals-- <= 0);
        const mover = createFocusMover({ target: () => summaryLink, fallback: () => null, ours: () => true, active: () => world.active, ...world.schedule });
        mover.move();
        world.run();
        expect(world.active).toBe('summary link');
    });

    it('leaves focus alone once the reader has moved it inside the retry window', () => {
        const world = focusWorld();
        let refusals = 3;
        const summaryLink = world.element('summary link', () => refusals-- <= 0);
        const nav = world.element('Health place');
        const mover = createFocusMover({
            target: () => summaryLink,
            fallback: () => nav,
            ours: () => world.active === null || world.active === 'hidden card link',
            active: () => world.active,
            ...world.schedule
        });
        mover.move();
        // The first try is refused; before the next frame the reader presses Tab.
        world.schedule.frame(() => { world.active = 'Settings place'; });
        world.run();
        expect(world.active).toBe('Settings place');
    });

    it('falls back when the new form never takes focus, rather than leaving it on nothing', () => {
        const world = focusWorld();
        const summaryLink = world.element('summary link', () => false);
        const nav = world.element('Health place');
        const parked: string[] = [];
        const mover = createFocusMover({ target: () => summaryLink, fallback: () => nav, ours: () => true, active: () => world.active, onFallback: (element) => parked.push(element.name), ...world.schedule });
        mover.move();
        world.run();
        expect(world.active).toBe('Health place');
        expect(parked).toEqual(['Health place']);
    });

    it('does nothing once cancelled, as when the sidebar goes away', () => {
        const world = focusWorld();
        const mover = createFocusMover({ target: () => world.element('summary link'), fallback: () => null, ours: () => true, active: () => world.active, ...world.schedule });
        mover.move();
        mover.cancel();
        world.run();
        expect(world.active).toBe('hidden card link');
    });
});

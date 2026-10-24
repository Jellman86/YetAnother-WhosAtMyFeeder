import { describe, expect, it } from 'vitest';
import type { GardenCapture } from '../api/garden';
import type { DetectionVisit } from '../api/visits';
import { gardenBlocker, gardenEntryText, gardenEntryView, gardenWindow, placeGardenCaptures, type GardenFilterState } from './garden-explorer';

function capture(overrides: Partial<GardenCapture> = {}): GardenCapture {
    return {
        id: 'a'.repeat(32),
        camera: 'patio',
        frigate_label: 'cat',
        observed_at: '2026-10-13T09:00:00Z',
        status: 'pending',
        reviewed_at: null,
        snapshot_url: '/api/garden/x/snapshot',
        identification: null,
        source_kind: 'frigate_event',
        motion_source: null,
        automatic_check: null,
        automatic_check_overridden: false,
        ...overrides
    };
}

type Identification = NonNullable<GardenCapture['identification']>;

function named(review: Identification['review'], automatic = false): Identification {
    return {
        outcome: 'suggestion',
        reason: 'confident',
        review,
        automatic,
        name: 'Red fox',
        rank: 'species',
        score: 0.91,
        country: 'GBR',
        variant: '4.0.3b',
        provider: 'cpu',
        devices: ['cpu'],
        output_index: 3,
        input_kind: 'whole_image',
        frame_size: [1920, 1080],
        identified_at: '2026-10-13T09:01:00Z'
    } as Identification;
}

describe('gardenEntryView', () => {
    it('asks for a presence review on a capture nobody has confirmed', () => {
        expect(gardenEntryView(capture())).toEqual({ name: null, nameState: 'none', score: null, review: 'presence' });
    });

    it('names a confirmed animal only from an identification that still stands', () => {
        expect(gardenEntryView(capture({ status: 'confirmed', identification: named('accepted') })))
            .toEqual({ name: 'Red fox', nameState: 'confirmed', score: 0.91, review: null });
        expect(gardenEntryView(capture({ status: 'confirmed', identification: named('accepted', true) })).nameState)
            .toBe('automatic');
        expect(gardenEntryView(capture({ status: 'confirmed', identification: named('dismissed') })))
            .toEqual({ name: null, nameState: 'none', score: null, review: null });
    });

    it('flags an unreviewed species suggestion on a confirmed animal as work for a person', () => {
        expect(gardenEntryView(capture({ status: 'confirmed', identification: named('unreviewed') })))
            .toEqual({ name: 'Red fox', nameState: 'suggested', score: 0.91, review: 'species' });
    });

    it('never reads an unknown outcome as a name', () => {
        const unknown = { ...named('unreviewed'), outcome: 'unknown', name: null, score: null } as Identification;
        expect(gardenEntryView(capture({ status: 'confirmed', identification: unknown })).nameState).toBe('none');
    });
});

describe('gardenBlocker', () => {
    const open: GardenFilterState = {
        speciesFilter: '',
        favoritesOnly: false,
        showHidden: false,
        multipleSpeciesOnly: false,
        audioConfirmedOnly: false,
        sortOrder: 'newest',
        groupVisits: true,
        selectionMode: false
    };

    it('has nothing to say when only birds are shown, or when nothing stands in the way', () => {
        expect(gardenBlocker('birds', { ...open, favoritesOnly: true })).toBeNull();
        expect(gardenBlocker('all', open)).toBeNull();
    });

    it('steps aside beside birds for anything that only describes a bird visit', () => {
        expect(gardenBlocker('all', { ...open, speciesFilter: 'Turdus merula' })).toBe('bird_filter');
        expect(gardenBlocker('all', { ...open, showHidden: true })).toBe('bird_filter');
        expect(gardenBlocker('all', { ...open, sortOrder: 'confidence' })).toBe('confidence_sort');
        expect(gardenBlocker('all', { ...open, groupVisits: false })).toBe('ungrouped');
        expect(gardenBlocker('all', { ...open, selectionMode: true })).toBe('selection');
    });

    it('shows Garden on its own regardless, saying the bird filters do not apply', () => {
        expect(gardenBlocker('garden', open)).toBeNull();
        expect(gardenBlocker('garden', { ...open, favoritesOnly: true, sortOrder: 'confidence' })).toBe('bird_filter_ignored');
    });
});

describe('placeGardenCaptures', () => {
    const entries = [
        { id: 'visit-11', at: '2026-10-13T11:00:00Z' },
        { id: 'visit-09', at: '2026-10-13T09:00:00Z' },
        { id: 'visit-07', at: '2026-10-13T07:00:00Z' }
    ];
    const at = (entry: { at: string }) => Date.parse(entry.at);
    const captures = [
        capture({ id: 'fox-12', observed_at: '2026-10-13T12:00:00Z' }),
        capture({ id: 'cat-08', observed_at: '2026-10-13T08:00:00Z' }),
        capture({ id: 'cat-10', observed_at: '2026-10-13T10:00:00Z' })
    ];
    const ids = (placed: Array<{ id: string } | { kind: 'garden'; capture: GardenCapture }>) =>
        placed.map((entry) => ('kind' in entry ? entry.capture.id : entry.id));

    it('slots each capture between the visits it fell between, newest first', () => {
        expect(ids(placeGardenCaptures(entries, at, captures, 'newest')))
            .toEqual(['fox-12', 'visit-11', 'cat-10', 'visit-09', 'cat-08', 'visit-07']);
    });

    it('keeps the same reading order oldest first', () => {
        expect(ids(placeGardenCaptures([...entries].reverse(), at, captures, 'oldest')))
            .toEqual(['visit-07', 'cat-08', 'visit-09', 'cat-10', 'visit-11', 'fox-12']);
    });

    it('keeps the visits in the order the server gave them', () => {
        expect(ids(placeGardenCaptures(entries, at, [], 'newest'))).toEqual(['visit-11', 'visit-09', 'visit-07']);
    });
});

describe('gardenWindow', () => {
    const visit = (start: string, end: string) => ({ start_time: start, end_time: end }) as DetectionVisit;
    const now = new Date('2026-10-14T00:00:00Z');

    it("owns the same span of time as the page's heard calls when there are visits", () => {
        const span = gardenWindow({
            visits: [visit('2026-10-13T09:00:00Z', '2026-10-13T09:05:00Z')],
            sort: 'newest',
            previous: null,
            hasNextPage: false,
            birdTotal: 1,
            rangeStart: new Date('2026-10-13T00:00:00Z'),
            rangeEnd: null,
            now
        });
        expect(span).toEqual({ start: new Date('2026-10-13T00:00:00Z'), end: now });
    });

    it('still shows animals on a span with no bird visits at all', () => {
        expect(gardenWindow({ visits: [], sort: 'newest', previous: null, hasNextPage: false, birdTotal: 0, rangeStart: null, rangeEnd: null, now }))
            .toEqual({ start: null, end: now });
    });

    it('shows nothing on an empty page past the end of the visits', () => {
        expect(gardenWindow({ visits: [], sort: 'newest', previous: null, hasNextPage: false, birdTotal: 30, rangeStart: null, rangeEnd: null, now }))
            .toBeNull();
    });
});

describe('gardenEntryText', () => {
    const t = (_key: string, fallback: string) => fallback;

    it('names nothing a model has not named, and says what still needs a person', () => {
        const pending = capture();
        expect(gardenEntryText(pending, gardenEntryView(pending), t)).toEqual({ title: 'Possible animal', state: 'Needs review: is an animal there?' });
        const suggested = capture({ status: 'confirmed', identification: named('unreviewed') });
        expect(gardenEntryText(suggested, gardenEntryView(suggested), t)).toEqual({ title: 'Red fox', state: 'Needs review: suggested species' });
        const unnamed = capture({ status: 'confirmed' });
        expect(gardenEntryText(unnamed, gardenEntryView(unnamed), t)).toEqual({ title: 'Animal, not named', state: 'Animal confirmed, species not named' });
    });
});

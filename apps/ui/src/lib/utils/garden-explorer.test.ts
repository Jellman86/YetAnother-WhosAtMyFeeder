import { describe, expect, it } from 'vitest';
import type { GardenCapture } from '../api/garden';
import type { DetectionVisit } from '../api/visits';
import { gardenBelongs, gardenBlocker, gardenCaptureFacts, gardenEntryText, gardenRowDetail, groupGardenVisits, gardenEntryView, gardenWindow, placeGardenCaptures, type GardenFilterState } from './garden-explorer';

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
    it('waits for automatic identification without asking for presence verification', () => {
        expect(gardenEntryView(capture())).toEqual({ name: null, nameState: 'none', score: null, review: null });
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
        expect(gardenEntryText(pending, gardenEntryView(pending), t, 'owner')).toEqual({ title: 'Possible animal', state: 'Waiting for automatic identification' });
        const suggested = capture({ status: 'confirmed', identification: named('unreviewed') });
        expect(gardenEntryText(suggested, gardenEntryView(suggested), t, 'owner')).toEqual({ title: 'Red fox', state: 'Needs review: suggested species' });
        const unnamed = capture({ status: 'confirmed' });
        expect(gardenEntryText(unnamed, gardenEntryView(unnamed), t, 'owner')).toEqual({ title: 'Animal, not named', state: 'Animal confirmed, species not named' });
    });

    it('credits a confirmed species to the person reading only when that person is the owner', () => {
        const confirmed = capture({ status: 'confirmed', identification: named('accepted') });
        const view = gardenEntryView(confirmed);
        expect(gardenEntryText(confirmed, view, t, 'owner')).toEqual({ title: 'Red fox', state: 'Species confirmed by you' });
        // A public visitor did not confirm anything, so the owner is named instead.
        expect(gardenEntryText(confirmed, view, t, 'visitor')).toEqual({ title: 'Red fox', state: 'Owner confirmed' });
        expect(gardenEntryText(confirmed, view, t, 'visitor').state).not.toContain('by you');
    });
});

describe('dismissed captures', () => {
    const t = (_key: string, fallback: string) => fallback;

    it('read as dismissed, never as a confirmed or unnamed animal, and ask nothing of a person', () => {
        const dismissed = capture({ status: 'dismissed' });
        expect(gardenEntryView(dismissed).review).toBeNull();
        expect(gardenEntryText(dismissed, gardenEntryView(dismissed), t, 'owner'))
            .toEqual({ title: 'Dismissed capture', state: 'Dismissed, not counted as an animal' });
    });
});

describe('gardenBelongs', () => {
    it('keeps a reviewed capture only in the views that still describe it', () => {
        const confirmed = capture({ status: 'confirmed' });
        const dismissed = capture({ status: 'dismissed' });
        expect(gardenBelongs(confirmed, 'reviewable')).toBe(true);
        expect(gardenBelongs(dismissed, 'reviewable')).toBe(false);
        expect(gardenBelongs(confirmed, 'pending')).toBe(false);
        expect(gardenBelongs(dismissed, 'dismissed')).toBe(true);
        expect(gardenBelongs(capture(), 'dismissed')).toBe(false);
    });
});

describe('groupGardenVisits', () => {
    const at = (seconds: number) => new Date(Date.UTC(2026, 9, 24, 7, 0, seconds)).toISOString();
    const fox = (id: string, seconds: number, extra: Partial<GardenCapture> = {}) =>
        capture({ id, observed_at: at(seconds), status: 'confirmed', identification: named('accepted', true), ...extra });
    const ids = (visits: ReturnType<typeof groupGardenVisits>) => visits.map((visit) => visit.items.map((item) => item.id));

    it("folds one animal's captures on one camera less than a minute apart into one visit, as birds are", () => {
        const visits = groupGardenVisits([fox('c', 100), fox('b', 50), fox('a', 0)]);
        expect(ids(visits)).toEqual([['c', 'b', 'a']]);
        expect(visits[0].kind).toBe('visit');
    });

    it('starts a new visit after a minute without a capture, on another camera, or for another animal', () => {
        const badger = { ...named('accepted', true), name: 'Badger' } as Identification;
        const visits = groupGardenVisits([
            fox('late', 200),
            fox('lawn', 15, { camera: 'lawn' }),
            fox('badger', 12, { identification: badger }),
            fox('b', 10),
            fox('a', 0)
        ]);
        expect(ids(visits)).toEqual([['late'], ['lawn'], ['badger'], ['b', 'a']]);
    });

    it('never merges unconfirmed motion proposals by time, so an animal is not buried in a feeder stack', () => {
        const box = { camera: 'patio', clip_start: 1, clip_end: 9, frame_index: 1, frame_offset: 1, clip_sha256: 'a'.repeat(64), image_sha256: 'b'.repeat(64), detector_sha256: 'c'.repeat(64), detector_score: 0.8 };
        const feeder = (id: string, seconds: number) => capture({ id, observed_at: at(seconds), source_kind: 'motion', motion_source: { ...box, box_xywh: [0.1, 0.1, 0.1, 0.1] } } as Partial<GardenCapture>);
        const animal = capture({ id: 'cat', observed_at: at(5), source_kind: 'motion', motion_source: { ...box, box_xywh: [0.6, 0.5, 0.2, 0.2] } } as Partial<GardenCapture>);
        const visits = groupGardenVisits([feeder('f2', 10), animal, feeder('f1', 0)]);
        expect(ids(visits)).toEqual([['f2', 'f1'], ['cat']]);
        expect(visits[0].kind).toBe('position');
    });

    it('keeps unconfirmed Frigate events and confirmed animals apart, and keeps the order it was given', () => {
        const visits = groupGardenVisits([capture({ id: 'p', observed_at: at(20) }), fox('f', 10), capture({ id: 'q', observed_at: at(0) })]);
        expect(ids(visits)).toEqual([['p', 'q'], ['f']]);
    });
});

describe('gardenCaptureFacts', () => {
    const lead = capture({ id: 'lead'.padEnd(32, '0'), status: 'confirmed', identification: named('accepted', true) });
    const visit = { id: 'visit-1', kind: 'visit' as const, captureCount: 3, items: [lead] };

    it('marks the capture the visit shows as its photograph', () => {
        expect(gardenCaptureFacts(lead, visit)).toEqual({ shown: true, motion: false, review: null });
        expect(gardenCaptureFacts(capture({ id: 'other'.padEnd(32, '0'), status: 'confirmed' }), visit).shown).toBe(false);
    });

    it('says when a capture came from motion footage and when it still needs a person', () => {
        const proposal = capture({ id: 'motion'.padEnd(32, '0'), source_kind: 'motion', status: 'confirmed', identification: named('unreviewed') });
        expect(gardenCaptureFacts(proposal, visit)).toEqual({ shown: false, motion: true, review: 'species' });
    });
});


it('owner names replace the display identity without borrowing model confidence', () => {
    const original = named('accepted', true);
    const corrected = capture({ status: 'confirmed', identification: original, owner_identification: {
        species_id: 123, name: 'Domestic Cat', scientific_name: 'Felis catus', changed_at: '2026-10-29T00:00:00Z'
    }});
    expect(gardenEntryView(corrected)).toEqual({ name: 'Domestic Cat', nameState: 'confirmed', score: null, review: null });
    expect(corrected.identification).toBe(original);
});

describe('gardenRowDetail', () => {
    it('names a settled animal by its scientific name, as a settled bird row does', () => {
        const fox = capture({ status: 'confirmed', identification: named('accepted', true), scientific_name: 'Vulpes vulpes' });
        expect(gardenRowDetail(fox, gardenEntryView(fox))).toEqual({ scientific: 'Vulpes vulpes', showState: false });
        const chosen = capture({ status: 'confirmed', identification: named('accepted'), scientific_name: 'Vulpes vulpes' });
        expect(gardenRowDetail(chosen, gardenEntryView(chosen))).toEqual({ scientific: 'Vulpes vulpes', showState: false });
    });

    it('keeps the state in words while the entry waits on a person or has no name', () => {
        const suggested = capture({ status: 'confirmed', identification: named('unreviewed'), scientific_name: 'Vulpes vulpes' });
        expect(gardenRowDetail(suggested, gardenEntryView(suggested)).showState).toBe(true);
        const unnamed = capture({ status: 'confirmed' });
        expect(gardenRowDetail(unnamed, gardenEntryView(unnamed))).toEqual({ scientific: null, showState: true });
        const pending = capture();
        expect(gardenRowDetail(pending, gardenEntryView(pending)).showState).toBe(true);
    });

    it('never claims a scientific name the catalogue did not give', () => {
        const fox = capture({ status: 'confirmed', identification: named('accepted', true), scientific_name: null });
        expect(gardenRowDetail(fox, gardenEntryView(fox))).toEqual({ scientific: null, showState: true });
    });
});

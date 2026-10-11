import { describe, expect, it } from 'vitest';
import type { HeardGroup, HeardVisitCalls } from '../api/audio';
import type { DetectionVisit } from '../api/visits';
import type { Detection } from '../api';
import { buildHeardTimeline, heardWindow } from './heard-timeline';

const at = (hhmm: string): string => `2026-10-08T${hhmm}:00Z`;

function visit(id: string, start: string, end: string, options: { confirmed?: boolean; species?: string; scientific?: string } = {}): DetectionVisit {
    const representative = {
        frigate_event: id,
        detection_time: at(start),
        display_name: options.species ?? 'Dunnock',
        common_name: options.species ?? 'Dunnock',
        scientific_name: options.scientific ?? 'Prunella modularis',
        camera_name: 'birdcam',
        score: 0.9
    } as unknown as Detection;
    return {
        visit_id: id,
        start_time: at(start),
        end_time: at(end),
        representative,
        latest: representative,
        peak_capture: null,
        capture_count: 1,
        best_score: 0.9,
        needs_review: false,
        audio_confirmed: options.confirmed ?? false
    } as DetectionVisit;
}

function group(species: string, first: string, last: string, calls: number, extra: Partial<HeardGroup> = {}): HeardGroup {
    const scientific: Record<string, string> = { Dunnock: 'Prunella modularis', 'House Sparrow': 'Passer domesticus', 'European Robin': 'Erithacus rubecula' };
    return {
        species,
        scientific_name: scientific[species] ?? null,
        first_heard: at(first),
        last_heard: at(last),
        call_count: calls,
        best_confidence: 0.9,
        best_heard: at(first),
        best_birdnet_id: calls,
        source_name: 'patiocam',
        ...extra
    };
}

const base = { sort: 'newest' as const, matched: [] as HeardVisitCalls[], hasPreviousPage: false, hasNextPage: false };

describe('heard timeline', () => {
    it('gathers calls between two visits into one band, newest first', () => {
        const entries = buildHeardTimeline({
            ...base,
            visits: [visit('b', '10:04', '10:05'), visit('a', '09:30', '09:31')],
            groups: [group('House Sparrow', '09:34', '09:42', 2), group('Dunnock', '09:48', '09:49', 4)]
        });
        expect(entries.map((entry) => entry.kind)).toEqual(['visit', 'band', 'visit']);
        const band = entries[1].kind === 'band' ? entries[1].band : null;
        expect(band?.position).toBe('between');
        expect(band?.callCount).toBe(6);
        expect(band?.firstHeard).toBe(at('09:34'));
        expect(band?.lastHeard).toBe(at('09:49'));
        expect(band?.species).toEqual([
            { name: 'Dunnock', count: 4 },
            { name: 'House Sparrow', count: 2 }
        ]);
    });

    it('names the ends of the timeline only on the pages that hold them', () => {
        const visits = [visit('a', '09:30', '09:31')];
        const groups = [group('House Sparrow', '11:00', '11:10', 3), group('European Robin', '08:00', '08:00', 1)];
        const first = buildHeardTimeline({ ...base, visits, groups });
        expect(first.filter((entry) => entry.kind === 'band').map((entry) => entry.kind === 'band' && entry.band.position)).toEqual(['after-last', 'before-first']);
        const middle = buildHeardTimeline({ ...base, visits, groups, hasPreviousPage: true, hasNextPage: true });
        expect(middle.every((entry) => entry.kind !== 'band' || entry.band.position === 'between')).toBe(true);
    });

    it('shows the calls the server counted on the visit it names', () => {
        const entries = buildHeardTimeline({
            ...base,
            visits: [visit('a', '08:14', '08:15', { confirmed: true })],
            groups: [group('House Sparrow', '08:30', '08:30', 1)],
            matched: [{ visit_id: 'a', start_time: at('08:14'), end_time: at('08:15'), scientific_name: 'prunella modularis', call_count: 3 }]
        });
        expect(entries.find((entry) => entry.kind === 'visit')).toMatchObject({ matchedCalls: 3 });
        expect(entries.filter((entry) => entry.kind === 'band')).toHaveLength(1);
    });

    it('finds the visit by species and span when the server named it by a later capture', () => {
        const entries = buildHeardTimeline({
            ...base,
            visits: [visit('a', '08:14', '08:16', { confirmed: true })],
            groups: [],
            matched: [{ visit_id: 'later-capture', start_time: at('08:15'), end_time: at('08:16'), scientific_name: 'prunella modularis', call_count: 2 }]
        });
        expect(entries.find((entry) => entry.kind === 'visit')).toMatchObject({ matchedCalls: 2 });
    });

    it('leaves a visit the server did not name without matched calls', () => {
        const entries = buildHeardTimeline({
            ...base,
            visits: [visit('a', '08:14', '08:15', { confirmed: true }), visit('b', '09:00', '09:01', { confirmed: true, species: 'European Robin', scientific: 'Erithacus rubecula' })],
            groups: [],
            matched: [{ visit_id: 'a', start_time: at('08:14'), end_time: at('08:15'), scientific_name: 'prunella modularis', call_count: 5 }]
        });
        expect(entries.map((entry) => entry.kind === 'visit' && [entry.visit.visit_id, entry.matchedCalls])).toEqual([['b', 0], ['a', 5]]);
    });

    it('reads oldest first when the Explorer does', () => {
        const entries = buildHeardTimeline({
            ...base,
            sort: 'oldest',
            visits: [visit('a', '09:30', '09:31'), visit('b', '10:04', '10:05')],
            groups: [group('House Sparrow', '09:40', '09:41', 1)]
        });
        expect(entries.map((entry) => (entry.kind === 'visit' ? entry.visit.visit_id : 'band'))).toEqual(['a', 'band', 'b']);
    });

    it('pictures a band with the strongest call of its busiest species first', () => {
        const entries = buildHeardTimeline({
            ...base,
            visits: [],
            groups: [
                group('House Sparrow', '09:00', '09:10', 9, { best_birdnet_id: 11, best_confidence: 0.7 }),
                group('House Sparrow', '10:00', '10:10', 4, { best_birdnet_id: 12, best_confidence: 0.95 }),
                group('Dunnock', '09:30', '09:31', 2, { best_birdnet_id: null }),
                group('European Robin', '09:40', '09:41', 1, { best_birdnet_id: 31 })
            ]
        });
        expect(entries[0].kind === 'band' && entries[0].band.pictures).toEqual([12, 31]);
    });
});

describe('heard window', () => {
    const now = new Date(at('12:00'));
    const page = [visit('b', '10:04', '10:05'), visit('a', '09:30', '09:31')];

    it('runs from the oldest visit to now on a lone first page with no dates', () => {
        expect(heardWindow({ visits: page, sort: 'newest', previous: null, hasNextPage: false, rangeStart: null, rangeEnd: null, now })).toEqual({
            start: new Date(at('09:30')),
            end: now
        });
    });

    it('owns the gap back to the previous page but leaves its own trailing gap to the next page', () => {
        const previous = visit('c', '11:20', '11:21');
        expect(heardWindow({ visits: page, sort: 'newest', previous, hasNextPage: true, rangeStart: null, rangeEnd: null, now })).toEqual({
            start: new Date(at('09:30')),
            end: new Date(at('11:20'))
        });
    });

    it('reaches back to the chosen start date on the last page', () => {
        const rangeStart = new Date(at('00:00'));
        expect(heardWindow({ visits: page, sort: 'newest', previous: null, hasNextPage: false, rangeStart, rangeEnd: null, now })?.start).toEqual(rangeStart);
    });

    it('has no window without visits', () => {
        expect(heardWindow({ visits: [], sort: 'newest', previous: null, hasNextPage: false, rangeStart: null, rangeEnd: null, now })).toBeNull();
    });
});

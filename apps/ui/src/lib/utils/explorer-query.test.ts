import { describe, expect, it } from 'vitest';
import { defaultExplorerQuery, explorerPresetDays, explorerReadWindow, explorerWindow, parseExplorerQuery, rereadsAfterRecordChange, writeExplorerQuery, type ExplorerQuery } from './explorer-query';

const owner = { owner: true, gardenAvailable: true };
const guest = { owner: false, gardenAvailable: true };

function chosen(overrides: Partial<ExplorerQuery>): ExplorerQuery {
    return { ...defaultExplorerQuery(), ...overrides };
}

describe('writeExplorerQuery', () => {
    it('writes nothing for the default view, so a plain Explorer keeps a plain address', () => {
        expect(writeExplorerQuery('', chosen({ subjects: 'all' }), { owner: true, gardenAvailable: false })).toBe('');
    });

    it('round-trips every rail field an owner can choose', () => {
        const state = chosen({
            subjects: 'garden',
            gardenReview: 'pending',
            datePreset: 'custom',
            customStartDate: '2026-10-01',
            customEndDate: '2026-10-28',
            speciesFilter: 'Prunella modularis',
            cameraFilter: 'greenhouse cam',
            favoritesOnly: true,
            audioConfirmedOnly: true,
            multipleSpeciesOnly: true,
            ownerConfirmedOnly: true,
            showHidden: true,
            groupVisits: false,
            page: 3
        });
        const search = writeExplorerQuery('', state, owner);
        expect(parseExplorerQuery(search, owner)).toEqual(state);
    });

    it('round-trips a group of species chosen in the search', () => {
        const state = chosen({ subjects: 'all', taxonFilter: 4512 });
        const search = writeExplorerQuery('', state, owner);
        expect(search).toBe('visitors=all&taxon=4512');
        expect(parseExplorerQuery(search, owner)).toEqual(state);
    });

    it('keeps the addresses other features own, such as a shared clip or a fixture flag', () => {
        const search = writeExplorerQuery('?event=abc&share=tok&video=1&surface=explorer&species=Old', chosen({ speciesFilter: 'New' }), owner);
        const params = new URLSearchParams(search);
        expect(params.get('event')).toBe('abc');
        expect(params.get('share')).toBe('tok');
        expect(params.get('video')).toBe('1');
        expect(params.get('surface')).toBe('explorer');
        expect(params.getAll('species')).toEqual(['New']);
    });

    it('removes a filter from the address once it is cleared', () => {
        const search = writeExplorerQuery('?species=Dunnock&favorites=1&page=4&date=week', defaultExplorerQuery(), owner);
        expect(search).toBe('');
    });

    it('states the custom dates only while the custom window is chosen', () => {
        const search = writeExplorerQuery('', chosen({ datePreset: 'week', customStartDate: '2026-10-01' }), owner);
        expect(new URLSearchParams(search).has('start')).toBe(false);
        expect(new URLSearchParams(search).get('date')).toBe('week');
    });

    it('names the visitors whenever Garden is readable, so a shared link shows the same subjects', () => {
        expect(new URLSearchParams(writeExplorerQuery('', chosen({ subjects: 'all' }), owner)).get('visitors')).toBe('all');
    });

    it('leaves visitors and review alone while Garden is not known to be available', () => {
        // Settings load after the page; a write before then must not drop a Garden link.
        const search = writeExplorerQuery('?visitors=garden&review=pending', chosen({ speciesFilter: 'Dunnock' }), { owner: true, gardenAvailable: false });
        const params = new URLSearchParams(search);
        expect(params.get('visitors')).toBe('garden');
        expect(params.get('review')).toBe('pending');
    });

    it('writes no owner-only filter for a visitor', () => {
        const search = writeExplorerQuery('', chosen({ subjects: 'garden', gardenReview: 'pending', showHidden: true, multipleSpeciesOnly: true, ownerConfirmedOnly: true }), guest);
        const params = new URLSearchParams(search);
        expect(params.has('review')).toBe(false);
        expect(params.has('hidden')).toBe(false);
        expect(params.has('multiple')).toBe(false);
        expect(params.has('confirmed')).toBe(false);
    });

    it('writes Owner confirmed as confirmed=1 for the owner and drops it once cleared', () => {
        expect(writeExplorerQuery('', chosen({ ownerConfirmedOnly: true }), owner)).toBe('confirmed=1');
        expect(writeExplorerQuery('?confirmed=1&species=Dunnock', chosen({ speciesFilter: 'Dunnock' }), owner)).toBe('species=Dunnock');
    });

    it('strips Owner confirmed from an address a visitor holds, as access falls away', () => {
        // A signed-out owner keeps the old address until the next write; that write must not keep it.
        expect(writeExplorerQuery('?confirmed=1&favorites=1', chosen({ favoritesOnly: true, ownerConfirmedOnly: true }), guest)).toBe('favorites=1');
    });

    it('writes the Garden review only under Garden animals', () => {
        const search = writeExplorerQuery('', chosen({ subjects: 'all', gardenReview: 'pending' }), owner);
        expect(new URLSearchParams(search).has('review')).toBe(false);
    });
});

describe('parseExplorerQuery', () => {
    it('reads a group of species chosen in the search as a whole positive catalogue id', () => {
        expect(parseExplorerQuery('taxon=4512', owner).taxonFilter).toBe(4512);
        expect(parseExplorerQuery('taxon=4512', guest).taxonFilter).toBe(4512);
        for (const value of ['0', '-3', '4.5', 'family', '99999999999', '']) {
            expect(parseExplorerQuery(`taxon=${value}`, owner).taxonFilter).toBeNull();
        }
    });

    it('never holds a species and a group of species at once; the species wins', () => {
        const query = parseExplorerQuery('species=Prunella%20modularis&taxon=4512', owner);
        expect(query.speciesFilter).toBe('Prunella modularis');
        expect(query.taxonFilter).toBeNull();
    });

    it('opens a pasted link with its filters', () => {
        const query = parseExplorerQuery('?visitors=birds&date=month&species=Erithacus%20rubecula&camera=birdcam&favorites=true&audio=1&show=captures&page=2', owner);
        expect(query).toEqual(chosen({
            subjects: 'birds',
            datePreset: 'month',
            speciesFilter: 'Erithacus rubecula',
            cameraFilter: 'birdcam',
            favoritesOnly: true,
            audioConfirmedOnly: true,
            groupVisits: false,
            page: 2
        }));
    });

    it('leaves the subjects to the device when the link does not name them', () => {
        expect(parseExplorerQuery('?species=Dunnock', owner).subjects).toBeNull();
    });

    it('ignores values it cannot trust and keeps the rest', () => {
        const query = parseExplorerQuery('?visitors=cats&review=everything&date=yesterday&page=-2&favorites=maybe&show=both&species=Dunnock', owner);
        expect(query).toEqual(chosen({ speciesFilter: 'Dunnock' }));
    });

    it('accepts only real calendar days for a custom window', () => {
        expect(parseExplorerQuery('?date=custom&start=2026-02-30&end=2026-13-01', owner)).toEqual(chosen({ datePreset: 'custom' }));
        expect(parseExplorerQuery('?date=custom&start=2026-10-01&end=2026-10-28', owner)).toEqual(
            chosen({ datePreset: 'custom', customStartDate: '2026-10-01', customEndDate: '2026-10-28' })
        );
    });

    it('drops a custom window that ends before it starts', () => {
        expect(parseExplorerQuery('?date=custom&start=2026-10-28&end=2026-10-01', owner)).toEqual(chosen({ datePreset: 'custom' }));
    });

    it('reads dates without a stated window as a custom window', () => {
        expect(parseExplorerQuery('?start=2026-10-01', owner)).toEqual(chosen({ datePreset: 'custom', customStartDate: '2026-10-01' }));
    });

    it('ignores custom dates under a preset window', () => {
        expect(parseExplorerQuery('?date=week&start=2026-10-01', owner)).toEqual(chosen({ datePreset: 'week' }));
    });

    it('never lets a link give a visitor owner-only filters', () => {
        const query = parseExplorerQuery('?visitors=garden&review=pending&hidden=1&multiple=1&confirmed=1', guest);
        expect(query).toEqual(chosen({ subjects: 'garden' }));
    });

    it('reads Owner confirmed for the owner only', () => {
        expect(parseExplorerQuery('?confirmed=1', owner).ownerConfirmedOnly).toBe(true);
        expect(parseExplorerQuery('?confirmed=true', owner).ownerConfirmedOnly).toBe(true);
        expect(parseExplorerQuery('?confirmed=yes', owner).ownerConfirmedOnly).toBe(false);
        expect(parseExplorerQuery('?confirmed=1', guest).ownerConfirmedOnly).toBe(false);
    });

    it('refuses an oversized or control-character name rather than sending it on', () => {
        const long = 'x'.repeat(300);
        expect(parseExplorerQuery(`?species=${long}&camera=a%0Ab`, owner)).toEqual(defaultExplorerQuery());
    });

    it('caps the page at a sane number and needs a whole number', () => {
        expect(parseExplorerQuery('?page=2.5', owner).page).toBe(1);
        expect(parseExplorerQuery('?page=99999999', owner).page).toBe(1);
        expect(parseExplorerQuery('?page=12', owner).page).toBe(12);
    });
});

describe('the last 24 hours', () => {
    it('round-trips through the address as date=24h with no dates beside it', () => {
        const state = chosen({ subjects: 'birds', datePreset: '24h' });
        const search = writeExplorerQuery('', state, owner);
        expect(search).toBe('visitors=birds&date=24h');
        expect(parseExplorerQuery(search, owner)).toEqual(state);
    });

    it('ignores custom dates a link sets beside it', () => {
        const query = parseExplorerQuery('date=24h&start=2026-10-01&end=2026-10-02', owner);
        expect(query.datePreset).toBe('24h');
        expect(query.customStartDate).toBe('');
        expect(query.customEndDate).toBe('');
    });
});

describe('explorerWindow', () => {
    const now = new Date('2026-11-25T10:15:30.250Z');

    it('reads the last 24 hours as one pair of exact instants ending now', () => {
        const window = explorerWindow('24h', {}, now);
        expect(window.request).toEqual({ startTime: '2026-11-24T10:15:30.250Z', endTime: '2026-11-25T10:15:30.250Z' });
        expect(window.start?.toISOString()).toBe('2026-11-24T10:15:30.250Z');
        expect(window.end?.toISOString()).toBe('2026-11-25T10:15:30.250Z');
    });

    it('ignores calendar days under the last 24 hours', () => {
        const window = explorerWindow('24h', { start: '2026-01-01', end: '2026-01-02' }, now);
        expect(window.request.startDate).toBeUndefined();
        expect(window.request.endDate).toBeUndefined();
    });

    it('keeps calendar days as days, bounded by local midnight and the last instant of the day', () => {
        const window = explorerWindow('custom', { start: '2026-11-01', end: '2026-11-03' }, now);
        expect(window.request).toEqual({ startDate: '2026-11-01', endDate: '2026-11-03' });
        expect(window.start).toEqual(new Date('2026-11-01T00:00:00'));
        expect(window.end).toEqual(new Date('2026-11-03T23:59:59.999'));
    });

    it('has no bounds for all time', () => {
        expect(explorerWindow('all', {}, now)).toEqual({ request: {}, start: null, end: null });
    });
});

describe('rereadsAfterRecordChange', () => {
    const captures = { ...defaultExplorerQuery(), groupVisits: false, selectionMode: false };

    it('re-reads grouped visits after any change, since a change can join or split them', () => {
        expect(rereadsAfterRecordChange({ ...captures, groupVisits: true })).toBe(true);
    });

    it('re-reads a filtered capture list and its count when a change can move a capture in or out', () => {
        // Retagging a capture Unknown Bird under Owner confirmed must drop it and lower the count.
        expect(rereadsAfterRecordChange({ ...captures, ownerConfirmedOnly: true })).toBe(true);
        for (const filter of [{ favoritesOnly: true }, { audioConfirmedOnly: true }, { multipleSpeciesOnly: true }, { showHidden: true }, { speciesFilter: 'Dunnock' }, { taxonFilter: 4512 }]) {
            expect(rereadsAfterRecordChange({ ...captures, ...filter })).toBe(true);
        }
    });

    it('patches an unfiltered capture list in place, and leaves a selection alone', () => {
        expect(rereadsAfterRecordChange(captures)).toBe(false);
        expect(rereadsAfterRecordChange({ ...captures, ownerConfirmedOnly: true, selectionMode: true })).toBe(false);
        expect(rereadsAfterRecordChange({ ...captures, groupVisits: true, selectionMode: true })).toBe(false);
    });
});

describe('explorerPresetDays', () => {
    const custom = { start: '2026-10-01', end: '2026-10-05' };

    function calendarDaysIn(range: { start?: string; end?: string }): number {
        const start = new Date(`${range.start}T00:00:00Z`).getTime();
        const end = new Date(`${range.end}T00:00:00Z`).getTime();
        return Math.round((end - start) / (24 * 60 * 60 * 1000)) + 1;
    }

    it('reads Today as the one calendar day', () => {
        expect(explorerPresetDays('today', custom, new Date(2026, 10, 25, 9, 0))).toEqual({ start: '2026-11-25', end: '2026-11-25' });
    });

    it('reads the last 7 days as seven calendar days ending today', () => {
        const range = explorerPresetDays('week', custom, new Date(2026, 10, 25, 9, 0));
        expect(range).toEqual({ start: '2026-11-19', end: '2026-11-25' });
        expect(calendarDaysIn(range)).toBe(7);
    });

    it('reads the last 30 days as thirty calendar days ending today', () => {
        const range = explorerPresetDays('month', custom, new Date(2026, 10, 25, 9, 0));
        expect(range).toEqual({ start: '2026-10-27', end: '2026-11-25' });
        expect(calendarDaysIn(range)).toBe(30);
    });

    it('counts calendar days across a month end and a clock change', () => {
        // 25 October 2026 is the night most of Europe moves its clocks back.
        expect(explorerPresetDays('week', custom, new Date(2026, 10, 1, 0, 30))).toEqual({ start: '2026-10-26', end: '2026-11-01' });
        expect(explorerPresetDays('month', custom, new Date(2026, 2, 1, 23, 30))).toEqual({ start: '2026-01-31', end: '2026-03-01' });
    });

    it('keeps a custom range as chosen and leaves the open ones open', () => {
        expect(explorerPresetDays('custom', custom, new Date())).toEqual(custom);
        expect(explorerPresetDays('custom', { start: '', end: '2026-10-05' }, new Date())).toEqual({ start: undefined, end: '2026-10-05' });
        expect(explorerPresetDays('all', custom, new Date())).toEqual({ start: undefined, end: undefined });
        expect(explorerPresetDays('24h', custom, new Date())).toEqual({ start: undefined, end: undefined });
    });
});

describe('explorerReadWindow', () => {
    const custom = { start: '', end: '' };

    it('reads the same period again on the new day after midnight', () => {
        const beforeMidnight = new Date(2026, 10, 25, 23, 59, 30);
        const afterMidnight = new Date(2026, 10, 26, 0, 0, 30);
        expect(explorerReadWindow('today', custom, beforeMidnight).request).toEqual({ startDate: '2026-11-25', endDate: '2026-11-25' });
        expect(explorerReadWindow('today', custom, afterMidnight).request).toEqual({ startDate: '2026-11-26', endDate: '2026-11-26' });
        expect(explorerReadWindow('week', custom, afterMidnight).request).toEqual({ startDate: '2026-11-20', endDate: '2026-11-26' });
        expect(explorerReadWindow('month', custom, afterMidnight).request).toEqual({ startDate: '2026-10-28', endDate: '2026-11-26' });
    });

    it('takes the days and the last 24 hours from the one instant it is given', () => {
        const now = new Date('2026-11-26T00:00:30Z');
        const window = explorerReadWindow('24h', custom, now);
        expect(window.end?.getTime()).toBe(now.getTime());
        expect(window.request.startTime).toBe('2026-11-25T00:00:30.000Z');
    });
});

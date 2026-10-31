import { describe, expect, it } from 'vitest';
import { defaultExplorerQuery, parseExplorerQuery, writeExplorerQuery, type ExplorerQuery } from './explorer-query';

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
            showHidden: true,
            groupVisits: false,
            page: 3
        });
        const search = writeExplorerQuery('', state, owner);
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
        const search = writeExplorerQuery('', chosen({ subjects: 'garden', gardenReview: 'pending', showHidden: true, multipleSpeciesOnly: true }), guest);
        const params = new URLSearchParams(search);
        expect(params.has('review')).toBe(false);
        expect(params.has('hidden')).toBe(false);
        expect(params.has('multiple')).toBe(false);
    });

    it('writes the Garden review only under Garden animals', () => {
        const search = writeExplorerQuery('', chosen({ subjects: 'all', gardenReview: 'pending' }), owner);
        expect(new URLSearchParams(search).has('review')).toBe(false);
    });
});

describe('parseExplorerQuery', () => {
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
        const query = parseExplorerQuery('?visitors=garden&review=pending&hidden=1&multiple=1', guest);
        expect(query).toEqual(chosen({ subjects: 'garden' }));
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

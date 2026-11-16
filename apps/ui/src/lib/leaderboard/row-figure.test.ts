import { describe, expect, it } from 'vitest';
import { rowFigureFor, speciesStatLead } from './row-figure';

const rows = [
    { species: 'Eurasian Blue Tit', count: 123, audio_only: false },
    { species: 'Tawny Owl', count: 0, audio_only: true }
];

describe('the figure a Leaderboard row showed', () => {
    it('is the row\'s own count, unit and window', () => {
        expect(rowFigureFor(rows, 'Eurasian Blue Tit', { countsAreVisits: true, span: 'month' })).toEqual({ unit: 'visits', count: 123, span: 'month' });
        expect(rowFigureFor(rows, 'Eurasian Blue Tit', { countsAreVisits: false, span: 'all' })).toEqual({ unit: 'detections', count: 123, span: 'all' });
    });

    it('is nothing for a species with no row, or a row that was only heard', () => {
        expect(rowFigureFor(rows, 'Mallard', { countsAreVisits: true, span: 'week' })).toBeNull();
        expect(rowFigureFor(rows, 'Tawny Owl', { countsAreVisits: true, span: 'week' })).toBeNull();
        expect(rowFigureFor(rows, null, { countsAreVisits: true, span: 'week' })).toBeNull();
        expect(rowFigureFor(rows, 'Eurasian Blue Tit', { countsAreVisits: true, span: undefined })).toBeNull();
    });
});

describe('what the species dialog leads with', () => {
    it('leads with the visits the row showed, then the all-time detections', () => {
        expect(speciesStatLead({ unit: 'visits', count: 123, span: 'month' })).toBe('row_visits');
    });

    it('leads with detections when the row showed detections, or the dialog was opened elsewhere', () => {
        expect(speciesStatLead({ unit: 'detections', count: 161, span: 'all' })).toBe('detections');
        expect(speciesStatLead(null)).toBe('detections');
        expect(speciesStatLead(undefined)).toBe('detections');
    });
});

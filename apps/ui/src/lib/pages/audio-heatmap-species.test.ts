import { describe, expect, it } from 'vitest';
import { HEATMAP_SPECIES_CHOICES, keptHeatmapChoice } from '../leaderboard/heatmap';
import { audioHeatmapReading, audioHeatmapSpeciesOptions, audioSpeciesHeatmapParams, keptSpeciesHeatmap } from './audio-heatmap-species';

const heard = (species: string, scientific_name: string | null, count: number) => ({ species, scientific_name, count });

describe('audioHeatmapSpeciesOptions', () => {
    it('offers the most heard species, by calls heard, as many as the Leaderboard offers', () => {
        const options = audioHeatmapSpeciesOptions([
            heard('Wren', 'Troglodytes troglodytes', 10),
            heard('Dunnock', 'Prunella modularis', 38),
            heard('Robin', 'Erithacus rubecula', 25),
            heard('Blackbird', 'Turdus merula', 9),
            heard('Great Tit', 'Parus major', 8),
            heard('Blue Tit', 'Cyanistes caeruleus', 7),
            heard('Goldcrest', 'Regulus regulus', 6),
        ], '');

        expect(HEATMAP_SPECIES_CHOICES).toBe(5);
        expect(options.map((option) => option.label)).toEqual(['Dunnock', 'Robin', 'Wren', 'Blackbird', 'Great Tit']);
        // Asked for by scientific name: the name shown is translated, and the grid matches it exactly.
        expect(options[0].key).toBe('Prunella modularis');
    });

    it('offers only species with calls in the window and a scientific name to ask for', () => {
        const options = audioHeatmapSpeciesOptions([
            heard('Dunnock', 'Prunella modularis', 38),
            heard('Silent', 'Silentia nulla', 0),
            heard('Mystery Warbler', null, 30),
            heard('Robin', '  ', 25),
        ], '');

        expect(options.map((option) => option.label)).toEqual(['Dunnock']);
    });

    it('folds the rows of one species stored under two common names into one choice', () => {
        const options = audioHeatmapSpeciesOptions([
            heard('Robin', 'Erithacus rubecula', 20),
            heard('Dunnock', 'Prunella modularis', 30),
            heard('Rotkehlchen', 'erithacus rubecula', 15),
        ], '');

        expect(options).toEqual([
            { key: 'Erithacus rubecula', label: 'Robin', count: 35 },
            { key: 'Prunella modularis', label: 'Dunnock', count: 30 },
        ]);
    });

    it('tells apart two species that translate to the same name', () => {
        const options = audioHeatmapSpeciesOptions([
            heard('Kleiber', 'Sitta europaea', 12),
            heard('Kleiber', 'Sittidae', 4),
        ], '');

        expect(options.map((option) => option.label)).toEqual(['Kleiber (Sitta europaea)', 'Kleiber (Sittidae)']);
    });

    it('offers no choice while the page is filtered to a species, so the two never disagree', () => {
        const top = [heard('Dunnock', 'Prunella modularis', 38), heard('Dunnock Two', 'Prunella two', 3)];

        expect(audioHeatmapSpeciesOptions(top, 'Dunnock')).toEqual([]);
        expect(audioHeatmapSpeciesOptions(top, '   ')).toHaveLength(2);
    });
});

describe('keptHeatmapChoice', () => {
    const options = [{ key: 'Prunella modularis' }, { key: 'Erithacus rubecula' }];

    it('keeps a species still offered in the new window', () => {
        expect(keptHeatmapChoice('Erithacus rubecula', options)).toBe('Erithacus rubecula');
    });

    it('goes back to all species when the choice is no longer offered', () => {
        expect(keptHeatmapChoice('Troglodytes troglodytes', options)).toBeNull();
        expect(keptHeatmapChoice('Prunella modularis', [])).toBeNull();
    });

    it('leaves all species as it is', () => {
        expect(keptHeatmapChoice(null, options)).toBeNull();
    });
});

describe('audioHeatmapReading', () => {
    it('keeps the filters a reading was read under, without paging or unset filters', () => {
        const reading = audioHeatmapReading({ days: 30, species: undefined, source: 'BirdCam', min_confidence: 0, limit: undefined, offset: undefined });

        expect(reading.filters).toEqual({ days: 30, source: 'BirdCam', min_confidence: 0 });
        expect(Object.keys(reading.filters)).toEqual(['days', 'source', 'min_confidence']);
    });

    it('gives two readings of the same filters the same key, and another window another key', () => {
        const page = { days: 30, source: 'BirdCam', min_confidence: 0.5 };

        expect(audioHeatmapReading(page).key).toBe(audioHeatmapReading({ ...page, limit: 25, offset: 50 }).key);
        expect(audioHeatmapReading(page).key).not.toBe(audioHeatmapReading({ ...page, days: 7 }).key);
        expect(audioHeatmapReading(page).key).not.toBe(audioHeatmapReading({ ...page, source: undefined }).key);
    });

    it('names a Today reading by its start, so a refresh keeps the species grid but asks for the new end', () => {
        const morning = audioHeatmapReading({ start_date: '2026-11-25T00:00:00.000Z', end_date: '2026-11-25T08:00:00.000Z' });
        const later = audioHeatmapReading({ start_date: '2026-11-25T00:00:00.000Z', end_date: '2026-11-25T08:05:00.000Z' });
        const tomorrow = audioHeatmapReading({ start_date: '2026-11-26T00:00:00.000Z', end_date: '2026-11-26T08:00:00.000Z' });

        expect(later.key).toBe(morning.key);
        expect(later.filters.end_date).toBe('2026-11-25T08:05:00.000Z');
        expect(tomorrow.key).not.toBe(morning.key);
    });
});

describe('audioSpeciesHeatmapParams', () => {
    it('asks for the chosen species under every filter of the reading on screen', () => {
        const onScreen = audioHeatmapReading({ days: 7, species: undefined, source: 'BirdCam', min_confidence: 0.6 });

        expect(audioSpeciesHeatmapParams(onScreen, 'Prunella modularis')).toEqual({
            days: 7,
            source: 'BirdCam',
            min_confidence: 0.6,
            scientific_name: 'Prunella modularis'
        });
    });

    it('asks under the reading on screen, not a window chosen since that is still being read or failed', () => {
        const onScreen = audioHeatmapReading({ days: 30, min_confidence: 0 });
        // The page has already moved its applied window to 7 days; the figures beside the grid are still 30.
        const chosen = audioHeatmapReading({ days: 7, min_confidence: 0 });

        expect(audioSpeciesHeatmapParams(onScreen, 'Erithacus rubecula').days).toBe(30);
        expect(audioSpeciesHeatmapParams(chosen, 'Erithacus rubecula').days).toBe(7);
    });
});

describe('keptSpeciesHeatmap', () => {
    const thirtyDays = audioHeatmapReading({ days: 30, min_confidence: 0 });
    const shown = { key: 'Prunella modularis', readingKey: thirtyDays.key, grid: 'dunnock grid' };

    it('keeps the species grid through a new reading of the same filters, to dim while it refreshes', () => {
        expect(keptSpeciesHeatmap(shown, audioHeatmapReading({ days: 30, min_confidence: 0, limit: 25, offset: 25 }))).toBe(shown);
    });

    it('drops a grid read under other filters, so it never stands beside another window\u2019s figures', () => {
        expect(keptSpeciesHeatmap(shown, audioHeatmapReading({ days: 7, min_confidence: 0 }))).toBeNull();
        expect(keptSpeciesHeatmap(null, thirtyDays)).toBeNull();
    });
});

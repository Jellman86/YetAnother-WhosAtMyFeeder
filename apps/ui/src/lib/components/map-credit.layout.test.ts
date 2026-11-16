import { describe, expect, it } from 'vitest';
import mapSource from './Map.svelte?raw';
import rangeMapSource from './RangeMap.svelte?raw';
import creditSource from './MapCredit.svelte?raw';
import enSpeciesDetail from '../i18n/locales/en/species_detail.json';

/**
 * OpenStreetMap's tiles may be used only with a visible credit. Both maps had switched Leaflet's
 * attribution off "for a cleaner look" and drew nothing in its place.
 */
describe('maps', () => {
    it('credit OpenStreetMap on every map that draws its tiles', () => {
        for (const [file, source] of Object.entries({ mapSource, rangeMapSource })) {
            expect(source, file).toContain('tile.openstreetmap.org');
            expect(source, file).toContain('<MapCredit />');
        }
        expect(creditSource).toContain('https://www.openstreetmap.org/copyright');
        expect(creditSource).toContain("common.map_credit");
    });

    it('describe only the zoom the range map offers', () => {
        // Wheel zoom is off there so a page scroll is never captured; the hint must not promise it.
        expect(rangeMapSource).toContain('scrollWheelZoom: false');
        expect(enSpeciesDetail.range_map_hint).not.toMatch(/scroll/i);
        expect(enSpeciesDetail.range_map_hint).toBe('Drag to pan. Use + and − to zoom.');
    });
});

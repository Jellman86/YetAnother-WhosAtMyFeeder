import { describe, expect, it } from 'vitest';

import speciesDetailSource from './SpeciesDetailModal.svelte?raw';
import barChartSource from './SimpleBarChart.svelte?raw';

describe('species detail field-record layout', () => {
    it('uses a responsive dialog shell with an accessible close target', () => {
        expect(speciesDetailSource).toContain('max-w-6xl');
        expect(speciesDetailSource).toContain('h-[100dvh]');
        expect(speciesDetailSource).not.toContain('max-w-4xl');
        expect(speciesDetailSource).toContain('min-h-11 min-w-11');
    });

    it('prioritizes the owner record before reference and activity detail', () => {
        const record = speciesDetailSource.indexOf('data-species-record-summary');
        const sightings = speciesDetailSource.indexOf('data-species-recent-sightings');
        const reference = speciesDetailSource.indexOf('data-species-reference');
        const activity = speciesDetailSource.indexOf('data-species-activity');

        expect(record).toBeGreaterThan(-1);
        expect(sightings).toBeGreaterThan(record);
        expect(reference).toBeGreaterThan(sightings);
        expect(activity).toBeGreaterThan(reference);
    });

    it('removes the tiny-label and card-wall treatments', () => {
        expect(speciesDetailSource).not.toMatch(/text-\[(?:9|10|11)px\]/);
        expect(speciesDetailSource.match(/card-base/g) ?? []).toHaveLength(0);
        expect(speciesDetailSource).not.toContain('<!-- Footer -->');
    });

    it('respects reduced-motion preferences', () => {
        expect(speciesDetailSource).toContain('@media (prefers-reduced-motion: reduce)');
    });

    it('labels charts without empty headings or fake keyboard controls', () => {
        expect(speciesDetailSource.match(/ariaLabel=/g) ?? []).toHaveLength(4);
        expect(barChartSource).toContain('{#if title}');
        expect(barChartSource).toContain('{#if onclick}');
        expect(barChartSource).toContain('<button');
        expect(barChartSource).not.toContain('tabindex="0"');
        expect(barChartSource).not.toContain('text-[9px]');
    });
});

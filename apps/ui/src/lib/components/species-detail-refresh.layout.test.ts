import { describe, expect, it } from 'vitest';

import speciesDetailSource from './SpeciesDetailModal.svelte?raw';
import lineageSource from './TaxonomyLineage.svelte?raw';
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

    it('places the bird in its family tree after the record and before the reference text', () => {
        const sightings = speciesDetailSource.indexOf('data-species-recent-sightings');
        const taxonomy = speciesDetailSource.indexOf('<TaxonomyLineage');
        const reference = speciesDetailSource.indexOf('data-species-reference');

        expect(taxonomy).toBeGreaterThan(sightings);
        expect(reference).toBeGreaterThan(taxonomy);
        expect(speciesDetailSource).toMatch(/<TaxonomyLineage\s+scientificName=\{lineageName\}/);
        expect(speciesDetailSource).toMatch(/\{#if !isUnknownBird && lineageName\}/);
    });

    it('draws the family tree band only when there is a lineage to put in it', () => {
        // The rule and padding travel with the lineage, which renders nothing when the catalogue
        // does not know the bird; a wrapper section here would leave an empty ruled band.
        expect(speciesDetailSource).not.toMatch(/<section data-species-taxonomy[^>]*>\s*<TaxonomyLineage/);
        expect(speciesDetailSource).toMatch(/<TaxonomyLineage[^>]*class="border-t border-slate-200 pt-8 dark:border-slate-700"/);
        expect(lineageSource).toMatch(/<section class="space-y-2 \{className\}"/);
    });

    it('keeps the reference description out of the header, where it repeated the section below', () => {
        const header = speciesDetailSource.slice(
            speciesDetailSource.indexOf('<header data-species-modal-header'),
            speciesDetailSource.indexOf('</header>')
        );
        expect(header).not.toContain('info.description');
    });

    it('removes the tiny-label and card-wall treatments', () => {
        expect(speciesDetailSource).not.toMatch(/text-\[(?:9|10|11)px\]/);
        expect(speciesDetailSource.match(/card-base/g) ?? []).toHaveLength(0);
        expect(speciesDetailSource).not.toContain('<!-- Footer -->');
    });

    it('respects reduced-motion preferences', () => {
        expect(speciesDetailSource).toContain('@media (prefers-reduced-motion: reduce)');
    });

    it('shows the complete reference image instead of forcing a panoramic crop', () => {
        expect(speciesDetailSource).toContain('data-species-hero-image');
        expect(speciesDetailSource).toContain('aspect-[4/3]');
        expect(speciesDetailSource).toContain('object-contain');
        expect(speciesDetailSource).not.toContain('object-cover object-center');
    });

    it('uses a restrained, accessible icon language for primary record sections', () => {
        expect(speciesDetailSource.match(/data-species-section-icon/g) ?? []).toHaveLength(5);
        expect(speciesDetailSource.match(/data-species-section-icon[^>]+aria-hidden="true"/g) ?? []).toHaveLength(5);
        expect(speciesDetailSource).toContain('focus-visible:ring-2 focus-visible:ring-brand-500');
    });

    it('labels charts without empty headings or fake keyboard controls', () => {
        expect(speciesDetailSource.match(/ariaLabel=/g) ?? []).toHaveLength(4);
        expect(barChartSource).toContain('{#if title}');
        expect(barChartSource).toContain('{#if onclick}');
        expect(barChartSource).toContain('<button');
        expect(barChartSource).not.toContain('tabindex="0"');
        expect(barChartSource).not.toContain('text-[9px]');
    });

    it('keeps unknown-species reclassification owner-only', () => {
        expect(speciesDetailSource).toContain('if (!authStore.canModify || !recentSighting || reclassifying) return;');
        expect(speciesDetailSource).toContain('{#if authStore.canModify}');
    });
});

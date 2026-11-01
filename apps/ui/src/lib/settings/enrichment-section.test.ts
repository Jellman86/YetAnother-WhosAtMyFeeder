import { describe, expect, it } from 'vitest';
import type { Settings } from '../api/settings';
import { enrichmentSection } from './enrichment-section';
import { sectionIsDirty } from './section-adapter';

function saved(fields: Partial<Settings>): Settings {
    return fields as Settings;
}

describe('Enrichment section draft', () => {
    it('shows the default providers when a server leaves them out', () => {
        expect(enrichmentSection.decode(saved({}))).toEqual({
            enrichmentMode: 'per_enrichment',
            enrichmentSingleProvider: 'wikipedia',
            enrichmentSummarySource: 'wikipedia',
            enrichmentTaxonomySource: 'inaturalist',
            enrichmentSightingsSource: 'disabled',
            enrichmentSeasonalitySource: 'disabled',
            enrichmentRaritySource: 'disabled',
            enrichmentLinksSources: ['wikipedia', 'inaturalist']
        });
    });

    it('sends the stored providers back unchanged with every save', () => {
        const stored = saved({
            enrichment_mode: 'single',
            enrichment_single_provider: 'inaturalist',
            enrichment_summary_source: 'inaturalist',
            enrichment_taxonomy_source: 'inaturalist',
            enrichment_sightings_source: 'ebird',
            enrichment_seasonality_source: 'ebird',
            enrichment_rarity_source: 'ebird',
            enrichment_links_sources: ['ebird']
        });
        expect(enrichmentSection.encodePatch(enrichmentSection.decode(stored))).toEqual({
            enrichment_mode: 'single',
            enrichment_single_provider: 'inaturalist',
            enrichment_summary_source: 'inaturalist',
            enrichment_taxonomy_source: 'inaturalist',
            enrichment_sightings_source: 'ebird',
            enrichment_seasonality_source: 'ebird',
            enrichment_rarity_source: 'ebird',
            enrichment_links_sources: ['ebird']
        });
        expect(sectionIsDirty(enrichmentSection, enrichmentSection.decode(stored), stored)).toBe(false);
    });

    it('keeps an empty link list as saved rather than restoring the defaults', () => {
        const stored = saved({ enrichment_links_sources: [] });
        expect(enrichmentSection.decode(stored).enrichmentLinksSources).toEqual([]);
        expect(sectionIsDirty(enrichmentSection, enrichmentSection.decode(stored), stored)).toBe(false);
    });

    it('compares the link list by content', () => {
        const stored = saved({ enrichment_links_sources: ['wikipedia'] });
        const draft = enrichmentSection.decode(stored);
        expect(sectionIsDirty(enrichmentSection, { ...draft, enrichmentLinksSources: ['wikipedia'] }, stored)).toBe(false);
        expect(sectionIsDirty(enrichmentSection, { ...draft, enrichmentLinksSources: ['ebird'] }, stored)).toBe(true);
    });
});

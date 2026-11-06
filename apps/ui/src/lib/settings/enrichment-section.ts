import type { Settings } from '../api/settings';
import type { SettingsSectionAdapter } from './section-adapter';

/**
 * Which provider fills each part of a species page. The Enrichment tab shows these; it does not
 * edit them, but a save still sends them so the stored choice is never dropped.
 */
export interface EnrichmentDraft {
    enrichmentMode: 'single' | 'per_enrichment';
    enrichmentSingleProvider: string;
    enrichmentSummarySource: string;
    enrichmentTaxonomySource: string;
    enrichmentSightingsSource: string;
    enrichmentSeasonalitySource: string;
    enrichmentRaritySource: string;
    enrichmentLinksSources: string[];
}

interface EnrichmentPatch {
    enrichment_mode: EnrichmentDraft['enrichmentMode'];
    enrichment_single_provider: string;
    enrichment_summary_source: string;
    enrichment_taxonomy_source: string;
    enrichment_sightings_source: string;
    enrichment_seasonality_source: string;
    enrichment_rarity_source: string;
    enrichment_links_sources: string[];
}

export const enrichmentSection: SettingsSectionAdapter<EnrichmentDraft, EnrichmentPatch> = {
    decode(saved: Settings): EnrichmentDraft {
        return {
            enrichmentMode: (saved.enrichment_mode as EnrichmentDraft['enrichmentMode'] | undefined) ?? 'per_enrichment',
            enrichmentSingleProvider: saved.enrichment_single_provider ?? 'wikipedia',
            enrichmentSummarySource: saved.enrichment_summary_source ?? 'wikipedia',
            enrichmentTaxonomySource: saved.enrichment_taxonomy_source ?? 'inaturalist',
            enrichmentSightingsSource: saved.enrichment_sightings_source ?? 'disabled',
            enrichmentSeasonalitySource: saved.enrichment_seasonality_source ?? 'disabled',
            enrichmentRaritySource: saved.enrichment_rarity_source ?? 'disabled',
            enrichmentLinksSources: saved.enrichment_links_sources || ['wikipedia', 'inaturalist']
        };
    },
    encodePatch(draft: EnrichmentDraft): EnrichmentPatch {
        return {
            enrichment_mode: draft.enrichmentMode,
            enrichment_single_provider: draft.enrichmentSingleProvider,
            enrichment_summary_source: draft.enrichmentSummarySource,
            enrichment_taxonomy_source: draft.enrichmentTaxonomySource,
            enrichment_sightings_source: draft.enrichmentSightingsSource,
            enrichment_seasonality_source: draft.enrichmentSeasonalitySource,
            enrichment_rarity_source: draft.enrichmentRaritySource,
            enrichment_links_sources: draft.enrichmentLinksSources
        };
    }
};

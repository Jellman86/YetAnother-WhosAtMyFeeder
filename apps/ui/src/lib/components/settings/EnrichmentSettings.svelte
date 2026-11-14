<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';

    // A read-only summary: the sources follow from the integrations above it, so it has no
    // controls of its own. A save still sends the stored choice so it is never dropped.
    let {
        enrichmentMode = 'per_enrichment',
        enrichmentSingleProvider = 'wikipedia',
        enrichmentSummarySource = 'wikipedia',
        enrichmentTaxonomySource = 'inaturalist',
        enrichmentSightingsSource = 'disabled',
        enrichmentSeasonalitySource = 'disabled',
        enrichmentRaritySource = 'disabled',
        enrichmentLinksSources = ['wikipedia', 'inaturalist'],
        onOpenEbird
    }: {
        enrichmentMode: 'single' | 'per_enrichment';
        enrichmentSingleProvider: string;
        enrichmentSummarySource: string;
        enrichmentTaxonomySource: string;
        enrichmentSightingsSource: string;
        enrichmentSeasonalitySource: string;
        enrichmentRaritySource: string;
        enrichmentLinksSources: string[];
        /** Moves to the eBird settings, which turn on the sources that need eBird. */
        onOpenEbird?: () => void;
    } = $props();

    const formatProvider = (value: string) => {
        const normalized = (value || '').toLowerCase();
        if (normalized === 'ebird') return 'eBird';
        if (normalized === 'inaturalist') return 'iNaturalist';
        if (normalized === 'wikipedia') return 'Wikipedia';
        return value;
    };

    // Nearby sightings, seasonality and rarity come from eBird; without it they have no source.
    const rows: { titleKey: string; value: string; needsEbird: boolean }[] = $derived([
        { titleKey: 'settings.enrichment.summary_title', value: enrichmentMode === 'single' ? enrichmentSingleProvider : enrichmentSummarySource, needsEbird: false },
        { titleKey: 'settings.enrichment.taxonomy_title', value: enrichmentTaxonomySource, needsEbird: false },
        { titleKey: 'settings.enrichment.sightings_title', value: enrichmentSightingsSource, needsEbird: true },
        { titleKey: 'settings.enrichment.seasonality_title', value: enrichmentSeasonalitySource, needsEbird: true },
        { titleKey: 'settings.enrichment.rarity_title', value: enrichmentRaritySource, needsEbird: true }
    ]);
    const missingEbird = $derived(rows.some((row) => row.needsEbird && row.value.toLowerCase() === 'disabled'));
</script>

<SettingsCard
    title={$_('settings.enrichment.title')}
    description={$_('settings.enrichment.desc')}
>
    <dl class="divide-y divide-line-soft" data-enrichment-summary>
        {#each rows as row (row.titleKey)}
            {@const off = row.value.toLowerCase() === 'disabled'}
            <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 first:pt-0">
                <dt class="text-sm font-semibold text-slate-900 dark:text-white">{$_(row.titleKey)}</dt>
                <dd class="text-sm text-slate-700 dark:text-slate-200">
                    {#if off && row.needsEbird}
                        {$_('settings.enrichment.needs_ebird', { default: 'Not shown: needs an eBird API key' })}
                    {:else if off}
                        {$_('settings.enrichment.disabled')}
                    {:else}
                        {formatProvider(row.value)}
                    {/if}
                </dd>
            </div>
        {/each}
        <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3">
            <dt class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.enrichment.links_title')}</dt>
            <dd class="text-sm text-slate-700 dark:text-slate-200">{enrichmentLinksSources.map(formatProvider).join(', ')}</dd>
        </div>
    </dl>
    {#if missingEbird && onOpenEbird}
        <div class="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-4">
            <p class="min-w-0 flex-1 basis-56 text-sm text-slate-600 dark:text-slate-300">
                {$_('settings.enrichment.ebird_hint', { default: 'Nearby sightings, seasonality and rarity appear on species pages once eBird is on with an API key.' })}
            </p>
            <button type="button" class="btn btn-secondary min-h-11 px-4" onclick={onOpenEbird}>
                {$_('settings.enrichment.open_ebird', { default: 'Set up eBird' })}
            </button>
        </div>
    {/if}
</SettingsCard>

<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';

    let {
        enrichmentMode = 'per_enrichment',
        enrichmentSingleProvider = 'wikipedia',
        enrichmentSummarySource = 'wikipedia',
        enrichmentTaxonomySource = 'inaturalist',
        enrichmentSightingsSource = 'disabled',
        enrichmentSeasonalitySource = 'disabled',
        enrichmentRaritySource = 'disabled',
        enrichmentLinksSources = ['wikipedia', 'inaturalist'],
    }: {
        enrichmentMode: 'single' | 'per_enrichment';
        enrichmentSingleProvider: string;
        enrichmentSummarySource: string;
        enrichmentTaxonomySource: string;
        enrichmentSightingsSource: string;
        enrichmentSeasonalitySource: string;
        enrichmentRaritySource: string;
        enrichmentLinksSources: string[];
    } = $props();

    const formatProvider = (value: string) => {
        const normalized = (value || '').toLowerCase();
        if (normalized === 'disabled') return $_('settings.enrichment.disabled');
        if (normalized === 'ebird') return 'eBird';
        if (normalized === 'inaturalist') return 'iNaturalist';
        if (normalized === 'wikipedia') return 'Wikipedia';
        return value;
    };

    const tiles: { titleKey: string; value: string }[] = $derived([
        { titleKey: 'settings.enrichment.summary_title', value: enrichmentSummarySource },
        { titleKey: 'settings.enrichment.taxonomy_title', value: enrichmentTaxonomySource },
        { titleKey: 'settings.enrichment.sightings_title', value: enrichmentSightingsSource },
        { titleKey: 'settings.enrichment.seasonality_title', value: enrichmentSeasonalitySource },
        { titleKey: 'settings.enrichment.rarity_title', value: enrichmentRaritySource }
    ]);
</script>

{#snippet enrichmentIcon()}
    <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 1.4 4.1 4.1 1.4-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3Zm6.5 11 .7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7.7-2.1Z" /></svg>
{/snippet}

<SettingsCard
    accent
    iconSnippet={enrichmentIcon}
    title={$_('settings.enrichment.title')}
    description={$_('settings.enrichment.desc')}
>
    <div class="divide-y divide-slate-200/70 dark:divide-slate-700/60">
        {#each tiles as tile}
            <div class="flex items-center justify-between gap-4 py-3 first:pt-0">
                <p class="text-xs font-bold text-slate-600 dark:text-slate-400">
                    {$_(tile.titleKey)}
                </p>
                <p class="text-sm font-black text-slate-900 dark:text-white">{formatProvider(tile.value)}</p>
            </div>
        {/each}
        <div class="flex items-center justify-between gap-4 py-3">
            <p class="text-xs font-bold text-slate-600 dark:text-slate-400">
                {$_('settings.enrichment.links_title')}
            </p>
            <div class="flex flex-wrap justify-end gap-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
                {#each enrichmentLinksSources as source}
                    <span class="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 dark:border-slate-700 dark:bg-slate-800">
                        {formatProvider(source)}
                    </span>
                {/each}
            </div>
        </div>
    </div>

    <div class="border-t border-slate-200/70 pt-4 text-sm text-slate-600 dark:border-slate-700/60 dark:text-slate-300">
        {#if enrichmentMode === 'single'}
            <strong class="text-slate-700 dark:text-slate-100">{$_('settings.enrichment.mode_single')}:</strong>
            <span class="ml-2">{formatProvider(enrichmentSingleProvider)}</span>
        {:else}
            <strong class="text-slate-700 dark:text-slate-100">{$_('settings.enrichment.mode_per')}:</strong>
            <span class="ml-2">{$_('settings.enrichment.desc')}</span>
        {/if}
    </div>
</SettingsCard>

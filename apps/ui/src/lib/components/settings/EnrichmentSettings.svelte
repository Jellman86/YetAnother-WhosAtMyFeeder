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

<SettingsCard
    icon="✨"
    title={$_('settings.enrichment.title')}
    description={$_('settings.enrichment.desc')}
>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        {#each tiles as tile}
            <div class="rounded-2xl border border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-900/50 p-4">
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                    {$_(tile.titleKey)}
                </p>
                <p class="text-sm font-bold text-slate-900 dark:text-white mt-2">{formatProvider(tile.value)}</p>
            </div>
        {/each}
        <div class="rounded-2xl border border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-900/50 p-4">
            <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                {$_('settings.enrichment.links_title')}
            </p>
            <div class="mt-2 flex flex-wrap gap-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
                {#each enrichmentLinksSources as source}
                    <span class="px-2 py-1 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                        {formatProvider(source)}
                    </span>
                {/each}
            </div>
        </div>
    </div>

    <div class="rounded-2xl border border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-900/50 p-4 text-xs text-slate-600 dark:text-slate-300">
        {#if enrichmentMode === 'single'}
            <strong class="text-slate-700 dark:text-slate-100">{$_('settings.enrichment.mode_single')}:</strong>
            <span class="ml-2">{formatProvider(enrichmentSingleProvider)}</span>
        {:else}
            <strong class="text-slate-700 dark:text-slate-100">{$_('settings.enrichment.mode_per')}:</strong>
            <span class="ml-2">{$_('settings.enrichment.desc')}</span>
        {/if}
    </div>
</SettingsCard>

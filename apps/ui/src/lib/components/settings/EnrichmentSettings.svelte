<script lang="ts">
    import { _ } from 'svelte-i18n';

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
</script>

<div class="space-y-6">
    <!-- Enrichment Sources -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.enrichment.title')}</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{$_('settings.enrichment.desc')}</p>
            </div>
        </div>

        <div class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-4">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.enrichment.summary_title')}</p>
                    <p class="text-sm font-bold text-slate-900 dark:text-white mt-2">{formatProvider(enrichmentSummarySource)}</p>
                </div>
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-4">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.enrichment.taxonomy_title')}</p>
                    <p class="text-sm font-bold text-slate-900 dark:text-white mt-2">{formatProvider(enrichmentTaxonomySource)}</p>
                </div>
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-4">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.enrichment.sightings_title')}</p>
                    <p class="text-sm font-bold text-slate-900 dark:text-white mt-2">{formatProvider(enrichmentSightingsSource)}</p>
                </div>
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-4">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.enrichment.seasonality_title')}</p>
                    <p class="text-sm font-bold text-slate-900 dark:text-white mt-2">{formatProvider(enrichmentSeasonalitySource)}</p>
                </div>
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-4">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.enrichment.rarity_title')}</p>
                    <p class="text-sm font-bold text-slate-900 dark:text-white mt-2">{formatProvider(enrichmentRaritySource)}</p>
                </div>
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-4">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.enrichment.links_title')}</p>
                    <div class="mt-2 flex flex-wrap gap-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
                        {#each enrichmentLinksSources as source}
                            <span class="px-2 py-1 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                                {formatProvider(source)}
                            </span>
                        {/each}
                    </div>
                </div>
            </div>

            <div class="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-900/40 p-4 text-xs text-slate-600 dark:text-slate-300">
                {#if enrichmentMode === 'single'}
                    <strong class="text-slate-700 dark:text-slate-100">{$_('settings.enrichment.mode_single')}:</strong>
                    <span class="ml-2">{formatProvider(enrichmentSingleProvider)}</span>
                {:else}
                    <strong class="text-slate-700 dark:text-slate-100">{$_('settings.enrichment.mode_per')}:</strong>
                    <span class="ml-2">{$_('settings.enrichment.desc')}</span>
                {/if}
            </div>
        </div>
    </section>
</div>

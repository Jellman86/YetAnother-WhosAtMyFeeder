<script lang="ts">
    import { _ } from 'svelte-i18n';

    let {
        enrichmentMode = $bindable<'single' | 'per_enrichment'>('per_enrichment'),
        enrichmentSingleProvider = $bindable('wikipedia'),
        enrichmentSummarySource = $bindable('wikipedia'),
        enrichmentTaxonomySource = $bindable('inaturalist'),
        enrichmentSightingsSource = $bindable('disabled'),
        enrichmentSeasonalitySource = $bindable('disabled'),
        enrichmentRaritySource = $bindable('disabled'),
        enrichmentLinksSources = $bindable<string[]>(['wikipedia', 'inaturalist']),
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
</script>

<div class="space-y-6">
    <!-- Enrichment Sources -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Enrichment Sources</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">Choose where each enrichment comes from</p>
            </div>
        </div>

        <div class="space-y-6">
            <div class="grid grid-cols-2 gap-3">
                <button
                    onclick={() => enrichmentMode = 'single'}
                    class="p-4 rounded-2xl border-2 transition-all text-center {enrichmentMode === 'single' ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                >
                    <p class="text-xs font-black uppercase tracking-widest">Single Provider</p>
                </button>
                <button
                    onclick={() => enrichmentMode = 'per_enrichment'}
                    class="p-4 rounded-2xl border-2 transition-all text-center {enrichmentMode === 'per_enrichment' ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                >
                    <p class="text-xs font-black uppercase tracking-widest">Per Enrichment</p>
                </button>
            </div>

            {#if enrichmentMode === 'single'}
                <div>
                    <label for="enrich-single" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Provider</label>
                    <select
                        id="enrich-single"
                        bind:value={enrichmentSingleProvider}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    >
                        <option value="wikipedia">Wikipedia</option>
                        <option value="inaturalist">iNaturalist</option>
                        <option value="ebird">eBird</option>
                    </select>
                    <p class="text-xs text-slate-500 mt-2">Fallbacks apply when a provider cannot supply a field.</p>
                </div>
            {:else}
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label for="enrich-summary" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Summary & Description</label>
                        <select
                            id="enrich-summary"
                            bind:value={enrichmentSummarySource}
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        >
                            <option value="wikipedia">Wikipedia</option>
                            <option value="inaturalist">iNaturalist</option>
                        </select>
                    </div>
                    <div>
                        <label for="enrich-taxonomy" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Taxonomy & Common Names</label>
                        <select
                            id="enrich-taxonomy"
                            bind:value={enrichmentTaxonomySource}
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        >
                            <option value="inaturalist">iNaturalist</option>
                            <option value="wikipedia">Wikipedia</option>
                        </select>
                    </div>
                    <div>
                        <label for="enrich-sightings" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Nearby Sightings</label>
                        <select
                            id="enrich-sightings"
                            bind:value={enrichmentSightingsSource}
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        >
                            <option value="disabled">Disabled</option>
                            <option value="ebird">eBird</option>
                        </select>
                    </div>
                    <div>
                        <label for="enrich-seasonality" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Seasonality</label>
                        <select
                            id="enrich-seasonality"
                            bind:value={enrichmentSeasonalitySource}
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        >
                            <option value="disabled">Disabled</option>
                            <option value="ebird">eBird</option>
                        </select>
                    </div>
                    <div>
                        <label for="enrich-rarity" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Rarity Indicators</label>
                        <select
                            id="enrich-rarity"
                            bind:value={enrichmentRaritySource}
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        >
                            <option value="disabled">Disabled</option>
                            <option value="ebird">eBird</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">External Links</label>
                        <div class="grid grid-cols-2 gap-2">
                            <button
                                onclick={() => enrichmentLinksSources = enrichmentLinksSources.includes('wikipedia') ? enrichmentLinksSources.filter(s => s !== 'wikipedia') : [...enrichmentLinksSources, 'wikipedia']}
                                class="p-3 rounded-xl border-2 transition-all text-center {enrichmentLinksSources.includes('wikipedia') ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                            >
                                <p class="text-[10px] font-black uppercase tracking-widest">Wikipedia</p>
                            </button>
                            <button
                                onclick={() => enrichmentLinksSources = enrichmentLinksSources.includes('inaturalist') ? enrichmentLinksSources.filter(s => s !== 'inaturalist') : [...enrichmentLinksSources, 'inaturalist']}
                                class="p-3 rounded-xl border-2 transition-all text-center {enrichmentLinksSources.includes('inaturalist') ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                            >
                                <p class="text-[10px] font-black uppercase tracking-widest">iNaturalist</p>
                            </button>
                        </div>
                    </div>
                </div>
            {/if}
        </div>
    </section>
</div>

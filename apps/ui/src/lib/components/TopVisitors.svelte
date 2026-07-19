<script lang="ts">
    import { _, locale } from 'svelte-i18n';
    import {
        fetchSpeciesInfo,
        type DailySpeciesSummary,
        type SpeciesInfo
    } from '../api';
    import { getBirdNames } from '../naming';
    import { authStore } from '../stores/auth.svelte';
    import { settingsStore } from '../stores/settings.svelte';

    interface Props {
        species: DailySpeciesSummary[];
        onSpeciesClick?: (speciesFilter: string) => void;
    }

    let { species, onSpeciesClick }: Props = $props();

    let speciesInfoCache = $state<Record<string, SpeciesInfo>>({});
    let speciesInfoPending = $state<Record<string, boolean>>({});
    const speciesInfoLocale = $derived((($locale || 'en') as string).split(/[-_]/)[0].toLowerCase());

    function speciesInfoKey(name: string): string {
        return `${speciesInfoLocale}:${name}`;
    }

    function cachedSpeciesThumb(name?: string | null): string | null {
        if (!name) return null;
        return speciesInfoCache[speciesInfoKey(name)]?.thumbnail_url ?? null;
    }

    async function loadSpeciesInfo(name: string) {
        const key = speciesInfoKey(name);
        if (!name || name === 'Unknown Bird' || speciesInfoCache[key] || speciesInfoPending[key]) {
            return;
        }
        speciesInfoPending = { ...speciesInfoPending, [key]: true };
        try {
            const info = await fetchSpeciesInfo(name);
            speciesInfoCache = { ...speciesInfoCache, [key]: info };
        } catch {
            // Species enrichment is optional; use the neutral bird mark when unavailable.
        } finally {
            const { [key]: _discarded, ...rest } = speciesInfoPending;
            speciesInfoPending = rest;
        }
    }

    let processedSpecies = $derived.by(() => {
        if (!species) return [];
        const showCommon = settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true;
        const preferSci = settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false;

        return species.slice(0, 5).map((item) => {
            const naming = getBirdNames(item, showCommon, preferSci);
            return {
                ...item,
                displayName: naming.primary,
                subName: naming.secondary
            };
        });
    });

    $effect(() => {
        for (const item of processedSpecies) {
            void loadSpeciesInfo(item.species);
        }
    });
</script>

<section class="space-y-4">
    <header class="flex flex-wrap items-end justify-between gap-3">
        <div>
            <h2 class="font-display text-xl font-bold text-slate-950 dark:text-white">{$_('dashboard.top_visitors_title')}</h2>
            <p class="text-sm text-slate-500 dark:text-slate-400">{$_('dashboard.histogram.last_24h')}</p>
        </div>
    </header>

    {#if processedSpecies.length > 0}
        <ol class="grid divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-700 dark:border-slate-700 sm:grid-cols-2 sm:divide-y-0 xl:grid-cols-5 xl:divide-x">
            {#each processedSpecies as item, index (item.species)}
                <li class="min-w-0 {index >= 2 ? 'sm:border-t sm:border-slate-200 sm:dark:border-slate-700 xl:border-t-0' : ''} {index % 2 === 1 ? 'sm:border-l sm:border-slate-200 sm:dark:border-slate-700' : ''} {index > 0 ? 'xl:border-l xl:border-slate-200 xl:dark:border-slate-700' : ''}">
                    <button
                        type="button"
                        onclick={() => onSpeciesClick?.(item.taxa_id ? `taxa:${item.taxa_id}` : item.species)}
                        class="group flex min-h-24 w-full items-center gap-3 px-3 py-4 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:hover:bg-slate-800/35 xl:px-4"
                        aria-label={`${item.displayName}, ${$_('dashboard.top_visitors_count', { values: { count: item.count } })}`}
                    >
                        <span class="relative shrink-0">
                            <span
                                data-dashboard-species-portrait
                                class="flex h-14 w-14 items-center justify-center overflow-hidden rounded-full border-2 border-white bg-slate-100 text-slate-400 shadow-sm ring-1 ring-brand-200 dark:border-slate-800 dark:bg-slate-800 dark:ring-brand-800"
                            >
                                {#if cachedSpeciesThumb(item.species)}
                                    <img src={cachedSpeciesThumb(item.species) ?? undefined} alt="" class="h-full w-full object-cover" loading="lazy" />
                                {:else}
                                    <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" /></svg>
                                {/if}
                            </span>
                            <span class="absolute -left-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full border-2 border-white bg-brand-600 px-1 text-xs font-bold tabular-nums text-white shadow-sm dark:border-slate-900 dark:bg-brand-500 dark:text-slate-950" aria-hidden="true">{index + 1}</span>
                        </span>
                        <span class="min-w-0 flex-1">
                            <span class="block text-sm font-semibold leading-tight text-slate-900 transition-colors group-hover:text-brand-700 dark:text-white dark:group-hover:text-brand-300" title={item.displayName}>{item.displayName}</span>
                            {#if item.subName}
                                <span class="mt-0.5 block truncate text-xs italic text-slate-500 dark:text-slate-400" title={item.subName}>{item.subName}</span>
                            {/if}
                            <span class="mt-1 block text-xs font-semibold text-brand-700 dark:text-brand-300">{$_('dashboard.top_visitors_count', { values: { count: item.count } })}</span>
                        </span>
                    </button>
                </li>
            {/each}
        </ol>
    {:else}
        <div class="border-y border-dashed border-slate-200 py-10 text-center dark:border-slate-700">
            <p class="text-sm text-slate-500 dark:text-slate-400">{$_('dashboard.top_visitors_empty')}</p>
        </div>
    {/if}
</section>

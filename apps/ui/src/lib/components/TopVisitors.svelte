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

        // The API once returned the same species twice when catalogue identity
        // was patchy across its rows, and a duplicate key here took the whole
        // lower dashboard down. Merge duplicates instead of trusting the list.
        const merged = new Map<string, (typeof species)[number]>();
        for (const item of species) {
            const key = (item.species ?? '').trim().toLowerCase();
            const existing = merged.get(key);
            if (existing) {
                merged.set(key, {
                    ...existing,
                    count: existing.count + item.count,
                    visit_count: (existing.visit_count ?? 0) + (item.visit_count ?? 0)
                });
            } else {
                merged.set(key, item);
            }
        }

        return [...merged.values()]
            .sort((left, right) => (right.visit_count ?? 0) - (left.visit_count ?? 0) || right.count - left.count)
            .slice(0, 5)
            .map((item) => {
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

<section class="panel space-y-4" aria-labelledby="dashboard-visitors-title">
    <div>
        <h2 id="dashboard-visitors-title" class="flex items-center gap-2 font-display text-xl font-bold text-slate-950 dark:text-white">
            <svg class="h-5 w-5 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" /></svg>
            {$_('dashboard.top_visitors_title')}
        </h2>
        <p class="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{$_('dashboard.day_bar.window', { default: 'Last 24 hours' })}</p>
    </div>

    {#if processedSpecies.length > 0}
        <ol class="divide-y divide-slate-200/70 dark:divide-slate-700/50">
            {#each processedSpecies as item, index (item.species)}
                <li>
                    <button
                        type="button"
                        onclick={() => onSpeciesClick?.(item.taxa_id ? `taxa:${item.taxa_id}` : item.species)}
                        class="group flex min-h-12 w-full items-center gap-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
                        aria-label={`${item.displayName}, ${$_('dashboard.top_visitors_count', { values: { count: item.visit_count ?? item.count } })}`}
                    >
                        <span class="w-4 shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400" aria-hidden="true">{index + 1}</span>
                        <span
                            data-dashboard-species-portrait
                            class="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800"
                        >
                            {#if cachedSpeciesThumb(item.species)}
                                <img src={cachedSpeciesThumb(item.species) ?? undefined} alt="" class="h-full w-full object-cover" loading="lazy" />
                            {:else}
                                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" /></svg>
                            {/if}
                        </span>
                        <span class="min-w-0 flex-1">
                            <span class="block truncate text-sm font-semibold text-slate-900 transition-colors group-hover:text-brand-700 dark:text-white dark:group-hover:text-brand-300">{item.displayName}</span>
                            {#if item.subName}
                                <span class="block truncate text-xs italic text-slate-500 dark:text-slate-400">{item.subName}</span>
                            {/if}
                        </span>
                        <span class="shrink-0 text-sm tabular-nums text-slate-700 dark:text-slate-200">{$_('dashboard.top_visitors_count', { values: { count: item.visit_count ?? item.count } })}</span>
                    </button>
                </li>
            {/each}
        </ol>
    {:else}
        <p class="text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.top_visitors_empty_window', { default: 'No visits in the last 24 hours.' })}</p>
    {/if}
</section>

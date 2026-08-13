<script lang="ts">
    import type { EventFilterSpecies, EventFilters } from '../api';
    import { _ } from 'svelte-i18n';

    type DatePreset = 'all' | 'today' | 'week' | 'month' | 'custom';

    interface Props {
        species: EventFilterSpecies[];
        cameras: string[];
        filters: EventFilters | null;
        datePreset: DatePreset;
        speciesFilter: string;
        cameraFilter: string;
        favoritesOnly: boolean;
        audioConfirmedOnly: boolean;
        /** Owner-only: hidden detections are soft-deleted, not gone. */
        showHidden: boolean;
        hiddenCount: number;
        canSeeHidden: boolean;
        customStartDate: string;
        customEndDate: string;
        refreshing?: boolean;
        resultCount: number;
        onchange: (next: {
            datePreset?: DatePreset;
            speciesFilter?: string;
            cameraFilter?: string;
            favoritesOnly?: boolean;
            audioConfirmedOnly?: boolean;
            showHidden?: boolean;
            customStartDate?: string;
            customEndDate?: string;
        }) => void;
        onclear: () => void;
        onrefresh: () => void;
    }

    let {
        species,
        cameras,
        filters,
        datePreset,
        speciesFilter,
        cameraFilter,
        favoritesOnly,
        audioConfirmedOnly,
        showHidden,
        hiddenCount,
        canSeeHidden,
        customStartDate,
        customEndDate,
        refreshing = false,
        resultCount,
        onchange,
        onclear,
        onrefresh
    }: Props = $props();

    let panelOpen = $state(false);
    let search = $state('');

    const totals = $derived(filters?.totals ?? null);
    const cameraCounts = $derived(filters?.camera_counts ?? {});

    const datePresets: DatePreset[] = ['all', 'today', 'week', 'month', 'custom'];

    const speciesLabel = $derived(
        species.find((item) => item.value === speciesFilter)?.display_name ?? speciesFilter
    );

    // Every applied filter is a token: visible, and removable where it stands.
    const tokens = $derived.by(() => {
        const applied: { key: string; label: string; clear: () => void }[] = [];
        if (datePreset !== 'all') {
            applied.push({
                key: 'date',
                label: $_(`events.filters.${datePreset === 'today' ? 'today' : datePreset}`, {
                    default: datePreset
                }),
                clear: () => onchange({ datePreset: 'all' })
            });
        }
        if (speciesFilter) {
            applied.push({
                key: 'species',
                label: speciesLabel,
                clear: () => onchange({ speciesFilter: '' })
            });
        }
        if (cameraFilter) {
            applied.push({
                key: 'camera',
                label: cameraFilter,
                clear: () => onchange({ cameraFilter: '' })
            });
        }
        if (favoritesOnly) {
            applied.push({
                key: 'favorites',
                label: $_('events.filters.favorites', { default: 'Favourites' }),
                clear: () => onchange({ favoritesOnly: false })
            });
        }
        if (audioConfirmedOnly) {
            applied.push({
                key: 'audio',
                label: $_('events.filters.audio_matches', { default: 'Audio matches' }),
                clear: () => onchange({ audioConfirmedOnly: false })
            });
        }
        if (showHidden) {
            applied.push({
                key: 'hidden',
                label: $_('events.filters.hidden', { default: 'Hidden' }),
                clear: () => onchange({ showHidden: false })
            });
        }
        return applied;
    });

    const visibleSpecies = $derived.by(() => {
        const term = search.trim().toLowerCase();
        const matched = term
            ? species.filter((item) =>
                  [item.display_name, item.common_name, item.scientific_name]
                      .filter(Boolean)
                      .some((name) => String(name).toLowerCase().includes(term))
              )
            : species;
        // Counts are absent on older backends, where sorting by them would leave an
        // arbitrary order, so fall back to alphabetical.
        return [...matched]
            .sort(
                (left, right) =>
                    (right.count ?? 0) - (left.count ?? 0) ||
                    left.display_name.localeCompare(right.display_name)
            )
            .slice(0, 12);
    });
</script>

<section class="border-y border-slate-200 py-3 lg:border-0 lg:py-0" data-events-filter-bar>
    <div class="flex flex-wrap items-center gap-2">
        <p class="text-sm font-semibold text-slate-900 dark:text-white">
            {$_('events.filters.result_count', {
                values: { count: resultCount.toLocaleString() },
                default: '{count} visits'
            })}
        </p>

        {#each tokens as token (token.key)}
            <button
                class="inline-flex min-h-11 items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-800 transition-colors hover:bg-brand-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:bg-brand-950/40 dark:text-brand-200 dark:hover:bg-brand-950/70"
                onclick={token.clear}
                data-explorer-token
            >
                {token.label}
                <span aria-hidden="true">&times;</span>
                <span class="sr-only">{$_('common.clear', { default: 'Clear' })}</span>
            </button>
        {/each}

        <button
            class="btn btn-secondary ml-auto min-h-11 px-3 py-2 text-xs lg:hidden"
            aria-expanded={panelOpen}
            onclick={() => (panelOpen = !panelOpen)}
            data-explorer-filter-toggle
        >
            {$_('events.filters.title', { default: 'Filters' })}
        </button>

        {#if tokens.length > 0}
            <button class="btn btn-ghost min-h-11 px-3 py-2 text-xs" onclick={onclear}>
                {$_('events.filters.clear_all', { default: 'Clear all' })}
            </button>
        {/if}
    </div>

    <div
        class="mt-3 gap-5 border-t border-slate-200 pt-3 lg:!block dark:border-slate-700 {panelOpen
            ? 'grid grid-cols-1 sm:grid-cols-3'
            : 'hidden'} lg:mt-0 lg:space-y-5 lg:border-t-0 lg:pt-0"
        data-explorer-facets
    >
            <div>
                <p class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('events.filters.when', { default: 'When' })}
                </p>
                <div class="mt-2 flex flex-wrap gap-1.5">
                    {#each datePresets as preset}
                        <button
                            class="min-h-11 rounded-full border px-3 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {datePreset ===
                            preset
                                ? 'border-brand-400 bg-brand-50 text-brand-800 dark:border-brand-600 dark:bg-brand-950/40 dark:text-brand-200'
                                : 'border-slate-200 text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:text-slate-300'}"
                            aria-pressed={datePreset === preset}
                            onclick={() => onchange({ datePreset: preset })}
                        >
                            {$_(`events.filters.${preset === 'all' ? 'all_time' : preset}`, { default: preset })}
                        </button>
                    {/each}
                </div>

                {#if datePreset === 'custom'}
                    <div class="mt-2 grid grid-cols-2 gap-2">
                        <label class="block">
                            <span class="sr-only">{$_('events.filters.start_date', { default: 'Start date' })}</span>
                            <input
                                class="input-base text-xs"
                                type="date"
                                value={customStartDate}
                                onchange={(event) =>
                                    onchange({ customStartDate: (event.currentTarget as HTMLInputElement).value })}
                            />
                        </label>
                        <label class="block">
                            <span class="sr-only">{$_('events.filters.end_date', { default: 'End date' })}</span>
                            <input
                                class="input-base text-xs"
                                type="date"
                                value={customEndDate}
                                onchange={(event) =>
                                    onchange({ customEndDate: (event.currentTarget as HTMLInputElement).value })}
                            />
                        </label>
                    </div>
                {/if}

                <p class="mt-4 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('events.filters.only', { default: 'Only' })}
                </p>
                <div class="mt-2 space-y-1">
                    <button
                        class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 text-xs transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800/60 {favoritesOnly
                            ? 'font-semibold text-brand-800 dark:text-brand-200'
                            : 'text-slate-700 dark:text-slate-300'}"
                        aria-pressed={favoritesOnly}
                        onclick={() => onchange({ favoritesOnly: !favoritesOnly })}
                    >
                        <span>{$_('events.filters.favorites', { default: 'Favourites' })}</span>
                        <span class="tabular-nums text-slate-500 dark:text-slate-400">{totals?.favorites ?? 0}</span>
                    </button>
                    <button
                        class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 text-xs transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800/60 {audioConfirmedOnly
                            ? 'font-semibold text-brand-800 dark:text-brand-200'
                            : 'text-slate-700 dark:text-slate-300'}"
                        aria-pressed={audioConfirmedOnly}
                        onclick={() => onchange({ audioConfirmedOnly: !audioConfirmedOnly })}
                    >
                        <span>{$_('events.filters.audio_matches', { default: 'Audio matches' })}</span>
                        <span class="tabular-nums text-slate-500 dark:text-slate-400">{totals?.audio_matched ?? 0}</span>
                    </button>

                    {#if canSeeHidden && (hiddenCount > 0 || showHidden)}
                        <button
                            class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 text-xs transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800/60 {showHidden
                                ? 'font-semibold text-brand-800 dark:text-brand-200'
                                : 'text-slate-700 dark:text-slate-300'}"
                            aria-pressed={showHidden}
                            onclick={() => onchange({ showHidden: !showHidden })}
                            data-explorer-hidden-facet
                        >
                            <span>{$_('events.filters.hidden', { default: 'Hidden' })}</span>
                            <span class="tabular-nums text-slate-500 dark:text-slate-400">{hiddenCount}</span>
                        </button>
                    {/if}

                    <button
                        class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 text-xs text-slate-700 transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800/60"
                        disabled={refreshing}
                        onclick={onrefresh}
                    >
                        <span>
                            {refreshing
                                ? $_('events.filters.refreshing_options', { default: 'Refreshing options' })
                                : $_('events.filters.refresh_options', { default: 'Refresh options' })}
                        </span>
                    </button>
                </div>
            </div>

            <div>
                <p class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('events.filters.all_species')}
                </p>
                <label class="mt-2 block">
                    <span class="sr-only">{$_('events.filters.search_species', { default: 'Search species' })}</span>
                    <input class="input-base text-xs" type="search" bind:value={search} placeholder={$_('events.filters.search_species', { default: 'Search species' })} />
                </label>
                <div class="mt-2 max-h-56 space-y-0.5 overflow-y-auto">
                    {#each visibleSpecies as item (item.value)}
                        <button
                            class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 text-left text-xs transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800/60 {speciesFilter ===
                            item.value
                                ? 'font-semibold text-brand-800 dark:text-brand-200'
                                : 'text-slate-700 dark:text-slate-300'}"
                            aria-pressed={speciesFilter === item.value}
                            onclick={() =>
                                onchange({ speciesFilter: speciesFilter === item.value ? '' : item.value })}
                        >
                            <span class="truncate">{item.display_name}</span>
                            <span class="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">{item.count ?? 0}</span>
                        </button>
                    {:else}
                        <p class="px-2 py-2 text-xs text-slate-500 dark:text-slate-400">
                            {$_('events.filters.no_species_match', { default: 'No species matches that.' })}
                        </p>
                    {/each}
                </div>
            </div>

            <div>
                <p class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('events.filters.all_cameras')}
                </p>
                <div class="mt-2 space-y-0.5">
                    {#each cameras as camera (camera)}
                        <button
                            class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 text-left text-xs transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800/60 {cameraFilter ===
                            camera
                                ? 'font-semibold text-brand-800 dark:text-brand-200'
                                : 'text-slate-700 dark:text-slate-300'}"
                            aria-pressed={cameraFilter === camera}
                            onclick={() => onchange({ cameraFilter: cameraFilter === camera ? '' : camera })}
                        >
                            <span class="truncate">{camera}</span>
                            <span class="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">
                                {cameraCounts[camera] ?? 0}
                            </span>
                        </button>
                    {/each}
                </div>
            </div>
    </div>
</section>

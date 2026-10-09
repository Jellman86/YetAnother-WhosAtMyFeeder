<script lang="ts">
    import type { EventFilterSpecies, EventFilters } from '../api';
    import { _ } from 'svelte-i18n';
    import { filterExplorerSpecies } from '../utils/explorer-species';

    type DatePreset = 'all' | 'today' | 'week' | 'month' | 'custom';

    interface Props {
        species: EventFilterSpecies[];
        cameras: string[];
        filters: EventFilters | null;
        /** Desktop only: the rail folds away and gives its width to the results. */
        collapsed?: boolean;
        oncollapsechange?: (collapsed: boolean) => void;
        datePreset: DatePreset;
        speciesFilter: string;
        cameraFilter: string;
        favoritesOnly: boolean;
        audioConfirmedOnly: boolean;
        multipleSpeciesOnly?: boolean;
        /** How results are shown: a species' visits, or every capture on its own. */
        groupVisits?: boolean;
        /** Selecting works on captures, so the choice is held while selecting. */
        groupingLocked?: boolean;
        /** Owner-only: hidden detections are soft-deleted, not gone. */
        showHidden: boolean;
        hiddenCount: number;
        canSeeHidden: boolean;
        customStartDate: string;
        customEndDate: string;
        refreshing?: boolean;
        onchange: (next: {
            datePreset?: DatePreset;
            speciesFilter?: string;
            cameraFilter?: string;
            favoritesOnly?: boolean;
            audioConfirmedOnly?: boolean;
            multipleSpeciesOnly?: boolean;
            groupVisits?: boolean;
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
        collapsed = false,
        oncollapsechange,
        datePreset,
        speciesFilter,
        cameraFilter,
        favoritesOnly,
        audioConfirmedOnly,
        multipleSpeciesOnly = false,
        groupVisits = true,
        groupingLocked = false,
        showHidden,
        hiddenCount,
        canSeeHidden,
        customStartDate,
        customEndDate,
        refreshing = false,
        onchange,
        onclear,
        onrefresh
    }: Props = $props();

    let panelOpen = $state(false);

    // Collapsing arrives from the header toolbar. The collapsed desktop shares
    // the phone's Filters button, so the moment the rail folds away the facets
    // close with it - leaving them open would show the facets under a control
    // reading "Show filters". Tracking the previous value keeps the valid
    // collapsed-with-panel-open state, which is what the Filters button opens.
    let previousCollapsed: boolean | null = null;
    $effect(() => {
        const current = collapsed;
        if (previousCollapsed !== null && current && current !== previousCollapsed) {
            panelOpen = false;
        }
        previousCollapsed = current;
    });
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
        if (multipleSpeciesOnly) applied.push({ key: 'multiple-species', label: $_('visits.multiple_species', { default: 'Multiple bird species' }), clear: () => onchange({ multipleSpeciesOnly: false }) });
        if (showHidden) {
            applied.push({
                key: 'hidden',
                label: $_('events.filters.hidden', { default: 'Hidden' }),
                clear: () => onchange({ showHidden: false })
            });
        }
        return applied;
    });

    const visibleSpecies = $derived(filterExplorerSpecies(species, search));
</script>

<section
    class="pb-4 pt-1 {collapsed
        ? ''
        : 'lg:flex lg:h-[calc(100dvh-2rem)] lg:max-h-[calc(100dvh-2rem)] lg:flex-col lg:rounded-2xl lg:border lg:border-slate-200 lg:bg-white/80 lg:p-3 lg:dark:border-slate-800 lg:dark:bg-slate-900/50'}"
    data-events-filter-bar
>
    <div class="flex shrink-0 flex-wrap items-center gap-2">
        <!-- The toolbar above the list already counts the results; the rail names itself. -->
        <h2 class="hidden text-sm font-semibold text-slate-900 dark:text-white {collapsed ? '' : 'lg:block lg:flex-1'}">
            {$_('events.filters.title', { default: 'Filters' })}
        </h2>

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
            class="btn min-h-11 px-3 py-2 text-xs {panelOpen
                ? 'border border-brand-300 bg-brand-100 text-brand-700 dark:border-brand-400/60 dark:bg-brand-500/20 dark:text-brand-100'
                : 'btn-secondary'} {collapsed ? '' : 'lg:hidden'}"
            aria-expanded={panelOpen}
            aria-controls="explorer-facets"
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
        id="explorer-facets"
        class="mt-3 gap-3 border-t border-slate-200 pt-3 dark:border-slate-700 {panelOpen
            ? 'flex flex-col'
            : 'hidden'} {collapsed
            ? ''
            : 'lg:!flex lg:mt-2 lg:min-h-0 lg:flex-1 lg:flex-col lg:gap-3 lg:overflow-y-auto lg:overscroll-contain lg:border-t-0 lg:pt-0'}"
        data-explorer-facets
    >
            <!-- How results are shown, not what they are: Clear all leaves it as it is. -->
            <div class="min-w-0 shrink-0" role="group" aria-labelledby="explorer-show-heading" data-explorer-show-facet>
                <p id="explorer-show-heading" class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('events.filters.show', { default: 'Show' })}
                </p>
                <div class="mt-2 space-y-0.5">
                    {#each [
                        { grouped: true, label: $_('events.filters.show_visits', { default: 'Visits of one species' }), hint: $_('events.filters.show_visits_hint', { default: "One bird's stay: its captures less than a minute apart." }) },
                        { grouped: false, label: $_('events.filters.show_captures', { default: 'Individual captures' }), hint: $_('events.filters.show_captures_hint', { default: 'Every capture on its own.' }) }
                    ] as option (option.grouped)}
                        {@const chosen = groupVisits === option.grouped && !groupingLocked}
                        <button
                            type="button"
                            class="flex min-h-11 w-full flex-col items-start justify-center rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60 dark:hover:bg-slate-800/60 {chosen
                                ? 'bg-brand-50 dark:bg-brand-950/40'
                                : ''}"
                            aria-pressed={chosen}
                            disabled={groupingLocked}
                            onclick={() => onchange({ groupVisits: option.grouped })}
                            data-explorer-show={option.grouped ? 'visits' : 'captures'}
                        >
                            <span class="text-xs {chosen ? 'font-semibold text-brand-800 dark:text-brand-200' : 'text-slate-700 dark:text-slate-300'}">{option.label}</span>
                            <span class="text-2xs leading-4 text-slate-500 dark:text-slate-400">{option.hint}</span>
                        </button>
                    {/each}
                </div>
                {#if groupingLocked}
                    <p class="mt-1 px-2 text-2xs text-slate-500 dark:text-slate-400">{$_('events.filters.show_locked', { default: 'Selecting works on individual captures.' })}</p>
                {/if}
            </div>

            <div class="min-w-0 shrink-0" data-explorer-species-facet>
                <p class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('events.filters.all_species')}
                </p>
                <label class="mt-2 block">
                    <span class="sr-only">{$_('events.filters.search_species', { default: 'Search species' })}</span>
                    <input class="input-base text-xs" type="search" bind:value={search} placeholder={$_('events.filters.search_species', { default: 'Search species' })} />
                </label>
                <div
                    class="mt-2 max-h-64 space-y-0.5 overflow-y-auto"
                    data-explorer-species-list
                >
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
                            <span class="min-w-0 py-1.5 leading-4 [overflow-wrap:anywhere]">{item.display_name}</span>
                            <span class="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">{item.count ?? 0}</span>
                        </button>
                    {:else}
                        <p class="px-2 py-2 text-xs text-slate-500 dark:text-slate-400">
                            {$_('events.filters.no_species_match', { default: 'No species matches that.' })}
                        </p>
                    {/each}
                </div>
            </div>

            <details class="group shrink-0 border-t border-slate-200/70 pt-1 dark:border-slate-800" data-explorer-date-facet>
                <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-lg text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200 [&::-webkit-details-marker]:hidden">
                    <span>{$_('events.filters.when', { default: 'When' })}</span>
                    <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                </summary>
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

            </details>

            <details class="group shrink-0 border-t border-slate-200/70 pt-1 dark:border-slate-800" data-explorer-only-facet>
                <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-lg text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200 [&::-webkit-details-marker]:hidden">
                    <span>{$_('events.filters.only', { default: 'Only' })}</span>
                    <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                </summary>
                <div class="mt-2 space-y-1">
                    {#if canSeeHidden}
                        <!-- The same row as the facets beneath it; it has no count, so its state is a check. -->
                        <button
                            class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 text-xs transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800/60 {multipleSpeciesOnly
                                ? 'font-semibold text-brand-800 dark:text-brand-200'
                                : 'text-slate-700 dark:text-slate-300'}"
                            aria-pressed={multipleSpeciesOnly}
                            onclick={() => onchange({ multipleSpeciesOnly: !multipleSpeciesOnly })}
                            data-explorer-multiple-species-facet
                        >
                            <span>{$_('visits.multiple_species', { default: 'Multiple bird species' })}</span>
                            {#if multipleSpeciesOnly}
                                <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="m5 10 3.5 3.5L15 7" />
                                </svg>
                            {/if}
                        </button>
                        <p class="px-2 text-xs text-slate-500 dark:text-slate-400">{$_('visits.multiple_species_hint', { default: 'Two or more named species in one analyzed capture.' })}</p>
                    {/if}

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

                </div>
            </details>

            <details class="group shrink-0 border-t border-slate-200/70 pt-1 dark:border-slate-800" data-explorer-camera-facet>
                <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-lg text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200 [&::-webkit-details-marker]:hidden">
                    <span>{$_('events.filters.cameras', { default: 'Cameras' })}</span>
                    <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                </summary>
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
            </details>

            <!-- Options are counted when the page loads; this re-reads them, it changes no filter. -->
            <button
                type="button"
                class="mt-auto inline-flex min-h-11 shrink-0 items-center gap-1.5 self-start rounded-lg text-xs font-semibold text-slate-500 transition-colors hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:opacity-50 dark:text-slate-400 dark:hover:text-slate-200"
                disabled={refreshing}
                onclick={onrefresh}
            >
                <svg class="h-3.5 w-3.5 {refreshing ? 'animate-spin motion-reduce:animate-none' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M16 10a6 6 0 1 1-1.8-4.3M16 4v3.5h-3.5" /></svg>
                {refreshing
                    ? $_('events.filters.refreshing_options', { default: 'Refreshing options' })
                    : $_('events.filters.refresh_options', { default: 'Refresh options' })}
            </button>
    </div>
</section>

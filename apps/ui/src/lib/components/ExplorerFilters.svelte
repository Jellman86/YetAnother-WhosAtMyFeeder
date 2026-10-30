<script lang="ts">
    import type { EventFilterSpecies, EventFilters } from '../api';
    import { _ } from 'svelte-i18n';
    import { filterExplorerSpecies, shownExplorerSpecies } from '../utils/explorer-species';
    import type { ExplorerSubjects, GardenReview } from '../utils/garden-explorer';

    type DatePreset = 'all' | 'today' | 'week' | 'month' | 'custom';

    /** A species option, named as the owner names birds: a primary name and, when shown, the other. */
    type ExplorerSpeciesOption = EventFilterSpecies & { display_secondary?: string | null };

    interface Props {
        species: ExplorerSpeciesOption[];
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
        /** Owner with the Garden beta on: the rail can show Garden visitors instead of, or beside, birds. */
        gardenAvailable?: boolean;
        subjects?: ExplorerSubjects;
        gardenReview?: GardenReview;
        onchange: (next: {
            subjects?: ExplorerSubjects;
            gardenReview?: GardenReview;
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
        gardenAvailable = false,
        subjects = 'birds',
        gardenReview = 'reviewable',
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

    const gardenOnly = $derived(gardenAvailable && subjects === 'garden');
    // Set once and left: a compact switch, with the chosen option explained beneath it.
    const subjectOptions = $derived<{ value: ExplorerSubjects; label: string; short: string; hint: string }[]>([
        { value: 'birds', label: $_('garden.explorer.subjects_birds', { default: 'Birds' }), short: $_('garden.explorer.subjects_short_birds', { default: 'Birds' }), hint: $_('garden.explorer.subjects_birds_hint', { default: 'Bird visits only.' }) },
        { value: 'all', label: $_('garden.explorer.subjects_all_visitors', { default: 'Birds and Garden' }), short: $_('garden.explorer.subjects_short_all', { default: 'Both' }), hint: $_('garden.explorer.subjects_all_hint', { default: 'Garden animals between the bird visits.' }) },
        { value: 'garden', label: $_('garden.explorer.subjects_garden_visitors', { default: 'Garden visitors' }), short: $_('garden.explorer.subjects_short_garden', { default: 'Garden' }), hint: $_('garden.explorer.subjects_garden_hint', { default: 'Animals from Garden cameras only.' }) }
    ]);
    const showOptions = $derived([
        { grouped: true, short: $_('events.filters.show_visits_short', { default: 'Visits' }), hint: $_('events.filters.show_visits_hint', { default: "One bird's stay: its captures less than a minute apart." }) },
        { grouped: false, short: $_('events.filters.show_captures_short', { default: 'Captures' }), hint: $_('events.filters.show_captures_hint', { default: 'Every capture on its own.' }) }
    ]);
    const reviewOptions = $derived<{ value: GardenReview; label: string }[]>([
        { value: 'reviewable', label: $_('garden.explorer.review_animals', { default: 'Animals and waiting for review' }) },
        { value: 'pending', label: $_('garden.pending', { default: 'Needs review' }) },
        { value: 'confirmed', label: $_('garden.confirmed', { default: 'Confirmed animals' }) },
        { value: 'dismissed', label: $_('garden.dismissed', { default: 'Dismissed' }) }
    ]);

    // Every applied filter is a token: visible, and removable where it stands.
    const tokens = $derived.by(() => {
        const applied: { key: string; label: string; clear: () => void }[] = [];
        if (gardenAvailable && subjects !== 'all') {
            applied.push({
                key: 'subjects',
                label: subjectOptions.find((option) => option.value === subjects)?.label ?? subjects,
                clear: () => onchange({ subjects: 'all', gardenReview: 'reviewable' })
            });
        }
        if (gardenOnly && gardenReview !== 'reviewable') {
            applied.push({
                key: 'garden-review',
                label: reviewOptions.find((option) => option.value === gardenReview)?.label ?? gardenReview,
                clear: () => onchange({ gardenReview: 'reviewable' })
            });
        }
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

    let speciesExpanded = $state(false);
    const shownSpecies = $derived(
        shownExplorerSpecies(filterExplorerSpecies(species, search), {
            expanded: speciesExpanded,
            searching: search.trim() !== '',
            selected: speciesFilter
        })
    );
    // A folded section names what is chosen inside it, so a choice is never out of sight.
    const onlyActiveCount = $derived([favoritesOnly, audioConfirmedOnly, multipleSpeciesOnly, showHidden].filter(Boolean).length);

    // One look for every choice: a chosen row carries a bar and weight as well as colour.
    const rowClass = 'flex min-h-11 w-full items-center justify-between gap-3 rounded-lg border-l-2 px-2 text-left text-xs transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800/60';
    const rowChosenClass = 'border-brand-500 bg-brand-50 font-semibold text-brand-800 dark:border-brand-400 dark:bg-brand-950/40 dark:text-brand-100';
    const rowIdleClass = 'border-transparent text-slate-700 dark:text-slate-300';
    const segmentClass = 'mt-2 grid gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800/70';
    const segmentButtonClass = 'min-h-11 min-w-0 rounded-lg px-1.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500';
    const segmentChosenClass = 'bg-white text-brand-800 shadow-sm ring-1 ring-brand-500/50 dark:bg-brand-500/25 dark:text-white dark:ring-brand-400/70';
    const segmentIdleClass = 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-900/60 dark:hover:text-white';
</script>

<section
    class="pb-4 pt-1 {collapsed
        ? ''
        : 'lg:flex lg:h-[calc(100dvh-2rem)] lg:max-h-[calc(100dvh-2rem)] lg:flex-col lg:rounded-2xl lg:border lg:border-line-soft lg:bg-surface lg:p-3'}"
    data-events-filter-bar
>
    <div class="flex shrink-0 flex-wrap items-center gap-2">
        <!-- The toolbar above the list already counts the results; the rail names itself, with Clear all beside it. -->
        <div class="hidden w-full items-center justify-between gap-2 {collapsed ? '' : 'lg:flex'}">
            <h2 class="text-sm font-semibold text-slate-900 dark:text-white">
                {$_('events.filters.title', { default: 'Filters' })}
            </h2>
            {#if tokens.length > 0}
                <button class="btn btn-ghost min-h-11 px-3 py-2 text-xs" onclick={onclear} data-explorer-clear-all>
                    {$_('events.filters.clear_all', { default: 'Clear all' })}
                </button>
            {/if}
        </div>

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
            <!-- Beside the tokens on a phone, or on a collapsed desktop; the rail's header holds it otherwise. -->
            <button class="btn btn-ghost min-h-11 px-3 py-2 text-xs {collapsed ? '' : 'lg:hidden'}" onclick={onclear}>
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
            {#if gardenAvailable}
                <!-- Garden animals are stored apart from birds; this chooses which the results hold. -->
                <div class="min-w-0 shrink-0" role="group" aria-labelledby="explorer-visitors-heading" data-explorer-visitors-facet>
                    <p id="explorer-visitors-heading" class="eyebrow">{$_('garden.explorer.visitors', { default: 'Visitors' })}</p>
                    <div class="{segmentClass} grid-cols-3">
                        {#each subjectOptions as option (option.value)}
                            {@const chosen = subjects === option.value}
                            <button
                                type="button"
                                class="{segmentButtonClass} {chosen ? segmentChosenClass : segmentIdleClass}"
                                aria-pressed={chosen}
                                aria-describedby="explorer-visitors-hint"
                                onclick={() => onchange({ subjects: option.value, gardenReview: 'reviewable' })}
                                data-explorer-subjects-option={option.value}
                            >
                                {option.short}
                            </button>
                        {/each}
                    </div>
                    <p id="explorer-visitors-hint" class="mt-1.5 px-1 text-2xs leading-4 text-slate-500 dark:text-slate-400">
                        {subjectOptions.find((option) => option.value === subjects)?.hint ?? ''}
                    </p>
                </div>
                {#if gardenOnly}
                    <div class="min-w-0 shrink-0" role="group" aria-labelledby="explorer-garden-review-heading" data-explorer-garden-review-facet>
                        <p id="explorer-garden-review-heading" class="eyebrow">{$_('garden.explorer.review_heading', { default: 'Review' })}</p>
                        <div class="mt-2 space-y-0.5">
                            {#each reviewOptions as option (option.value)}
                                {@const chosen = gardenReview === option.value}
                                <button
                                    type="button"
                                    class="{rowClass} {chosen ? rowChosenClass : rowIdleClass}"
                                    aria-pressed={chosen}
                                    onclick={() => onchange({ gardenReview: option.value })}
                                    data-explorer-garden-review={option.value}
                                >
                                    <span class="min-w-0">{option.label}</span>
                                </button>
                            {/each}
                        </div>
                    </div>
                {/if}
            {/if}

            {#if !gardenOnly}
            <!-- How results are shown, not what they are: Clear all leaves it as it is. -->
            <div class="min-w-0 shrink-0" role="group" aria-labelledby="explorer-show-heading" data-explorer-show-facet>
                <p id="explorer-show-heading" class="eyebrow">
                    {$_('events.filters.show', { default: 'Show' })}
                </p>
                <div class="{segmentClass} grid-cols-2">
                    {#each showOptions as option (option.grouped)}
                        {@const chosen = groupVisits === option.grouped && !groupingLocked}
                        <button
                            type="button"
                            class="{segmentButtonClass} disabled:cursor-not-allowed disabled:opacity-60 {chosen ? segmentChosenClass : segmentIdleClass}"
                            aria-pressed={chosen}
                            aria-describedby="explorer-show-hint"
                            disabled={groupingLocked}
                            onclick={() => onchange({ groupVisits: option.grouped })}
                            data-explorer-show={option.grouped ? 'visits' : 'captures'}
                        >
                            {option.short}
                        </button>
                    {/each}
                </div>
                <p id="explorer-show-hint" class="mt-1.5 px-1 text-2xs leading-4 text-slate-500 dark:text-slate-400">
                    {groupingLocked
                        ? $_('events.filters.show_locked', { default: 'Selecting works on individual captures.' })
                        : (showOptions.find((option) => option.grouped === groupVisits)?.hint ?? '')}
                </p>
            </div>
            {/if}

            <!-- The window is the filter most often changed, so it is never folded away. -->
            <div class="min-w-0 shrink-0" role="group" aria-labelledby="explorer-when-heading" data-explorer-date-facet>
                <p id="explorer-when-heading" class="eyebrow">{$_('events.filters.when', { default: 'When' })}</p>
                <div class="mt-2 flex flex-wrap gap-1.5">
                    {#each datePresets as preset}
                        <button
                            type="button"
                            class="min-h-11 rounded-full border px-3 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {datePreset ===
                            preset
                                ? 'border-brand-500 bg-brand-50 text-brand-800 dark:border-brand-400 dark:bg-brand-950/40 dark:text-brand-200'
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
            </div>

            {#if !gardenOnly}
            <div class="min-w-0 shrink-0" data-explorer-species-facet>
                <p class="eyebrow">
                    {$_('events.filters.all_species')}
                </p>
                <label class="mt-2 block">
                    <span class="sr-only">{$_('events.filters.search_species', { default: 'Search species' })}</span>
                    <input class="input-base text-xs" type="search" bind:value={search} placeholder={$_('events.filters.search_species', { default: 'Search species' })} />
                </label>
                <!-- One scrolling rail: the list grows in place rather than scrolling inside it. -->
                <div id="explorer-species-list" class="mt-2 space-y-0.5" data-explorer-species-list>
                    {#each shownSpecies.items as item (item.value)}
                        {@const chosen = speciesFilter === item.value}
                        <button
                            type="button"
                            class="{rowClass} {chosen ? rowChosenClass : rowIdleClass}"
                            aria-pressed={chosen}
                            onclick={() => onchange({ speciesFilter: chosen ? '' : item.value })}
                        >
                            <span class="min-w-0 py-1.5 leading-4">
                                <span class="block [overflow-wrap:anywhere]">{item.display_name}</span>
                                {#if item.display_secondary}
                                    <span class="block text-2xs font-normal italic text-slate-500 [overflow-wrap:anywhere] dark:text-slate-400">{item.display_secondary}</span>
                                {/if}
                            </span>
                            <span class="shrink-0 tabular-nums font-normal text-slate-500 dark:text-slate-400">{item.count ?? 0}</span>
                        </button>
                    {:else}
                        <p class="px-2 py-2 text-xs text-slate-500 dark:text-slate-400">
                            {$_('events.filters.no_species_match', { default: 'No species matches that.' })}
                        </p>
                    {/each}
                </div>
                {#if shownSpecies.more > 0 || speciesExpanded}
                    <button
                        type="button"
                        class="mt-1 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-brand-700 transition-colors hover:text-brand-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-brand-300 dark:hover:text-brand-100"
                        aria-expanded={speciesExpanded}
                        aria-controls="explorer-species-list"
                        onclick={() => (speciesExpanded = !speciesExpanded)}
                        data-explorer-species-more
                    >
                        {speciesExpanded
                            ? $_('events.filters.show_fewer_species', { default: 'Show fewer' })
                            : $_('events.filters.show_all_species', { default: 'Show all {count} species', values: { count: species.length } })}
                    </button>
                {/if}
            </div>

            {/if}

            <details class="group shrink-0 border-t border-line-soft pt-1" data-explorer-camera-facet>
                <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 eyebrow rounded-lg hover:bg-surface-raised hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:text-slate-200 [&::-webkit-details-marker]:hidden">
                    <span class="min-w-0 truncate">
                        {$_('events.filters.cameras', { default: 'Cameras' })}{#if cameraFilter}<span class="normal-case tracking-normal text-brand-700 dark:text-brand-300"> · {cameraFilter}</span>{/if}
                    </span>
                    <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                </summary>
                <div class="mt-2 space-y-0.5">
                    {#each cameras as camera (camera)}
                        {@const chosen = cameraFilter === camera}
                        <button
                            type="button"
                            class="{rowClass} {chosen ? rowChosenClass : rowIdleClass}"
                            aria-pressed={chosen}
                            onclick={() => onchange({ cameraFilter: chosen ? '' : camera })}
                        >
                            <span class="truncate">{camera}</span>
                            <span class="shrink-0 tabular-nums font-normal text-slate-500 dark:text-slate-400">
                                {cameraCounts[camera] ?? 0}
                            </span>
                        </button>
                    {/each}
                </div>
            </details>

            {#if !gardenOnly}
            <details class="group shrink-0 border-t border-line-soft pt-1" data-explorer-only-facet>
                <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 eyebrow rounded-lg hover:bg-surface-raised hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:text-slate-200 [&::-webkit-details-marker]:hidden">
                    <span>
                        {$_('events.filters.only', { default: 'Only' })}{#if onlyActiveCount > 0}<span class="normal-case tracking-normal text-brand-700 dark:text-brand-300"> · {$_('events.filters.only_active', { default: '{count} on', values: { count: onlyActiveCount } })}</span>{/if}
                    </span>
                    <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                </summary>
                <div class="mt-2 space-y-1">
                    {#if canSeeHidden}
                        <button
                            type="button"
                            class="{rowClass} {multipleSpeciesOnly ? rowChosenClass : rowIdleClass}"
                            aria-pressed={multipleSpeciesOnly}
                            aria-describedby="explorer-multiple-species-hint"
                            onclick={() => onchange({ multipleSpeciesOnly: !multipleSpeciesOnly })}
                            data-explorer-multiple-species-facet
                        >
                            <span>{$_('visits.multiple_species', { default: 'Multiple bird species' })}</span>
                        </button>
                        <p id="explorer-multiple-species-hint" class="px-2 text-2xs leading-4 text-slate-500 dark:text-slate-400">{$_('visits.multiple_species_hint', { default: 'Two or more named species in one analyzed capture.' })}</p>
                    {/if}

                    <button
                        type="button"
                        class="{rowClass} {favoritesOnly ? rowChosenClass : rowIdleClass}"
                        aria-pressed={favoritesOnly}
                        onclick={() => onchange({ favoritesOnly: !favoritesOnly })}
                    >
                        <span>{$_('events.filters.favorites', { default: 'Favourites' })}</span>
                        <span class="tabular-nums font-normal text-slate-500 dark:text-slate-400">{totals?.favorites ?? 0}</span>
                    </button>
                    <button
                        type="button"
                        class="{rowClass} {audioConfirmedOnly ? rowChosenClass : rowIdleClass}"
                        aria-pressed={audioConfirmedOnly}
                        onclick={() => onchange({ audioConfirmedOnly: !audioConfirmedOnly })}
                    >
                        <span>{$_('events.filters.audio_matches', { default: 'Audio matches' })}</span>
                        <span class="tabular-nums font-normal text-slate-500 dark:text-slate-400">{totals?.audio_matched ?? 0}</span>
                    </button>

                    {#if canSeeHidden && (hiddenCount > 0 || showHidden)}
                        <button
                            type="button"
                            class="{rowClass} {showHidden ? rowChosenClass : rowIdleClass}"
                            aria-pressed={showHidden}
                            onclick={() => onchange({ showHidden: !showHidden })}
                            data-explorer-hidden-facet
                        >
                            <span>{$_('events.filters.hidden', { default: 'Hidden' })}</span>
                            <span class="tabular-nums font-normal text-slate-500 dark:text-slate-400">{hiddenCount}</span>
                        </button>
                    {/if}
                </div>
            </details>
            {/if}

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

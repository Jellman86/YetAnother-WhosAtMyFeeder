<script lang="ts">
    import { onDestroy } from 'svelte';
    import { _, locale } from 'svelte-i18n';
    import { searchExplorer, type ExplorerSearchRecord, type ExplorerSearchResponse, type ExplorerSearchTaxon } from '../api/explorer';
    import { getBirdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { formatCalendarDay, formatDateTime } from '../utils/datetime';
    import {
        SEARCH_MAX_LENGTH,
        classifyExplorerQuery,
        explorerDateWords,
        explorerSearchGroups,
        type SearchFacetSpecies,
        type SearchGroupKey,
        type SearchOption
    } from '../utils/explorer-search';

    /**
     * One search box for the Explorer, as a WAI-ARIA combobox: focus stays in the input while the
     * arrow keys move the active result (aria-activedescendant), Enter chooses it and Escape clears
     * and closes. "/" focuses it from anywhere on the page that is not already a text field.
     */
    interface Props {
        species: SearchFacetSpecies[];
        cameras: string[];
        cameraCounts: Record<string, number> | null;
        /** Off while a record or dialog is open, so "/" types into that instead. */
        shortcutEnabled: boolean;
        onchoose: (option: SearchOption) => void;
    }

    let { species, cameras, cameraCounts, shortcutEnabled, onchoose }: Props = $props();

    const DEBOUNCE_MS = 250;
    const LISTBOX_ID = 'explorer-search-results';
    const STATUS_ID = 'explorer-search-status';

    let input = $state<HTMLInputElement | null>(null);
    let text = $state('');
    let open = $state(false);
    let activeIndex = $state(0);
    let response = $state.raw<ExplorerSearchResponse | null>(null);
    /** The query the response answers, so a late answer never labels newer text. */
    let answered = $state('');
    let loading = $state(false);
    let failed = $state(false);
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    const dateWords = $derived(
        explorerDateWords($locale ?? 'en', {
            today: $_('events.filters.today', { default: 'Today' }),
            yesterday: $_('events.search.yesterday', { default: 'Yesterday' })
        })
    );
    const query = $derived(classifyExplorerQuery(text, new Date(), dateWords));
    const current = $derived(answered === text.trim() ? response : null);
    const groups = $derived(explorerSearchGroups({ query, response: current, facetSpecies: species, cameras, cameraCounts }));
    const options = $derived(groups.flatMap((group) => group.options));
    const settled = $derived(!loading && (!query.askServer || current !== null || failed));
    const expanded = $derived(open && options.length > 0);
    const activeOption = $derived(expanded ? options[Math.min(activeIndex, options.length - 1)] : undefined);

    const groupLabels = $derived<Record<SearchGroupKey, string>>({
        records: $_('events.search.group_records', { default: 'Record' }),
        species: $_('events.search.group_species', { default: 'Species and groups' }),
        cameras: $_('events.search.group_cameras', { default: 'Cameras' }),
        dates: $_('events.search.group_dates', { default: 'Date' })
    });

    /** What the panel says beneath the results, in words; also what a screen reader hears. */
    const status = $derived.by((): string => {
        const typed = text.trim();
        if (!open || !typed) return '';
        if (!settled) return $_('events.search.searching', { default: 'Searching…' });
        if (failed && options.length === 0) {
            return $_('events.search.failed', { default: 'Species and records could not be searched just now. Try again in a moment.' });
        }
        if (query.record && !current?.record) {
            return $_('events.search.record_unavailable', { default: 'No record you can open has this ID.' });
        }
        if (options.length === 0) {
            return $_('events.search.empty', { values: { query: typed }, default: "No match for “{query}”. Try a scientific name or a camera." });
        }
        const count = $_('events.search.results', { values: { count: options.length }, default: '{count, plural, one {# result} other {# results}}' });
        if (failed) return `${count}. ${$_('events.search.failed_partial', { default: 'Species and records could not be searched just now.' })}`;
        if (current?.truncated) return `${count}. ${$_('events.search.more', { default: 'More species match. Type more of the name to narrow them.' })}`;
        return count;
    });

    function cancelPending(): void {
        if (timer) clearTimeout(timer);
        timer = null;
        controller?.abort();
        controller = null;
    }

    async function ask(value: string): Promise<void> {
        const request = new AbortController();
        controller = request;
        loading = true;
        try {
            const result = await searchExplorer(value, request.signal);
            if (request.signal.aborted) return;
            response = result;
            answered = value;
            failed = false;
        } catch (error) {
            if (request.signal.aborted) return;
            console.error('Explorer search failed', error);
            failed = true;
            response = null;
        } finally {
            if (controller === request) {
                loading = false;
                controller = null;
            }
        }
    }

    function handleInput(): void {
        cancelPending();
        open = true;
        activeIndex = 0;
        failed = false;
        const value = text.trim();
        const kinds = classifyExplorerQuery(value, new Date(), dateWords);
        if (!kinds.askServer) {
            loading = false;
            return;
        }
        loading = true;
        timer = setTimeout(() => {
            timer = null;
            void ask(value.slice(0, SEARCH_MAX_LENGTH));
        }, DEBOUNCE_MS);
    }

    function clear(): void {
        cancelPending();
        text = '';
        open = false;
        loading = false;
        failed = false;
        response = null;
        answered = '';
        activeIndex = 0;
    }

    function choose(option: SearchOption): void {
        clear();
        onchoose(option);
    }

    function move(step: number): void {
        if (!options.length) return;
        open = true;
        activeIndex = (Math.min(activeIndex, options.length - 1) + step + options.length) % options.length;
        document.getElementById(optionId(activeIndex))?.scrollIntoView({ block: 'nearest' });
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            if (!open) open = true;
            else move(1);
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            move(-1);
        } else if (event.key === 'Enter') {
            if (activeOption) {
                event.preventDefault();
                choose(activeOption);
            }
        } else if (event.key === 'Escape') {
            if (text || open) {
                // Clearing the box is this Escape's whole job; no dialog behind it should close.
                event.preventDefault();
                event.stopPropagation();
                clear();
            }
        } else if (event.key === 'Tab') {
            open = false;
        }
    }

    function isTextField(target: EventTarget | null): boolean {
        if (!(target instanceof HTMLElement)) return false;
        if (target.isContentEditable) return true;
        if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
        return target instanceof HTMLInputElement && !['button', 'checkbox', 'radio', 'submit', 'reset', 'range', 'color', 'file'].includes(target.type);
    }

    function handleWindowKeydown(event: KeyboardEvent): void {
        if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
        if (!shortcutEnabled || isTextField(event.target) || !input || input.getClientRects().length === 0) return;
        event.preventDefault();
        input.focus();
        input.select();
    }

    function optionId(index: number): string {
        return `explorer-search-option-${index}`;
    }

    function speciesNames(item: { display_name?: string | null; common_name?: string | null; scientific_name?: string | null }): { primary: string; secondary: string | null } {
        const names = getBirdNames(
            { display_name: item.display_name ?? item.common_name ?? item.scientific_name ?? '', common_name: item.common_name ?? undefined, scientific_name: item.scientific_name ?? undefined },
            settingsStore.displayCommonNames,
            settingsStore.scientificNamePrimary
        );
        return { primary: names.primary, secondary: names.secondary || null };
    }

    function taxonNames(taxon: ExplorerSearchTaxon): { primary: string; secondary: string | null } {
        if (taxon.rank === 'species') return speciesNames({ display_name: taxon.name, common_name: taxon.name, scientific_name: taxon.scientific_name });
        return taxon.name ? { primary: taxon.name, secondary: taxon.scientific_name } : { primary: taxon.scientific_name, secondary: null };
    }

    /** What a group holds, beside its rank label; empty for a species seen only as birds. */
    function taxonNote(taxon: ExplorerSearchTaxon): string {
        const parts: string[] = [];
        if (taxon.rank !== 'species') {
            parts.push($_('events.search.species_seen', { values: { count: taxon.bird_species + taxon.garden_species }, default: '{count, plural, one {# species seen} other {# species seen}}' }));
        }
        if (taxon.garden_captures > 0 && taxon.bird_detections === 0) parts.push($_('events.search.garden_marker', { default: 'Garden animals' }));
        return parts.join(' · ');
    }

    function taxonCount(taxon: ExplorerSearchTaxon): string {
        const counts: string[] = [];
        if (taxon.bird_detections > 0) counts.push($_('events.search.detections', { values: { count: taxon.bird_detections }, default: '{count, plural, one {# detection} other {# detections}}' }));
        if (taxon.garden_captures > 0) counts.push($_('events.search.garden_captures', { values: { count: taxon.garden_captures }, default: '{count, plural, one {# Garden capture} other {# Garden captures}}' }));
        return counts.join(', ');
    }

    function recordTitle(record: ExplorerSearchRecord): string {
        const named = record.display_name || record.common_name || record.scientific_name;
        if (record.kind === 'garden') return named ?? $_('events.search.garden_record', { default: 'Garden capture' });
        return named ? speciesNames(record).primary : $_('events.search.detection_record', { default: 'Detection' });
    }

    function recordDetail(record: ExplorerSearchRecord): string {
        const parts = [$_('events.search.open_record', { default: 'Open record' }), formatDateTime(record.observed_at)];
        if (record.camera) parts.push(record.camera);
        if (record.hidden) parts.push($_('events.filters.hidden', { default: 'Hidden' }));
        return parts.join(' · ');
    }

    onDestroy(cancelPending);
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="relative w-full" data-explorer-search>
    <label for="explorer-search-input" class="sr-only">{$_('events.search.label', { default: 'Search the Explorer' })}</label>
    <div class="relative">
        <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <circle cx="9" cy="9" r="5.5" /><path stroke-linecap="round" d="m13 13 4 4" />
        </svg>
        <input
            bind:this={input}
            bind:value={text}
            id="explorer-search-input"
            class="input-base input-focus-inset min-h-11 pl-9 pr-9 text-sm [&::-webkit-search-cancel-button]:hidden"
            type="search"
            role="combobox"
            autocomplete="off"
            spellcheck="false"
            maxlength={SEARCH_MAX_LENGTH}
            placeholder={$_('events.search.placeholder', { default: 'Species, camera or ID' })}
            aria-autocomplete="list"
            aria-expanded={expanded}
            aria-controls={LISTBOX_ID}
            aria-activedescendant={activeOption ? optionId(options.indexOf(activeOption)) : undefined}
            aria-describedby={STATUS_ID}
            aria-keyshortcuts="/"
            oninput={handleInput}
            onkeydown={handleKeydown}
            onfocus={() => { if (text.trim()) open = true; }}
            onblur={() => (open = false)}
        />
        {#if text}
            <button
                type="button"
                class="absolute right-0 top-0 inline-flex h-11 w-11 items-center justify-center rounded-lg text-slate-500 hover:text-slate-800 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-400 dark:hover:text-slate-100"
                onmousedown={(event) => event.preventDefault()}
                onclick={() => { clear(); input?.focus(); }}
                data-explorer-search-clear
            >
                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" d="m6 6 8 8M14 6l-8 8" /></svg>
                <span class="sr-only">{$_('events.search.clear', { default: 'Clear search' })}</span>
            </button>
        {:else}
            <kbd class="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded-sm border border-line-soft px-1.5 text-2xs text-slate-500 sm:block dark:text-slate-400" aria-hidden="true">/</kbd>
        {/if}
    </div>

    <div
        class="absolute left-0 top-full z-30 mt-1 w-full rounded-xl border border-line-soft bg-surface p-1 shadow-lg {open && text.trim() ? '' : 'hidden'}"
        data-explorer-search-panel
    >
        <div id={LISTBOX_ID} role="listbox" aria-label={$_('events.search.label', { default: 'Search the Explorer' })} class="max-h-96 overflow-y-auto overscroll-contain">
            {#each groups as group (group.key)}
                <div role="group" aria-labelledby="explorer-search-group-{group.key}" data-explorer-search-group={group.key}>
                    <p id="explorer-search-group-{group.key}" class="eyebrow px-2 pb-1 pt-2 text-2xs" role="presentation">{groupLabels[group.key]}</p>
                    {#each group.options as option (option.key)}
                        {@const index = options.indexOf(option)}
                        {@const active = activeOption === option}
                        <!-- svelte-ignore a11y_click_events_have_key_events -->
                        <!-- Focus stays in the input, which owns the keyboard: arrows move and Enter chooses. -->
                        <div
                            id={optionId(index)}
                            role="option"
                            aria-selected={active}
                            tabindex="-1"
                            class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 text-left {active
                                ? 'choice-active'
                                : 'text-slate-800 dark:text-slate-200'}"
                            onmousedown={(event) => event.preventDefault()}
                            onpointermove={() => (activeIndex = index)}
                            onclick={() => choose(option)}
                            data-explorer-search-option={option.kind}
                        >
                            <!-- One line where the panel is wide enough; a phone wraps the label beneath the names. -->
                            <span class="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5 leading-5">
                                {#if option.kind === 'taxon'}
                                    {@const names = taxonNames(option.taxon)}
                                    {@const note = taxonNote(option.taxon)}
                                    <span class="text-sm wrap-anywhere">{names.primary}</span>
                                    {#if names.secondary}<span class="text-xs italic text-slate-500 wrap-anywhere dark:text-slate-400">{names.secondary}</span>{/if}
                                    <span class="taxon-rank">{$_(`taxonomy.rank.${option.taxon.rank}`, { default: option.taxon.rank })}</span>
                                    {#if note}<span class="text-2xs text-slate-500 dark:text-slate-400">{note}</span>{/if}
                                {:else if option.kind === 'species'}
                                    {@const names = speciesNames(option.species)}
                                    <span class="text-sm wrap-anywhere">{names.primary}</span>
                                    {#if names.secondary}<span class="text-xs italic text-slate-500 wrap-anywhere dark:text-slate-400">{names.secondary}</span>{/if}
                                    <span class="taxon-rank">{$_('taxonomy.rank.species', { default: 'Species' })}</span>
                                {:else if option.kind === 'camera'}
                                    <span class="min-w-0 truncate text-sm">{option.camera}</span>
                                {:else if option.kind === 'date'}
                                    <span class="text-sm">
                                        {$_('events.search.show_day', { values: { day: formatCalendarDay(option.day) }, default: 'Show {day}' })}
                                    </span>
                                {:else}
                                    <span class="text-sm wrap-anywhere">{recordTitle(option.record)}</span>
                                    <span class="text-xs text-slate-500 dark:text-slate-400">{recordDetail(option.record)}</span>
                                {/if}
                            </span>
                            {#if option.kind === 'taxon'}
                                <span class="shrink-0 text-right text-2xs tabular-nums text-slate-500 dark:text-slate-400">{taxonCount(option.taxon)}</span>
                            {:else if option.kind === 'species'}
                                <span class="shrink-0 text-2xs tabular-nums text-slate-500 dark:text-slate-400">
                                    {$_('events.search.detections', { values: { count: option.species.count ?? 0 }, default: '{count, plural, one {# detection} other {# detections}}' })}
                                </span>
                            {:else if option.kind === 'camera' && option.count !== null}
                                <span class="shrink-0 text-2xs tabular-nums text-slate-500 dark:text-slate-400">{option.count}</span>
                            {/if}
                            <!-- What Enter does, on the active result only; the slot is kept so nothing shifts as it moves. -->
                            <svg
                                class="h-3.5 w-3.5 shrink-0 {active ? '' : 'invisible'}"
                                viewBox="0 0 20 20"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="1.8"
                                aria-hidden="true"
                                data-explorer-search-active-cue
                            >
                                <path stroke-linecap="round" stroke-linejoin="round" d="M15.5 4.5v5a2 2 0 0 1-2 2h-9m0 0 3.5-3.5M4.5 11.5 8 15" />
                            </svg>
                        </div>
                    {/each}
                </div>
            {/each}
        </div>
        <p class="px-2 py-2 text-xs text-slate-600 empty:hidden dark:text-slate-300" aria-hidden="true" data-explorer-search-status>{status}</p>
    </div>
    <!-- Always present, so a change of state is announced; the panel shows the same words. -->
    <p id={STATUS_ID} class="sr-only" role="status">{status}</p>
</div>

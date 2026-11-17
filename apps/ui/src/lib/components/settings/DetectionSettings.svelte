<script lang="ts">
    import { onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { searchSpecies, type SearchResult } from '../../api';
    import type { BlockedSpeciesEntry } from '../../api/settings';
    import { getManualTagSearchOptions } from '../../search/manual-tag-search';
    import {
        buildBlockedSpeciesEntry,
        formatBlockedSpeciesLabel,
        mergeBlockedSpeciesEntries
    } from '../../settings/blocked-species';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import RangeFilterSettings from './RangeFilterSettings.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';

    let {
        trustFrigateSublabel = $bindable(true),
        writeFrigateSublabel = $bindable(true),
        autoVideoClassification = $bindable(false),
        videoClassificationDelay = $bindable(30),
        videoClassificationMaxRetries = $bindable(3),
        videoClassificationFrames = $bindable(15),
        blockedLabels = $bindable<string[]>([]),
        blockedSpecies = $bindable<BlockedSpeciesEntry[]>([]),
        rangeFilterEnabled = $bindable(false),
        rangeFilterRegionLevel = $bindable<'county' | 'state' | 'country'>('county'),
        onopenlocationsettings,
        onopenebirdsettings,
        onopenactivitylog,
        onopenmanualobservation
    }: {
        trustFrigateSublabel: boolean;
        writeFrigateSublabel: boolean;
        autoVideoClassification: boolean;
        videoClassificationDelay: number;
        videoClassificationMaxRetries: number;
        videoClassificationFrames: number;
        blockedLabels: string[];
        blockedSpecies: BlockedSpeciesEntry[];
        rangeFilterEnabled?: boolean;
        rangeFilterRegionLevel?: 'county' | 'state' | 'country';
        onopenlocationsettings?: () => void;
        onopenebirdsettings?: () => void;
        onopenactivitylog?: () => void;
        onopenmanualobservation?: () => void;
    } = $props();


    let blockedSpeciesSearchQuery = $state('');
    let blockedSpeciesSearchResults = $state<SearchResult[]>([]);
    let blockedSpeciesSearching = $state(false);
    let blockedSpeciesSearchError = $state<string | null>(null);
    let blockedSpeciesSearchTimeout: ReturnType<typeof setTimeout> | undefined;

    $effect(() => {
        const query = blockedSpeciesSearchQuery.trim();
        clearTimeout(blockedSpeciesSearchTimeout);

        if (!query) {
            blockedSpeciesSearchResults = [];
            blockedSpeciesSearchError = null;
            blockedSpeciesSearching = false;
            return;
        }

        blockedSpeciesSearchTimeout = setTimeout(async () => {
            blockedSpeciesSearching = true;
            blockedSpeciesSearchError = null;
            try {
                const searchOptions = getManualTagSearchOptions(query);
                blockedSpeciesSearchResults = await searchSpecies(
                    query,
                    searchOptions.limit,
                    searchOptions.hydrateMissing
                );
            } catch (error) {
                console.error('Blocked species search failed', error);
                blockedSpeciesSearchResults = [];
                blockedSpeciesSearchError = $_('common.error');
            } finally {
                blockedSpeciesSearching = false;
            }
        }, 300);
    });

    onDestroy(() => {
        if (blockedSpeciesSearchTimeout) {
            clearTimeout(blockedSpeciesSearchTimeout);
            blockedSpeciesSearchTimeout = undefined;
        }
    });

    function normalizeEntryText(value: string | null | undefined): string | null {
        const text = String(value || '').trim();
        return text || null;
    }

    function blockedSpeciesKey(entry: BlockedSpeciesEntry): string | null {
        if (entry.taxa_id != null) return `taxa:${entry.taxa_id}`;
        const scientific = normalizeEntryText(entry.scientific_name);
        if (scientific) return `scientific:${scientific.toLocaleLowerCase()}`;
        const common = normalizeEntryText(entry.common_name);
        if (common) return `common:${common.toLocaleLowerCase()}`;
        return null;
    }

    function sameBlockedSpeciesEntry(a: BlockedSpeciesEntry, b: BlockedSpeciesEntry): boolean {
        const keyA = blockedSpeciesKey(a);
        const keyB = blockedSpeciesKey(b);
        return Boolean(keyA && keyB && keyA === keyB);
    }

    function getResultNames(result: SearchResult) {
        const common = result.common_name?.trim() || null;
        const scientific = result.scientific_name?.trim() || null;
        const fallback = result.display_name || result.id;
        if (common && scientific && common !== scientific) {
            return { primary: common, secondary: scientific };
        }
        return { primary: common || scientific || fallback, secondary: null };
    }

    function isSearchResultAlreadyBlocked(result: SearchResult): boolean {
        const entry = buildBlockedSpeciesEntry(result);
        if (!entry) return false;
        return blockedSpecies.some((existingEntry) => sameBlockedSpeciesEntry(existingEntry, entry));
    }

    function resetBlockedSpeciesSearch() {
        blockedSpeciesSearchQuery = '';
        blockedSpeciesSearchResults = [];
        blockedSpeciesSearchError = null;
    }

    function addBlockedLabelText(label: string) {
        const value = label.trim();
        if (!value) return;
        if (!blockedLabels.some((existing) => existing.toLowerCase() === value.toLowerCase())) {
            blockedLabels = [...blockedLabels, value];
        }
        resetBlockedSpeciesSearch();
    }

    function addBlockedSpecies(result: SearchResult) {
        const entry = buildBlockedSpeciesEntry(result);
        if (!entry) {
            // A result with no canonical identity used to no-op silently: the
            // row looked clickable and nothing happened. The raw label still
            // blocks - matching is label-first - so store it as written (#311).
            addBlockedLabelText(result.display_name || result.id);
            return;
        }
        blockedSpecies = mergeBlockedSpeciesEntries([...blockedSpecies, entry]);
        resetBlockedSpeciesSearch();
    }

    function removeBlockedSpecies(entryToRemove: BlockedSpeciesEntry) {
        blockedSpecies = blockedSpecies.filter((entry) => !sameBlockedSpeciesEntry(entry, entryToRemove));
    }

    function removeLegacyBlockedLabel(labelToRemove: string) {
        blockedLabels = blockedLabels.filter((label) => label !== labelToRemove);
    }
</script>

<div class="space-y-6">
    <SettingsCard
        title={$_('settings.detection.blocked_labels')}
        description={$_('settings.detection.blocked_species_picker_desc', { default: 'Search for a species to block it reliably across common-name, scientific-name, and taxonomy-aware matches. Legacy raw labels still apply until you remove them.' })}
    >
        <div class="space-y-3">
            <SettingsInput
                id="blocked-species-search"
                type="text"
                value={blockedSpeciesSearchQuery}
                placeholder={$_('settings.detection.blocked_species_placeholder', { default: 'Search species to block' })}
                ariaLabel={$_('settings.detection.blocked_labels')}
                oninput={(v) => (blockedSpeciesSearchQuery = v)}
            />

            {#if blockedSpeciesSearchQuery.trim()}
                <div class="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700/50 bg-white/60 dark:bg-slate-900/40 shadow-xs">
                    <div class="max-h-64 overflow-y-auto p-1">
                        {#each blockedSpeciesSearchResults as result}
                            {@const names = getResultNames(result)}
                            {@const alreadyBlocked = isSearchResultAlreadyBlocked(result)}
                            <button
                                type="button"
                                onclick={() => addBlockedSpecies(result)}
                                disabled={alreadyBlocked}
                                class="focus-ring min-h-11 w-full cursor-pointer rounded-xl px-4 py-2.5 text-left text-sm font-medium transition-colors hover:bg-red-50 hover:text-red-600 disabled:cursor-default disabled:opacity-60 dark:hover:bg-red-950/20 dark:hover:text-red-300 {alreadyBlocked ? 'bg-red-500/10 text-red-700 dark:text-red-300' : 'text-slate-700 dark:text-slate-200'}"
                            >
                                <span class="block">
                                    {names.primary}
                                    {#if alreadyBlocked}
                                        <span class="ml-2 inline-flex items-center rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-bold text-red-700 dark:text-red-300">
                                            {$_('common.added', { default: 'Added' })}
                                        </span>
                                    {/if}
                                </span>
                                {#if names.secondary}
                                    <span class="block text-xs italic text-slate-600 dark:text-slate-400">{names.secondary}</span>
                                {/if}
                            </button>
                        {/each}
                        {#if blockedSpeciesSearchError}
                            <p role="alert" class="px-4 py-4 text-sm font-medium text-red-700 dark:text-red-400">{blockedSpeciesSearchError}</p>
                        {:else if blockedSpeciesSearchResults.length === 0}
                            <p role="status" class="px-4 py-4 text-sm text-slate-600 dark:text-slate-400">
                                {blockedSpeciesSearching ? $_('common.loading') : $_('settings.detection.no_blocked_species_results', { default: 'No matching species found.' })}
                            </p>
                        {/if}
                        <!-- Search only offers what it can name, and some model
                             labels carry no name it can find - the species on a
                             detection card must always be blockable, so the typed
                             text itself is offered as written (#311). -->
                        {#if !blockedSpeciesSearching && blockedSpeciesSearchQuery.trim() && !blockedLabels.some((existing) => existing.toLowerCase() === blockedSpeciesSearchQuery.trim().toLowerCase())}
                            <button
                                type="button"
                                onclick={() => addBlockedLabelText(blockedSpeciesSearchQuery)}
                                data-blocked-label-escape-hatch
                                class="focus-ring min-h-11 w-full cursor-pointer text-left text-sm font-medium transition-colors hover:text-red-600 dark:hover:text-red-300 text-red-700 dark:text-red-300"
                            >
                                {$_('settings.detection.block_exact_label', {
                                    values: { label: blockedSpeciesSearchQuery.trim() },
                                    default: 'Block"{label}" exactly as written'
                                })}
                            </button>
                        {/if}
                    </div>
                </div>
            {/if}

            {#if blockedSpecies.length > 0}
                <div>
                    <p class="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.detection.blocked_species_structured', { default: 'Blocked species' })}</p>
                    <div class="flex flex-wrap gap-2">
                        {#each blockedSpecies as entry}
                            <span class="group flex min-h-11 items-center gap-2 rounded-xl border border-red-200 bg-red-50 pl-3 text-xs font-bold text-red-700 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-200">
                                {formatBlockedSpeciesLabel(entry)}
                                <button
                                    type="button"
                                    onclick={() => removeBlockedSpecies(entry)}
                                    aria-label={$_('settings.detection.blocked_label_remove', { values: { label: formatBlockedSpeciesLabel(entry) } })}
                                    class="inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl text-red-700 dark:text-red-300 transition-colors hover:bg-red-100 hover:text-red-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-red-500 dark:hover:bg-red-900/40 dark:hover:text-red-100"
                                >
                                    <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                                        <path d="M6 6l12 12M18 6 6 18" />
                                    </svg>
                                </button>
                            </span>
                        {/each}
                    </div>
                </div>
            {/if}

            {#if blockedLabels.length > 0}
                <div>
                    <p class="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.detection.blocked_species_legacy', { default: 'Legacy raw labels' })}</p>
                    <div class="flex flex-wrap gap-2">
                        {#each blockedLabels as label}
                            <span class="group flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white pl-3 text-xs font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                                {label}
                                <span class="rounded-full bg-slate-500/10 px-2 py-0.5 text-xs font-semibold text-slate-700 dark:text-slate-200">{$_('common.legacy', { default: 'Legacy' })}</span>
                                <button
                                    type="button"
                                    onclick={() => removeLegacyBlockedLabel(label)}
                                    aria-label={$_('settings.detection.blocked_label_remove', { values: { label } })}
                                    class="inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl text-slate-600 dark:text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-red-500 dark:hover:bg-red-950/30 dark:hover:text-red-300"
                                >
                                    <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                                        <path d="M6 6l12 12M18 6 6 18" />
                                    </svg>
                                </button>
                            </span>
                        {/each}
                    </div>
                </div>
            {/if}

            {#if blockedSpecies.length === 0 && blockedLabels.length === 0}
                <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.detection.no_blocked_labels')}</p>
            {/if}
        </div>
    </SettingsCard>

    <RangeFilterSettings
        bind:enabled={rangeFilterEnabled}
        bind:regionLevel={rangeFilterRegionLevel}
        {onopenlocationsettings}
        {onopenebirdsettings}
        {onopenactivitylog}
        {onopenmanualobservation}
    />

    <SettingsCard
        collapsible
        id="detection-frigate-video"
        title={$_('settings.detection.frigate_video_title', { default: 'Frigate and video' })}
        description={$_('settings.detection.frigate_video_desc', { default: 'Whether to use labels Frigate already has, write YA-WAMF species back to Frigate, and check recorded clips after the snapshot.' })}
    >
        <SettingsRow
            labelId="setting-trust-frigate"
            label={$_('settings.detection.trust_frigate')}
            description={$_('settings.detection.trust_frigate_desc')}
        >
            <SettingsToggle
                checked={trustFrigateSublabel}
                labelledBy="setting-trust-frigate"
                srLabel={$_('settings.detection.trust_frigate')}
                onchange={(v) => (trustFrigateSublabel = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-write-frigate"
            label={$_('settings.detection.write_frigate_sublabel')}
            description={$_('settings.detection.write_frigate_sublabel_desc')}
        >
            <SettingsToggle
                checked={writeFrigateSublabel}
                labelledBy="setting-write-frigate"
                srLabel={$_('settings.detection.write_frigate_sublabel')}
                onchange={(v) => (writeFrigateSublabel = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-auto-video"
            label={$_('settings.detection.auto_video')}
            description={$_('settings.detection.auto_video_desc')}
        >
            <SettingsToggle
                checked={autoVideoClassification}
                labelledBy="setting-auto-video"
                srLabel={$_('settings.detection.auto_video')}
                onchange={(v) => (autoVideoClassification = v)}
            />
        </SettingsRow>

        {#if autoVideoClassification}
            <div class="pt-2 border-t border-dashed border-slate-200/70 dark:border-slate-700/60">
                <p class="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
                    {$_('settings.detection.auto_video_advanced_title', { default: 'Auto-video tuning' })}
                </p>
                <div class="space-y-4">
                    <SettingsRow
                        labelId="setting-video-delay"
                        label={$_('settings.detection.video_delay')}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="video-delay"
                            field="video_classification_delay"
                            type="number"
                            min={0}
                            value={videoClassificationDelay}
                            ariaLabel={$_('settings.detection.video_delay')}
                            oninput={(v) => (videoClassificationDelay = Number(v) || 0)}
                        />
                    </SettingsRow>
                    <SettingsRow
                        labelId="setting-video-retries"
                        label={$_('settings.detection.video_retries')}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="video-retries"
                            field="video_classification_max_retries"
                            type="number"
                            min={0}
                            value={videoClassificationMaxRetries}
                            ariaLabel={$_('settings.detection.video_retries')}
                            oninput={(v) => (videoClassificationMaxRetries = Number(v) || 0)}
                        />
                    </SettingsRow>
                    <SettingsRow
                        labelId="setting-video-frames"
                        label={$_('settings.detection.video_frames', { default: 'Frames' })}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="video-frames"
                            field="video_classification_frames"
                            type="number"
                            min={5}
                            max={100}
                            value={videoClassificationFrames}
                            ariaLabel={$_('settings.detection.video_frames', { default: 'Video Frames' })}
                            oninput={(v) => (videoClassificationFrames = Number(v) || 5)}
                        />
                    </SettingsRow>
                </div>
                <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('settings.detection.video_retry_note')}</p>
                <p class="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                    {$_('settings.detection.video_concurrency_follows_workers', { default: 'Clips are analysed as many at a time as there are background workers. The models classify one image per worker, so a separate concurrency setting could only queue jobs or starve workers.' })}
                </p>
            </div>
        {/if}
    </SettingsCard>
</div>

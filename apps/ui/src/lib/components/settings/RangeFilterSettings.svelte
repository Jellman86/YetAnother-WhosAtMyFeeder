<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import {
        fetchRangeFilterPreview,
        fetchRangeFilterSkips,
        fetchRangeFilterStatus,
        refreshRangeList,
        type RangeFilterPreview,
        type RangeFilterStatus,
        type RangePreviewSpecies,
        type RangeSkip
    } from '../../api/range-filter';
    import {
        rangeAge,
        rangeNeighbourCount,
        rangeProblemKey,
        rangeRegionNote,
        summarizeRangeStatus,
        type RangeAge
    } from '../../settings/range-filter';
    import { formatDateTime } from '../../utils/datetime';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';

    type RegionLevel = 'county' | 'state' | 'country';

    let {
        enabled = $bindable(false),
        regionLevel = $bindable<RegionLevel>('county'),
        onopenlocationsettings,
        onopenebirdsettings,
        onopenactivitylog,
        onopenmanualobservation
    }: {
        enabled: boolean;
        regionLevel: RegionLevel;
        onopenlocationsettings?: () => void;
        onopenebirdsettings?: () => void;
        onopenactivitylog?: () => void;
        onopenmanualobservation?: () => void;
    } = $props();

    const POLL_MS = 2000;
    const MAX_AGE_DAYS = 30;

    let status = $state.raw<RangeFilterStatus | null>(null);
    let statusError = $state<string | null>(null);
    let preview = $state.raw<RangeFilterPreview | null>(null);
    let previewError = $state<string | null>(null);
    let previewLoading = $state(false);
    let skips = $state.raw<RangeSkip[]>([]);
    let refreshRequested = $state(false);
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let destroyed = false;

    const summary = $derived(status ? summarizeRangeStatus(status) : null);
    const noLocation = $derived(status?.location_precision === 'none');
    const savedEnabled = $derived(status?.enabled ?? false);
    const unsaved = $derived(status !== null && enabled !== savedEnabled);
    const refreshing = $derived(Boolean(status?.refreshing) || refreshRequested);
    const listAge = $derived<RangeAge | null>(rangeAge(status?.refreshed_at));
    const regionText = $derived(status?.region ? status.region.name ?? status.region.code : '');
    const regionNote = $derived(status ? rangeRegionNote(status) : null);
    const neighbours = $derived(status ? rangeNeighbourCount(status) : 0);
    const problemKey = $derived(rangeProblemKey(status?.problem ?? status?.last_error));

    function ageText(age: RangeAge | null): string {
        if (!age) return '';
        if (age.unit === 'just_now') return $_('settings.range_filter.age_just_now', { default: 'just now' });
        if (age.unit === 'minutes') {
            return $_('settings.range_filter.age_minutes', { values: { count: age.count }, default: '{count, plural, one {# minute ago} other {# minutes ago}}' });
        }
        if (age.unit === 'hours') {
            return $_('settings.range_filter.age_hours', { values: { count: age.count }, default: '{count, plural, one {# hour ago} other {# hours ago}}' });
        }
        return $_('settings.range_filter.age_days', { values: { count: age.count }, default: '{count, plural, one {# day ago} other {# days ago}}' });
    }

    function problemText(): string {
        switch (problemKey) {
            case 'ebird_key_rejected':
                return $_('settings.range_filter.problem.ebird_key_rejected', { default: 'eBird rejected the API key.' });
            case 'ebird_unreachable':
                return $_('settings.range_filter.problem.ebird_unreachable', { default: 'eBird could not be reached.' });
            case 'ebird_error':
                return $_('settings.range_filter.problem.ebird_error', { default: 'eBird answered with an error.' });
            case 'region_not_found':
                return $_('settings.range_filter.problem.region_not_found', { default: 'No eBird region was found for your location.' });
            case 'taxonomy_unavailable':
                return $_('settings.range_filter.problem.taxonomy_unavailable', { default: "eBird's species list could not be read." });
            case 'response_too_large':
                return $_('settings.range_filter.problem.response_too_large', { default: 'eBird sent more data than is allowed.' });
            case 'invalid_response':
                return $_('settings.range_filter.problem.invalid_response', { default: 'eBird sent an answer that could not be read.' });
            case 'list_problem':
                return $_('settings.range_filter.problem.list_problem', { default: 'The list was empty or could not be matched to known species.' });
            case 'refresh_failed':
                return $_('settings.range_filter.problem.refresh_failed', { default: 'The refresh failed for an unexpected reason.' });
            default:
                return '';
        }
    }

    const chipLabel = $derived.by(() => {
        switch (summary?.tone) {
            case 'filtering':
                return $_('settings.range_filter.chip_filtering', { default: 'Filtering' });
            case 'waiting':
                return $_('settings.range_filter.chip_waiting', { default: 'Waiting' });
            case 'not_filtering':
                return $_('settings.range_filter.chip_not_filtering', { default: 'Not filtering' });
            default:
                return $_('settings.range_filter.chip_off', { default: 'Off' });
        }
    });

    const headline = $derived.by(() => {
        if (!status) return '';
        const count = status.species_in_range ?? 0;
        switch (status.reason) {
            case 'active':
                return $_('settings.range_filter.status_active', {
                    values: { count, region: regionText, age: ageText(listAge) },
                    default: 'Filtering to {count, plural, one {# species} other {# species}} recorded in {region} (eBird, refreshed {age}).'
                });
            case 'ready':
                return $_('settings.range_filter.status_ready', {
                    values: { count, region: regionText },
                    default: 'Off. Turning it on would filter to {count, plural, one {# species} other {# species}} recorded in {region}.'
                });
            case 'needs_location':
                return status.enabled
                    ? $_('settings.range_filter.status_needs_location_on', { default: 'Not filtering: needs your location.' })
                    : $_('settings.range_filter.status_needs_location', { default: 'Off: needs your location.' });
            case 'needs_ebird_key':
                return $_('settings.range_filter.status_needs_key', { default: 'Add an eBird API key to use range filtering.' });
            case 'waiting_for_list':
                if (refreshing) return $_('settings.range_filter.status_fetching', { default: 'Fetching the eBird list for your area…' });
                return status.enabled
                    ? $_('settings.range_filter.status_waiting', { default: 'Waiting for the first eBird list.' })
                    : $_('settings.range_filter.status_no_list', { default: 'No regional list yet. Fetch it to see the effect before turning the filter on.' });
            case 'lookup_failed':
                return $_('settings.range_filter.status_lookup_failed', {
                    values: { problem: problemText() },
                    default: 'Not filtering: the eBird list could not be fetched. {problem}'
                });
            case 'location_changed':
                return $_('settings.range_filter.status_location_changed', { default: 'Not filtering: your location or region setting changed, so the old list no longer applies.' });
            case 'list_stale':
                return $_('settings.range_filter.status_stale', {
                    values: { age: ageText(listAge), days: MAX_AGE_DAYS },
                    default: 'Not filtering: the list was fetched {age}. A list older than {days, plural, one {# day} other {# days}} is not trusted.'
                });
            case 'list_unusable':
                return $_('settings.range_filter.status_unusable', {
                    values: { problem: problemText() },
                    default: 'Not filtering: the stored list failed its checks. {problem}'
                });
            default:
                return '';
        }
    });

    const detail = $derived.by(() => {
        if (!status) return '';
        if (status.reason === 'needs_location') {
            return $_('settings.range_filter.status_needs_location_detail', { default: 'The filter uses the location set under Integrations to find your eBird region.' });
        }
        if (status.reason === 'needs_ebird_key') {
            return $_('settings.range_filter.status_needs_key_detail', { default: "eBird's regional list is the only range source. BirdNET-Go can show that a species is here, but it can never show that one is not, so on its own it filters nothing." });
        }
        if (status.reason === 'lookup_failed') {
            return $_('settings.range_filter.status_failed_open', { default: 'Nothing is filtered until a list is fetched. It is tried again every few hours.' });
        }
        return '';
    });

    async function loadStatus(): Promise<void> {
        try {
            const next = await fetchRangeFilterStatus();
            if (destroyed) return;
            const listChanged = next.refreshed_at !== status?.refreshed_at || next.reason !== status?.reason;
            status = next;
            statusError = null;
            if (!next.refreshing) refreshRequested = false;
            if (listChanged) void loadPreview();
            schedulePoll();
        } catch (failure) {
            if (destroyed) return;
            statusError = failure instanceof Error ? failure.message : $_('common.error', { default: 'Error' });
            refreshRequested = false;
        }
    }

    function schedulePoll(): void {
        if (pollTimer) clearTimeout(pollTimer);
        pollTimer = null;
        if (status?.refreshing || refreshRequested) pollTimer = setTimeout(() => void loadStatus(), POLL_MS);
    }

    async function loadPreview(): Promise<void> {
        if (!status?.region) {
            preview = null;
            return;
        }
        previewLoading = true;
        try {
            const [nextPreview, nextSkips] = await Promise.all([fetchRangeFilterPreview(), fetchRangeFilterSkips(5)]);
            if (destroyed) return;
            preview = nextPreview;
            skips = nextSkips;
            previewError = null;
        } catch (failure) {
            if (destroyed) return;
            previewError = failure instanceof Error ? failure.message : $_('common.error', { default: 'Error' });
        } finally {
            previewLoading = false;
        }
    }

    async function requestRefresh(): Promise<void> {
        refreshRequested = true;
        try {
            status = await refreshRangeList();
            statusError = null;
        } catch (failure) {
            statusError = failure instanceof Error ? failure.message : $_('common.error', { default: 'Error' });
            refreshRequested = false;
            return;
        }
        schedulePoll();
    }

    function speciesName(species: RangePreviewSpecies): string {
        return species.common_name || species.scientific_name;
    }

    onMount(() => {
        void loadStatus();
        void fetchRangeFilterSkips(5)
            .then((items) => {
                if (!destroyed) skips = items;
            })
            .catch(() => undefined);
    });

    onDestroy(() => {
        destroyed = true;
        if (pollTimer) clearTimeout(pollTimer);
    });

    const levelOptions = $derived([
        { value: 'county' as const, label: $_('settings.range_filter.level_county', { default: 'County' }) },
        { value: 'state' as const, label: $_('settings.range_filter.level_state', { default: 'State or province' }) },
        { value: 'country' as const, label: $_('settings.range_filter.level_country', { default: 'Country' }) }
    ]);

    function levelName(level: RegionLevel): string {
        return levelOptions.find((option) => option.value === level)?.label ?? level;
    }
</script>

{#snippet rangeIcon()}
    <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s-6-5.2-6-10a6 6 0 1 1 12 0c0 4.8-6 10-6 10Z" /><circle cx="12" cy="11" r="2.2" /></svg>
{/snippet}

<SettingsCard
    iconSnippet={rangeIcon}
    title={$_('settings.range_filter.title', { default: 'Range filter' })}
    description={$_('settings.range_filter.description', { default: 'Sets aside automatic identifications of birds eBird has never recorded in your region, so a European species is not named at a Californian feeder.' })}
>
    <div data-range-filter class="space-y-4">
        <div
            role="status"
            aria-live="polite"
            data-range-filter-status
            data-state={status?.reason ?? (statusError ? 'error' : 'loading')}
            class="rounded-2xl border p-4 {summary?.needsPerson ? 'border-attention-500/50 bg-attention-500/10' : 'border-line-soft bg-surface-raised/40'}"
        >
            {#if statusError && !status}
                <p class="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {$_('settings.range_filter.status_error', { values: { message: statusError }, default: 'The range filter status could not be loaded. {message}' })}
                </p>
                <button type="button" class="btn btn-secondary mt-3 min-h-11 px-4 text-sm" onclick={() => void loadStatus()}>
                    {$_('common.retry', { default: 'Retry' })}
                </button>
            {:else if !status}
                <p class="text-sm text-slate-600 dark:text-slate-300">{$_('settings.range_filter.status_loading', { default: 'Loading the range filter status…' })}</p>
            {:else}
                <div class="flex flex-wrap items-start gap-x-3 gap-y-2">
                    <span
                        data-range-filter-chip
                        class="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold {summary?.tone === 'filtering'
                            ? 'border-success-500/40 bg-success-500/10 text-success-800 dark:text-success-200'
                            : summary?.needsPerson
                              ? 'border-attention-500/50 bg-attention-500/15 text-attention-900 dark:text-attention-100'
                              : 'border-slate-300 bg-white/60 text-slate-700 dark:border-slate-600 dark:bg-slate-900/40 dark:text-slate-200'}"
                    >
                        {#if summary?.tone === 'filtering'}
                            <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m5 10.5 3 3 7-7" /></svg>
                        {:else if summary?.tone === 'waiting'}
                            <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="10" cy="10" r="7" /><path d="M10 6v4l2.5 1.5" /></svg>
                        {:else if summary?.needsPerson}
                            <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M10 6v5M10 14h.01" /><circle cx="10" cy="10" r="7.5" /></svg>
                        {:else}
                            <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 10h10" /></svg>
                        {/if}
                        {chipLabel}
                    </span>
                    <p class="min-w-0 flex-1 text-sm font-semibold leading-relaxed text-slate-900 dark:text-white" data-range-filter-headline>{headline}</p>
                </div>
                {#if detail}
                    <p class="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-300">{detail}</p>
                {/if}
                {#if unsaved}
                    <p class="mt-2 text-xs font-semibold text-slate-700 dark:text-slate-200" data-range-filter-unsaved>
                        {enabled
                            ? $_('settings.range_filter.unsaved_on', { default: 'Apply settings to turn the filter on.' })
                            : $_('settings.range_filter.unsaved_off', { default: 'Apply settings to turn the filter off.' })}
                    </p>
                {/if}
                {#if summary?.action === 'location' && onopenlocationsettings}
                    <button type="button" class="btn btn-secondary mt-3 min-h-11 px-4 text-sm" onclick={onopenlocationsettings} data-range-filter-open-location>
                        {$_('settings.range_filter.open_location', { default: 'Set location' })}
                    </button>
                {:else if summary?.action === 'ebird_key' && onopenebirdsettings}
                    <button type="button" class="btn btn-secondary mt-3 min-h-11 px-4 text-sm" onclick={onopenebirdsettings} data-range-filter-open-ebird>
                        {$_('settings.range_filter.open_ebird', { default: 'Add eBird key' })}
                    </button>
                {/if}
                {#if statusError}
                    <p class="mt-2 text-xs text-slate-600 dark:text-slate-300" role="alert">
                        {$_('settings.range_filter.status_error', { values: { message: statusError }, default: 'The range filter status could not be loaded. {message}' })}
                    </p>
                {/if}
            {/if}
        </div>

        <SettingsRow
            labelId="setting-range-filter"
            descriptionId="setting-range-filter-desc"
            label={$_('settings.range_filter.toggle', { default: 'Check new detections against your region' })}
            description={noLocation
                ? $_('settings.range_filter.toggle_disabled_location', { default: "Set a location first. The filter needs it to know which region's birds to expect." })
                : $_('settings.range_filter.toggle_desc', { default: 'Off by default. Applies to new detections only; nothing already recorded is changed.' })}
        >
            <SettingsToggle
                checked={enabled}
                labelledBy="setting-range-filter"
                srLabel={$_('settings.range_filter.toggle', { default: 'Check new detections against your region' })}
                disabled={noLocation && !enabled}
                onchange={(next) => (enabled = next)}
            />
        </SettingsRow>

        {#if status && status.location_precision !== 'none' && status.ebird_configured}
            <dl class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2" data-range-filter-facts>
                <div class="rounded-xl bg-surface-raised/70 p-3">
                    <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('settings.range_filter.source_label', { default: 'Source' })}</dt>
                    <dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{$_('settings.range_filter.source_value', { default: 'eBird regional species list' })}</dd>
                </div>
                <div class="rounded-xl bg-surface-raised/70 p-3">
                    <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('settings.range_filter.region_label', { default: 'Region' })}</dt>
                    <dd class="mt-0.5 font-semibold text-slate-900 dark:text-white" data-range-filter-region>
                        {#if status.region}
                            {regionText}
                            <span class="block text-xs font-medium text-slate-600 dark:text-slate-300">{levelName(status.region.level)}</span>
                        {:else}
                            {$_('settings.range_filter.region_none', { default: 'Not fetched yet' })}
                        {/if}
                    </dd>
                </div>
                <div class="rounded-xl bg-surface-raised/70 p-3">
                    <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('settings.range_filter.species_label', { default: 'Species in range' })}</dt>
                    <dd class="mt-0.5 font-semibold tabular-nums text-slate-900 dark:text-white" data-range-filter-species>
                        {status.species_in_range ?? '–'}
                    </dd>
                </div>
                <div class="rounded-xl bg-surface-raised/70 p-3">
                    <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('settings.range_filter.refreshed_label', { default: 'Refreshed' })}</dt>
                    <dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">
                        {#if status.refreshed_at}
                            <time datetime={status.refreshed_at} title={formatDateTime(status.refreshed_at)}>{ageText(listAge)}</time>
                        {:else}
                            {$_('settings.range_filter.never', { default: 'Never' })}
                        {/if}
                    </dd>
                </div>
            </dl>

            <ul class="space-y-1.5 text-xs leading-relaxed text-slate-600 dark:text-slate-300" data-range-filter-notes>
                <li>{$_('settings.range_filter.freshness', { values: { days: MAX_AGE_DAYS }, default: 'Refreshed weekly in the background. A list older than {days, plural, one {# day} other {# days}} stops filtering until it is refreshed.' })}</li>
                {#if status.last_error && status.region && status.reason === 'active'}
                    <li data-range-filter-last-error>{$_('settings.range_filter.last_refresh_failed', { values: { problem: problemText() }, default: 'The last refresh failed. {problem} The current list is still used until it is too old.' })}</li>
                {/if}
                {#if regionNote === 'approximate'}
                    <li>{$_('settings.range_filter.region_approximate', { default: 'Your location is approximate, so a state list is used rather than a county.' })}</li>
                {:else if regionNote === 'country_only'}
                    <li>{$_('settings.range_filter.region_country_only', { default: 'Only a country is set, so the country list is used.' })}</li>
                {:else if regionNote === 'county_too_short'}
                    <li>{$_('settings.range_filter.region_county_too_short', { default: 'The county list was too short to trust, so the state list is used.' })}</li>
                {/if}
                {#if neighbours > 0}
                    <li>{$_('settings.range_filter.region_neighbours', { values: { count: neighbours }, default: '{count, plural, one {Combined with # neighbouring county, because your feeder is near a border.} other {Combined with # neighbouring counties, because your feeder is near a border.}}' })}</li>
                {/if}
                {#if status.heard_species > 0}
                    <li data-range-filter-heard>{$_('settings.range_filter.heard', { values: { count: status.heard_species }, default: '{count, plural, one {# species BirdNET-Go heard here in the last year also counts as present.} other {# species BirdNET-Go heard here in the last year also count as present.}}' })}</li>
                {:else if status.birdnet_enabled}
                    <li>{$_('settings.range_filter.heard_none', { default: 'Species BirdNET-Go hears here count as present too. It adds evidence and never removes any.' })}</li>
                {/if}
                {#if status.model && status.model.unmatched > 0}
                    <li data-range-filter-unmatched>{$_('settings.range_filter.unmatched', { values: { count: status.model.unmatched }, default: '{count, plural, one {# model label could not be matched to eBird and is never filtered.} other {# model labels could not be matched to eBird and are never filtered.}}' })}</li>
                {/if}
                <li>{$_('settings.range_filter.seasons', { default: 'The list covers every season together, so a summer visitor counts as present all year.' })}</li>
            </ul>

            <div class="flex flex-wrap items-center gap-3">
                <button
                    type="button"
                    class="btn btn-secondary min-h-11 px-4 text-sm"
                    onclick={() => void requestRefresh()}
                    disabled={refreshing}
                    aria-disabled={refreshing}
                    data-range-filter-refresh
                >
                    {#if refreshing}
                        {$_('settings.range_filter.refreshing', { default: 'Refreshing…' })}
                    {:else if status.region}
                        {$_('settings.range_filter.refresh', { default: 'Refresh list' })}
                    {:else}
                        {$_('settings.range_filter.fetch', { default: 'Fetch list' })}
                    {/if}
                </button>
            </div>

            <SettingsRow
                labelId="setting-range-filter-level"
                label={$_('settings.range_filter.level_label', { default: 'Finest region' })}
                description={$_('settings.range_filter.level_desc', { default: 'A county list is tighter. An approximate location or a country alone always uses a coarser region.' })}
            >
                <SettingsSelect
                    id="range-filter-level"
                    value={regionLevel}
                    options={levelOptions}
                    ariaLabel={$_('settings.range_filter.level_label', { default: 'Finest region' })}
                    onchange={(next) => (regionLevel = next)}
                />
            </SettingsRow>
        {/if}

        <section class="space-y-2" aria-labelledby="range-filter-how" data-range-filter-how>
            <h4 id="range-filter-how" class="text-sm font-bold text-slate-900 dark:text-white">{$_('settings.range_filter.how_title', { default: 'What happens to a bird outside the range' })}</h4>
            <ul class="list-disc space-y-1.5 pl-5 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                <li>{$_('settings.range_filter.how_fallback', { default: "If the model's top answer has never been recorded in your region, its next answer that has been recorded, and still clears your confidence threshold, is used instead. The record keeps a note of what the model said first." })}</li>
                <li>{$_('settings.range_filter.how_skip', { default: 'If no answer qualifies, the detection is not recorded. It is listed below and in the activity log, so a genuine rarity can still be recorded by hand.' })}</li>
                <li>{$_('settings.range_filter.how_open', { default: 'Whenever the list is missing, out of date or unreachable, nothing is filtered.' })}</li>
                <li>{$_('settings.range_filter.how_owner', { default: 'Species you choose yourself are never filtered.' })}</li>
            </ul>
        </section>

        {#if status?.region}
            <section class="space-y-3" aria-labelledby="range-filter-preview" data-range-filter-preview>
                <div>
                    <h4 id="range-filter-preview" class="text-sm font-bold text-slate-900 dark:text-white">{$_('settings.range_filter.preview_title', { default: 'Preview' })}</h4>
                    <p class="mt-0.5 text-xs leading-relaxed text-slate-600 dark:text-slate-300">{$_('settings.range_filter.preview_desc', { default: 'What the filter would set aside with this list and the current model. Detections already recorded stay in your history.' })}</p>
                </div>
                {#if previewLoading && !preview}
                    <p class="text-xs text-slate-600 dark:text-slate-300" role="status">{$_('settings.range_filter.preview_loading', { default: 'Loading the preview…' })}</p>
                {:else if previewError}
                    <p class="text-xs text-slate-700 dark:text-slate-200" role="alert">{$_('settings.range_filter.preview_error', { values: { message: previewError }, default: 'The preview could not be loaded. {message}' })}</p>
                {:else if preview && !preview.available}
                    <p class="text-xs text-slate-600 dark:text-slate-300">{$_('settings.range_filter.preview_unavailable', { default: 'A preview needs a current list for this location. Refresh the list to see one.' })}</p>
                {:else if preview}
                    <div class="rounded-xl bg-surface-raised/70 p-3">
                        <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{$_('settings.range_filter.preview_seen_heading', { values: { count: preview.window_days }, default: '{count, plural, one {Recorded here in the last # day} other {Recorded here in the last # days}}' })}</p>
                        {#if preview.recently_seen.length > 0}
                            <ul class="mt-2 divide-y divide-line-soft" data-range-filter-preview-seen>
                                {#each preview.recently_seen as species (species.species_id)}
                                    <li class="flex items-baseline justify-between gap-3 py-1.5 text-sm">
                                        <span class="min-w-0">
                                            <span class="font-semibold text-slate-900 dark:text-white">{speciesName(species)}</span>
                                            {#if species.common_name}<span class="ml-1 text-xs italic text-slate-500 dark:text-slate-400">{species.scientific_name}</span>{/if}
                                        </span>
                                        <span class="shrink-0 text-xs tabular-nums text-slate-600 dark:text-slate-300">{$_('settings.range_filter.preview_seen_detections', { values: { count: species.detections ?? 0 }, default: '{count, plural, one {# detection} other {# detections}}' })}</span>
                                    </li>
                                {/each}
                            </ul>
                        {:else}
                            <p class="mt-1 text-xs text-slate-600 dark:text-slate-300" data-range-filter-preview-none>{$_('settings.range_filter.preview_seen_none', { default: 'Nothing recorded here in that time would have been set aside.' })}</p>
                        {/if}
                    </div>
                    {#if preview.model_out_of_range_total === null || preview.model_out_of_range_total === undefined}
                        <p class="text-xs text-slate-600 dark:text-slate-300">{$_('settings.range_filter.preview_model_unknown', { default: "The current model's labels are not in the species catalogue, so its effect cannot be previewed. Its labels are never filtered." })}</p>
                    {:else}
                        <p class="text-xs text-slate-600 dark:text-slate-300" data-range-filter-preview-total>{$_('settings.range_filter.preview_model_total', { values: { count: preview.model_out_of_range_total }, default: '{count, plural, one {The current model can name # species this list treats as outside the range.} other {The current model can name # species this list treats as outside the range.}}' })}</p>
                        {#if preview.examples.length > 0}
                            <p class="text-xs text-slate-600 dark:text-slate-300">
                                <span class="font-semibold">{$_('settings.range_filter.preview_examples', { default: 'For example:' })}</span>
                                {preview.examples.map(speciesName).join(', ')}
                            </p>
                        {/if}
                    {/if}
                {/if}
            </section>
        {/if}

        <section class="space-y-2" aria-labelledby="range-filter-skips" data-range-filter-skips>
            <h4 id="range-filter-skips" class="text-sm font-bold text-slate-900 dark:text-white">{$_('settings.range_filter.skips_title', { default: 'Recently set aside' })}</h4>
            {#if skips.length === 0}
                <p class="text-xs text-slate-600 dark:text-slate-300">{$_('settings.range_filter.skips_empty', { default: 'Nothing has been set aside as outside the range.' })}</p>
            {:else}
                <ul class="divide-y divide-line-soft rounded-xl bg-surface-raised/70 px-3">
                    {#each skips as skip (skip.frigate_event)}
                        <li class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-2 text-sm">
                            <span class="min-w-0 font-semibold text-slate-900 dark:text-white">{skip.label}</span>
                            <span class="text-xs tabular-nums text-slate-600 dark:text-slate-300">
                                {$_('settings.range_filter.skips_score', { values: { score: Math.round(skip.score * 100) }, default: '{score}% confidence' })}
                                {#if skip.detected_at}<span aria-hidden="true"> · </span><time datetime={skip.detected_at}>{formatDateTime(skip.detected_at)}</time>{/if}
                                {#if skip.camera}<span aria-hidden="true"> · </span>{skip.camera}{/if}
                            </span>
                        </li>
                    {/each}
                </ul>
                <p class="text-xs leading-relaxed text-slate-600 dark:text-slate-300">{$_('settings.range_filter.skips_recover', { default: 'To keep a genuine rarity, record it by hand. Frigate keeps the clip for as long as its retention allows.' })}</p>
            {/if}
            <div class="flex flex-wrap gap-3">
                {#if onopenactivitylog}
                    <button type="button" class="btn btn-ghost min-h-11 px-3 text-sm" onclick={onopenactivitylog} data-range-filter-open-log>
                        {$_('settings.range_filter.skips_open_log', { default: 'Open the activity log' })}
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                    </button>
                {/if}
                {#if onopenmanualobservation}
                    <button type="button" class="btn btn-ghost min-h-11 px-3 text-sm" onclick={onopenmanualobservation} data-range-filter-record>
                        {$_('settings.range_filter.skips_add_manually', { default: 'Record a sighting by hand' })}
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                    </button>
                {/if}
            </div>
        </section>
    </div>
</SettingsCard>

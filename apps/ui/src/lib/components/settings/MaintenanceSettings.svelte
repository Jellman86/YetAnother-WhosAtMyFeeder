<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { BackfillResult, WeatherBackfillResult, TaxonomySyncStatus, AnalysisStatus, TimezoneRepairPreview } from '../../api';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';

    // Jobs that repair or fill in the history, and the actions that delete it. Every button here
    // acts at once; only the two settings (the daily analysis and jobs at once) wait for Save.
    let {
        maintenanceMaxConcurrent = $bindable(1),
        autoAnalyzeUnknowns = $bindable(false),
        clearingFavorites,
        taxonomyStatus,
        syncingTaxonomy,
        timezoneRepairPreview,
        previewingTimezoneRepair,
        applyingTimezoneRepair,
        backfillDateRange = $bindable<'day' | 'week' | 'month' | 'custom'>('week'),
        backfillStartDate = $bindable(''),
        backfillEndDate = $bindable(''),
        backfillCustomError = null,
        backfillCustomValid = true,
        backfilling,
        backfillResult,
        backfillTotal = $bindable(0),
        weatherBackfilling,
        weatherBackfillResult,
        weatherBackfillTotal = $bindable(0),
        resettingDatabase,
        clearingFeedback,
        analyzingUnknowns,
        analysisStatus,
        analysisTotal,
        handleClearFavorites,
        handleStartTaxonomySync,
        handlePreviewTimezoneRepair,
        handleApplyTimezoneRepair,
        handleBackfill,
        handleWeatherBackfill,
        handleAnalyzeUnknowns,
        handleResetDatabase,
        handleClearFeedback,
    }: {
        maintenanceMaxConcurrent: number;
        autoAnalyzeUnknowns: boolean;
        clearingFavorites: boolean;
        taxonomyStatus: TaxonomySyncStatus | null;
        syncingTaxonomy: boolean;
        timezoneRepairPreview: TimezoneRepairPreview | null;
        previewingTimezoneRepair: boolean;
        applyingTimezoneRepair: boolean;
        backfillDateRange: 'day' | 'week' | 'month' | 'custom';
        backfillStartDate: string;
        backfillEndDate: string;
        backfillCustomError: string | null;
        backfillCustomValid: boolean;
        backfilling: boolean;
        backfillResult: BackfillResult | null;
        backfillTotal: number;
        weatherBackfilling: boolean;
        weatherBackfillResult: WeatherBackfillResult | null;
        weatherBackfillTotal: number;
        resettingDatabase: boolean;
        clearingFeedback: boolean;
        analyzingUnknowns: boolean;
        analysisStatus: AnalysisStatus | null;
        analysisTotal: number;
        handleClearFavorites: () => Promise<void>;
        handleStartTaxonomySync: () => Promise<void>;
        handlePreviewTimezoneRepair: () => Promise<void>;
        handleApplyTimezoneRepair: () => Promise<void>;
        handleBackfill: () => Promise<void>;
        handleWeatherBackfill: () => Promise<void>;
        handleAnalyzeUnknowns: () => Promise<void>;
        handleResetDatabase: () => Promise<void>;
        handleClearFeedback: () => Promise<void>;
    } = $props();

    const safeCount = (value: unknown): number => {
        const parsed = Number(value ?? 0);
        return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
    };
    const fmtCount = (value: unknown): string => safeCount(value).toLocaleString();
    const formatSafeTime = (value: unknown): string => {
        if (!value) return '';
        const date = new Date(String(value));
        if (Number.isNaN(date.getTime())) return '';
        return date.toLocaleTimeString();
    };
    const formatPreviewTimestamp = (value: unknown): string => {
        if (!value) return '';
        return String(value).replace('T', ' ').replace(/Z$/, ' UTC');
    };

    const formatDateOnly = (date: Date): string => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };

    const parseDateOnly = (value: string): Date | null => {
        const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
        if (!match) return null;
        const year = Number(match[1]);
        const month = Number(match[2]);
        const day = Number(match[3]);
        const date = new Date(year, month - 1, day);
        if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
        date.setHours(0, 0, 0, 0);
        return date;
    };

    const todayDateOnly = (): string => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return formatDateOnly(today);
    };

    const setCustomRangeDays = (days: number) => {
        const end = new Date();
        end.setHours(0, 0, 0, 0);
        const start = new Date(end);
        start.setDate(end.getDate() - (days - 1));
        backfillStartDate = formatDateOnly(start);
        backfillEndDate = formatDateOnly(end);
    };

    const clearCustomRange = () => {
        backfillStartDate = '';
        backfillEndDate = todayDateOnly();
    };

    $effect(() => {
        if (backfillDateRange !== 'custom') return;
        if (!parseDateOnly(backfillEndDate)) backfillEndDate = todayDateOnly();
    });

    const timezoneRepairCandidates = $derived(timezoneRepairPreview?.summary.repair_candidate_count ?? 0);

    const buttonNeutralClass = 'btn btn-secondary min-h-11 px-4 py-3';
    const buttonDangerOutlineClass = 'btn btn-danger min-h-11 px-4 py-3';
    const buttonDangerSolidClass = 'btn btn-danger-solid min-h-11 px-4 py-3';
</script>

{#snippet spinner()}
    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
{/snippet}

<div class="space-y-6">
    <SettingsCard
        title={$_('settings.data.taxonomy_title')}
        description={$_('settings.data.taxonomy_desc')}
    >
        {#if taxonomyStatus}
            {#if taxonomyStatus.is_running}
                <div class="flex items-center justify-between gap-3 text-brand-700 dark:text-brand-300">
                    <span class="text-sm font-semibold">{taxonomyStatus.message || taxonomyStatus.current_item || $_('settings.data.taxonomy_repairing')}</span>
                    <span class="text-xs font-bold">{taxonomyStatus.processed} / {taxonomyStatus.total}</span>
                </div>
            {:else if taxonomyStatus.current_item || taxonomyStatus.message || taxonomyStatus.error}
                <div class="border-t border-line-soft pt-4 flex items-center gap-3">
                    {#if taxonomyStatus.error}
                        <div class="w-2 h-2 rounded-full bg-red-500"></div>
                        <p class="text-xs font-bold text-red-700 dark:text-red-300">{taxonomyStatus.error}</p>
                    {:else}
                        <div class="w-2 h-2 rounded-full bg-brand-500"></div>
                        <p class="text-xs font-bold text-slate-600 dark:text-slate-300">{taxonomyStatus.message || taxonomyStatus.current_item}</p>
                    {/if}
                </div>
            {/if}
        {/if}

        <div>
            <button
                type="button"
                onclick={handleStartTaxonomySync}
                disabled={taxonomyStatus?.is_running || syncingTaxonomy}
                aria-label={$_('settings.data.taxonomy_run_button')}
                class={buttonNeutralClass}
            >
                {#if syncingTaxonomy || taxonomyStatus?.is_running}{@render spinner()}{/if}
                {$_('settings.data.taxonomy_run_button')}
            </button>
        </div>
    </SettingsCard>

    <SettingsCard
        title={$_('settings.data.timezone_repair_title', { default: 'Timezone repair' })}
        description={$_('settings.data.timezone_repair_desc', { default: 'Validate older detection timestamps against Frigate and repair only safe whole-hour timezone offsets.' })}
    >
        <p class="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            {$_('settings.data.timezone_repair_note', { default: 'This only updates detections when Frigate still has the matching event and the timestamp difference looks like a real timezone offset.' })}
        </p>

        {#if timezoneRepairPreview}
            <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div class="">
                    <p class="text-lg font-bold text-slate-900 dark:text-white">{fmtCount(timezoneRepairPreview.summary.scanned_count)}</p>
                    <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.data.timezone_repair_scanned', { default: 'Scanned' })}</p>
                </div>
                <div class="text-attention-800 dark:text-attention-200">
                    <p class="text-lg font-bold text-attention-600 dark:text-attention-400">{fmtCount(timezoneRepairPreview.summary.repair_candidate_count)}</p>
                    <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.data.timezone_repair_candidates', { default: 'Repair candidates' })}</p>
                </div>
                <div class="">
                    <p class="text-lg font-bold text-slate-900 dark:text-white">{fmtCount(timezoneRepairPreview.summary.missing_frigate_event_count)}</p>
                    <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.data.timezone_repair_missing', { default: 'Missing in Frigate' })}</p>
                </div>
                <div class="">
                    <p class="text-lg font-bold text-red-700 dark:text-red-400">{fmtCount(timezoneRepairPreview.summary.lookup_error_count)}</p>
                    <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.data.timezone_repair_lookup_errors', { default: 'Lookup errors' })}</p>
                </div>
                <div class="">
                    <p class="text-lg font-bold text-slate-900 dark:text-white">{fmtCount(timezoneRepairPreview.summary.unsupported_delta_count)}</p>
                    <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.data.timezone_repair_unsupported', { default: 'Unsupported delta' })}</p>
                </div>
            </div>

            {#if timezoneRepairPreview.candidates.length > 0}
                <div class="">
                    <div class="border-t border-line-soft pt-4 px-5 border-b">
                        <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.data.timezone_repair_preview_list', { default: 'Preview' })}</p>
                    </div>
                    <div class="divide-y divide-slate-200 dark:divide-slate-700">
                        {#each timezoneRepairPreview.candidates.slice(0, 5) as candidate}
                            <div class="px-5 py-4 space-y-1">
                                <div class="flex items-center justify-between gap-3">
                                    <p class="text-sm font-bold text-slate-900 dark:text-white truncate">{candidate.display_name || candidate.frigate_event}</p>
                                    <span class="text-xs font-bold {candidate.status === 'repair_candidate' ? 'text-attention-600 dark:text-attention-400' : 'text-slate-600 dark:text-slate-400'}">{candidate.status.replace(/_/g, ' ')}</span>
                                </div>
                                <p class="text-xs text-slate-600 dark:text-slate-400 truncate">{candidate.frigate_event}</p>
                                <div class="text-xs text-slate-600 dark:text-slate-300">
                                    <span>{formatPreviewTimestamp(candidate.stored_detection_time)}</span>
                                    {#if candidate.repaired_detection_time}<span> -> {formatPreviewTimestamp(candidate.repaired_detection_time)}</span>{/if}
                                    {#if candidate.delta_hours != null}<span class="ml-2">({candidate.delta_hours > 0 ? '+' : ''}{candidate.delta_hours}h)</span>{/if}
                                </div>
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
        {/if}

        <div class="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <button
                type="button"
                onclick={handlePreviewTimezoneRepair}
                disabled={previewingTimezoneRepair || applyingTimezoneRepair}
                aria-label={$_('settings.data.timezone_repair_preview_button', { default: 'Scan for timezone issues' })}
                class={buttonNeutralClass}
            >
                {previewingTimezoneRepair
                    ? $_('settings.data.timezone_repair_preview_loading', { default: 'Scanning...' })
                    : $_('settings.data.timezone_repair_preview_button', { default: 'Scan for timezone issues' })}
            </button>
            <button
                type="button"
                onclick={handleApplyTimezoneRepair}
                disabled={previewingTimezoneRepair || applyingTimezoneRepair || timezoneRepairCandidates === 0}
                aria-label={$_('settings.data.timezone_repair_apply_button', { default: 'Apply timezone repair' })}
                class={buttonNeutralClass}
            >
                {applyingTimezoneRepair
                    ? $_('settings.data.timezone_repair_apply_loading', { default: 'Repairing...' })
                    : $_('settings.data.timezone_repair_apply_button', { default: 'Apply timezone repair' })}
            </button>
        </div>
    </SettingsCard>

    <SettingsCard
        title={$_('settings.data.backfill_title')}
        description={$_('settings.data.backfill_desc')}
    >
        <SettingsRow
            labelId="setting-backfill-window"
            label={$_('settings.data.backfill_window')}
            layout="stacked"
        >
            <SettingsSelect
                id="backfill-range"
                value={backfillDateRange}
                ariaLabel={$_('settings.data.backfill_window')}
                options={[
                    { value: 'day', label: $_('settings.data.backfill_24h') },
                    { value: 'week', label: $_('settings.data.backfill_week') },
                    { value: 'month', label: $_('settings.data.backfill_month') },
                    { value: 'custom', label: $_('settings.data.backfill_custom') }
                ]}
                onchange={(v) => (backfillDateRange = v as 'day' | 'week' | 'month' | 'custom')}
            />
        </SettingsRow>

        {#if backfillDateRange === 'custom'}
            <div class="space-y-3 animate-in fade-in slide-in-from-top-2">
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label for="backfill-from-date" class="block text-sm font-semibold text-slate-700 mb-2 dark:text-slate-200">
                            {$_('settings.data.backfill_from', { default: 'From' })}
                        </label>
                        <input
                            id="backfill-from-date"
                            type="date"
                            bind:value={backfillStartDate}
                            max={backfillEndDate || todayDateOnly()}
                            aria-label={$_('settings.data.backfill_from', { default: 'From date' })}
                            class="input-base"
                        />
                    </div>
                    <div>
                        <label for="backfill-to-date" class="block text-sm font-semibold text-slate-700 mb-2 dark:text-slate-200">
                            {$_('settings.data.backfill_to', { default: 'To' })}
                        </label>
                        <input
                            id="backfill-to-date"
                            type="date"
                            bind:value={backfillEndDate}
                            min={backfillStartDate || undefined}
                            max={todayDateOnly()}
                            aria-label={$_('settings.data.backfill_to', { default: 'To date' })}
                            class="input-base"
                        />
                    </div>
                </div>
                <div class="grid grid-cols-3 gap-2">
                    <button type="button" class="btn btn-ghost min-h-11 px-3 py-2" onclick={() => setCustomRangeDays(7)}>7D</button>
                    <button type="button" class="btn btn-ghost min-h-11 px-3 py-2" onclick={() => setCustomRangeDays(30)}>30D</button>
                    <button type="button" class="btn btn-ghost min-h-11 px-3 py-2" onclick={clearCustomRange}>{$_('common.clear', { default: 'Clear' })}</button>
                </div>
                {#if backfillCustomError}
                    <p class="text-xs font-bold text-red-700 dark:text-red-300">{backfillCustomError}</p>
                {/if}
            </div>
        {/if}

        {#if backfillResult}
            {#if backfillResult.message}
                <p class="flex items-start gap-2 {backfilling ? 'text-brand-800 dark:text-brand-200' : safeCount(backfillResult.errors) > 0 ? 'text-attention-800 dark:text-attention-200' : 'text-slate-700 dark:text-slate-300'} text-sm" aria-live="polite">
                    {#if backfilling}{@render spinner()}{/if}
                    <span>{backfillResult.message}</span>
                </p>
            {/if}
            <dl class="grid grid-cols-2 divide-x divide-y divide-slate-200 border-y border-slate-200 text-center dark:divide-slate-700 dark:border-slate-700 sm:grid-cols-5 sm:divide-y-0">
                <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_total')}</dt><dd class="order-1 text-base font-bold tabular-nums text-slate-900 dark:text-white">{safeCount(backfillResult.processed)}</dd></div>
                <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_new')}</dt><dd class="order-1 text-base font-bold tabular-nums text-slate-900 dark:text-white">{safeCount(backfillResult.new_detections)}</dd></div>
                <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_updated')}</dt><dd class="order-1 text-base font-bold tabular-nums text-slate-900 dark:text-white">{safeCount(backfillResult.updated)}</dd></div>
                <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_skip')}</dt><dd class="order-1 text-base font-bold tabular-nums text-slate-600 dark:text-slate-300">{safeCount(backfillResult.skipped)}</dd></div>
                <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_err')}</dt><dd class="order-1 text-base font-bold tabular-nums {safeCount(backfillResult.errors) > 0 ? 'text-rose-700 dark:text-rose-400' : 'text-slate-600 dark:text-slate-300'}">{safeCount(backfillResult.errors)}</dd></div>
            </dl>
            {#if backfillResult.skipped_reasons && Object.keys(backfillResult.skipped_reasons).length > 0}
                <div class="">
                    <p class="text-sm font-semibold text-slate-700 mb-2 dark:text-slate-200">{$_('settings.data.backfill_skipped_breakdown')}</p>
                    <div class="grid grid-cols-1 gap-2">
                        {#each Object.entries(backfillResult.skipped_reasons) as [reason, count]}
                            <div class="flex justify-between items-center text-xs">
                                <span class="text-slate-600 dark:text-slate-400">
                                    {$_(`settings.data.backfill_reasons.${reason}`, { default: reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) })}
                                </span>
                                <span class="font-bold text-slate-700 dark:text-slate-300">{count}</span>
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
            {#if backfillResult.error_reasons && Object.keys(backfillResult.error_reasons).length > 0}
                <div>
                    <p class="mb-2 text-xs font-semibold text-rose-700 dark:text-rose-300">{$_('settings.data.backfill_error_breakdown', { default: 'Errors that need attention' })}</p>
                    <div class="space-y-1.5">
                        {#each Object.entries(backfillResult.error_reasons) as [reason, count]}
                            <div class="flex items-center justify-between gap-3 text-xs">
                                <span class="wrap-break-word text-slate-600 dark:text-slate-300">{$_(`settings.data.backfill_reasons.${reason}`, { default: reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) })}</span>
                                <span class="font-bold tabular-nums text-rose-700 dark:text-rose-300">{count}</span>
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
        {/if}

        <div>
            <button
                type="button"
                onclick={handleBackfill}
                disabled={backfilling || weatherBackfilling || !backfillCustomValid}
                aria-label={$_('settings.data.backfill_scan_button')}
                class={buttonNeutralClass}
            >
                {#if backfilling}{@render spinner()}{/if}
                {backfilling ? $_('settings.data.backfill_scanning') : $_('settings.data.backfill_scan_button')}
            </button>
        </div>

        <AdvancedSection
            id="data-backfill-weather"
            title={$_('settings.data.weather_backfill_title')}
        >
            {#if weatherBackfillResult}
                {#if weatherBackfillResult.message}<p class="text-sm text-slate-600 dark:text-slate-300" aria-live="polite">{weatherBackfillResult.message}</p>{/if}
                <dl class="grid grid-cols-2 divide-x divide-y divide-slate-200 border-y border-slate-200 text-center dark:divide-slate-700 dark:border-slate-700 sm:grid-cols-4 sm:divide-y-0">
                    <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_total')}</dt><dd class="order-1 text-base font-bold tabular-nums text-slate-900 dark:text-white">{safeCount(weatherBackfillResult.processed)}</dd></div>
                    <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_updated', { default: 'Updated' })}</dt><dd class="order-1 text-base font-bold tabular-nums text-slate-900 dark:text-white">{safeCount(weatherBackfillResult.updated)}</dd></div>
                    <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_skip')}</dt><dd class="order-1 text-base font-bold tabular-nums text-slate-600 dark:text-slate-300">{safeCount(weatherBackfillResult.skipped)}</dd></div>
                    <div class="flex flex-col px-2 py-3"><dt class="order-2 text-xs font-semibold text-slate-600 dark:text-slate-400">{$_('settings.data.backfill_err')}</dt><dd class="order-1 text-base font-bold tabular-nums {safeCount(weatherBackfillResult.errors) > 0 ? 'text-rose-700 dark:text-rose-400' : 'text-slate-600 dark:text-slate-300'}">{safeCount(weatherBackfillResult.errors)}</dd></div>
                </dl>
                {#if weatherBackfillResult.error_reasons && Object.keys(weatherBackfillResult.error_reasons).length > 0}
                    <div>
                        <p class="mb-2 text-xs font-semibold text-rose-700 dark:text-rose-300">{$_('settings.data.backfill_error_breakdown', { default: 'Errors that need attention' })}</p>
                        {#each Object.entries(weatherBackfillResult.error_reasons) as [reason, count]}
                            <div class="flex items-center justify-between gap-3 text-xs">
                                <span class="wrap-break-word text-slate-600 dark:text-slate-300">{$_(`settings.data.backfill_reasons.${reason}`, { default: reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) })}</span>
                                <span class="font-bold tabular-nums text-rose-700 dark:text-rose-300">{count}</span>
                            </div>
                        {/each}
                    </div>
                {/if}
            {/if}
            <button
                type="button"
                onclick={handleWeatherBackfill}
                disabled={weatherBackfilling || backfilling || !backfillCustomValid}
                aria-label={$_('settings.data.weather_backfill_button')}
                class={buttonNeutralClass}
            >
                {#if weatherBackfilling}{@render spinner()}{/if}
                {weatherBackfilling ? $_('settings.data.weather_backfill_filling') : $_('settings.data.weather_backfill_button')}
            </button>
        </AdvancedSection>
    </SettingsCard>

    <SettingsCard
        title={$_('settings.data.batch_analysis_title')}
        description={$_('settings.data.batch_analysis_desc')}
    >
        <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">
            {$_('settings.data.batch_analysis_long_desc')}
        </p>

        <div>
            <button
                type="button"
                onclick={handleAnalyzeUnknowns}
                disabled={analyzingUnknowns}
                aria-label={$_('settings.data.batch_analysis_button')}
                class={buttonNeutralClass}
            >
                {#if analyzingUnknowns}{@render spinner()}{/if}
                {analyzingUnknowns ? $_('settings.data.batch_analysis_queueing') : $_('settings.data.batch_analysis_button')}
            </button>
        </div>

        <SettingsRow
            labelId="setting-auto-analyze"
            label={$_('settings.data.auto_analyze_unknowns', { default: 'Run automatically (daily)' })}
        >
            <SettingsToggle
                checked={autoAnalyzeUnknowns}
                labelledBy="setting-auto-analyze"
                srLabel={$_('settings.data.auto_analyze_unknowns', { default: 'Run automatically (daily)' })}
                onchange={(v) => (autoAnalyzeUnknowns = v)}
            />
        </SettingsRow>

        {#if analysisStatus && (analysisStatus.pending > 0 || analysisStatus.active > 0)}
            {@const remaining = analysisStatus.pending + analysisStatus.active}
            {@const processed = analysisTotal > 0 ? Math.max(0, analysisTotal - remaining) : 0}

            <div class="border-t border-line-soft pt-4 space-y-3 animate-in fade-in slide-in-from-top-2">
                <div class="flex justify-between text-sm font-semibold">
                    <span class="text-slate-700 dark:text-slate-200">{$_('settings.data.batch_analysis_processing')}</span>
                    <span class="text-slate-600 dark:text-slate-400">{processed} / {analysisTotal}</span>
                </div>
                <div class="flex justify-between text-xs font-bold text-slate-600 dark:text-slate-400">
                    <span>{$_('settings.data.batch_analysis_pending')}: {analysisStatus.pending}</span>
                    <span>{$_('settings.data.batch_analysis_active')}: {analysisStatus.active}</span>
                </div>
                {#if analysisStatus.maintenance_status_message}
                    <div class="text-xs text-slate-700 dark:text-slate-200">
                        {analysisStatus.maintenance_status_message}
                    </div>
                {/if}
                {#if analysisStatus.circuit_open}
                    <div class="text-xs flex items-center gap-1 text-attention-800 dark:text-attention-200">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                        {$_('settings.data.batch_analysis_circuit_open')}
                        {#if analysisStatus.open_until}
                            <span class="ml-auto text-xs font-bold text-attention-600 dark:text-attention-300">{formatSafeTime(analysisStatus.open_until)}</span>
                        {/if}
                    </div>
                    {#if analysisStatus.failure_count !== undefined}
                        <div class="text-xs font-bold text-attention-700 dark:text-attention-300">
                            {$_('settings.data.batch_analysis_recent_failures', { default: 'Recent failures' })}: {analysisStatus.failure_count}
                        </div>
                    {/if}
                {/if}
            </div>
        {/if}
    </SettingsCard>

    <SettingsCard
        collapsible
        id="maintenance-concurrency"
        title={$_('settings.data.maintenance_jobs_title', { default: 'Jobs at once' })}
        description={$_('settings.data.maintenance_jobs_desc', { default: 'The jobs above run one at a time, so they never compete with bird identification.' })}
    >
            <SettingsRow
                labelId="setting-maint-concurrency"
                label={$_('settings.data.maintenance_max_concurrent', { default: 'Maintenance concurrency' })}
                description={$_('settings.data.maintenance_max_concurrent_help', { default: 'Best practice is 1. Increase this only if you intentionally want backfill, taxonomy repair, timezone repair, or analyze-unknowns to overlap.' })}
                layout="stacked"
            >
                <SettingsInput
                    id="maintenance-max-concurrent"
                    field="maintenance_max_concurrent"
                    type="number"
                    min={1}
                    max={8}
                    value={maintenanceMaxConcurrent}
                    ariaLabel={$_('settings.data.maintenance_max_concurrent', { default: 'Maintenance concurrency' })}
                    oninput={(v) => (maintenanceMaxConcurrent = Number(v) || 1)}
                />
            </SettingsRow>
    </SettingsCard>

    <SettingsCard
        collapsible
        id="data-danger"
        title={$_('settings.danger.title')}
        description={$_('settings.danger.subtitle')}
        openByDefault={resettingDatabase || clearingFavorites || clearingFeedback}
    >
        <!-- One block per action, narrowest reach first, each consequence beside its own button. -->
        <ul class="@container divide-y divide-red-500/15" data-danger-actions>
            <li class="flex flex-col gap-3 p-4 @xl:flex-row @xl:items-center @xl:justify-between @xl:gap-6" data-danger-action="feedback">
                <div class="min-w-0 space-y-1">
                    <h3 class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.danger.feedback_title', { default: 'Personalization data' })}</h3>
                    <p id="danger-feedback-consequence" class="text-xs leading-snug text-slate-600 dark:text-slate-300">
                        {$_('settings.danger.clear_feedback_desc', { default: 'Clearing personalization feedback will delete all manual tag corrections the AI uses to adjust confidence scores. This will revert the classifier to its baseline accuracy.' })}
                        {$_('settings.danger.clear_feedback_hint', { default: 'This does not delete detections or media. Re-ranking will begin learning again as you make new manual corrections.' })}
                    </p>
                </div>
                <button
                    type="button"
                    onclick={handleClearFeedback}
                    disabled={clearingFeedback}
                    aria-describedby="danger-feedback-consequence"
                    class="shrink-0 {buttonDangerOutlineClass}"
                >
                    {#if clearingFeedback}{@render spinner()}{/if}
                    {clearingFeedback ? $_('settings.danger.clearing_feedback', { default: 'Clearing...' }) : $_('settings.danger.clear_feedback_button', { default: 'Clear Personalization Data' })}
                </button>
            </li>
            <li class="flex flex-col gap-3 p-4 @xl:flex-row @xl:items-center @xl:justify-between @xl:gap-6" data-danger-action="favorites">
                <div class="min-w-0 space-y-1">
                    <h3 class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.danger.favorites_title', { default: 'Favourites' })}</h3>
                    <p id="danger-favorites-consequence" class="text-xs leading-snug text-slate-600 dark:text-slate-300">{$_('settings.data.clear_favorites_desc')}</p>
                </div>
                <button
                    type="button"
                    onclick={handleClearFavorites}
                    disabled={clearingFavorites}
                    aria-describedby="danger-favorites-consequence"
                    class="shrink-0 {buttonDangerOutlineClass}"
                >
                    {#if clearingFavorites}{@render spinner()}{/if}
                    {clearingFavorites ? $_('settings.data.cleaning') : $_('settings.data.clear_favorites_button')}
                </button>
            </li>
            <li class="flex flex-col gap-3 p-4 @xl:flex-row @xl:items-center @xl:justify-between @xl:gap-6" data-danger-action="reset">
                <div class="min-w-0 space-y-1">
                    <h3 class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.danger.reset_title', { default: 'Database and media cache' })}</h3>
                    <p id="danger-reset-consequence" class="text-xs leading-snug text-slate-600 dark:text-slate-300">{$_('settings.danger.reset_desc')}</p>
                </div>
                <button
                    type="button"
                    onclick={handleResetDatabase}
                    disabled={resettingDatabase}
                    aria-describedby="danger-reset-consequence"
                    class="shrink-0 {buttonDangerSolidClass}"
                >
                    {#if resettingDatabase}{@render spinner()}{/if}
                    {resettingDatabase ? $_('settings.danger.resetting') : $_('settings.danger.reset_button')}
                </button>
            </li>
        </ul>
    </SettingsCard>
</div>

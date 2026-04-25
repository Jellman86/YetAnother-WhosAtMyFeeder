<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { formatDate } from '../../utils/datetime';
    import type { MaintenanceStats, BackfillResult, WeatherBackfillResult, CacheStats, TaxonomySyncStatus, AnalysisStatus, TimezoneRepairPreview } from '../../api';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';

    let {
        maintenanceStats,
        retentionDays = $bindable(0),
        maintenanceMaxConcurrent = $bindable(1),
        frigateMissingBehavior = $bindable<'mark_missing' | 'keep' | 'delete'>('mark_missing'),
        autoPurgeMissingClips = $bindable(false),
        autoPurgeMissingSnapshots = $bindable(false),
        autoAnalyzeUnknowns = $bindable(false),
        cacheRetentionDays = $bindable(0),
        cleaningUp,
        clearingFavorites,
        purgingMissingMedia,
        cacheEnabled = $bindable(true),
        cacheSnapshots = $bindable(true),
        cacheClips = $bindable(false),
        cacheHighQualityEventSnapshots = $bindable(false),
        cacheHighQualityEventSnapshotBirdCrop = $bindable(false),
        cacheHighQualityEventSnapshotJpegQuality = $bindable(95),
        cacheStats,
        cleaningCache,
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
        handleCleanup,
        handleClearFavorites,
        handlePurgeMissingMedia,
        handleCacheCleanup,
        handleStartTaxonomySync,
        handlePreviewTimezoneRepair,
        handleApplyTimezoneRepair,
        handleBackfill,
        handleWeatherBackfill,
        handleAnalyzeUnknowns,
        handleResetDatabase,
        handleClearFeedback
    }: {
        maintenanceStats: MaintenanceStats | null;
        retentionDays: number;
        maintenanceMaxConcurrent: number;
        frigateMissingBehavior: 'mark_missing' | 'keep' | 'delete';
        autoPurgeMissingClips: boolean;
        autoPurgeMissingSnapshots: boolean;
        autoAnalyzeUnknowns: boolean;
        cacheRetentionDays: number;
        cleaningUp: boolean;
        clearingFavorites: boolean;
        purgingMissingMedia: boolean;
        cacheEnabled: boolean;
        cacheSnapshots: boolean;
        cacheClips: boolean;
        cacheHighQualityEventSnapshots: boolean;
        cacheHighQualityEventSnapshotBirdCrop: boolean;
        cacheHighQualityEventSnapshotJpegQuality: number;
        cacheStats: CacheStats | null;
        cleaningCache: boolean;
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
        handleCleanup: () => Promise<void>;
        handleClearFavorites: () => Promise<void>;
        handlePurgeMissingMedia: () => Promise<void>;
        handleCacheCleanup: () => Promise<void>;
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
    const autoMediaIntegrityScan = $derived(autoPurgeMissingClips || autoPurgeMissingSnapshots);

    const setAutoMediaIntegrityScan = (enabled: boolean) => {
        autoPurgeMissingClips = enabled;
        autoPurgeMissingSnapshots = enabled;
    };

    const buttonPrimaryClass = 'px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-400 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3';
    const buttonNeutralClass = 'px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-400 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3';
    const buttonAmberClass = 'px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-amber-500 hover:bg-amber-600 text-white transition-all shadow-lg shadow-amber-500/20 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-400 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3';
    const buttonDangerClass = 'px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-red-500 hover:bg-red-600 text-white transition-all shadow-lg shadow-red-500/20 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-400 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3';
</script>

{#snippet spinner()}
    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
{/snippet}

<div class="space-y-6">
    {#if maintenanceStats}
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            {#each [
                { label: $_('settings.data.records'), val: fmtCount(maintenanceStats.total_detections) },
                { label: $_('settings.data.oldest'), val: maintenanceStats.oldest_detection ? formatDate(maintenanceStats.oldest_detection) : 'N/A' },
                { label: $_('settings.data.retention'), val: retentionDays === 0 ? '∞' : `${retentionDays} ${$_('leaderboard.days')}` },
                { label: $_('settings.data.pending_gc'), val: fmtCount(maintenanceStats.detections_to_cleanup), highlight: safeCount(maintenanceStats.detections_to_cleanup) > 0 }
            ] as stat}
                <div class="card-base rounded-3xl p-6 text-center backdrop-blur-md">
                    <p class="text-2xl font-black tracking-tight {stat.highlight ? 'text-amber-500' : 'text-slate-900 dark:text-white'}">{stat.val}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mt-1">{stat.label}</p>
                </div>
            {/each}
        </div>
    {/if}

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        <SettingsCard icon="🗂️" title={$_('settings.data.retention_title')}>
            <SettingsRow
                labelId="setting-retention-days"
                label={$_('settings.data.history_duration')}
                layout="stacked"
            >
                <SettingsSelect
                    id="retention-days"
                    value={String(retentionDays)}
                    ariaLabel={$_('settings.data.history_duration')}
                    options={[
                        { value: '0', label: $_('settings.data.keep_everything') },
                        { value: '7', label: $_('settings.data.retention_week') },
                        { value: '14', label: $_('settings.data.retention_weeks') },
                        { value: '30', label: $_('settings.data.retention_month') },
                        { value: '90', label: $_('settings.data.retention_months') },
                        { value: '365', label: $_('settings.data.retention_year') }
                    ]}
                    onchange={(v) => (retentionDays = Number(v) || 0)}
                />
            </SettingsRow>

            <button
                type="button"
                onclick={handleCleanup}
                disabled={cleaningUp || retentionDays === 0 || (maintenanceStats?.detections_to_cleanup ?? 0) === 0}
                aria-label={$_('settings.data.purge_button')}
                class="w-full {buttonAmberClass}"
            >
                {cleaningUp ? $_('settings.data.cleaning') : $_('settings.data.purge_button')}
            </button>
            <p class="text-[10px] text-center text-slate-400 font-bold italic">{$_('settings.data.auto_cleanup_note')}</p>

            <AdvancedSection
                id="data-retention-advanced"
                title={$_('settings.data.advanced_title', { default: 'Maintenance & media integrity' })}
            >
                <SettingsRow
                    labelId="setting-maint-concurrency"
                    label={$_('settings.data.maintenance_max_concurrent', { default: 'Maintenance concurrency' })}
                    description={$_('settings.data.maintenance_max_concurrent_help', { default: 'Per-kind default — each maintenance kind (backfill, weather backfill, video classification, taxonomy repair, timezone repair, analyze-unknowns) gets this many slots. Different kinds already run independently; increase this only if you want multiple jobs of the same kind to overlap.' })}
                    layout="stacked"
                >
                    <SettingsInput
                        id="maintenance-max-concurrent"
                        type="number"
                        min={1}
                        max={8}
                        value={maintenanceMaxConcurrent}
                        ariaLabel={$_('settings.data.maintenance_max_concurrent', { default: 'Maintenance concurrency' })}
                        oninput={(v) => (maintenanceMaxConcurrent = Number(v) || 1)}
                    />
                </SettingsRow>

                <SettingsRow
                    labelId="setting-frigate-missing-behavior"
                    label={$_('settings.data.frigate_missing_behavior', { default: 'When Frigate no longer has the event/media' })}
                    description={$_('settings.data.frigate_missing_behavior_note', { default: 'This policy is applied during manual scans and scheduled checks. Use mark-missing when YA-WAMF should keep detections longer than Frigate.' })}
                    layout="stacked"
                >
                    <SettingsSelect
                        id="frigate-missing-behavior"
                        value={frigateMissingBehavior}
                        ariaLabel={$_('settings.data.frigate_missing_behavior', { default: 'When Frigate no longer has the event/media' })}
                        options={[
                            { value: 'mark_missing', label: $_('settings.data.frigate_missing_behavior_mark', { default: 'Mark missing and keep local data' }) },
                            { value: 'keep', label: $_('settings.data.frigate_missing_behavior_keep', { default: 'Keep local data unchanged' }) },
                            { value: 'delete', label: $_('settings.data.frigate_missing_behavior_delete', { default: 'Delete local data' }) }
                        ]}
                        onchange={(v) => (frigateMissingBehavior = v as 'mark_missing' | 'keep' | 'delete')}
                    />
                </SettingsRow>

                <button
                    type="button"
                    onclick={handlePurgeMissingMedia}
                    disabled={purgingMissingMedia}
                    aria-label={$_('settings.data.purge_missing_media', { default: 'Run media integrity scan now' })}
                    class="w-full {buttonAmberClass}"
                >
                    {purgingMissingMedia
                        ? $_('settings.data.cleaning', { default: 'Cleaning...' })
                        : $_('settings.data.purge_missing_media', { default: 'Run media integrity scan now' })}
                </button>

                <SettingsRow
                    labelId="setting-auto-media-integrity"
                    label={$_('settings.data.auto_purge_missing_media', { default: 'Run media integrity scan daily' })}
                    description={$_('settings.data.media_integrity_note', { default: 'These scans apply the selected upstream-missing policy instead of always deleting detections.' })}
                >
                    <SettingsToggle
                        checked={autoMediaIntegrityScan}
                        labelledBy="setting-auto-media-integrity"
                        srLabel={$_('settings.data.auto_purge_missing_media', { default: 'Run media integrity scan daily' })}
                        onchange={(v) => setAutoMediaIntegrityScan(v)}
                    />
                </SettingsRow>
            </AdvancedSection>
        </SettingsCard>

        <SettingsCard icon="📦" title={$_('settings.data.cache_title')}>
            <SettingsRow
                labelId="setting-cache-enabled"
                label={$_('settings.data.cache_title')}
            >
                <SettingsToggle
                    checked={cacheEnabled}
                    labelledBy="setting-cache-enabled"
                    srLabel={$_('settings.data.cache_title')}
                    onchange={(v) => (cacheEnabled = v)}
                />
            </SettingsRow>

            {#if cacheEnabled}
                <SettingsRow
                    labelId="setting-cache-snapshots"
                    label={$_('settings.data.cache_snapshots')}
                >
                    <SettingsToggle
                        checked={cacheSnapshots}
                        labelledBy="setting-cache-snapshots"
                        srLabel={$_('settings.data.cache_snapshots')}
                        onchange={(v) => (cacheSnapshots = v)}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-cache-clips"
                    label={$_('settings.data.cache_clips')}
                >
                    <SettingsToggle
                        checked={cacheClips}
                        labelledBy="setting-cache-clips"
                        srLabel={$_('settings.data.cache_clips')}
                        onchange={(v) => (cacheClips = v)}
                    />
                </SettingsRow>

                <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                    <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">{$_('settings.data.cache_size')}</span>
                    <span class="text-sm font-black text-slate-900 dark:text-white">{cacheStats?.total_size_mb ?? 0} MB</span>
                </div>

                <button
                    type="button"
                    onclick={handleCacheCleanup}
                    disabled={cleaningCache}
                    aria-label={$_('settings.data.cache_clear_button')}
                    class="w-full {buttonNeutralClass}"
                >
                    {cleaningCache ? $_('settings.data.cleaning') : $_('settings.data.cache_clear_button')}
                </button>

                <AdvancedSection
                    id="data-cache-advanced"
                    title={$_('settings.data.cache_advanced_title', { default: 'High-quality snapshots & quality' })}
                >
                    <SettingsRow
                        labelId="setting-cache-hq"
                        label={$_('settings.data.cache_high_quality_event_snapshots', { default: 'HQ Event Snapshots' })}
                        description={$_('settings.data.cache_high_quality_event_snapshots_help', { default: 'Replace Frigate snapshots later with a frame from the main-stream clip.' })}
                    >
                        <SettingsToggle
                            checked={cacheHighQualityEventSnapshots}
                            labelledBy="setting-cache-hq"
                            srLabel={$_('settings.data.cache_high_quality_event_snapshots', { default: 'HQ Event Snapshots' })}
                            onchange={(v) => {
                                cacheHighQualityEventSnapshots = v;
                                if (!v) cacheHighQualityEventSnapshotBirdCrop = false;
                            }}
                        />
                    </SettingsRow>

                    {#if cacheHighQualityEventSnapshots}
                        <SettingsRow
                            labelId="setting-cache-hq-bird-crop"
                            label={$_('settings.data.cache_high_quality_event_snapshot_bird_crop', { default: 'HQ Bird Crop Snapshots' })}
                            description={$_('settings.data.cache_high_quality_event_snapshot_bird_crop_help', { default: 'Use the bird crop detector on HQ frames. Falls back to the full HQ frame if no crop is found.' })}
                        >
                            <SettingsToggle
                                checked={cacheHighQualityEventSnapshotBirdCrop}
                                labelledBy="setting-cache-hq-bird-crop"
                                srLabel={$_('settings.data.cache_high_quality_event_snapshot_bird_crop', { default: 'HQ Bird Crop Snapshots' })}
                                onchange={(v) => (cacheHighQualityEventSnapshotBirdCrop = v)}
                            />
                        </SettingsRow>

                        <SettingsRow
                            labelId="setting-cache-hq-jpeg-quality"
                            label={$_('settings.data.cache_high_quality_event_snapshot_jpeg_quality', { default: 'HQ Snapshot JPEG Quality' })}
                            description={$_('settings.data.cache_high_quality_event_snapshot_jpeg_quality_help', { default: 'Higher values keep more detail but create larger derived snapshot files.' })}
                            layout="stacked"
                        >
                            <div class="space-y-2">
                                <div class="flex justify-end">
                                    <span class="text-sm font-black text-slate-900 dark:text-white">{cacheHighQualityEventSnapshotJpegQuality}</span>
                                </div>
                                <input
                                    type="range"
                                    min="70"
                                    max="100"
                                    step="1"
                                    bind:value={cacheHighQualityEventSnapshotJpegQuality}
                                    aria-label={$_('settings.data.cache_high_quality_event_snapshot_jpeg_quality', { default: 'HQ Snapshot JPEG Quality' })}
                                    class="w-full accent-teal-500"
                                />
                                <div class="flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-slate-400">
                                    <span>70</span>
                                    <span>100</span>
                                </div>
                            </div>
                        </SettingsRow>
                    {/if}
                </AdvancedSection>
            {/if}
        </SettingsCard>
    </div>

    <SettingsCard
        icon="🌳"
        title={$_('settings.data.taxonomy_title')}
        description={$_('settings.data.taxonomy_desc')}
    >
        {#if taxonomyStatus}
            {#if taxonomyStatus.is_running}
                <div class="flex items-center justify-between gap-3 px-4 py-3 rounded-2xl bg-teal-500/10 border border-teal-500/20 text-teal-700 dark:text-teal-300">
                    <span class="text-[10px] font-black uppercase tracking-widest">{taxonomyStatus.message || taxonomyStatus.current_item || $_('settings.data.taxonomy_repairing')}</span>
                    <span class="text-[10px] font-black">{taxonomyStatus.processed} / {taxonomyStatus.total}</span>
                </div>
            {:else if taxonomyStatus.current_item || taxonomyStatus.message || taxonomyStatus.error}
                <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center gap-3">
                    {#if taxonomyStatus.error}
                        <div class="w-2 h-2 rounded-full bg-red-500"></div>
                        <p class="text-xs font-bold text-red-500">{taxonomyStatus.error}</p>
                    {:else}
                        <div class="w-2 h-2 rounded-full bg-emerald-500"></div>
                        <p class="text-xs font-bold text-slate-600 dark:text-slate-300">{taxonomyStatus.message || taxonomyStatus.current_item}</p>
                    {/if}
                </div>
            {/if}
        {/if}

        <button
            type="button"
            onclick={handleStartTaxonomySync}
            disabled={taxonomyStatus?.is_running || syncingTaxonomy}
            aria-label={$_('settings.data.taxonomy_run_button')}
            class="w-full {buttonPrimaryClass}"
        >
            {#if syncingTaxonomy || taxonomyStatus?.is_running}{@render spinner()}{/if}
            {$_('settings.data.taxonomy_run_button')}
        </button>
    </SettingsCard>

    <SettingsCard
        icon="🕒"
        title={$_('settings.data.timezone_repair_title', { default: 'Timezone Repair' })}
        description={$_('settings.data.timezone_repair_desc', { default: 'Validate older detection timestamps against Frigate and repair only safe whole-hour timezone offsets.' })}
    >
        <p class="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            {$_('settings.data.timezone_repair_note', { default: 'This only updates detections when Frigate still has the matching event and the timestamp difference looks like a real timezone offset.' })}
        </p>

        {#if timezoneRepairPreview}
            <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 px-4 py-3">
                    <p class="text-lg font-black text-slate-900 dark:text-white">{fmtCount(timezoneRepairPreview.summary.scanned_count)}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.data.timezone_repair_scanned', { default: 'Scanned' })}</p>
                </div>
                <div class="rounded-2xl border border-amber-200 dark:border-amber-700/60 px-4 py-3">
                    <p class="text-lg font-black text-amber-600 dark:text-amber-400">{fmtCount(timezoneRepairPreview.summary.repair_candidate_count)}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.data.timezone_repair_candidates', { default: 'Repair candidates' })}</p>
                </div>
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 px-4 py-3">
                    <p class="text-lg font-black text-slate-900 dark:text-white">{fmtCount(timezoneRepairPreview.summary.missing_frigate_event_count)}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.data.timezone_repair_missing', { default: 'Missing in Frigate' })}</p>
                </div>
                <div class="rounded-2xl border border-red-200 dark:border-red-700/60 px-4 py-3">
                    <p class="text-lg font-black text-red-600 dark:text-red-400">{fmtCount(timezoneRepairPreview.summary.lookup_error_count)}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.data.timezone_repair_lookup_errors', { default: 'Lookup errors' })}</p>
                </div>
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 px-4 py-3">
                    <p class="text-lg font-black text-slate-900 dark:text-white">{fmtCount(timezoneRepairPreview.summary.unsupported_delta_count)}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.data.timezone_repair_unsupported', { default: 'Unsupported delta' })}</p>
                </div>
            </div>

            {#if timezoneRepairPreview.candidates.length > 0}
                <div class="rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div class="px-5 py-3 bg-slate-50 dark:bg-slate-900/50 border-b border-slate-200 dark:border-slate-700">
                        <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.data.timezone_repair_preview_list', { default: 'Preview' })}</p>
                    </div>
                    <div class="divide-y divide-slate-200 dark:divide-slate-700">
                        {#each timezoneRepairPreview.candidates.slice(0, 5) as candidate}
                            <div class="px-5 py-4 space-y-1">
                                <div class="flex items-center justify-between gap-3">
                                    <p class="text-sm font-black text-slate-900 dark:text-white truncate">{candidate.display_name || candidate.frigate_event}</p>
                                    <span class="text-[10px] font-black uppercase tracking-widest {candidate.status === 'repair_candidate' ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500'}">{candidate.status.replace(/_/g, ' ')}</span>
                                </div>
                                <p class="text-xs text-slate-500 dark:text-slate-400 truncate">{candidate.frigate_event}</p>
                                <div class="text-xs text-slate-600 dark:text-slate-300">
                                    <span>{formatPreviewTimestamp(candidate.stored_detection_time)}</span>
                                    {#if candidate.repaired_detection_time}<span> -> {formatPreviewTimestamp(candidate.repaired_detection_time)}</span>{/if}
                                    {#if candidate.delta_hours !== null}<span class="ml-2">({candidate.delta_hours > 0 ? '+' : ''}{candidate.delta_hours}h)</span>{/if}
                                </div>
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
        {/if}

        <div class="flex flex-col md:flex-row gap-3">
            <button
                type="button"
                onclick={handlePreviewTimezoneRepair}
                disabled={previewingTimezoneRepair || applyingTimezoneRepair}
                aria-label={$_('settings.data.timezone_repair_preview_button', { default: 'Scan for timezone issues' })}
                class="flex-1 {buttonNeutralClass}"
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
                class="flex-1 {buttonAmberClass}"
            >
                {applyingTimezoneRepair
                    ? $_('settings.data.timezone_repair_apply_loading', { default: 'Repairing...' })
                    : $_('settings.data.timezone_repair_apply_button', { default: 'Apply timezone repair' })}
            </button>
        </div>
    </SettingsCard>

    <SettingsCard
        icon="🔄"
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
                        <label for="backfill-from-date" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                            {$_('settings.data.backfill_from', { default: 'From' })}
                        </label>
                        <input
                            id="backfill-from-date"
                            type="date"
                            bind:value={backfillStartDate}
                            max={backfillEndDate || todayDateOnly()}
                            aria-label={$_('settings.data.backfill_from', { default: 'From date' })}
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                        />
                    </div>
                    <div>
                        <label for="backfill-to-date" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                            {$_('settings.data.backfill_to', { default: 'To' })}
                        </label>
                        <input
                            id="backfill-to-date"
                            type="date"
                            bind:value={backfillEndDate}
                            min={backfillStartDate || undefined}
                            max={todayDateOnly()}
                            aria-label={$_('settings.data.backfill_to', { default: 'To date' })}
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                        />
                    </div>
                </div>
                <div class="grid grid-cols-3 gap-2">
                    <button type="button" class="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:border-teal-400" onclick={() => setCustomRangeDays(7)}>7D</button>
                    <button type="button" class="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:border-teal-400" onclick={() => setCustomRangeDays(30)}>30D</button>
                    <button type="button" class="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:border-teal-400" onclick={clearCustomRange}>{$_('common.clear', { default: 'Clear' })}</button>
                </div>
                {#if backfillCustomError}
                    <p class="text-[11px] font-bold text-red-500">{backfillCustomError}</p>
                {/if}
            </div>
        {/if}

        {#if backfillResult}
            <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 grid grid-cols-4 gap-2 text-center">
                <div><p class="text-sm font-black text-slate-900 dark:text-white">{safeCount(backfillResult.processed)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_total')}</p></div>
                <div><p class="text-sm font-black text-emerald-500">{safeCount(backfillResult.new_detections)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_new')}</p></div>
                <div><p class="text-sm font-black text-slate-400">{safeCount(backfillResult.skipped)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_skip')}</p></div>
                <div><p class="text-sm font-black text-red-500">{safeCount(backfillResult.errors)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_err')}</p></div>
            </div>
            {#if backfillResult.skipped_reasons && Object.keys(backfillResult.skipped_reasons).length > 0}
                <div class="p-3 rounded-xl bg-slate-50/50 dark:bg-slate-900/30 border border-slate-100 dark:border-slate-700/30">
                    <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-2">{$_('settings.data.backfill_skipped_breakdown')}</p>
                    <div class="grid grid-cols-1 gap-2">
                        {#each Object.entries(backfillResult.skipped_reasons) as [reason, count]}
                            <div class="flex justify-between items-center text-xs">
                                <span class="text-slate-500">
                                    {$_(`settings.data.backfill_reasons.${reason}`, { default: reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) })}
                                </span>
                                <span class="font-bold text-slate-700 dark:text-slate-300">{count}</span>
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
        {/if}

        <button
            type="button"
            onclick={handleBackfill}
            disabled={backfilling || !backfillCustomValid}
            aria-label={$_('settings.data.backfill_scan_button')}
            class="w-full {buttonPrimaryClass}"
        >
            {#if backfilling}{@render spinner()}{/if}
            {backfilling ? $_('settings.data.backfill_scanning') : $_('settings.data.backfill_scan_button')}
        </button>

        <AdvancedSection
            id="data-backfill-weather"
            title={$_('settings.data.weather_backfill_title')}
        >
            {#if weatherBackfillResult}
                <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 grid grid-cols-4 gap-2 text-center">
                    <div><p class="text-sm font-black text-slate-900 dark:text-white">{safeCount(weatherBackfillResult.processed)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_total')}</p></div>
                    <div><p class="text-sm font-black text-emerald-500">{safeCount(weatherBackfillResult.updated)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Upd</p></div>
                    <div><p class="text-sm font-black text-slate-400">{safeCount(weatherBackfillResult.skipped)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_skip')}</p></div>
                    <div><p class="text-sm font-black text-red-500">{safeCount(weatherBackfillResult.errors)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_err')}</p></div>
                </div>
            {/if}
            <button
                type="button"
                onclick={handleWeatherBackfill}
                disabled={weatherBackfilling || !backfillCustomValid}
                aria-label={$_('settings.data.weather_backfill_button')}
                class="w-full {buttonNeutralClass}"
            >
                {#if weatherBackfilling}{@render spinner()}{/if}
                {weatherBackfilling ? $_('settings.data.weather_backfill_filling') : $_('settings.data.weather_backfill_button')}
            </button>
        </AdvancedSection>
    </SettingsCard>

    <SettingsCard
        icon="🧪"
        title={$_('settings.data.batch_analysis_title')}
        description={$_('settings.data.batch_analysis_desc')}
    >
        <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">
            {$_('settings.data.batch_analysis_long_desc')}
        </p>

        <button
            type="button"
            onclick={handleAnalyzeUnknowns}
            disabled={analyzingUnknowns}
            aria-label={$_('settings.data.batch_analysis_button')}
            class="w-full {buttonPrimaryClass}"
        >
            {#if analyzingUnknowns}{@render spinner()}{/if}
            {analyzingUnknowns ? $_('settings.data.batch_analysis_queueing') : $_('settings.data.batch_analysis_button')}
        </button>

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

            <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 space-y-3 animate-in fade-in slide-in-from-top-2">
                <div class="flex justify-between text-xs font-bold uppercase tracking-widest">
                    <span class="text-slate-700 dark:text-slate-200">{$_('settings.data.batch_analysis_processing')}</span>
                    <span class="text-slate-500">{processed} / {analysisTotal}</span>
                </div>
                <div class="flex justify-between text-[10px] font-bold text-slate-400">
                    <span>{$_('settings.data.batch_analysis_pending')}: {analysisStatus.pending}</span>
                    <span>{$_('settings.data.batch_analysis_active')}: {analysisStatus.active}</span>
                </div>
                {#if analysisStatus.maintenance_status_message}
                    <div class="text-[10px] font-bold text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 p-2 rounded-lg border border-slate-200 dark:border-slate-700">
                        {analysisStatus.maintenance_status_message}
                    </div>
                {/if}
                {#if analysisStatus.circuit_open}
                    <div class="text-[10px] font-bold text-amber-500 flex items-center gap-1 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                        {$_('settings.data.batch_analysis_circuit_open')}
                        {#if analysisStatus.open_until}
                            <span class="ml-auto text-[10px] font-bold text-amber-600 dark:text-amber-300">{formatSafeTime(analysisStatus.open_until)}</span>
                        {/if}
                    </div>
                    {#if analysisStatus.failure_count !== undefined}
                        <div class="text-[10px] font-bold text-amber-500/90">
                            {$_('settings.data.batch_analysis_recent_failures', { default: 'Recent failures' })}: {analysisStatus.failure_count}
                        </div>
                    {/if}
                {/if}
            </div>
        {/if}
    </SettingsCard>

    <section class="card-base rounded-3xl p-6 md:p-8 backdrop-blur-md border-2 border-red-500/20 bg-red-500/5">
        <header class="flex items-start gap-3 mb-6">
            <div class="flex items-center justify-center w-10 h-10 rounded-2xl bg-red-500/10 text-red-600 dark:text-red-400 flex-shrink-0">
                <span class="text-xl" aria-hidden="true">⚠️</span>
            </div>
            <div class="min-w-0">
                <h3 class="text-lg md:text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.danger.title')}</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-red-500 mt-1">{$_('settings.danger.subtitle')}</p>
            </div>
        </header>

        <div class="space-y-4">
            <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">{$_('settings.danger.reset_desc')}</p>
            <button
                type="button"
                onclick={handleClearFavorites}
                disabled={clearingFavorites}
                aria-label={$_('settings.data.clear_favorites_button')}
                class="w-full {buttonDangerClass}"
            >
                {#if clearingFavorites}{@render spinner()}{/if}
                {clearingFavorites ? $_('settings.data.cleaning') : $_('settings.data.clear_favorites_button')}
            </button>
            <p class="text-[11px] text-slate-500 dark:text-slate-400 font-bold">{$_('settings.data.clear_favorites_desc')}</p>

            <div class="h-px bg-red-500/10"></div>

            <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">
                {$_('settings.danger.clear_feedback_desc', { default: 'Clearing personalization feedback will delete all manual tag corrections the AI uses to adjust confidence scores. This will revert the classifier to its baseline accuracy.' })}
            </p>
            <button
                type="button"
                onclick={handleClearFeedback}
                disabled={clearingFeedback}
                aria-label={$_('settings.danger.clear_feedback_button', { default: 'Clear Personalization Data' })}
                class="w-full {buttonAmberClass}"
            >
                {#if clearingFeedback}{@render spinner()}{/if}
                {clearingFeedback ? $_('settings.danger.clearing_feedback', { default: 'Clearing...' }) : $_('settings.danger.clear_feedback_button', { default: 'Clear Personalization Data' })}
            </button>
            <p class="text-[11px] text-slate-500 dark:text-slate-400 font-bold">
                {$_('settings.danger.clear_feedback_hint', { default: 'This does not delete detections or media. Re-ranking will begin learning again as you make new manual corrections.' })}
            </p>

            <div class="h-px bg-red-500/10"></div>

            <button
                type="button"
                onclick={handleResetDatabase}
                disabled={resettingDatabase}
                aria-label={$_('settings.danger.reset_button')}
                class="w-full {buttonDangerClass}"
            >
                {#if resettingDatabase}{@render spinner()}{/if}
                {resettingDatabase ? $_('settings.danger.resetting') : $_('settings.danger.reset_button')}
            </button>
        </div>
    </section>
</div>

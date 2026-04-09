<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { formatDate } from '../../utils/datetime';
    import type { MaintenanceStats, BackfillResult, WeatherBackfillResult, CacheStats, TaxonomySyncStatus, AnalysisStatus, TimezoneRepairPreview } from '../../api';

    // Props
    let {
        maintenanceStats,
        retentionDays = $bindable(0),
        autoPurgeMissingClips = $bindable(false),
        autoPurgeMissingSnapshots = $bindable(false),
        autoAnalyzeUnknowns = $bindable(false),
        cacheRetentionDays = $bindable(0),
        cleaningUp,
        clearingFavorites,
        purgingMissingClips,
        purgingMissingSnapshots,
        cacheEnabled = $bindable(true),
        cacheSnapshots = $bindable(true),
        cacheClips = $bindable(false),
        cacheHighQualityEventSnapshots = $bindable(false),
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
        handlePurgeMissingClips,
        handlePurgeMissingSnapshots,
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
        autoPurgeMissingClips: boolean;
        autoPurgeMissingSnapshots: boolean;
        autoAnalyzeUnknowns: boolean;
        cacheRetentionDays: number;
        cleaningUp: boolean;
        clearingFavorites: boolean;
        purgingMissingClips: boolean;
        purgingMissingSnapshots: boolean;
        cacheEnabled: boolean;
        cacheSnapshots: boolean;
        cacheClips: boolean;
        cacheHighQualityEventSnapshots: boolean;
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
        handlePurgeMissingClips: () => Promise<void>;
        handlePurgeMissingSnapshots: () => Promise<void>;
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
        if (
            date.getFullYear() !== year
            || date.getMonth() !== month - 1
            || date.getDate() !== day
        ) {
            return null;
        }
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
        if (backfillDateRange !== 'custom') {
            return;
        }
        // Keep "To" anchored to today's date by default in custom mode.
        if (!parseDateOnly(backfillEndDate)) {
            backfillEndDate = todayDateOnly();
        }
    });

    const timezoneRepairCandidates = $derived(timezoneRepairPreview?.summary.repair_candidate_count ?? 0);
</script>

<div class="space-y-6">
    <!-- Maintenance Stats -->
    {#if maintenanceStats}
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            {#each [
                { label: $_('settings.data.records'), val: fmtCount(maintenanceStats.total_detections), color: 'text-teal-500' },
                { label: $_('settings.data.oldest'), val: maintenanceStats.oldest_detection ? formatDate(maintenanceStats.oldest_detection) : 'N/A', color: 'text-blue-500' },
                { label: $_('settings.data.retention'), val: retentionDays === 0 ? '∞' : `${retentionDays} ${$_('leaderboard.days')}`, color: 'text-indigo-500' },
                { label: $_('settings.data.pending_gc'), val: fmtCount(maintenanceStats.detections_to_cleanup), color: safeCount(maintenanceStats.detections_to_cleanup) > 0 ? 'text-amber-500' : 'text-slate-400' }
            ] as stat}
                <div class="card-base rounded-3xl p-6 text-center">
                    <p class="text-2xl font-black {stat.color} tracking-tight">{stat.val}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{stat.label}</p>
                </div>
            {/each}
        </div>
    {/if}

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        <!-- Retention & Cleanup -->
        <section class="card-base rounded-3xl p-8">
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight mb-6">{$_('settings.data.retention_title')}</h3>
            <div class="space-y-6">
                <div>
                    <label for="retention-days" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.data.history_duration')}</label>
                    <select
                        id="retention-days"
                        bind:value={retentionDays}
                        aria-label={$_('settings.data.history_duration')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all"
                    >
                        <option value={0}>{$_('settings.data.keep_everything')}</option>
                        <option value={7}>{$_('settings.data.retention_week')}</option>
                        <option value={14}>{$_('settings.data.retention_weeks')}</option>
                        <option value={30}>{$_('settings.data.retention_month')}</option>
                        <option value={90}>{$_('settings.data.retention_months')}</option>
                        <option value={365}>{$_('settings.data.retention_year')}</option>
                    </select>
                </div>
                <div class="pt-4 border-t border-slate-100 dark:border-slate-700/50 flex flex-col gap-3">
                    <button
                        onclick={handleCleanup}
                        disabled={cleaningUp || retentionDays === 0 || (maintenanceStats?.detections_to_cleanup ?? 0) === 0}
                        aria-label={$_('settings.data.purge_button')}
                        class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-amber-500 hover:bg-amber-600 text-white transition-all shadow-lg shadow-amber-500/20 disabled:opacity-50"
                    >
                        {cleaningUp ? $_('settings.data.cleaning') : $_('settings.data.purge_button')}
                    </button>
                    <p class="text-[10px] text-center text-slate-400 font-bold italic">{$_('settings.data.auto_cleanup_note')}</p>
                </div>

                <div class="pt-4 border-t border-slate-100 dark:border-slate-700/50 space-y-3">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-400">
                        {$_('settings.data.media_integrity_title', { default: 'Media Integrity Cleanup' })}
                    </p>
                    <button
                        onclick={handlePurgeMissingClips}
                        disabled={purgingMissingClips}
                        aria-label={$_('settings.data.purge_missing_clips', { default: 'Remove detections without clips' })}
                        class="btn btn-danger w-full py-3 text-xs font-black uppercase tracking-widest"
                    >
                        {purgingMissingClips
                            ? $_('settings.data.cleaning', { default: 'Cleaning...' })
                            : $_('settings.data.purge_missing_clips', { default: 'Remove detections without clips' })}
                    </button>
                    <div class="flex items-center justify-between px-1">
                        <span class="text-[10px] font-bold text-slate-500 dark:text-slate-400">{$_('settings.data.auto_purge_missing_clips', { default: 'Run automatically (daily)' })}</span>
                        <button
                            role="switch"
                            aria-checked={autoPurgeMissingClips}
                            aria-label={$_('settings.data.auto_purge_missing_clips', { default: 'Run automatically (daily)' })}
                            onclick={() => autoPurgeMissingClips = !autoPurgeMissingClips}
                            onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); autoPurgeMissingClips = !autoPurgeMissingClips; } }}
                            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {autoPurgeMissingClips ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'}"
                        >
                            <span class="sr-only">{$_('settings.data.auto_purge_missing_clips', { default: 'Run automatically (daily)' })}</span>
                            <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {autoPurgeMissingClips ? 'translate-x-5' : 'translate-x-0'}"></span>
                        </button>
                    </div>
                    <button
                        onclick={handlePurgeMissingSnapshots}
                        disabled={purgingMissingSnapshots}
                        aria-label={$_('settings.data.purge_missing_snapshots', { default: 'Remove detections without snapshots' })}
                        class="btn btn-danger w-full py-3 text-xs font-black uppercase tracking-widest"
                    >
                        {purgingMissingSnapshots
                            ? $_('settings.data.cleaning', { default: 'Cleaning...' })
                            : $_('settings.data.purge_missing_snapshots', { default: 'Remove detections without snapshots' })}
                    </button>
                    <div class="flex items-center justify-between px-1">
                        <span class="text-[10px] font-bold text-slate-500 dark:text-slate-400">{$_('settings.data.auto_purge_missing_snapshots', { default: 'Run automatically (daily)' })}</span>
                        <button
                            role="switch"
                            aria-checked={autoPurgeMissingSnapshots}
                            aria-label={$_('settings.data.auto_purge_missing_snapshots', { default: 'Run automatically (daily)' })}
                            onclick={() => autoPurgeMissingSnapshots = !autoPurgeMissingSnapshots}
                            onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); autoPurgeMissingSnapshots = !autoPurgeMissingSnapshots; } }}
                            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {autoPurgeMissingSnapshots ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'}"
                        >
                            <span class="sr-only">{$_('settings.data.auto_purge_missing_snapshots', { default: 'Run automatically (daily)' })}</span>
                            <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {autoPurgeMissingSnapshots ? 'translate-x-5' : 'translate-x-0'}"></span>
                        </button>
                    </div>
                    <p class="text-[10px] text-slate-400 font-bold italic">
                        {$_('settings.data.media_integrity_note', { default: 'Deletes detections when Frigate media is missing.' })}
                    </p>
                </div>
            </div>
        </section>

        <!-- Media Cache -->
        <section class="card-base rounded-3xl p-8">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.data.cache_title')}</h3>
                <button
                    role="switch"
                    aria-checked={cacheEnabled}
                    aria-label={$_('settings.data.cache_title')}
                    onclick={() => cacheEnabled = !cacheEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            cacheEnabled = !cacheEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {cacheEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.data.cache_title')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {cacheEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            {#if cacheEnabled}
                <div class="space-y-6 animate-in fade-in slide-in-from-top-2">
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <button
                            onclick={() => cacheSnapshots = !cacheSnapshots}
                            aria-label={$_('settings.data.cache_snapshots')}
                            class="p-4 rounded-2xl border-2 transition-all text-center {cacheSnapshots ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                        >
                            <p class="text-xs font-black uppercase tracking-widest">{$_('settings.data.cache_snapshots')}</p>
                        </button>
                        <button
                            onclick={() => cacheClips = !cacheClips}
                            aria-label={$_('settings.data.cache_clips')}
                            class="p-4 rounded-2xl border-2 transition-all text-center {cacheClips ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                        >
                            <p class="text-xs font-black uppercase tracking-widest">{$_('settings.data.cache_clips')}</p>
                        </button>
                        <button
                            onclick={() => cacheHighQualityEventSnapshots = !cacheHighQualityEventSnapshots}
                            aria-label={$_('settings.data.cache_high_quality_event_snapshots', { default: 'Upgrade event snapshots from clips' })}
                            class="p-4 rounded-2xl border-2 transition-all text-center {cacheHighQualityEventSnapshots ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                        >
                            <p class="text-xs font-black uppercase tracking-widest">{$_('settings.data.cache_high_quality_event_snapshots', { default: 'HQ Event Snapshots' })}</p>
                            <p class="mt-2 text-[10px] font-bold normal-case tracking-normal text-slate-500 dark:text-slate-400">
                                {$_('settings.data.cache_high_quality_event_snapshots_help', { default: 'Replace Frigate snapshots later with a frame from the main-stream clip.' })}
                            </p>
                        </button>
                    </div>
                    {#if cacheHighQualityEventSnapshots}
                        <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 space-y-3">
                            <div class="flex items-center justify-between gap-4">
                                <div>
                                    <p class="text-xs font-black uppercase tracking-widest text-slate-700 dark:text-slate-200">
                                        {$_('settings.data.cache_high_quality_event_snapshot_jpeg_quality', { default: 'HQ Snapshot JPEG Quality' })}
                                    </p>
                                    <p class="mt-1 text-[10px] font-bold text-slate-500 dark:text-slate-400">
                                        {$_('settings.data.cache_high_quality_event_snapshot_jpeg_quality_help', { default: 'Higher values keep more detail but create larger derived snapshot files.' })}
                                    </p>
                                </div>
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
                    {/if}
                    <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                        <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">{$_('settings.data.cache_size')}</span>
                        <span class="text-sm font-black text-slate-900 dark:text-white">{cacheStats?.total_size_mb ?? 0} MB</span>
                    </div>
                    <button
                        onclick={handleCacheCleanup}
                        disabled={cleaningCache}
                        aria-label={$_('settings.data.cache_clear_button')}
                        class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-900 dark:bg-slate-700 text-white hover:bg-slate-800 transition-all disabled:opacity-50"
                    >
                        {cleaningCache ? $_('settings.data.cleaning') : $_('settings.data.cache_clear_button')}
                    </button>
                </div>
            {/if}
        </section>
    </div>

    <!-- Taxonomy Sync -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.data.taxonomy_title')}</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{$_('settings.data.taxonomy_desc')}</p>
            </div>
            {#if taxonomyStatus?.is_running}
                <div class="flex items-center gap-2 px-3 py-1 rounded-full bg-teal-500/10 text-teal-600 animate-pulse">
                    <div class="w-1.5 h-1.5 rounded-full bg-teal-500"></div>
                    <span class="text-[10px] font-black uppercase tracking-widest">{$_('settings.data.taxonomy_syncing')}</span>
                </div>
            {/if}
        </div>

        {#if taxonomyStatus}
            {#if taxonomyStatus.is_running}
                <div class="mb-6">
                    <div class="flex justify-between text-[10px] font-black uppercase tracking-widest">
                        <span class="text-slate-400">{taxonomyStatus.message || taxonomyStatus.current_item || $_('settings.data.taxonomy_repairing')}</span>
                        <span class="text-teal-500">{taxonomyStatus.processed} / {taxonomyStatus.total}</span>
                    </div>
                </div>
            {:else if taxonomyStatus.current_item || taxonomyStatus.message || taxonomyStatus.error}
                <div class="mb-6 p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/30 border border-slate-100 dark:border-slate-700/50 flex items-center gap-3">
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
            onclick={handleStartTaxonomySync}
            disabled={taxonomyStatus?.is_running || syncingTaxonomy}
            aria-label={$_('settings.data.taxonomy_run_button')}
            class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
        >
            {#if syncingTaxonomy || taxonomyStatus?.is_running}
                <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
            {/if}
            {$_('settings.data.taxonomy_run_button')}
        </button>
    </section>

    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between gap-4 mb-6">
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.data.timezone_repair_title', { default: 'Timezone Repair' })}</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">
                    {$_('settings.data.timezone_repair_desc', { default: 'Validate older detection timestamps against Frigate and repair only safe whole-hour timezone offsets.' })}
                </p>
            </div>
            {#if timezoneRepairPreview}
                <div class="rounded-2xl bg-slate-50 dark:bg-slate-900/40 px-4 py-3 text-right">
                    <p class="text-lg font-black text-slate-900 dark:text-white">{timezoneRepairCandidates}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">
                        {$_('settings.data.timezone_repair_candidates', { default: 'Repair candidates' })}
                    </p>
                </div>
            {/if}
        </div>

        <p class="text-xs text-slate-500 dark:text-slate-400 leading-relaxed mb-6">
            {$_('settings.data.timezone_repair_note', { default: 'This only updates detections when Frigate still has the matching event and the timestamp difference looks like a real timezone offset.' })}
        </p>

        {#if timezoneRepairPreview}
            <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
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
                <div class="rounded-3xl border border-slate-200 dark:border-slate-700 overflow-hidden mb-6">
                    <div class="px-5 py-4 bg-slate-50 dark:bg-slate-900/40 border-b border-slate-200 dark:border-slate-700">
                        <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">
                            {$_('settings.data.timezone_repair_preview_list', { default: 'Preview' })}
                        </p>
                    </div>
                    <div class="divide-y divide-slate-200 dark:divide-slate-700">
                        {#each timezoneRepairPreview.candidates.slice(0, 5) as candidate}
                            <div class="px-5 py-4 space-y-1">
                                <div class="flex items-center justify-between gap-3">
                                    <p class="text-sm font-black text-slate-900 dark:text-white truncate">
                                        {candidate.display_name || candidate.frigate_event}
                                    </p>
                                    <span class="text-[10px] font-black uppercase tracking-widest {candidate.status === 'repair_candidate' ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500'}">
                                        {candidate.status.replace(/_/g, ' ')}
                                    </span>
                                </div>
                                <p class="text-xs text-slate-500 dark:text-slate-400 truncate">{candidate.frigate_event}</p>
                                <div class="text-xs text-slate-600 dark:text-slate-300">
                                    <span>{formatPreviewTimestamp(candidate.stored_detection_time)}</span>
                                    {#if candidate.repaired_detection_time}
                                        <span> -> {formatPreviewTimestamp(candidate.repaired_detection_time)}</span>
                                    {/if}
                                    {#if candidate.delta_hours !== null}
                                        <span class="ml-2">({candidate.delta_hours > 0 ? '+' : ''}{candidate.delta_hours}h)</span>
                                    {/if}
                                </div>
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
        {/if}

        <div class="flex flex-col md:flex-row gap-3">
            <button
                onclick={handlePreviewTimezoneRepair}
                disabled={previewingTimezoneRepair || applyingTimezoneRepair}
                aria-label={$_('settings.data.timezone_repair_preview_button', { default: 'Scan for timezone issues' })}
                class="flex-1 px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-900 dark:bg-slate-700 text-white hover:bg-slate-800 transition-all disabled:opacity-50"
            >
                {previewingTimezoneRepair
                    ? $_('settings.data.timezone_repair_preview_loading', { default: 'Scanning...' })
                    : $_('settings.data.timezone_repair_preview_button', { default: 'Scan for timezone issues' })}
            </button>
            <button
                onclick={handleApplyTimezoneRepair}
                disabled={previewingTimezoneRepair || applyingTimezoneRepair || timezoneRepairCandidates === 0}
                aria-label={$_('settings.data.timezone_repair_apply_button', { default: 'Apply timezone repair' })}
                class="flex-1 px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-amber-500 hover:bg-amber-600 text-white transition-all shadow-lg shadow-amber-500/20 disabled:opacity-50"
            >
                {applyingTimezoneRepair
                    ? $_('settings.data.timezone_repair_apply_loading', { default: 'Repairing...' })
                    : $_('settings.data.timezone_repair_apply_button', { default: 'Apply timezone repair' })}
            </button>
        </div>
    </section>

    <!-- Missed Detections (Backfill) -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.data.backfill_title')}</h3>
        </div>
        <p class="text-xs font-bold text-slate-500 leading-relaxed uppercase tracking-wider mb-6">{$_('settings.data.backfill_desc')}</p>

        <div class="space-y-6">
            <div>
                <label for="backfill-range" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.data.backfill_window')}</label>
                <select
                    id="backfill-range"
                    bind:value={backfillDateRange}
                    aria-label={$_('settings.data.backfill_window')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                >
                    <option value="day">{$_('settings.data.backfill_24h')}</option>
                    <option value="week">{$_('settings.data.backfill_week')}</option>
                    <option value="month">{$_('settings.data.backfill_month')}</option>
                    <option value="custom">{$_('settings.data.backfill_custom')}</option>
                </select>
            </div>

            {#if backfillDateRange === 'custom'}
                <div class="space-y-3 animate-in fade-in slide-in-from-top-2">
                    <p class="block text-[10px] font-black uppercase tracking-widest text-slate-500">
                        {$_('settings.data.backfill_custom', { default: 'Custom range' })}
                    </p>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
                        <div class="min-w-0">
                            <label for="backfill-from-date" class="block text-[9px] sm:text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1.5 sm:mb-2">
                                {$_('settings.data.backfill_from', { default: 'From' })}
                            </label>
                            <input
                                id="backfill-from-date"
                                type="date"
                                bind:value={backfillStartDate}
                                max={backfillEndDate || todayDateOnly()}
                                aria-label={$_('settings.data.backfill_from', { default: 'From date' })}
                                class="w-full min-w-0 px-3 py-2.5 sm:px-4 sm:py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs sm:text-sm"
                            />
                        </div>
                        <div class="min-w-0">
                            <label for="backfill-to-date" class="block text-[9px] sm:text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1.5 sm:mb-2">
                                {$_('settings.data.backfill_to', { default: 'To' })}
                            </label>
                            <input
                                id="backfill-to-date"
                                type="date"
                                bind:value={backfillEndDate}
                                min={backfillStartDate || undefined}
                                max={todayDateOnly()}
                                aria-label={$_('settings.data.backfill_to', { default: 'To date' })}
                                class="w-full min-w-0 px-3 py-2.5 sm:px-4 sm:py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs sm:text-sm"
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
                    <div class="mt-2 p-3 rounded-xl bg-slate-50/50 dark:bg-slate-900/30 border border-slate-100 dark:border-slate-700/30">
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
                onclick={handleBackfill}
                disabled={backfilling || !backfillCustomValid}
                aria-label={$_('settings.data.backfill_scan_button')}
                class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {#if backfilling}
                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {backfilling ? $_('settings.data.backfill_scanning') : $_('settings.data.backfill_scan_button')}
            </button>

            <div class="pt-2 border-t border-slate-100 dark:border-slate-800">
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">{$_('settings.data.weather_backfill_title')}</p>
                {#if weatherBackfillResult}
                    <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 grid grid-cols-4 gap-2 text-center mb-3">
                        <div><p class="text-sm font-black text-slate-900 dark:text-white">{safeCount(weatherBackfillResult.processed)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_total')}</p></div>
                        <div><p class="text-sm font-black text-emerald-500">{safeCount(weatherBackfillResult.updated)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Upd</p></div>
                        <div><p class="text-sm font-black text-slate-400">{safeCount(weatherBackfillResult.skipped)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_skip')}</p></div>
                        <div><p class="text-sm font-black text-red-500">{safeCount(weatherBackfillResult.errors)}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">{$_('settings.data.backfill_err')}</p></div>
                    </div>
                {/if}
                <button
                    onclick={handleWeatherBackfill}
                    disabled={weatherBackfilling || !backfillCustomValid}
                    aria-label={$_('settings.data.weather_backfill_button')}
                    class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-800 hover:bg-slate-900 text-white transition-all shadow-lg shadow-slate-500/10 flex items-center justify-center gap-3 disabled:opacity-50"
                >
                    {#if weatherBackfilling}
                        <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    {/if}
                    {weatherBackfilling ? $_('settings.data.weather_backfill_filling') : $_('settings.data.weather_backfill_button')}
                </button>
            </div>
        </div>
    </section>

    <!-- Batch Analysis -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
            </div>
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.data.batch_analysis_title')}</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{$_('settings.data.batch_analysis_desc')}</p>
            </div>
        </div>

        <div class="space-y-4">
            <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">
                {$_('settings.data.batch_analysis_long_desc')}
            </p>
            <button
                onclick={handleAnalyzeUnknowns}
                disabled={analyzingUnknowns}
                aria-label={$_('settings.data.batch_analysis_button')}
                class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-lg shadow-indigo-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {#if analyzingUnknowns}
                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {analyzingUnknowns ? $_('settings.data.batch_analysis_queueing') : $_('settings.data.batch_analysis_button')}
            </button>
            <div class="flex items-center justify-between px-1">
                <span class="text-[10px] font-bold text-slate-500 dark:text-slate-400">{$_('settings.data.auto_analyze_unknowns', { default: 'Run automatically (daily)' })}</span>
                <button
                    role="switch"
                    aria-checked={autoAnalyzeUnknowns}
                    aria-label={$_('settings.data.auto_analyze_unknowns', { default: 'Run automatically (daily)' })}
                    onclick={() => autoAnalyzeUnknowns = !autoAnalyzeUnknowns}
                    onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); autoAnalyzeUnknowns = !autoAnalyzeUnknowns; } }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {autoAnalyzeUnknowns ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.data.auto_analyze_unknowns', { default: 'Run automatically (daily)' })}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {autoAnalyzeUnknowns ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            {#if analysisStatus && (analysisStatus.pending > 0 || analysisStatus.active > 0)}
                {@const remaining = analysisStatus.pending + analysisStatus.active}
                {@const processed = analysisTotal > 0 ? Math.max(0, analysisTotal - remaining) : 0}

                <div class="mt-4 p-4 rounded-2xl bg-indigo-50/50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-700/30 space-y-3 animate-in fade-in slide-in-from-top-2">
                    <div class="flex justify-between text-xs font-bold uppercase tracking-widest">
                        <span class="text-indigo-600 dark:text-indigo-400">{$_('settings.data.batch_analysis_processing')}</span>
                        <span class="text-slate-500">{processed} / {analysisTotal}</span>
                    </div>
                    <div class="flex justify-between text-[10px] font-bold text-slate-400">
                        <span>{$_('settings.data.batch_analysis_pending')}: {analysisStatus.pending}</span>
                        <span>{$_('settings.data.batch_analysis_active')}: {analysisStatus.active}</span>
                    </div>
                    {#if analysisStatus.maintenance_status_message}
                        <div class="text-[10px] font-bold text-indigo-600 dark:text-indigo-300 bg-indigo-500/10 p-2 rounded-lg border border-indigo-500/20">
                            {analysisStatus.maintenance_status_message}
                        </div>
                    {/if}
                    {#if analysisStatus.circuit_open}
                        <div class="text-[10px] font-bold text-amber-500 flex items-center gap-1 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                            {$_('settings.data.batch_analysis_circuit_open')}
                            {#if analysisStatus.open_until}
                                <span class="ml-auto text-[10px] font-bold text-amber-600 dark:text-amber-300">
                                    {formatSafeTime(analysisStatus.open_until)}
                                </span>
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
        </div>
    </section>

    <!-- Danger Zone -->
    <section class="card-base rounded-3xl p-8 border-2 border-red-500/20 bg-red-500/5">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-red-500/10 flex items-center justify-center text-red-600 dark:text-red-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
            </div>
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.danger.title')}</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-red-500 mt-1">{$_('settings.danger.subtitle')}</p>
            </div>
        </div>

        <div class="space-y-4">
            <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">
                {$_('settings.danger.reset_desc')}
            </p>
            <button
                type="button"
                onclick={handleClearFavorites}
                disabled={clearingFavorites}
                aria-label={$_('settings.data.clear_favorites_button')}
                class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-rose-500 hover:bg-rose-600 text-white transition-all shadow-lg shadow-rose-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {#if clearingFavorites}
                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {clearingFavorites ? $_('settings.data.cleaning') : $_('settings.data.clear_favorites_button')}
            </button>
            <p class="text-[11px] text-slate-500 dark:text-slate-400 font-bold">
                {$_('settings.data.clear_favorites_desc')}
            </p>
            <div class="h-px bg-red-500/10 my-4"></div>
            
            <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">
                {$_('settings.danger.clear_feedback_desc', { default: 'Clearing personalization feedback will delete all manual tag corrections the AI uses to adjust confidence scores. This will revert the classifier to its baseline accuracy.' })}
            </p>
            <button
                type="button"
                onclick={handleClearFeedback}
                disabled={clearingFeedback}
                aria-label={$_('settings.danger.clear_feedback_button', { default: 'Clear Personalization Data' })}
                class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-amber-500 hover:bg-amber-600 text-white transition-all shadow-lg shadow-amber-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {#if clearingFeedback}
                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {clearingFeedback ? $_('settings.danger.clearing_feedback', { default: 'Clearing...' }) : $_('settings.danger.clear_feedback_button', { default: 'Clear Personalization Data' })}
            </button>
            <p class="text-[11px] text-slate-500 dark:text-slate-400 font-bold mb-4">
                {$_('settings.danger.clear_feedback_hint', { default: 'This does not delete detections or media. Re-ranking will begin learning again as you make new manual corrections.' })}
            </p>

            <div class="h-px bg-red-500/10 my-4"></div>
            
            <button
                type="button"
                onclick={handleResetDatabase}
                disabled={resettingDatabase}
                aria-label={$_('settings.danger.reset_button')}
                class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-red-500 hover:bg-red-600 text-white transition-all shadow-lg shadow-red-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {#if resettingDatabase}
                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {resettingDatabase ? $_('settings.danger.resetting') : $_('settings.danger.reset_button')}
            </button>
        </div>
    </section>
</div>

<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { formatDate } from '../../utils/datetime';
    import type { MaintenanceStats, CacheStats } from '../../api';
    import type { ClassifierStatus } from '../../api/classifier';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSlider from './_primitives/SettingsSlider.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import { gigabytesToStoredMegabytes, parseStorageLimitGigabytes, storedMegabytesToGigabytes } from '../../settings/storage-budget';

    // What YA-WAMF keeps, for how long, and the backup of its configuration. Jobs that repair or
    // fill in history, and the actions that delete it, are on the Maintenance tab.
    let {
        maintenanceStats,
        retentionNote = null,
        retentionDays = $bindable(0),
        frigateMissingBehavior = $bindable<'mark_missing' | 'keep' | 'delete'>('mark_missing'),
        autoPurgeMissingClips = $bindable(false),
        autoPurgeMissingSnapshots = $bindable(false),
        cacheRetentionDays = $bindable(0),
        cachePerSpeciesMaximum = $bindable<number>(0),
        cacheMaxSizeMb = $bindable<number>(0),
        cacheMaxSizeInvalid = $bindable(false),
        cacheAutomaticMultiBirdScan = $bindable(false),
        cacheBirdScanMode = $bindable<'standard' | 'intensive'>('intensive'),
        cachePerSpeciesMinimum = $bindable(0),
        cleaningUp,
        purgingMissingMedia,
        cacheClips = $bindable(false),
        cacheHighQualityEventSnapshots = $bindable(false),
        cacheHighQualityEventSnapshotJpegQuality = $bindable(95),
        cacheStats,
        cacheStatsError = false,
        cacheStatsLoading = false,
        onRetryCacheStats,
        classifierStatus,
        cleaningCache,
        exportingConfigBackup,
        importingConfigBackup,
        handleCleanup,
        handlePurgeMissingMedia,
        handleCacheCleanup,
        handleExportConfigBackup,
        handleImportConfigBackup,
    }: {
        maintenanceStats: MaintenanceStats | null;
        /** What saving a shorter retention deletes; null when the choice deletes nothing new. */
        retentionNote?: string | null;
        retentionDays: number;
        frigateMissingBehavior: 'mark_missing' | 'keep' | 'delete';
        autoPurgeMissingClips: boolean;
        autoPurgeMissingSnapshots: boolean;
        cacheRetentionDays: number;
        cachePerSpeciesMaximum: number;
        cacheMaxSizeMb: number;
        /** The size typed in GB could not be read; the limit stays as it was and the save is refused. */
        cacheMaxSizeInvalid?: boolean;
        cacheAutomaticMultiBirdScan?: boolean;
        cacheBirdScanMode: 'standard' | 'intensive';
        cachePerSpeciesMinimum: number;
        cleaningUp: boolean;
        purgingMissingMedia: boolean;
        cacheClips: boolean;
        cacheHighQualityEventSnapshots: boolean;
        cacheHighQualityEventSnapshotJpegQuality: number;
        cacheStats: CacheStats | null;
        cacheStatsError?: boolean;
        cacheStatsLoading?: boolean;
        onRetryCacheStats?: () => void;
        classifierStatus: ClassifierStatus | null;
        cleaningCache: boolean;
        exportingConfigBackup: boolean;
        importingConfigBackup: boolean;
        handleCleanup: () => Promise<void>;
        handlePurgeMissingMedia: () => Promise<void>;
        handleCacheCleanup: () => Promise<void>;
        handleExportConfigBackup: () => Promise<void>;
        handleImportConfigBackup: (file: File) => Promise<void>;
    } = $props();

    let configImportInput: HTMLInputElement | null = null;

    const safeCount = (value: unknown): number => {
        const parsed = Number(value ?? 0);
        return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
    };
    const fmtCount = (value: unknown): string => safeCount(value).toLocaleString();

    const openConfigImportPicker = () => {
        configImportInput?.click();
    };

    const handleConfigImportChange = async (event: Event) => {
        const input = event.currentTarget as HTMLInputElement;
        const file = input.files?.[0];
        input.value = '';
        if (!file) return;
        await handleImportConfigBackup(file);
    };

    const autoMediaIntegrityScan = $derived(autoPurgeMissingClips || autoPurgeMissingSnapshots);
    const cropDetectorReady = $derived(Boolean(
        classifierStatus?.crop_detector?.installed
        && classifierStatus?.crop_detector?.healthy
        && classifierStatus?.crop_detector?.enabled_for_runtime
    ));

    const setAutoMediaIntegrityScan = (enabled: boolean) => {
        autoPurgeMissingClips = enabled;
        autoPurgeMissingSnapshots = enabled;
    };

    // The summary and Purge follow the saved policy; the picker above them may hold an unsaved one.
    const savedRetentionDays = $derived(maintenanceStats?.retention_days ?? 0);
    const dueForDeletion = $derived(safeCount(maintenanceStats?.detections_to_cleanup));
    const purgeDisabledReason = $derived.by(() => {
        if (!maintenanceStats) return null;
        if (savedRetentionDays === 0) {
            return $_('settings.data.purge_disabled_forever', { default: 'Nothing to purge: history is kept forever.' });
        }
        if (dueForDeletion === 0) {
            return $_('settings.data.purge_disabled_none', {
                values: { days: savedRetentionDays },
                default: 'No detections are older than {days} days.'
            });
        }
        return null;
    });

    const historyTotal = $derived(safeCount(maintenanceStats?.total_detections));

    // Each limit is a switch with its number beside it, so "0 means off" never has to be typed or
    // explained. Turning one off and on again brings back the number it had.
    const DEFAULT_LIMIT_MB = 20 * 1024;
    const DEFAULT_SPECIES_FLOOR = 10;
    const DEFAULT_SPECIES_MAXIMUM = 100;
    const remembered = { size: DEFAULT_LIMIT_MB, floor: DEFAULT_SPECIES_FLOOR, maximum: DEFAULT_SPECIES_MAXIMUM };
    function setStorageLimit(on: boolean): void {
        if (!on && cacheMaxSizeMb > 0) remembered.size = cacheMaxSizeMb;
        cacheMaxSizeMb = on ? remembered.size : 0;
        cacheMaxSizeInvalid = false;
    }
    // What was typed while it cannot be read, so the field keeps showing it beside the reason.
    let invalidLimitText = $state('');
    const limitFieldText = $derived(cacheMaxSizeInvalid ? invalidLimitText : String(storedMegabytesToGigabytes(cacheMaxSizeMb)));
    function commitStorageLimit(text: string): void {
        const gigabytes = parseStorageLimitGigabytes(text);
        if (gigabytes === null) {
            invalidLimitText = text;
            cacheMaxSizeInvalid = true;
            return;
        }
        cacheMaxSizeMb = gigabytesToStoredMegabytes(gigabytes);
        cacheMaxSizeInvalid = false;
    }
    function setSpeciesFloor(on: boolean): void {
        if (!on && cachePerSpeciesMinimum > 0) remembered.floor = cachePerSpeciesMinimum;
        cachePerSpeciesMinimum = on ? remembered.floor : 0;
    }
    function setSpeciesMaximum(on: boolean): void {
        if (!on && cachePerSpeciesMaximum > 0) remembered.maximum = cachePerSpeciesMaximum;
        cachePerSpeciesMaximum = on ? remembered.maximum : 0;
    }
    const wholeCount = (value: string): number => Math.max(1, Math.min(10000, Math.round(Number(value)) || 1));
    // What the storage rules add up to, every active rule in it, so no limit evicts media unannounced.
    const storagePolicy = $derived(
        [
            cacheMaxSizeMb > 0
                ? $_('settings.data.storage_policy_size_limit', {
                    values: { size: storedMegabytesToGigabytes(cacheMaxSizeMb) },
                    default: 'When photos and video pass {size} GB, the oldest go first.'
                })
                : cachePerSpeciesMaximum > 0
                    ? $_('settings.data.storage_policy_no_size_limit', { default: 'No size limit.' })
                    : $_('settings.data.storage_policy_history_only', { default: 'No size limit: photos and video stay until the history window removes their visits.' }),
            cachePerSpeciesMaximum > 0
                ? $_('settings.data.storage_policy_species_cap', {
                    values: { count: cachePerSpeciesMaximum },
                    default: '{count, plural, one {Each species keeps photos and video only for its newest visit.} other {Each species keeps photos and video only for its newest # visits.}}'
                })
                : null,
            cachePerSpeciesMinimum > 0
                ? $_('settings.data.storage_policy_species_floor', {
                    values: { count: cachePerSpeciesMinimum },
                    default: "{count, plural, one {Each species' newest visit keeps its photos past the history window.} other {Each species' newest # visits keep their photos past the history window.}}"
                })
                : null,
            $_('settings.data.storage_policy_favourites', { default: 'Favourites and their archive are always kept.' })
        ].filter((part): part is string => part !== null).join(' ')
    );

    const buttonNeutralClass = 'btn btn-secondary min-h-11 px-4 py-3';
    const buttonDangerOutlineClass = 'btn btn-danger min-h-11 px-4 py-3';
</script>

{#snippet spinner()}
    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
{/snippet}

<div class="space-y-6">


    <div class="space-y-8">
        <SettingsCard title={$_('settings.data.retention_title')}>
            {#if maintenanceStats}
                <p class="text-sm text-slate-700 dark:text-slate-200" data-history-summary>
                    {maintenanceStats.oldest_detection
                        ? $_('settings.data.history_summary', {
                            values: { count: historyTotal, oldest: formatDate(maintenanceStats.oldest_detection) },
                            default: '{count, plural, one {# record} other {# records}}, the oldest from {oldest}.'
                        })
                        : $_('settings.data.history_summary_empty', { default: 'No records yet.' })}
                    {#if dueForDeletion > 0}
                        {$_('settings.data.history_due', {
                            values: { count: dueForDeletion },
                            default: '{count, plural, one {# is} other {# are}} older than the saved window and will go at the next clean-up.'
                        })}
                    {/if}
                </p>
            {/if}
            <SettingsRow
                labelId="setting-retention-days"
                label={$_('settings.data.history_duration')}
                layout="stacked"
            >
                <SettingsSelect
                    id="retention-days"
                    value={String(retentionDays)}
                    ariaLabel={$_('settings.data.history_duration')}
                    ariaDescribedBy={retentionNote ? 'retention-deletion-note' : undefined}
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
                {#if retentionNote}
                    <p id="retention-deletion-note" class="text-sm font-semibold text-attention-800 dark:text-attention-200" role="status" data-retention-deletion-note>
                        {retentionNote}
                    </p>
                {/if}
            </SettingsRow>

            <div class="space-y-2">
                <button
                    type="button"
                    onclick={handleCleanup}
                    disabled={cleaningUp || purgeDisabledReason !== null}
                    aria-describedby={purgeDisabledReason ? 'purge-disabled-reason' : undefined}
                    class="w-full sm:w-auto {buttonDangerOutlineClass}"
                >
                    {cleaningUp ? $_('settings.data.cleaning') : $_('settings.data.purge_button')}
                </button>
                {#if purgeDisabledReason}
                    <p id="purge-disabled-reason" class="text-xs text-slate-600 dark:text-slate-300">{purgeDisabledReason}</p>
                {/if}
            </div>
            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.data.auto_cleanup_note')}</p>
        </SettingsCard>

        <SettingsCard
            id="data-missing-media"
            title={$_('settings.data.missing_media_title', { default: 'When Frigate loses a visit' })}
            description={$_('settings.data.missing_media_desc', { default: 'Frigate deletes old events on its own schedule. This decides what YA-WAMF keeps when one is gone.' })}
        >
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

            <div>
                <button
                    type="button"
                    onclick={handlePurgeMissingMedia}
                    disabled={purgingMissingMedia}
                    aria-label={$_('settings.data.purge_missing_media', { default: 'Run media integrity scan now' })}
                    class={frigateMissingBehavior === 'delete' ? buttonDangerOutlineClass : buttonNeutralClass}
                >
                    {purgingMissingMedia
                        ? $_('settings.data.cleaning', { default: 'Cleaning...' })
                        : $_('settings.data.purge_missing_media', { default: 'Run media integrity scan now' })}
                </button>
            </div>

            <SettingsRow
                labelId="setting-auto-media-integrity"
                label={$_('settings.data.auto_purge_missing_media', { default: 'Run media integrity scan periodically' })}
                description={$_('settings.data.media_integrity_note', { default: 'Re-checks a batch of detections against Frigate every few hours and applies the upstream-missing behaviour above. It never deletes anything while Frigate is unreachable, and a long history takes several runs to work through.' })}
            >
                <SettingsToggle
                    checked={autoMediaIntegrityScan}
                    labelledBy="setting-auto-media-integrity"
                    srLabel={$_('settings.data.auto_purge_missing_media', { default: 'Run media integrity scan periodically' })}
                    onchange={(v) => setAutoMediaIntegrityScan(v)}
                />
            </SettingsRow>
        </SettingsCard>
    </div>

    <SettingsCard title={$_('settings.data.cache_title', { default: 'Photos and video' })}>
        <p class="text-sm text-slate-600 dark:text-slate-300" data-media-always-kept>
            {$_('settings.data.cache_always_kept', { default: 'Photos, full-visit clips and previews are kept with their visits until the history window or the storage limit removes them.' })}
        </p>
        {#if cacheStats && cacheStats.storage_available === false}
            <p class="text-sm text-attention-800 dark:text-attention-200" role="status" data-media-storage-unavailable>
                {$_('settings.data.cache_unavailable', { default: "The media folder can't be written, so photos and video are not being kept. Check the folder's permissions; system checks show the error." })}
            </p>
        {/if}
        <SettingsRow
            labelId="setting-cache-clips"
            label={$_('settings.data.cache_clips', { default: "Keep copies of Frigate's event clips" })}
            description={$_('settings.data.cache_clips_help', { default: 'Frigate already keeps these. Copies survive Frigate deleting them, at about the size of the clip each.' })}
        >
            <SettingsToggle
                checked={cacheClips}
                labelledBy="setting-cache-clips"
                srLabel={$_('settings.data.cache_clips', { default: "Keep copies of Frigate's event clips" })}
                onchange={(v) => (cacheClips = v)}
            />
        </SettingsRow>

        <div class="border-t border-line-soft pt-4 flex items-center justify-between gap-3">
            <span class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.data.cache_size')}</span>
            <span class="flex flex-wrap items-center justify-end gap-2">
                {#if cacheStats}
                    <span class="text-sm font-bold text-slate-900 dark:text-white" data-cache-size>{cacheStats.total_size_mb} MB</span>
                {/if}
                {#if cacheStatsLoading}
                    <span class="text-sm text-slate-600 dark:text-slate-300" role="status" data-cache-size-loading>
                        {$_('settings.data.cache_size_loading', { default: 'Measuring…' })}
                    </span>
                {:else if cacheStatsError}
                    <span class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300" data-cache-size-unavailable>
                        {$_('settings.data.cache_size_unavailable', { default: "Couldn't load" })}
                        {#if onRetryCacheStats}
                            <button type="button" class="btn btn-ghost min-h-11 px-2 text-sm" onclick={onRetryCacheStats} data-cache-size-retry>
                                {$_('settings.data.cache_size_retry', { default: 'Retry' })}
                            </button>
                        {/if}
                    </span>
                {:else if !cacheStats}
                    <span class="text-sm font-bold text-slate-900 dark:text-white" data-cache-size>…</span>
                {/if}
            </span>
        </div>
        {#if cacheStats && (cacheStats.garden_count ?? 0) > 0}
            <p class="px-4 text-xs text-slate-600 dark:text-slate-300" data-cache-garden-share>
                {$_('settings.data.cache_garden_share', {
                    values: { size: `${cacheStats.garden_size_mb ?? 0} MB` },
                    default: 'Includes {size} kept for confirmed Garden animals'
                })}
            </p>
        {/if}

        <!-- The archive is not the cache: clearing the cache leaves it alone (#178). -->
        <div class="border-t border-line-soft pt-4 flex flex-col gap-1" data-archive-usage>
            <div class="flex items-center justify-between gap-3">
                <span class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.data.archive_usage', { default: 'Archived favourites' })}</span>
                <!-- Zero only after a measurement: until then the figure is not known, so it is not shown. -->
                {#if cacheStats}
                    <span class="text-sm font-bold text-slate-900 dark:text-white">
                        {$_('settings.data.archive_usage_detail', {
                            values: { count: cacheStats.archive_durable ?? 0, size: `${cacheStats.archive_size_mb ?? 0} MB` },
                            default: '{count} kept, {size}'
                        })}
                    </span>
                {:else if cacheStatsError}
                    <span class="text-sm text-slate-600 dark:text-slate-300">{$_('settings.data.cache_size_unavailable', { default: "Couldn't load" })}</span>
                {:else}
                    <span class="text-sm text-slate-600 dark:text-slate-300">{$_('settings.data.cache_size_loading', { default: 'Measuring…' })}</span>
                {/if}
            </div>
            {#if (cacheStats?.archive_failed ?? 0) > 0}
                <p class="text-xs text-rose-700 dark:text-rose-300" data-archive-failed>
                    {$_('settings.data.archive_failed_count', {
                        values: { count: cacheStats?.archive_failed ?? 0 },
                        default: '{count} could not be archived. Open the visit to try again.'
                    })}
                </p>
            {/if}
        </div>

        <SettingsRow
            labelId="setting-cache-max_size_mb"
            label={$_('settings.data.storage_limit', { default: 'Limit the space photos and video use' })}
            description={storagePolicy}
        >
            <div class="flex flex-wrap items-center justify-end gap-3">
                {#if cacheMaxSizeMb > 0}
                    <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                        <span class="sr-only">{$_('settings.data.storage_limit_size', { default: 'Storage limit in GB' })}</span>
                        <input
                            id="cache-max-size-gb"
                            type="number"
                            min="0.5"
                            max="1024"
                            step="0.5"
                            value={limitFieldText}
                            onchange={(event) => commitStorageLimit(event.currentTarget.value)}
                            aria-invalid={cacheMaxSizeInvalid}
                            aria-describedby={cacheMaxSizeInvalid ? 'storage-limit-error' : undefined}
                            class="input-base w-24 py-2 text-right font-semibold"
                        />
                        <span aria-hidden="true">GB</span>
                    </label>
                {/if}
                <SettingsToggle
                    checked={cacheMaxSizeMb > 0}
                    labelledBy="setting-cache-max_size_mb"
                    srLabel={$_('settings.data.storage_limit', { default: 'Limit the space photos and video use' })}
                    onchange={setStorageLimit}
                />
            </div>
            {#if cacheMaxSizeInvalid && cacheMaxSizeMb > 0}
                <p id="storage-limit-error" class="mt-2 text-sm font-medium text-red-700 dark:text-red-300" role="alert" data-storage-limit-error>
                    {$_('settings.data.storage_limit_invalid', {
                        values: { size: storedMegabytesToGigabytes(cacheMaxSizeMb) },
                        default: 'Enter a size from 0.5 to 1024 GB. The limit stays at {size} GB until you do.'
                    })}
                </p>
            {/if}
        </SettingsRow>

        <div>
            <button
                type="button"
                onclick={handleCacheCleanup}
                disabled={cleaningCache}
                aria-label={$_('settings.data.cache_clear_button')}
                class="w-full sm:w-auto {buttonNeutralClass}"
            >
                {cleaningCache ? $_('settings.data.cleaning') : $_('settings.data.cache_clear_button')}
            </button>
        </div>

        <AdvancedSection
            id="data-cache-species"
            title={$_('settings.data.species_limits_title', { default: 'Per-species limits' })}
            openByDefault={cachePerSpeciesMinimum > 0 || cachePerSpeciesMaximum > 0}
        >
            <SettingsRow
                labelId="setting-cache-species-floor"
                label={$_('settings.data.per_species_minimum', { default: "Keep photos of each species' newest visits" })}
                description={$_('settings.data.per_species_minimum_help', { default: "That many of each species' newest visits keep their photos after they leave the history window, so a rare bird keeps its pictures. Video is not kept longer. The storage limit still applies." })}
            >
                <div class="flex flex-wrap items-center justify-end gap-3">
                    {#if cachePerSpeciesMinimum > 0}
                        <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                            <span class="sr-only">{$_('settings.data.per_species_minimum_count', { default: 'Visits kept per species' })}</span>
                            <input type="number" min="1" max="10000" step="1" value={cachePerSpeciesMinimum}
                                onchange={(event) => (cachePerSpeciesMinimum = wholeCount(event.currentTarget.value))}
                                class="input-base w-24 py-2 text-right font-semibold" />
                        </label>
                    {/if}
                    <SettingsToggle
                        checked={cachePerSpeciesMinimum > 0}
                        labelledBy="setting-cache-species-floor"
                        srLabel={$_('settings.data.per_species_minimum', { default: "Keep photos of each species' newest visits" })}
                        onchange={setSpeciesFloor}
                    />
                </div>
            </SettingsRow>

            <SettingsRow
                labelId="setting-cache-per_species_maximum"
                label={$_('settings.data.per_species_maximum', { default: 'Limit visits per species with photos and video' })}
                description={$_('settings.data.per_species_maximum_help', { default: "A species' visits beyond this number lose their photos and video, oldest first. The visits stay in history. Favourites don't count." })}
            >
                <div class="flex flex-wrap items-center justify-end gap-3">
                    {#if cachePerSpeciesMaximum > 0}
                        <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                            <span class="sr-only">{$_('settings.data.per_species_maximum_count', { default: 'Visits per species with photos and video' })}</span>
                            <input type="number" min="1" max="10000" step="1" value={cachePerSpeciesMaximum}
                                onchange={(event) => (cachePerSpeciesMaximum = wholeCount(event.currentTarget.value))}
                                class="input-base w-24 py-2 text-right font-semibold" />
                        </label>
                    {/if}
                    <SettingsToggle
                        checked={cachePerSpeciesMaximum > 0}
                        labelledBy="setting-cache-per_species_maximum"
                        srLabel={$_('settings.data.per_species_maximum', { default: 'Limit visits per species with photos and video' })}
                        onchange={setSpeciesMaximum}
                    />
                </div>
            </SettingsRow>
        </AdvancedSection>

        <AdvancedSection
            id="data-cache-advanced"
            title={$_('settings.data.cache_advanced_title', { default: 'Snapshot quality' })}
        >
            <SettingsRow
                labelId="setting-cache-hq"
                label={$_('settings.data.cache_high_quality_event_snapshots', { default: 'Best available event snapshots' })}
                description={`${$_('settings.data.cache_high_quality_event_snapshots_help', { default: 'After an event ends, choose the clearest main-stream frame and best crop available. The full frame is kept when a reliable crop cannot be made.' })} ${$_('settings.data.cache_high_quality_storage_note', { default: 'Each visit then also keeps full-resolution frames, often several MB, so set a storage limit if space is tight.' })}`}
            >
                <SettingsToggle
                    checked={cacheHighQualityEventSnapshots}
                    labelledBy="setting-cache-hq"
                    srLabel={$_('settings.data.cache_high_quality_event_snapshots', { default: 'Best available event snapshots' })}
                    onchange={(v) => (cacheHighQualityEventSnapshots = v)}
                />
            </SettingsRow>

            <SettingsRow
                labelId="setting-automatic-multi-bird-scan"
                layout="stacked"
                label={$_('settings.data.automatic_multi_bird_scan', { default: 'Automatically find additional birds' })}
                description={$_('settings.data.automatic_multi_bird_scan_help', { default: 'Off by default to reduce processing. Normal bird identification and the target bird’s crop continue, and existing findings are kept. Use Find more birds on a photograph whenever you need a scan. When enabled, scans run on retained whole frames.' })}
            >
                <SettingsToggle labelledBy="setting-automatic-multi-bird-scan" checked={cacheAutomaticMultiBirdScan}
                    srLabel={$_('settings.data.automatic_multi_bird_scan', { default: 'Automatically find additional birds' })}
                    onchange={(value) => (cacheAutomaticMultiBirdScan = value)} />
            </SettingsRow>

            <SettingsRow
                labelId="setting-bird-scan-mode"
                label={$_('settings.data.bird_scan_mode', { default: 'Bird scanning effort' })}
                description={$_('settings.data.bird_scan_mode_help', { default: 'Applies to manual and automatic scans. Standard uses less CPU. Intensive also searches tiles in large frames and classifies more crop choices. Neither guarantees every bird is found.' })}
                layout="stacked"
            >
                <SettingsSelect id="bird-scan-mode" value={cacheBirdScanMode}
                    ariaLabel={$_('settings.data.bird_scan_mode', { default: 'Bird scanning effort' })}
                    options={[
                        { value: 'standard', label: $_('settings.data.bird_scan_standard', { default: 'Standard' }) },
                        { value: 'intensive', label: $_('settings.data.bird_scan_intensive', { default: 'Intensive' }) }
                    ]}
                    onchange={(v) => (cacheBirdScanMode = v === 'standard' ? 'standard' : 'intensive')}
                />
            </SettingsRow>
            {#if cacheHighQualityEventSnapshots}
                <div class="flex items-start gap-3">
                    <svg class="mt-0.5 h-4 w-4 flex-none {cropDetectorReady ? 'text-success-500' : 'text-slate-600 dark:text-slate-400'}" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        {#if cropDetectorReady}
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                        {:else}
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7V4h3m10 0h3v3M4 17v3h3m10 0h3v-3M8 12h8" />
                        {/if}
                    </svg>
                    <div class="min-w-0">
                        <p class="text-sm font-bold text-slate-700 dark:text-slate-200">
                            {cropDetectorReady
                                ? $_('settings.data.cache_crop_detector_ready', { default: 'Crop detector ready' })
                                : $_('settings.data.cache_crop_fallback_ready', { default: 'Frigate tracking fallback ready' })}
                        </p>
                        <p class="mt-0.5 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                            {cropDetectorReady
                                ? $_('settings.data.cache_crop_detector_ready_help', { default: 'Frigate tracking hints and the crop detectors are evaluated automatically.' })
                                : $_('settings.data.cache_crop_fallback_ready_help', { default: 'Frigate tracking hints are used automatically; detector crops join in when a model is installed.' })}
                        </p>
                    </div>
                </div>

                <SettingsSlider
                    id="cache-hq-jpeg-quality"
                    label={$_('settings.data.cache_high_quality_event_snapshot_jpeg_quality', { default: 'HQ snapshot JPEG quality' })}
                    description={$_('settings.data.cache_high_quality_event_snapshot_jpeg_quality_help', { default: 'Higher values keep more detail but create larger derived snapshot files.' })}
                    bind:value={cacheHighQualityEventSnapshotJpegQuality}
                    min={70}
                    max={100}
                    step={1}
                    display={(value) => String(value)}
                    lowLabel="70"
                    highLabel="100"
                />
            {/if}
        </AdvancedSection>
    </SettingsCard>

    <SettingsCard
        title={$_('settings.data.config_backup_title', { default: 'Configuration backup' })}
        description={$_('settings.data.config_backup_desc', { default: 'Export or restore the complete YA-WAMF configuration as JSON, including secrets.' })}
    >
        <div class="space-y-4">
            <p class="max-w-prose text-sm font-medium text-slate-800 dark:text-slate-200">
                    {$_('settings.data.config_backup_secret_warning', { default: 'Backup files include tokens, webhooks, passwords, and auth secrets. Treat them like credentials.' })}
            </p>

            <div class="flex flex-wrap gap-3">
                <button
                    type="button"
                    onclick={handleExportConfigBackup}
                    disabled={exportingConfigBackup || importingConfigBackup}
                    aria-label={$_('settings.data.config_backup_export', { default: 'Export config JSON' })}
                    class="w-full sm:w-auto {buttonNeutralClass}"
                >
                    {#if exportingConfigBackup}
                        {@render spinner()}
                    {:else}
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                    {/if}
                    {exportingConfigBackup
                        ? $_('settings.data.config_backup_exporting', { default: 'Exporting...' })
                        : $_('settings.data.config_backup_export', { default: 'Export Config' })}
                </button>

                <button
                    type="button"
                    onclick={openConfigImportPicker}
                    disabled={exportingConfigBackup || importingConfigBackup}
                    aria-label={$_('settings.data.config_backup_import', { default: 'Import config JSON' })}
                    class="w-full sm:w-auto {buttonDangerOutlineClass}"
                >
                    {#if importingConfigBackup}
                        {@render spinner()}
                    {:else}
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l4-4m0 0l4 4m-4-4v12" />
                        </svg>
                    {/if}
                    {importingConfigBackup
                        ? $_('settings.data.config_backup_importing', { default: 'Importing...' })
                        : $_('settings.data.config_backup_import', { default: 'Import Config' })}
                </button>
            </div>

            <input
                bind:this={configImportInput}
                type="file"
                accept="application/json,.json"
                class="sr-only"
                onchange={handleConfigImportChange}
                aria-label={$_('settings.data.config_backup_import_file', { default: 'Select YA-WAMF config backup JSON' })}
            />

            <p class="max-w-prose text-sm text-slate-600 dark:text-slate-400">
                {$_('settings.data.config_backup_restore_note', { default: 'After importing on a fresh install, run a detection backfill to rebuild the event history from Frigate.' })}
            </p>
        </div>
    </SettingsCard>
</div>

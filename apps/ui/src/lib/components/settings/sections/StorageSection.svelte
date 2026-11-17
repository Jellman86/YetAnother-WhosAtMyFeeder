<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type DataSettingsView from '../DataSettings.svelte';
    import type MaintenanceSettingsView from '../MaintenanceSettings.svelte';
    import { loadDataSettings, loadMaintenanceSettings } from './part-loaders';

    // Storage & upkeep: what is kept and for how long, then the jobs that repair or fill in the
    // history, and deleting it. Holds what were the Data and Maintenance tabs.
    type Props = ComponentProps<typeof DataSettingsView> & ComponentProps<typeof MaintenanceSettingsView>;

    let {
        retentionDays = $bindable(),
        frigateMissingBehavior = $bindable(),
        autoPurgeMissingClips = $bindable(),
        autoPurgeMissingSnapshots = $bindable(),
        cacheClips = $bindable(),
        cacheHighQualityEventSnapshots = $bindable(),
        cacheHighQualityEventSnapshotJpegQuality = $bindable(),
        cacheRetentionDays = $bindable(),
        cachePerSpeciesMaximum = $bindable(),
        cacheMaxSizeMb = $bindable(),
        cacheMaxSizeInvalid = $bindable(),
        cacheAutomaticMultiBirdScan = $bindable(),
        cacheBirdScanMode = $bindable(),
        cachePerSpeciesMinimum = $bindable(),
        maintenanceStats,
        retentionNote,
        cacheStats,
        cacheStatsError,
        cacheStatsLoading,
        onRetryCacheStats,
        classifierStatus,
        cleaningUp,
        purgingMissingMedia,
        cleaningCache,
        exportingConfigBackup,
        importingConfigBackup,
        handleCleanup,
        handlePurgeMissingMedia,
        handleCacheCleanup,
        handleExportConfigBackup,
        handleImportConfigBackup,
        maintenanceMaxConcurrent = $bindable(),
        autoAnalyzeUnknowns = $bindable(),
        backfillDateRange = $bindable(),
        backfillStartDate = $bindable(),
        backfillEndDate = $bindable(),
        backfillCustomError,
        backfillCustomValid,
        clearingFavorites,
        backfilling,
        backfillResult,
        backfillTotal,
        weatherBackfilling,
        weatherBackfillResult,
        weatherBackfillTotal,
        taxonomyStatus,
        syncingTaxonomy,
        timezoneRepairPreview,
        previewingTimezoneRepair,
        applyingTimezoneRepair,
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
        handleClearFeedback
    }: Props = $props();
</script>

<div class="space-y-8" data-settings-section="storage">
    <!-- What is kept, for how long, and the configuration backup -->
    <div class="space-y-8" data-settings-part="data">
        <LazyRoute loader={loadDataSettings} label={$_('settings.tabs.data')}>
        {#snippet content(DataSettings)}
        <DataSettings
            bind:retentionDays
            bind:frigateMissingBehavior
            bind:autoPurgeMissingClips
            bind:autoPurgeMissingSnapshots
            bind:cacheClips
            bind:cacheHighQualityEventSnapshots
            bind:cacheHighQualityEventSnapshotJpegQuality
            bind:cacheRetentionDays
            bind:cachePerSpeciesMaximum
            bind:cacheMaxSizeMb
            bind:cacheMaxSizeInvalid
            bind:cacheAutomaticMultiBirdScan
            bind:cacheBirdScanMode
            bind:cachePerSpeciesMinimum
            {maintenanceStats}
            {retentionNote}
            {cacheStats}
            {cacheStatsError}
            {cacheStatsLoading}
            {onRetryCacheStats}
            {classifierStatus}
            {cleaningUp}
            {purgingMissingMedia}
            {cleaningCache}
            {exportingConfigBackup}
            {importingConfigBackup}
            {handleCleanup}
            {handlePurgeMissingMedia}
            {handleCacheCleanup}
            {handleExportConfigBackup}
            {handleImportConfigBackup}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <!-- Jobs that repair or fill in the history, and deleting it -->
    <div class="space-y-8" data-settings-part="maintenance">
        <LazyRoute loader={loadMaintenanceSettings} label={$_('settings.tabs.maintenance', { default: 'Maintenance' })}>
        {#snippet content(MaintenanceSettings)}
        <MaintenanceSettings
            bind:maintenanceMaxConcurrent
            bind:autoAnalyzeUnknowns
            bind:backfillDateRange
            bind:backfillStartDate
            bind:backfillEndDate
            {backfillCustomError}
            {backfillCustomValid}
            {clearingFavorites}
            {backfilling}
            {backfillResult}
            {backfillTotal}
            {weatherBackfilling}
            {weatherBackfillResult}
            {weatherBackfillTotal}
            {taxonomyStatus}
            {syncingTaxonomy}
            {timezoneRepairPreview}
            {previewingTimezoneRepair}
            {applyingTimezoneRepair}
            {resettingDatabase}
            {clearingFeedback}
            {analyzingUnknowns}
            {analysisStatus}
            {analysisTotal}
            {handleClearFavorites}
            {handleStartTaxonomySync}
            {handlePreviewTimezoneRepair}
            {handleApplyTimezoneRepair}
            {handleBackfill}
            {handleWeatherBackfill}
            {handleAnalyzeUnknowns}
            {handleResetDatabase}
            {handleClearFeedback}
        />
        {/snippet}
        </LazyRoute>
    </div>
</div>

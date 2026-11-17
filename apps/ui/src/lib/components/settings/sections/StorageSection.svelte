<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type DataSettingsView from '../DataSettings.svelte';
    import type MaintenanceSettingsView from '../MaintenanceSettings.svelte';
    import type DangerZoneSettingsView from '../DangerZoneSettings.svelte';
    import SectionMore from './SectionMore.svelte';
    import { loadDangerZoneSettings, loadDataSettings, loadMaintenanceSettings } from './part-loaders';

    // Storage & upkeep: what is kept and for how long, and the configuration backup, first; what
    // happens when Frigate loses a visit and the jobs that repair or fill in the history under More
    // options; deleting data last, outside it. Holds what were the Data and Maintenance tabs.
    type Props = Omit<ComponentProps<typeof DataSettingsView>, 'region'>
        & ComponentProps<typeof MaintenanceSettingsView>
        & ComponentProps<typeof DangerZoneSettingsView>;

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
            region="main"
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

    <SectionMore section="storage" summary={$_('settings.more.storage', { default: 'When Frigate loses a visit, and the jobs that repair or fill in the history' })}>
        <div class="space-y-8" data-settings-data-more>
            <LazyRoute loader={loadDataSettings} label={$_('settings.tabs.data')}>
            {#snippet content(DataSettings)}
            <DataSettings
                region="more"
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

        <!-- Jobs that repair or fill in the history -->
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
                {analyzingUnknowns}
                {analysisStatus}
                {analysisTotal}
                {handleStartTaxonomySync}
                {handlePreviewTimezoneRepair}
                {handleApplyTimezoneRepair}
                {handleBackfill}
                {handleWeatherBackfill}
                {handleAnalyzeUnknowns}
            />
            {/snippet}
            </LazyRoute>
        </div>
    </SectionMore>

    <!-- Deleting data: last, outside More options, each action stated in full beside its button. -->
    <div class="space-y-8" data-settings-danger>
        <LazyRoute loader={loadDangerZoneSettings} label={$_('settings.danger.title')}>
        {#snippet content(DangerZoneSettings)}
        <DangerZoneSettings
            {clearingFeedback}
            {clearingFavorites}
            {resettingDatabase}
            {handleClearFeedback}
            {handleClearFavorites}
            {handleResetDatabase}
        />
        {/snippet}
        </LazyRoute>
    </div>
</div>

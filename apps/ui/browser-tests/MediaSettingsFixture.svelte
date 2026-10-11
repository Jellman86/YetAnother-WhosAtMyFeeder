<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import DataSettings from '../src/lib/components/settings/DataSettings.svelte';
    import type { CacheStats } from '../src/lib/api/maintenance';
    const noop = async (): Promise<void> => {};
    let maximum = $state(0);
    let budget = $state(0);
    let scan = $state<'standard' | 'intensive'>('intensive');
    const props: Omit<ComponentProps<typeof DataSettings>, 'cachePerSpeciesMaximum' | 'cacheMaxSizeMb' | 'cacheBirdScanMode'> = {
        maintenanceStats: null,
        retentionDays: 0,
        maintenanceMaxConcurrent: 1,
        frigateMissingBehavior: 'mark_missing',
        autoPurgeMissingClips: false,
        autoPurgeMissingSnapshots: false,
        autoAnalyzeUnknowns: false,
        cacheRetentionDays: 0,
        cachePerSpeciesMinimum: 0,
        cleaningUp: false,
        clearingFavorites: false,
        purgingMissingMedia: false,
        cacheClips: false,
        cacheHighQualityEventSnapshots: true,
        cacheHighQualityEventSnapshotJpegQuality: 95,
        // ?storage=unavailable stands in for a media folder that cannot be written.
        cacheStats:
            new URLSearchParams(location.search).get('storage') === 'unavailable'
                ? ({ storage_available: false, total_size_mb: 0 } as unknown as CacheStats)
                : null,
        classifierStatus: null,
        cleaningCache: false,
        taxonomyStatus: null,
        syncingTaxonomy: false,
        timezoneRepairPreview: null,
        previewingTimezoneRepair: false,
        applyingTimezoneRepair: false,
        backfillDateRange: 'week',
        backfillStartDate: '',
        backfillEndDate: '',
        backfillCustomError: null,
        backfillCustomValid: true,
        backfilling: false,
        backfillResult: null,
        backfillTotal: 0,
        weatherBackfilling: false,
        weatherBackfillResult: null,
        weatherBackfillTotal: 0,
        resettingDatabase: false,
        clearingFeedback: false,
        exportingConfigBackup: false,
        importingConfigBackup: false,
        analyzingUnknowns: false,
        analysisStatus: null,
        analysisTotal: 0,
        handleCleanup: noop,
        handleClearFavorites: noop,
        handlePurgeMissingMedia: noop,
        handleCacheCleanup: noop,
        handleStartTaxonomySync: noop,
        handlePreviewTimezoneRepair: noop,
        handleApplyTimezoneRepair: noop,
        handleBackfill: noop,
        handleWeatherBackfill: noop,
        handleExportConfigBackup: noop,
        handleImportConfigBackup: noop,
        handleAnalyzeUnknowns: noop,
        handleResetDatabase: noop,
        handleClearFeedback: noop,
    };
</script>

<main class="mx-auto max-w-4xl space-y-6 p-4">
    <DataSettings {...props} bind:cachePerSpeciesMaximum={maximum} bind:cacheMaxSizeMb={budget} bind:cacheBirdScanMode={scan} />
    <output aria-label="Selected cache settings">{maximum} / {budget} / {scan}</output>
</main>

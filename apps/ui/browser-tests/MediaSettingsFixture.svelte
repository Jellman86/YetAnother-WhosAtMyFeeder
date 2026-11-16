<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import DataSettings from '../src/lib/components/settings/DataSettings.svelte';
    import type { CacheStats } from '../src/lib/api/maintenance';
    const noop = async (): Promise<void> => {};
    let maximum = $state(0);
    let budget = $state(0);
    let budgetInvalid = $state(false);
    let scan = $state<'standard' | 'intensive'>('intensive');
    const props: Omit<ComponentProps<typeof DataSettings>, 'cachePerSpeciesMaximum' | 'cacheMaxSizeMb' | 'cacheMaxSizeInvalid' | 'cacheBirdScanMode'> = {
        maintenanceStats: null,
        retentionDays: 0,
        frigateMissingBehavior: 'mark_missing',
        autoPurgeMissingClips: false,
        autoPurgeMissingSnapshots: false,
        cacheRetentionDays: 0,
        cachePerSpeciesMinimum: 0,
        cleaningUp: false,
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
        exportingConfigBackup: false,
        importingConfigBackup: false,
        handleCleanup: noop,
        handlePurgeMissingMedia: noop,
        handleCacheCleanup: noop,
        handleExportConfigBackup: noop,
        handleImportConfigBackup: noop,
    };
</script>

<main class="mx-auto max-w-4xl space-y-6 p-4">
    <DataSettings {...props} bind:cachePerSpeciesMaximum={maximum} bind:cacheMaxSizeMb={budget} bind:cacheMaxSizeInvalid={budgetInvalid} bind:cacheBirdScanMode={scan} />
    <output aria-label="Storage limit invalid">{budgetInvalid}</output>
    <output aria-label="Selected cache settings">{maximum} / {budget} / {scan}</output>
</main>

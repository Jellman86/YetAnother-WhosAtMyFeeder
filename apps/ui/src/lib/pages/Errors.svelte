<script lang="ts">
    import { _ } from 'svelte-i18n';
    import {
        jobDiagnosticsStore,
        type JobDiagnosticGroup,
        type JobDiagnosticBundle
    } from '../stores/job_diagnostics.svelte';
    import { formatDateTime } from '../utils/datetime';

    let diagnosticGroups = $derived(jobDiagnosticsStore.groups);
    let healthSnapshots = $derived(jobDiagnosticsStore.healthSnapshots);
    let bundles = $derived(jobDiagnosticsStore.bundles);
    let diagnosticEventCount = $derived(diagnosticGroups.reduce((sum, group) => sum + group.count, 0));
    let latestHealthSnapshot = $derived(healthSnapshots.length > 0 ? healthSnapshots[0] : null);
    let captureLabel = $state('');

    function severityClass(group: JobDiagnosticGroup): string {
        if (group.severity === 'critical') return 'text-rose-700 dark:text-rose-300';
        if (group.severity === 'error') return 'text-amber-700 dark:text-amber-300';
        return 'text-slate-600 dark:text-slate-300';
    }

    function severityBadgeClass(group: JobDiagnosticGroup): string {
        if (group.severity === 'critical') return 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200';
        if (group.severity === 'error') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200';
        return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200';
    }

    function findHealthSnapshot(snapshotId?: string) {
        if (!snapshotId) return null;
        return healthSnapshots.find((snapshot) => snapshot.id === snapshotId) ?? null;
    }

    function exportDiagnostics() {
        jobDiagnosticsStore.downloadJson();
    }

    function captureBundle() {
        const label = captureLabel.trim();
        const bundle = jobDiagnosticsStore.captureBundle(label || undefined);
        if (bundle) {
            captureLabel = '';
        }
    }

    function downloadBundle(bundle: JobDiagnosticBundle) {
        jobDiagnosticsStore.downloadBundle(bundle.id);
    }
</script>

<div class="space-y-6">
    <section class="card-base p-6">
        <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
                <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.errors_title', { default: 'Errors' })}</h3>
                <p class="text-xs text-slate-500">
                    {$_('jobs.errors_subtitle', { default: 'Grouped diagnostics to avoid spam; export JSON for troubleshooting.' })}
                </p>
            </div>
            <div class="flex items-center gap-2">
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={exportDiagnostics}>
                    {$_('jobs.errors_export', { default: 'Export Current JSON' })}
                </button>
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => jobDiagnosticsStore.clear()}>
                    {$_('jobs.errors_clear', { default: 'Clear Live Errors' })}
                </button>
            </div>
        </div>

        <div class="mb-3 text-[11px] font-semibold text-slate-500 dark:text-slate-300">
            {$_('jobs.errors_summary', {
                values: {
                    groups: diagnosticGroups.length.toLocaleString(),
                    events: diagnosticEventCount.toLocaleString(),
                    snapshots: healthSnapshots.length.toLocaleString()
                },
                default: '{groups} groups • {events} events • {snapshots} health snapshots'
            })}
            {#if latestHealthSnapshot}
                <span class="ml-2">
                    · {$_('jobs.errors_latest_health', {
                        values: {
                            status: latestHealthSnapshot.status,
                            at: formatDateTime(latestHealthSnapshot.timestamp)
                        },
                        default: 'Latest health: {status} at {at}'
                    })}
                </span>
            {/if}
        </div>

        {#if diagnosticGroups.length === 0}
            <p class="text-xs text-slate-500">{$_('jobs.errors_empty', { default: 'No grouped errors recorded yet.' })}</p>
        {:else}
            <div class="space-y-2">
                {#each diagnosticGroups as group (group.fingerprint)}
                    {@const snapshot = findHealthSnapshot(group.latestHealthSnapshotId)}
                    <details class="rounded-xl border border-slate-200/80 dark:border-slate-700/60 bg-white/80 dark:bg-slate-900/60 px-3 py-2">
                        <summary class="list-none cursor-pointer">
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <div class="flex min-w-0 items-center gap-2">
                                    <span class={`inline-flex rounded-md px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${severityBadgeClass(group)}`}>
                                        {group.severity}
                                    </span>
                                    <span class={`text-xs font-black uppercase tracking-wide ${severityClass(group)}`}>
                                        {group.component}{group.stage ? ` · ${group.stage}` : ''}
                                    </span>
                                    <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{group.reasonCode}</span>
                                </div>
                                <span class="text-[10px] font-black uppercase tracking-wider text-slate-500">
                                    {$_('jobs.errors_count', { values: { count: group.count.toLocaleString() }, default: '{count}x' })}
                                </span>
                            </div>
                            <p class="mt-1 text-xs text-slate-600 dark:text-slate-300">{group.message}</p>
                        </summary>
                        <div class="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                            <div>{$_('jobs.errors_first_seen', { default: 'First seen' })}: {formatDateTime(group.firstSeen)}</div>
                            <div>{$_('jobs.errors_last_seen', { default: 'Last seen' })}: {formatDateTime(group.lastSeen)}</div>
                        </div>
                        {#if group.sampleEventIds.length > 0}
                            <p class="mt-2 text-[10px] text-slate-500 dark:text-slate-300">
                                {$_('jobs.errors_samples', { default: 'Sample event IDs' })}: {group.sampleEventIds.join(', ')}
                            </p>
                        {/if}
                        {#if snapshot}
                            <p class="mt-2 text-[10px] text-slate-500 dark:text-slate-300">
                                {$_('jobs.errors_snapshot_ref', {
                                    values: {
                                        status: snapshot.status,
                                        at: formatDateTime(snapshot.timestamp)
                                    },
                                    default: 'Health snapshot: {status} @ {at}'
                                })}
                            </p>
                        {/if}
                    </details>
                {/each}
            </div>
        {/if}
    </section>

    <section class="card-base p-6">
        <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
                <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.error_bundles_title', { default: 'Error Bundles' })}</h3>
                <p class="text-xs text-slate-500">
                    {$_('jobs.error_bundles_subtitle', { default: 'Capture and keep multiple diagnostics bundles, then download any bundle later.' })}
                </p>
            </div>
            <div class="flex items-center gap-2">
                <input
                    class="input input-bordered h-9 w-52 text-xs"
                    bind:value={captureLabel}
                    placeholder={$_('jobs.error_bundles_label_placeholder', { default: 'Optional bundle label' })}
                />
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={captureBundle}>
                    {$_('jobs.error_bundles_capture', { default: 'Capture Bundle' })}
                </button>
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => jobDiagnosticsStore.clearBundles()}>
                    {$_('jobs.error_bundles_clear', { default: 'Clear Bundles' })}
                </button>
            </div>
        </div>

        {#if bundles.length === 0}
            <p class="text-xs text-slate-500">{$_('jobs.error_bundles_empty', { default: 'No saved bundles yet.' })}</p>
        {:else}
            <div class="divide-y divide-slate-100 dark:divide-slate-800/60">
                {#each bundles as bundle (bundle.id)}
                    <div class="py-3 px-2">
                        <div class="flex flex-wrap items-start justify-between gap-3">
                            <div class="min-w-0 flex-1">
                                <p class="text-sm font-semibold text-slate-900 dark:text-white truncate">{bundle.label}</p>
                                <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mt-1">
                                    {formatDateTime(bundle.createdAt)}
                                </p>
                                <p class="text-xs text-slate-500 dark:text-slate-300 mt-1">
                                    {$_('jobs.error_bundles_stats', {
                                        values: {
                                            groups: bundle.summary.error_groups.toLocaleString(),
                                            events: bundle.summary.total_events.toLocaleString(),
                                            snapshots: bundle.summary.health_snapshots.toLocaleString()
                                        },
                                        default: '{groups} groups • {events} events • {snapshots} snapshots'
                                    })}
                                </p>
                            </div>
                            <div class="flex items-center gap-2">
                                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => downloadBundle(bundle)}>
                                    {$_('jobs.error_bundles_download', { default: 'Download' })}
                                </button>
                                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => jobDiagnosticsStore.removeBundle(bundle.id)}>
                                    {$_('jobs.error_bundles_delete', { default: 'Delete' })}
                                </button>
                            </div>
                        </div>
                    </div>
                {/each}
            </div>
        {/if}
    </section>
</div>

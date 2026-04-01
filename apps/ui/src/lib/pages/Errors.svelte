<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import {
        incidentWorkspaceStore,
        type IncidentRecord
    } from '../stores/incident_workspace.svelte';
    import {
        jobDiagnosticsStore,
        type JobDiagnosticBundle
    } from '../stores/job_diagnostics.svelte';
    import { formatDateTime } from '../utils/datetime';

    let currentIssues = $derived(incidentWorkspaceStore.currentIssues);
    let recentIncidents = $derived(incidentWorkspaceStore.recentIncidents);
    let workspacePayload = $derived(incidentWorkspaceStore.workspacePayload);
    let healthSnapshots = $derived(jobDiagnosticsStore.healthSnapshots);
    let bundles = $derived(jobDiagnosticsStore.bundles);
    let captureLabel = $state('');
    let reportNotes = $state('');
    let selectedIncidentId = $state<string | null>(null);
    let refreshing = $state(false);
    let clearing = $state(false);
    let refreshError = $state('');

    let allIncidents = $derived([...currentIssues, ...recentIncidents]);
    let workspaceCapturedAt = $derived.by(() => {
        const raw = workspacePayload?.backend_diagnostics?.captured_at;
        if (typeof raw !== 'string' || raw.length === 0) return null;
        const parsed = Date.parse(raw);
        return Number.isFinite(parsed) ? parsed : null;
    });
    let selectedIncident = $derived.by(() =>
        allIncidents.find((incident) => incident.id === selectedIncidentId)
        ?? allIncidents[0]
        ?? null
    );
    let selectedDiagnosticGroups = $derived.by(() => incidentWorkspaceStore.getDiagnosticGroups(selectedIncident));
    let backendDiagnosticGroupCount = $derived.by(
        () => [...currentIssues, ...recentIncidents].reduce(
            (count, incident) => count + incidentWorkspaceStore.getDiagnosticGroups(incident).length,
            0
        )
    );
    let latestBundle = $derived(bundles[0] ?? null);

    $effect(() => {
        if (!selectedIncidentId && allIncidents[0]) {
            selectedIncidentId = allIncidents[0].id;
        }
        if (selectedIncidentId && !allIncidents.some((incident) => incident.id === selectedIncidentId)) {
            selectedIncidentId = allIncidents[0]?.id ?? null;
        }
    });

    onMount(() => {
        void refreshWorkspace();
    });

    async function refreshWorkspace() {
        refreshing = true;
        refreshError = '';
        try {
            await incidentWorkspaceStore.refresh();
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to refresh incident workspace';
            refreshError = message;
            jobDiagnosticsStore.recordError({
                source: 'runtime',
                component: 'incident_workspace',
                reasonCode: 'refresh_failed',
                message,
                severity: 'warning',
                context: { scope: 'Errors.svelte' }
            });
        } finally {
            refreshing = false;
        }
    }

    async function clearWorkspace() {
        clearing = true;
        refreshError = '';
        try {
            await incidentWorkspaceStore.clearRemote();
            jobDiagnosticsStore.clear();
            selectedIncidentId = null;
            await incidentWorkspaceStore.refresh();
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to clear incident workspace';
            refreshError = message;
            jobDiagnosticsStore.recordError({
                source: 'runtime',
                component: 'incident_workspace',
                reasonCode: 'clear_failed',
                message,
                severity: 'warning',
                context: { scope: 'Errors.svelte' }
            });
        } finally {
            clearing = false;
        }
    }

    function statusBadgeClass(incident: IncidentRecord): string {
        if (incident.status === 'resolved') return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200';
        if (incident.status === 'recovering') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200';
        return 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200';
    }

    function severityClass(incident: IncidentRecord): string {
        if (incident.severity === 'critical') return 'text-rose-700 dark:text-rose-300';
        if (incident.severity === 'error') return 'text-amber-700 dark:text-amber-300';
        return 'text-slate-600 dark:text-slate-300';
    }

    function captureBundle() {
        const label = captureLabel.trim();
        const notes = reportNotes.trim();
        const bundle = jobDiagnosticsStore.captureBundle(label || undefined, notes || undefined, workspacePayload ?? undefined);
        if (bundle) {
            captureLabel = '';
        }
    }

    function downloadBundle(bundle: JobDiagnosticBundle) {
        jobDiagnosticsStore.downloadBundle(bundle.id);
    }

    function bundleReport(bundle: JobDiagnosticBundle): { notes: string | null; generatedAt: string | null } {
        const report = bundle.payload && typeof bundle.payload === 'object'
            ? (bundle.payload as Record<string, unknown>).report
            : null;
        const reportObject = report && typeof report === 'object' ? report as Record<string, unknown> : null;
        const notes = reportObject && typeof reportObject.notes === 'string'
            ? reportObject.notes.trim()
            : '';
        const generatedAt = reportObject && typeof reportObject.generated_at === 'string'
            ? reportObject.generated_at.trim()
            : '';
        return {
            notes: notes.length > 0 ? notes : null,
            generatedAt: generatedAt.length > 0 ? generatedAt : null
        };
    }

    function bundleSummaryText(bundle: JobDiagnosticBundle): string {
        return `${bundle.summary.error_groups.toLocaleString()} groups • ${bundle.summary.total_events.toLocaleString()} events • ${bundle.summary.health_snapshots.toLocaleString()} snapshots`;
    }

    function bundleNotesPreview(bundle: JobDiagnosticBundle): string | null {
        const notes = bundleReport(bundle).notes;
        if (!notes) return null;
        return notes.length > 140 ? `${notes.slice(0, 137)}...` : notes;
    }

    async function copyIssueSummary() {
        const draft = incidentWorkspaceStore.buildIssueDraft(selectedIncident, {
            bundleLabel: captureLabel.trim() || undefined,
            bundleSchemaVersion: Number(jobDiagnosticsStore.exportJson().schema_version ?? 0) || null,
            reportNotes: reportNotes.trim() || undefined
        });
        if (!draft.body || typeof navigator === 'undefined' || !navigator.clipboard) return;
        await navigator.clipboard.writeText(draft.body);
    }

    function openGithubIssue() {
        if (!selectedIncident || typeof window === 'undefined') return;
        const draft = incidentWorkspaceStore.buildIssueDraft(selectedIncident, {
            bundleLabel: captureLabel.trim() || undefined,
            bundleSchemaVersion: Number(jobDiagnosticsStore.exportJson().schema_version ?? 0) || null,
            reportNotes: reportNotes.trim() || undefined
        });
        const title = encodeURIComponent(draft.title);
        const body = encodeURIComponent(draft.body);
        window.open(
            `https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/new?title=${title}&body=${body}`,
            '_blank',
            'noopener,noreferrer'
        );
    }
</script>

<div class="space-y-6">
    <section class="card-base p-6">
        <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
                <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.errors_title', { default: 'Errors' })}</h3>
                <p class="text-xs text-slate-500">
                    {$_('jobs.errors_subtitle', { default: 'Owner incident workspace for current failures, evidence bundles, and issue reporting.' })}
                </p>
            </div>
            <div class="flex items-center gap-2">
                <button
                    type="button"
                    class="btn btn-secondary px-3 py-2 text-xs"
                    onclick={() => jobDiagnosticsStore.downloadJson(undefined, workspacePayload ?? undefined)}
                >
                    {$_('jobs.errors_export', { default: 'Export Current JSON' })}
                </button>
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={clearWorkspace} disabled={clearing || refreshing}>
                    {clearing ? 'Clearing...' : $_('jobs.errors_clear', { default: 'Clear Live Errors' })}
                </button>
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={refreshWorkspace} disabled={refreshing}>
                    {refreshing ? 'Refreshing...' : 'Refresh'}
                </button>
            </div>
        </div>

        <div class="text-[11px] font-semibold text-slate-500 dark:text-slate-300">
            {currentIssues.length.toLocaleString()} current issues • {recentIncidents.length.toLocaleString()} recent incidents • {backendDiagnosticGroupCount.toLocaleString()} grouped diagnostics
            {#if workspacePayload?.health}
                <span class="ml-2">· {$_('jobs.errors_latest_health', {
                    values: {
                        status: String(workspacePayload.health.status ?? 'unknown'),
                        at: formatDateTime(workspaceCapturedAt ?? Date.now())
                    },
                    default: 'Latest health: {status} at {at}'
                })}</span>
            {/if}
        </div>

        {#if refreshError}
            <p class="mt-2 text-xs text-rose-600 dark:text-rose-300">{refreshError}</p>
        {/if}
    </section>

    <div class="grid grid-cols-1 xl:grid-cols-[1.2fr_1fr] gap-6">
        <section class="card-base p-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">
                    {$_('jobs.current_issues_title', { default: 'Current Issues' })}
                </h3>
                <span class="text-[10px] font-semibold text-slate-400">{currentIssues.length}</span>
            </div>
            {#if currentIssues.length === 0}
                <p class="text-xs text-slate-500">{$_('jobs.current_issues_empty', { default: 'No current incidents detected.' })}</p>
            {:else}
                <div class="space-y-2">
                    {#each currentIssues as incident (incident.id)}
                        <button
                            type="button"
                            class="w-full rounded-xl border border-slate-200/80 dark:border-slate-700/60 bg-white/80 dark:bg-slate-900/60 px-3 py-3 text-left"
                            onclick={() => (selectedIncidentId = incident.id)}
                        >
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <div class="min-w-0 flex items-center gap-2">
                                    <span class={`inline-flex rounded-md px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${statusBadgeClass(incident)}`}>
                                        {incident.status}
                                    </span>
                                    <span class={`text-xs font-black uppercase tracking-wide ${severityClass(incident)}`}>
                                        {incident.affected_area}
                                    </span>
                                </div>
                                <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                    {formatDateTime(incident.lastSeenAt)}
                                </span>
                            </div>
                            <p class="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{incident.title}</p>
                            <p class="mt-1 text-xs text-slate-500 dark:text-slate-300">{incident.summary}</p>
                        </button>
                    {/each}
                </div>
            {/if}
        </section>

        <section class="card-base p-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">
                    {$_('jobs.recent_incidents_title', { default: 'Recent Incidents' })}
                </h3>
                <span class="text-[10px] font-semibold text-slate-400">{recentIncidents.length}</span>
            </div>
            {#if recentIncidents.length === 0}
                <p class="text-xs text-slate-500">{$_('jobs.recent_incidents_empty', { default: 'No resolved incidents yet.' })}</p>
            {:else}
                <div class="space-y-2">
                    {#each recentIncidents as incident (incident.id)}
                        <button
                            type="button"
                            class="w-full rounded-xl border border-slate-200/80 dark:border-slate-700/60 bg-white/70 dark:bg-slate-900/50 px-3 py-3 text-left"
                            onclick={() => (selectedIncidentId = incident.id)}
                        >
                            <div class="flex items-center justify-between gap-2">
                                <span class={`inline-flex rounded-md px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${statusBadgeClass(incident)}`}>
                                    {incident.status}
                                </span>
                                <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                    {formatDateTime(incident.lastSeenAt)}
                                </span>
                            </div>
                            <p class="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{incident.title}</p>
                            <p class="mt-1 text-xs text-slate-500 dark:text-slate-300">{incident.summary}</p>
                        </button>
                    {/each}
                </div>
            {/if}
        </section>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-[1.3fr_1fr] gap-6">
        <section class="card-base p-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">
                    {$_('jobs.incident_detail_title', { default: 'Incident Detail' })}
                </h3>
                {#if selectedIncident}
                    <span class={`inline-flex rounded-md px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${statusBadgeClass(selectedIncident)}`}>
                        {selectedIncident.status}
                    </span>
                {/if}
            </div>
            {#if !selectedIncident}
                <p class="text-xs text-slate-500">{$_('jobs.report_issue_empty', { default: 'Select an incident to inspect or report it.' })}</p>
            {:else}
                <div class="space-y-4">
                    <div>
                        <p class="text-sm font-semibold text-slate-900 dark:text-white">{selectedIncident.title}</p>
                        <p class="mt-1 text-xs text-slate-500 dark:text-slate-300">{selectedIncident.summary}</p>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        <div>Area: {selectedIncident.affected_area}</div>
                        <div>Reason: {selectedIncident.primaryReasonCode}</div>
                        <div>First seen: {formatDateTime(selectedIncident.startedAt)}</div>
                        <div>Last seen: {formatDateTime(selectedIncident.lastSeenAt)}</div>
                    </div>
                    <div>
                        <p class="text-[11px] font-black uppercase tracking-wider text-slate-400 mb-2">Evidence</p>
                        <p class="text-xs text-slate-500 dark:text-slate-300">
                            {selectedIncident.evidenceRefs.length > 0 ? selectedIncident.evidenceRefs.join(', ') : 'No evidence references yet.'}
                        </p>
                    </div>
                    <div>
                        <p class="text-[11px] font-black uppercase tracking-wider text-slate-400 mb-2">Grouped Diagnostics</p>
                        {#if selectedDiagnosticGroups.length === 0}
                            <p class="text-xs text-slate-500">{$_('jobs.errors_empty', { default: 'No grouped errors recorded yet.' })}</p>
                        {:else}
                            <div class="space-y-2">
                                {#each selectedDiagnosticGroups.slice(0, 5) as group (group.fingerprint)}
                                    <div class="rounded-xl border border-slate-200/80 dark:border-slate-700/60 px-3 py-2">
                                        <div class="flex flex-wrap items-center justify-between gap-2">
                                            <span class="text-[10px] font-black uppercase tracking-wider text-slate-500">{group.component} · {group.reasonCode}</span>
                                            <span class="text-[10px] font-semibold text-slate-400">{group.count}x</span>
                                        </div>
                                        <p class="mt-1 text-xs text-slate-500 dark:text-slate-300">{group.message}</p>
                                    </div>
                                {/each}
                            </div>
                        {/if}
                    </div>
                    <div>
                        <p class="text-[11px] font-black uppercase tracking-wider text-slate-400 mb-2">Health Snapshots</p>
                        <p class="text-xs text-slate-500 dark:text-slate-300">{healthSnapshots.length.toLocaleString()} captured locally</p>
                    </div>
                </div>
            {/if}
        </section>

        <section class="card-base p-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">
                    {$_('jobs.report_issue_title', { default: 'Report Issue' })}
                </h3>
            </div>
            {#if !selectedIncident}
                <p class="text-xs text-slate-500">{$_('jobs.report_issue_empty', { default: 'Select an incident to inspect or report it.' })}</p>
            {:else}
                <div class="space-y-3">
                    <textarea class="textarea textarea-bordered min-h-24 w-full text-xs" bind:value={reportNotes} placeholder="Optional repro notes"></textarea>
                    <textarea class="textarea textarea-bordered min-h-40 w-full text-xs" readonly value={incidentWorkspaceStore.buildIssueDraft(selectedIncident, {
                        bundleLabel: captureLabel.trim() || undefined,
                        bundleSchemaVersion: Number(jobDiagnosticsStore.exportJson().schema_version ?? 0) || null,
                        reportNotes: reportNotes.trim() || undefined
                    }).body}></textarea>
                    <div class="flex items-center gap-2">
                        <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={copyIssueSummary}>
                            {$_('jobs.report_issue_copy_summary', { default: 'Copy Issue Summary' })}
                        </button>
                        <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={openGithubIssue}>
                            {$_('jobs.report_issue_open_github', { default: 'Open GitHub Issue' })}
                        </button>
                    </div>
                </div>
            {/if}
        </section>
    </div>

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

        {#if latestBundle}
            <div class="rounded-3xl border border-emerald-200/80 bg-gradient-to-br from-emerald-50 via-white to-white p-5 shadow-sm">
                <div class="flex flex-wrap items-start justify-between gap-4">
                    <div class="min-w-0 flex-1">
                        <div class="flex flex-wrap items-center gap-2">
                            <span class="inline-flex items-center rounded-full bg-emerald-600 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-white">
                                Saved locally
                            </span>
                            <span class="inline-flex items-center rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700">
                                Latest Bundle Ready
                            </span>
                        </div>
                        <h4 class="mt-3 truncate text-lg font-semibold text-slate-900 dark:text-white">{latestBundle.label}</h4>
                        <p class="mt-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
                            Captured {formatDateTime(latestBundle.createdAt)}
                        </p>
                        <p class="mt-2 text-sm text-slate-600 dark:text-slate-300">{bundleSummaryText(latestBundle)}</p>
                        {#if bundleNotesPreview(latestBundle)}
                            <p class="mt-3 rounded-2xl bg-white/75 px-3 py-2 text-xs text-slate-600 dark:bg-slate-950/40 dark:text-slate-200">
                                <span class="font-black uppercase tracking-wider text-slate-400">Notes</span>
                                <span class="ml-2">{bundleNotesPreview(latestBundle)}</span>
                            </p>
                        {/if}
                    </div>
                    <div class="flex flex-col gap-2 sm:items-end">
                        <button type="button" class="btn btn-primary px-4 py-2 text-xs" onclick={() => downloadBundle(latestBundle)}>
                            Download Latest
                        </button>
                        <button type="button" class="btn btn-secondary px-4 py-2 text-xs" onclick={() => jobDiagnosticsStore.removeBundle(latestBundle.id)}>
                            Delete Latest
                        </button>
                    </div>
                </div>
            </div>
        {:else}
            <div class="rounded-3xl border border-dashed border-slate-200 bg-slate-50/70 p-5 text-sm text-slate-500 dark:border-slate-700/60 dark:bg-slate-900/40 dark:text-slate-300">
                No captured bundles available yet.
            </div>
        {/if}

        <div class="mt-5 flex items-center justify-between gap-3">
            <div>
                <h4 class="text-[11px] font-black uppercase tracking-wider text-slate-500">Saved Bundles</h4>
                <p class="text-xs text-slate-500">Distinct snapshots stay local until you download or delete them.</p>
            </div>
            <span class="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:border-slate-700 dark:bg-slate-950/30">
                {bundles.length.toLocaleString()} saved
            </span>
        </div>

        {#if bundles.length === 0}
            <p class="mt-3 text-xs text-slate-500">No captured bundles available yet.</p>
        {:else}
            <div class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                {#each bundles as bundle, index (bundle.id)}
                    <article class={`rounded-3xl border p-4 shadow-sm ${index === 0 ? 'border-emerald-200/80 bg-white' : 'border-slate-200/80 bg-white/85 dark:border-slate-700/60 dark:bg-slate-950/40'}`}>
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0 flex-1">
                                <div class="flex flex-wrap items-center gap-2">
                                    {#if index === 0}
                                        <span class="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700">
                                            Newest
                                        </span>
                                    {/if}
                                    <p class="truncate text-sm font-semibold text-slate-900 dark:text-white">{bundle.label}</p>
                                </div>
                                <p class="mt-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                    {formatDateTime(bundle.createdAt)}
                                </p>
                                <p class="mt-2 text-xs text-slate-500 dark:text-slate-300">{bundleSummaryText(bundle)}</p>
                                {#if bundleNotesPreview(bundle)}
                                    <p class="mt-3 line-clamp-3 text-xs text-slate-600 dark:text-slate-200">
                                        {bundleNotesPreview(bundle)}
                                    </p>
                                {/if}
                            </div>
                            <div class="flex shrink-0 flex-col gap-2 sm:flex-row sm:flex-wrap">
                                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => downloadBundle(bundle)}>
                                    Download
                                </button>
                                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => jobDiagnosticsStore.removeBundle(bundle.id)}>
                                    Delete
                                </button>
                            </div>
                        </div>
                    </article>
                {/each}
            </div>
        {/if}
    </section>
</div>

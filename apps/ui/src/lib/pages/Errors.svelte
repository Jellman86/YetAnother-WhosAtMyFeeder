<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { incidentWorkspaceStore } from '../stores/incident_workspace.svelte';
    import {
        jobDiagnosticsStore,
        type DiagnosticsExportOptions,
        type JobDiagnosticBundle
    } from '../stores/job_diagnostics.svelte';
    import { formatDateTime } from '../utils/datetime';
    import { getVideoClassifierCardState } from '../errors/health';

    let currentIssues = $derived(incidentWorkspaceStore.currentIssues);
    let recentIncidents = $derived(incidentWorkspaceStore.recentIncidents);
    let workspacePayload = $derived(incidentWorkspaceStore.workspacePayload);
    let healthSnapshots = $derived(jobDiagnosticsStore.healthSnapshots);
    let bundles = $derived(jobDiagnosticsStore.bundles);
    let health = $derived((workspacePayload?.health as Record<string, any> | null) ?? null);
    let videoClassifierCard = $derived(getVideoClassifierCardState(health));
    let backendEvents = $derived(workspacePayload?.backend_diagnostics?.events ?? []);
    let startupWarnings = $derived(workspacePayload?.startup_warnings ?? []);
    let captureLabel = $state('');
    let reportNotes = $state('');
    let refreshing = $state(false);
    let clearing = $state(false);
    let refreshError = $state('');
    let lastRefreshedAt = $state<number | null>(null);

    let workspaceCapturedAt = $derived.by(() => {
        const raw = workspacePayload?.backend_diagnostics?.captured_at;
        if (typeof raw !== 'string' || raw.length === 0) return null;
        const parsed = Date.parse(raw);
        return Number.isFinite(parsed) ? parsed : null;
    });

    onMount(() => {
        void refreshWorkspace();
    });

    async function refreshWorkspace() {
        refreshing = true;
        refreshError = '';
        try {
            await incidentWorkspaceStore.refresh();
            lastRefreshedAt = Date.now();
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

    function buildExportOptions(): DiagnosticsExportOptions {
        return {
            workspacePayload: workspacePayload ?? undefined,
            currentIssues,
            recentIncidents,
            reportNotes: reportNotes.trim() || undefined,
        };
    }

    function captureBundle() {
        const label = captureLabel.trim();
        const notes = reportNotes.trim();
        const bundle = jobDiagnosticsStore.captureBundle(
            label || undefined,
            notes || undefined,
            buildExportOptions()
        );
        if (bundle) {
            captureLabel = '';
        }
    }

    function downloadCurrentJson() {
        jobDiagnosticsStore.downloadJson(undefined, buildExportOptions());
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

    function asNumber(value: unknown): number {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function asText(value: unknown, fallback = 'Unknown'): string {
        if (typeof value !== 'string') return fallback;
        const trimmed = value.trim();
        return trimmed.length > 0 ? trimmed : fallback;
    }

    function toneClass(value: string): string {
        const normalized = value.trim().toLowerCase();
        if (['ok', 'healthy', 'normal', 'idle', 'clear', 'resolved'].includes(normalized)) {
            return 'border-teal-200/80 bg-teal-50 text-teal-700 dark:border-teal-800/60 dark:bg-teal-900/30 dark:text-teal-300';
        }
        if (['warning', 'degraded', 'high', 'recovering', 'queued', 'processing', 'running'].includes(normalized)) {
            return 'border-amber-200/80 bg-amber-50 text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-200';
        }
        if (['critical', 'error', 'failing', 'failed', 'open'].includes(normalized)) {
            return 'border-rose-200/80 bg-rose-50 text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/30 dark:text-rose-200';
        }
        return 'border-slate-200/80 bg-slate-50 text-slate-700 dark:border-slate-700/60 dark:bg-slate-900/50 dark:text-slate-200';
    }

    function severityToneClass(severity: string): string {
        return toneClass(severity);
    }

    function overallStatusLabel(): string {
        return asText(health?.status, 'Unknown');
    }

    function overallSummary(): string {
        const status = overallStatusLabel().toLowerCase();
        if (status === 'ok' || status === 'healthy') {
            return 'All monitored services look healthy right now.';
        }
        if (status === 'degraded') {
            return 'Some subsystems are under pressure or recovering, but the app is still serving traffic.';
        }
        return 'The app is reporting active faults that need attention.';
    }

    function latestHealthLine(): string {
        if (!workspaceCapturedAt) return 'No recent workspace snapshot yet.';
        return $_('jobs.errors_latest_health', {
            values: {
                status: overallStatusLabel(),
                at: formatDateTime(workspaceCapturedAt)
            },
            default: 'Latest health: {status} at {at}'
        });
    }

    function eventPipelineStatus(): string {
        const pipeline = health?.event_pipeline ?? {};
        const criticalFailureActive = pipeline.critical_failure_active === true;
        const dropped = asNumber(pipeline.dropped_events);
        if (criticalFailureActive) return 'critical';
        if (dropped > 0) return 'degraded';
        return asText(pipeline.status, overallStatusLabel());
    }

    function eventPipelineSummary(): string {
        const pipeline = health?.event_pipeline ?? {};
        const criticalFailureActive = pipeline.critical_failure_active === true;
        const criticalFailures = asNumber(pipeline.critical_failures);
        const dropped = asNumber(pipeline.dropped_events);
        if (criticalFailureActive) return `${criticalFailures.toLocaleString()} critical failure${criticalFailures === 1 ? '' : 's'} recorded.`;
        if (criticalFailures > 0) return `${criticalFailures.toLocaleString()} historical failure${criticalFailures === 1 ? '' : 's'} recorded; pipeline has since recovered.`;
        if (dropped > 0) return `${dropped.toLocaleString()} events have been dropped.`;
        return 'The ingest pipeline is processing detections normally.';
    }

    function mqttStatus(): string {
        return asText(health?.mqtt?.pressure_level, 'unknown');
    }

    function mqttSummary(): string {
        const mqtt = health?.mqtt ?? {};
        const pressure = asText(mqtt.pressure_level, 'unknown').toLowerCase();
        const inFlight = asNumber(mqtt.in_flight);
        const capacity = asNumber(mqtt.in_flight_capacity);
        if (pressure === 'critical' || pressure === 'high') {
            return `MQTT handlers are under ${pressure} pressure at ${inFlight}/${capacity} in flight.`;
        }
        const reconnects = asNumber(mqtt.topic_liveness_reconnects);
        return reconnects > 0
            ? `MQTT recovered cleanly after ${reconnects.toLocaleString()} topic reconnects.`
            : 'MQTT traffic is flowing normally.';
    }

    function liveClassificationStatus(): string {
        const live = health?.ml?.live_image ?? {};
        return asText(live.pressure_level || live.status, 'unknown');
    }

    function liveClassificationSummary(): string {
        const live = health?.ml?.live_image ?? {};
        const queued = asNumber(live.queued);
        const running = asNumber(live.in_flight);
        const maxConcurrent = asNumber(live.max_concurrent);
        if (live.recovery_active) {
            return `Live classification is recovering while ${running}/${maxConcurrent} slots are active.`;
        }
        if (queued > 0) {
            return `${queued.toLocaleString()} live items are queued behind ${running}/${maxConcurrent} active slots.`;
        }
        return 'Live classification capacity is currently clear.';
    }

    function backgroundStatus(): string {
        const background = health?.ml?.background_image ?? {};
        if (background.background_throttled) return 'degraded';
        return asText(background.status, 'unknown');
    }

    function backgroundSummary(): string {
        const background = health?.ml?.background_image ?? {};
        if (background.background_throttled) {
            return `Background work is throttled with ${asNumber(background.queued).toLocaleString()} items waiting.`;
        }
        return `${asNumber(background.queued).toLocaleString()} queued background items, ${asNumber(background.in_flight).toLocaleString()} in flight.`;
    }

    function dispatcherStatus(): string {
        const droppedJobs = asNumber(health?.notification_dispatcher?.dropped_jobs);
        const dbWait = asNumber(health?.db_pool?.acquire_wait_max_ms);
        if (droppedJobs > 0) return 'error';
        if (dbWait >= 5000) return 'warning';
        return 'ok';
    }

    function dispatcherSummary(): string {
        const dispatcher = health?.notification_dispatcher ?? {};
        const dbPool = health?.db_pool ?? {};
        const droppedJobs = asNumber(dispatcher.dropped_jobs);
        const dbWait = asNumber(dbPool.acquire_wait_max_ms);
        if (droppedJobs > 0) {
            return `Notification dispatcher dropped ${droppedJobs.toLocaleString()} jobs.`;
        }
        if (dbWait >= 5000) {
            return `DB acquire wait reached ${dbWait.toLocaleString()}ms.`;
        }
        return 'Notification dispatch and DB pool look healthy.';
    }

    function startupStatus(): string {
        return startupWarnings.length > 0 ? 'warning' : 'ok';
    }

    function startupSummary(): string {
        if (startupWarnings.length <= 0) {
            return 'No startup warnings are currently recorded.';
        }
        const first = startupWarnings[0] ?? {};
        const phase = asText((first as Record<string, unknown>).phase, 'unknown phase');
        return `${startupWarnings.length.toLocaleString()} startup warnings recorded. Latest phase: ${phase}.`;
    }

    function refreshedAgoText(): string | null {
        if (!lastRefreshedAt) return null;
        const diff = Math.floor((Date.now() - lastRefreshedAt) / 1000);
        if (diff < 10) return 'Updated just now';
        if (diff < 60) return `Updated ${diff}s ago`;
        return `Updated ${Math.floor(diff / 60)}m ago`;
    }
</script>

<div class="space-y-6">
    <!-- ── Section header ─────────────────────────────────────────── -->
    <section class="card-base overflow-hidden">
        <div class="border-b border-slate-200/70 dark:border-slate-800/70 px-6 py-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.errors_title', { default: 'Errors' })}</h3>
                    <p class="mt-1 text-xs text-slate-500">Live system health for your bird detection setup.</p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                    {#if refreshedAgoText()}
                        <span class="text-[11px] font-semibold text-slate-400">{refreshedAgoText()}</span>
                    {/if}
                    <button
                        type="button"
                        class="btn btn-secondary px-3 py-2 text-xs"
                        onclick={clearWorkspace}
                        disabled={clearing || refreshing}
                    >
                        {clearing ? 'Clearing…' : $_('jobs.errors_clear', { default: 'Clear Live Errors' })}
                    </button>
                    <button
                        type="button"
                        class="btn btn-secondary inline-flex items-center gap-1.5 px-3 py-2 text-xs"
                        onclick={refreshWorkspace}
                        disabled={refreshing}
                    >
                        <svg
                            xmlns="http://www.w3.org/2000/svg"
                            class="h-3.5 w-3.5 {refreshing ? 'animate-spin' : ''}"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            stroke-width="2"
                        >
                            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        {refreshing ? 'Refreshing…' : 'Refresh Now'}
                    </button>
                </div>
            </div>
            {#if refreshError}
                <p class="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 dark:border-rose-800/50 dark:bg-rose-950/30 dark:text-rose-300">
                    {refreshError}
                </p>
            {/if}
        </div>

        <!-- ── System Status hero ──────────────────────────────────── -->
        <div class="px-6 py-6">
            <div class="rounded-3xl border border-slate-200/80 dark:border-slate-700/60 bg-gradient-to-br from-sky-50/80 via-white to-emerald-50/60 dark:from-slate-900/90 dark:via-slate-900/80 dark:to-slate-800/70 p-6">
                <div class="flex flex-wrap items-start justify-between gap-4">
                    <div class="min-w-0 flex-1">
                        <div class="flex flex-wrap items-center gap-2">
                            <span class={`inline-flex rounded-full border px-3 py-1 text-xs font-black uppercase tracking-[0.2em] ${toneClass(overallStatusLabel())}`}>
                                {overallStatusLabel()}
                            </span>
                            <span class="inline-flex rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-black uppercase tracking-[0.2em] text-slate-500 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
                                {currentIssues.length.toLocaleString()} current
                            </span>
                            <span class="inline-flex rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-black uppercase tracking-[0.2em] text-slate-500 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
                                {backendEvents.length.toLocaleString()} backend events
                            </span>
                        </div>
                        <h4 class="mt-4 text-2xl font-black tracking-tight text-slate-900 dark:text-white">System Status</h4>
                        <p class="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-200">
                            {overallSummary()}
                        </p>
                        <p class="mt-3 text-xs font-semibold text-slate-500 dark:text-slate-300">{latestHealthLine()}</p>
                    </div>
                    <div class="grid min-w-[220px] grid-cols-2 gap-3 text-right">
                        <div class="rounded-2xl border border-white/70 bg-white/70 p-3 dark:border-slate-800 dark:bg-slate-950/40">
                            <p class="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Health Snapshots</p>
                            <p class="mt-2 text-2xl font-black text-slate-900 dark:text-white">{healthSnapshots.length.toLocaleString()}</p>
                            <p class="mt-1 text-[10px] text-slate-400">this session</p>
                        </div>
                        <div class="rounded-2xl border border-white/70 bg-white/70 p-3 dark:border-slate-800 dark:bg-slate-950/40">
                            <p class="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Saved Bundles</p>
                            <p class="mt-2 text-2xl font-black text-slate-900 dark:text-white">{bundles.length.toLocaleString()}</p>
                            <p class="mt-1 text-[10px] text-slate-400">stored locally</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ── Subsystem cards ─────────────────────────────────── -->
            <div class="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">

                <!-- Event Pipeline -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(eventPipelineStatus())}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.pipeline_title', { default: 'Event Pipeline' })}</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{eventPipelineStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{eventPipelineSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Started</span><span>{asNumber(health?.event_pipeline?.started_events).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Completed</span><span>{asNumber(health?.event_pipeline?.completed_events).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Dropped</span><span>{asNumber(health?.event_pipeline?.dropped_events).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Critical</span><span>{asNumber(health?.event_pipeline?.critical_failures).toLocaleString()}</span></div>
                            </div>
                        </div>
                    </div>
                </article>

                <!-- MQTT -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(mqttStatus())}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">MQTT</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{mqttStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{mqttSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">In Flight</span><span>{asNumber(health?.mqtt?.in_flight).toLocaleString()} / {asNumber(health?.mqtt?.in_flight_capacity).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Reconnects</span><span>{asNumber(health?.mqtt?.topic_liveness_reconnects).toLocaleString()}</span></div>
                                <div class="col-span-2"><span class="block text-xs uppercase tracking-wider opacity-80">Last Reconnect Reason</span><span>{asText(health?.mqtt?.last_reconnect_reason, 'None')}</span></div>
                            </div>
                        </div>
                    </div>
                </article>

                <!-- Live Classification -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(liveClassificationStatus())}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">Live Classification</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{liveClassificationStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{liveClassificationSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Queued</span><span>{asNumber(health?.ml?.live_image?.queued).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">In Flight</span><span>{asNumber(health?.ml?.live_image?.in_flight).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Capacity</span><span>{asNumber(health?.ml?.live_image?.max_concurrent).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Abandoned</span><span>{asNumber(health?.ml?.live_image?.abandoned).toLocaleString()}</span></div>
                            </div>
                        </div>
                    </div>
                </article>

                <!-- Video Classification -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(videoClassifierCard.status)}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">Video Classification</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{videoClassifierCard.status}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{videoClassifierCard.summary}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Pending</span><span>{videoClassifierCard.pending.toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Active</span><span>{videoClassifierCard.active.toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Failures</span><span>{videoClassifierCard.failureCount.toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Open Until</span><span>{videoClassifierCard.openUntil}</span></div>
                            </div>
                        </div>
                    </div>
                </article>

                <!-- Background Maintenance -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(backgroundStatus())}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">Background Maintenance</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{backgroundStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{backgroundSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Queued</span><span>{asNumber(health?.ml?.background_image?.queued).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">In Flight</span><span>{asNumber(health?.ml?.background_image?.in_flight).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Abandoned</span><span>{asNumber(health?.ml?.background_image?.abandoned).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Throttled</span><span>{health?.ml?.background_image?.background_throttled ? 'Yes' : 'No'}</span></div>
                            </div>
                        </div>
                    </div>
                </article>

                <!-- Notifications & DB -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(dispatcherStatus())}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">Notifications & DB</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{dispatcherStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{dispatcherSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Dropped Jobs</span><span>{asNumber(health?.notification_dispatcher?.dropped_jobs).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">Queue Size</span><span>{asNumber(health?.notification_dispatcher?.queue_size).toLocaleString()} / {asNumber(health?.notification_dispatcher?.queue_max).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">DB Wait Max</span><span>{asNumber(health?.db_pool?.acquire_wait_max_ms).toLocaleString()}ms</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">DB Timeouts</span><span>{asNumber(health?.db_pool?.acquire_timeouts).toLocaleString()}</span></div>
                            </div>
                        </div>
                    </div>
                </article>

                <!-- Startup Warnings -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(startupStatus())}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">Startup Warnings</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{startupStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{startupSummary()}</p>
                            <div class="mt-4 space-y-2 text-xs font-semibold">
                                {#if startupWarnings.length === 0}
                                    <p class="opacity-80">No startup warnings captured in the current workspace snapshot.</p>
                                {:else}
                                    {#each startupWarnings.slice(0, 2) as warning}
                                        <div class="rounded-2xl bg-white/70 px-3 py-2 dark:bg-slate-950/40">
                                            <p class="text-xs uppercase tracking-wider opacity-80">{asText((warning as Record<string, unknown>).phase, 'unknown phase')}</p>
                                            <p class="mt-1">{asText((warning as Record<string, unknown>).error, 'Unknown warning')}</p>
                                        </div>
                                    {/each}
                                {/if}
                            </div>
                        </div>
                    </div>
                </article>

            </div>
        </div>
    </section>

    <!-- ── Current Issues + Recent Diagnostics ────────────────────── -->
    <div class="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_1fr]">
        <section class="card-base p-6">
            <div class="mb-4 flex items-center justify-between gap-3">
                <div>
                    <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.current_issues_title', { default: 'Current Issues' })}</h3>
                    <p class="mt-1 text-xs text-slate-500">Active incidents that need attention.</p>
                </div>
                <span class="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">{currentIssues.length.toLocaleString()} open</span>
            </div>
            <div class="space-y-3">
                {#if currentIssues.length === 0}
                    <p class="text-xs text-slate-500">{$_('jobs.current_issues_empty', { default: 'No current incidents detected.' })}</p>
                {:else}
                    {#each currentIssues as incident (incident.id)}
                        <article class="rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 dark:border-slate-700/60 dark:bg-slate-950/40">
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <span class={`inline-flex rounded-full border px-2.5 py-1 text-xs font-black uppercase tracking-[0.2em] ${severityToneClass(incident.severity)}`}>
                                    {incident.status}
                                </span>
                                <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{formatDateTime(incident.lastSeenAt)}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{incident.title}</p>
                            <p class="mt-1 text-xs text-slate-500 dark:text-slate-300">{incident.summary}</p>
                        </article>
                    {/each}
                {/if}

                {#if recentIncidents.length > 0}
                    <div class="pt-3">
                        <h4 class="text-[11px] font-black uppercase tracking-wider text-slate-400">{$_('jobs.recent_incidents_title', { default: 'Recent Incidents' })}</h4>
                        <div class="mt-3 space-y-2">
                            {#each recentIncidents.slice(0, 4) as incident (incident.id)}
                                <article class="rounded-2xl border border-slate-200/70 bg-slate-50/70 px-4 py-3 dark:border-slate-700/50 dark:bg-slate-900/40">
                                    <div class="flex items-center justify-between gap-2">
                                        <span class={`inline-flex rounded-full border px-2 py-0.5 text-xs font-black uppercase tracking-[0.2em] ${severityToneClass(incident.severity)}`}>
                                            {incident.status}
                                        </span>
                                        <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{formatDateTime(incident.lastSeenAt)}</span>
                                    </div>
                                    <p class="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{incident.title}</p>
                                </article>
                            {/each}
                        </div>
                    </div>
                {/if}
            </div>
        </section>

        <section class="card-base p-6">
            <div class="mb-4 flex items-center justify-between gap-3">
                <div>
                    <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">Recent Backend Diagnostics</h3>
                    <p class="mt-1 text-xs text-slate-500">Newest warnings and errors from the backend workspace snapshot.</p>
                </div>
                <span class="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">{backendEvents.length.toLocaleString()} events</span>
            </div>
            {#if backendEvents.length === 0}
                <p class="text-xs text-slate-500">{$_('jobs.errors_empty', { default: 'No grouped errors recorded yet.' })}</p>
            {:else}
                <div class="space-y-3">
                    {#each backendEvents.slice(0, 8) as event (event.id)}
                        <article class={`rounded-2xl border px-4 py-3 ${severityToneClass(event.severity ?? 'warning')}`}>
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <div class="flex flex-wrap items-center gap-2">
                                    <span class="inline-flex rounded-full border border-current/20 px-2 py-0.5 text-xs font-black uppercase tracking-[0.2em]">
                                        {event.severity}
                                    </span>
                                    <span class="text-xs font-black uppercase tracking-[0.2em] opacity-80">
                                        {event.component} · {event.reason_code}
                                    </span>
                                </div>
                                <span class="text-[10px] font-semibold uppercase tracking-wider opacity-70">{formatDateTime(Date.parse(event.timestamp))}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{event.message}</p>
                            {#if event.event_id || event.correlation_key}
                                <p class="mt-2 text-xs opacity-80">
                                    {#if event.event_id}<span>Event {event.event_id}</span>{/if}
                                    {#if event.event_id && event.correlation_key}<span> • </span>{/if}
                                    {#if event.correlation_key}<span>{event.correlation_key}</span>{/if}
                                </p>
                            {/if}
                        </article>
                    {/each}
                </div>
            {/if}
        </section>
    </div>

    <!-- ── Diagnostics Bundles ─────────────────────────────────────── -->
    <section class="card-base p-6">
        <div class="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div>
                <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.error_bundles_title', { default: 'Diagnostics Bundles' })}</h3>
                <p class="text-xs text-slate-500">
                    Download the current diagnostics snapshot or capture labeled bundles with notes for later comparison.
                </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => jobDiagnosticsStore.clearBundles()}>
                    {$_('jobs.error_bundles_clear', { default: 'Clear Bundles' })}
                </button>
            </div>
        </div>

        <div class="grid grid-cols-1 gap-6 xl:grid-cols-[1.25fr_1fr]">
            <div class="space-y-4">
                <!-- Download current snapshot -->
                <div class="rounded-3xl border border-slate-200/80 bg-slate-50/80 p-5 dark:border-slate-700/60 dark:bg-slate-900/40">
                    <h4 class="text-sm font-semibold text-slate-900 dark:text-white">Download Current Snapshot</h4>
                    <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">
                        Includes workspace health, backend diagnostics, classifier status, startup warnings, incidents, and client context.
                    </p>
                    <textarea
                        class="mt-4 min-h-24 w-full rounded-3xl border border-slate-200/80 bg-white/85 px-4 py-3 text-xs font-semibold text-slate-800 shadow-inner outline-none transition focus:border-teal-400 focus:ring-4 focus:ring-teal-500/15 dark:border-slate-700/70 dark:bg-slate-950/50 dark:text-slate-100 dark:placeholder:text-slate-500"
                        bind:value={reportNotes}
                        placeholder="Optional notes to include when you capture a saved bundle"
                    ></textarea>
                    <div class="mt-3 flex flex-wrap items-center gap-2">
                        <button type="button" class="btn btn-primary px-4 py-2 text-xs" onclick={downloadCurrentJson}>
                            {$_('jobs.errors_export', { default: 'Export Current JSON' })}
                        </button>
                        <div class="flex flex-1 items-center gap-2">
                            <input
                                class="h-10 flex-1 rounded-2xl border border-slate-200/80 bg-white/85 px-3 text-xs font-semibold text-slate-800 shadow-inner outline-none transition focus:border-teal-400 focus:ring-4 focus:ring-teal-500/15 dark:border-slate-700/70 dark:bg-slate-950/50 dark:text-slate-100 dark:placeholder:text-slate-500"
                                bind:value={captureLabel}
                                placeholder={$_('jobs.error_bundles_label_placeholder', { default: 'Optional bundle label' })}
                            />
                            <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={captureBundle}>
                                {$_('jobs.error_bundles_capture', { default: 'Capture Bundle' })}
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Saved bundles list -->
            <div>
                <div class="flex items-center justify-between gap-3">
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
                    <div class="mt-4 space-y-3">
                        {#each bundles as bundle, index (bundle.id)}
                            <article class={`rounded-3xl border p-4 shadow-sm ${index === 0 ? 'border-emerald-200/80 bg-white dark:border-emerald-800/60 dark:bg-slate-900/60' : 'border-slate-200/80 bg-white/85 dark:border-slate-700/60 dark:bg-slate-950/40'}`}>
                                <div class="flex items-start justify-between gap-3">
                                    <div class="min-w-0 flex-1">
                                        <div class="flex flex-wrap items-center gap-2">
                                            {#if index === 0}
                                                <span class="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
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
            </div>
        </div>
    </section>
</div>

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
    import {
        eventPipelineVerdict,
        expectedDropCount,
        expectedDropReasons,
        faultDiagnostics,
        faultDropCount,
        hasExpectedDrops,
        recentFilteredDetections
    } from '../utils/pipeline-health';
    import { getFrigateMediaAdvisory, getVideoClassifierCardState } from '../errors/health';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { groupDetectionsIntoVisits, withinDeskWindow } from '../utils/visit-grouping';
    import { buildHealthTimeline, hiddenEventCount, instanceWindowMs } from '../utils/health-timeline';
    import FieldLog from '../components/FieldLog.svelte';

    const FRIGATE_MISSING_DOCS_URL =
        'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/docs/troubleshooting/frigate-event-not-found.md';

    interface MetricGroup extends Record<string, unknown> {
        status?: unknown;
        pressure_level?: unknown;
        started_events?: unknown;
        completed_events?: unknown;
        dropped_events?: unknown;
        critical_failures?: unknown;
        critical_failure_active?: unknown;
        in_flight?: unknown;
        in_flight_capacity?: unknown;
        topic_liveness_reconnects?: unknown;
        last_reconnect_reason?: unknown;
        queued?: unknown;
        max_concurrent?: unknown;
        abandoned?: unknown;
        background_throttled?: unknown;
        dropped_jobs?: unknown;
        queue_size?: unknown;
        queue_max?: unknown;
        acquire_wait_max_ms?: unknown;
        acquire_timeouts?: unknown;
    }

    interface ModelHealth {
        loaded?: boolean;
        error?: string | null;
        /** Whether the label file still matches the checksum it was published with. */
        labels?: { verdict?: string; label_count?: number };
    }

    interface CatalogSource {
        id?: string | null;
        version?: string | null;
        licence?: string | null;
        citation?: string | null;
        url?: string | null;
    }

    interface CatalogArtifactHealth {
        registry_id?: string;
        output_width?: number;
        mapped_outputs?: number;
        unresolved_outputs?: number;
        complete?: boolean;
    }

    interface NamingHealth {
        species_reference?: { available?: boolean; taxon_count?: number; source?: string | null };
        localized_names?: { available?: boolean; locales?: Record<string, number> };
        species_catalog?: {
            available?: boolean;
            species_count?: number;
            artifacts?: CatalogArtifactHealth[];
            active_release?: {
                generated_at?: string | null;
                sources?: CatalogSource[];
            } | null;
        };
    }

    interface DiagnosticsHealth extends Record<string, unknown> {
        event_pipeline?: MetricGroup;
        mqtt?: MetricGroup;
        ml?: {
            live_image?: MetricGroup;
            background_image?: MetricGroup;
            models?: Record<string, ModelHealth>;
        };
        naming?: NamingHealth;
        notification_dispatcher?: MetricGroup;
        db_pool?: MetricGroup;
    }

    let currentIssues = $derived(incidentWorkspaceStore.currentIssues);
    let recentIncidents = $derived(incidentWorkspaceStore.recentIncidents);
    let workspacePayload = $derived(incidentWorkspaceStore.workspacePayload);
    let healthSnapshots = $derived(jobDiagnosticsStore.healthSnapshots);
    let bundles = $derived(jobDiagnosticsStore.bundles);
    let health = $derived(
        workspacePayload?.health && typeof workspacePayload.health === 'object'
            ? workspacePayload.health as DiagnosticsHealth
            : null
    );
    let videoClassifierCard = $derived(getVideoClassifierCardState(health));
    let frigateMediaAdvisory = $derived(getFrigateMediaAdvisory(health));
    let frigateMediaDropPercent = $derived(Math.round(frigateMediaAdvisory.rate * 100));
    let backendEvents = $derived(faultDiagnostics(workspacePayload?.backend_diagnostics?.events ?? []));
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

    // The health counters are measured from startup, so the visits shown beside them
    // use the same window rather than a rolling day (layout-patterns 1.1).
    const instanceWindow = $derived(instanceWindowMs(health?.startup_started_at as string | undefined));
    const reviewThreshold = $derived(settingsStore.settings?.classification_threshold ?? null);
    const windowedDetections = $derived(
        instanceWindow === null ? [] : withinDeskWindow(detectionsStore.detections, Date.now(), instanceWindow)
    );
    const keptVisits = $derived(groupDetectionsIntoVisits(windowedDetections, { reviewThreshold }));
    const timelineRows = $derived(
        buildHealthTimeline({
            visits: keptVisits,
            filtered: recentFilteredDetections(health?.event_pipeline, 12)
        })
    );
    const timelineHidden = $derived(
        hiddenEventCount(asNumber(health?.event_pipeline?.started_events), timelineRows.length)
    );

    onMount(() => {
        void detectionsStore.loadInitial();
        void refreshWorkspace();
    });

    $effect(() => {
        return pageRefreshAction.register(refreshWorkspace);
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

    /**
     * The hero carries the verdict, so the whole card takes the colour rather than
     * a pill on a neutral ground. Green is healthy, amber is work waiting, rose is
     * a failure, slate is a state we have not measured (layout-patterns 1.3, 1.5).
     */
    function heroToneClass(value: string): string {
        const normalized = value.trim().toLowerCase();
        if (['ok', 'healthy', 'normal'].includes(normalized)) {
            return 'border-emerald-200/80 bg-gradient-to-br from-emerald-50 via-white to-emerald-50/40 dark:border-emerald-800/50 dark:from-emerald-950/40 dark:via-slate-900/80 dark:to-emerald-950/20';
        }
        if (['degraded', 'warning', 'recovering', 'high'].includes(normalized)) {
            // Literal amber, not the accent token: accent is emerald in the classic
            // theme, which would paint a degraded instance green.
            return 'border-amber-200/80 bg-gradient-to-br from-amber-50 via-white to-amber-50/40 dark:border-amber-800/50 dark:from-amber-950/40 dark:via-slate-900/80 dark:to-amber-950/20';
        }
        if (['critical', 'error', 'failing', 'failed'].includes(normalized)) {
            return 'border-rose-200/80 bg-gradient-to-br from-rose-50 via-white to-rose-50/40 dark:border-rose-800/50 dark:from-rose-950/40 dark:via-slate-900/80 dark:to-rose-950/20';
        }
        return 'border-slate-200/80 bg-gradient-to-br from-slate-50 via-white to-slate-50/40 dark:border-slate-700/60 dark:from-slate-900/90 dark:via-slate-900/80 dark:to-slate-800/70';
    }

    function toneClass(value: string): string {
        const normalized = value.trim().toLowerCase();
        if (['ok', 'healthy', 'normal', 'idle', 'clear', 'resolved'].includes(normalized)) {
            return 'border-brand-200/80 bg-brand-50 text-brand-700 dark:border-brand-800/60 dark:bg-brand-900/30 dark:text-brand-300';
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
            return $_('jobs.errors_summary_healthy', { default: 'All monitored services look healthy right now.' });
        }
        if (status === 'degraded') {
            return $_('jobs.errors_summary_degraded', { default: 'Some subsystems are under pressure or recovering, but the app is still serving traffic.' });
        }
        return $_('jobs.errors_summary_faults', { default: 'The app is reporting active faults that need attention.' });
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
        return eventPipelineVerdict(health?.event_pipeline, overallStatusLabel());
    }

    function eventPipelineSummary(): string {
        const pipeline = health?.event_pipeline ?? {};
        const criticalFailureActive = pipeline.critical_failure_active === true;
        const criticalFailures = asNumber(pipeline.critical_failures);
        const faults = faultDropCount(pipeline);
        if (criticalFailureActive) return $_('jobs.errors_pipeline_critical', { values: { count: criticalFailures.toLocaleString() }, default: `${criticalFailures.toLocaleString()} critical failures recorded.` });
        if (criticalFailures > 0) return $_('jobs.errors_pipeline_historical', { values: { count: criticalFailures.toLocaleString() }, default: `${criticalFailures.toLocaleString()} historical failures recorded; pipeline has since recovered.` });
        if (faults > 0) return $_('jobs.errors_pipeline_dropped', { values: { count: faults.toLocaleString() }, default: `${faults.toLocaleString()} events were dropped by a fault.` });
        return $_('jobs.errors_pipeline_ok', { default: 'The ingest pipeline is processing detections normally.' });
    }

    // Filtering is reported on its own, away from the health verdict: it is useful
    // to see how much the confidence threshold is rejecting, but it is not a fault.
    function filteredStatus(): string {
        return hasExpectedDrops(health?.event_pipeline) ? 'info' : 'clear';
    }

    function filteredSummary(): string {
        const count = expectedDropCount(health?.event_pipeline);
        if (count === 0) {
            return $_('jobs.errors_filtered_none', { default: 'Nothing has been filtered out yet.' });
        }
        return $_('jobs.errors_filtered_summary', {
            values: { count: count.toLocaleString() },
            default: `${count.toLocaleString()} detections did not meet your detection settings. This is the filter working, not a fault.`
        });
    }

    function filteredReasonLabel(reason: string): string {
        return $_(`jobs.errors_drop_reason.${reason}`, { default: reason });
    }

    function filteredScoreLabel(score: number | null): string {
        if (score === null) return '';
        return `${Math.round(score * 100)}%`;
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
            return $_('jobs.errors_mqtt_pressure', { values: { pressure, inFlight: inFlight.toLocaleString(), capacity: capacity.toLocaleString() }, default: `MQTT handlers are under ${pressure} pressure at ${inFlight}/${capacity} in flight.` });
        }
        const reconnects = asNumber(mqtt.topic_liveness_reconnects);
        return reconnects > 0
            ? $_('jobs.errors_mqtt_reconnected', { values: { count: reconnects.toLocaleString() }, default: `MQTT recovered cleanly after ${reconnects.toLocaleString()} topic reconnects.` })
            : $_('jobs.errors_mqtt_ok', { default: 'MQTT traffic is flowing normally.' });
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
            return $_('jobs.errors_live_class_recovering', { values: { running: running.toLocaleString(), maxConcurrent: maxConcurrent.toLocaleString() }, default: `Live classification is recovering while ${running}/${maxConcurrent} slots are active.` });
        }
        if (queued > 0) {
            return $_('jobs.errors_live_class_queued', { values: { queued: queued.toLocaleString(), running: running.toLocaleString(), maxConcurrent: maxConcurrent.toLocaleString() }, default: `${queued.toLocaleString()} live items are queued behind ${running}/${maxConcurrent} active slots.` });
        }
        return $_('jobs.errors_live_class_ok', { default: 'Live classification capacity is currently clear.' });
    }

    function backgroundStatus(): string {
        const background = health?.ml?.background_image ?? {};
        if (background.background_throttled) return 'degraded';
        return asText(background.status, 'unknown');
    }

    function backgroundSummary(): string {
        const background = health?.ml?.background_image ?? {};
        if (background.background_throttled) {
            return $_('jobs.errors_background_throttled', { values: { queued: asNumber(background.queued).toLocaleString() }, default: `Background work is throttled with ${asNumber(background.queued).toLocaleString()} items waiting.` });
        }
        return $_('jobs.errors_background_summary', { values: { queued: asNumber(background.queued).toLocaleString(), inFlight: asNumber(background.in_flight).toLocaleString() }, default: `${asNumber(background.queued).toLocaleString()} queued background items, ${asNumber(background.in_flight).toLocaleString()} in flight.` });
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
            return $_('jobs.errors_dispatcher_dropped', { values: { count: droppedJobs.toLocaleString() }, default: `Notification dispatcher dropped ${droppedJobs.toLocaleString()} jobs.` });
        }
        if (dbWait >= 5000) {
            return $_('jobs.errors_dispatcher_db_wait', { values: { ms: dbWait.toLocaleString() }, default: `DB acquire wait reached ${dbWait.toLocaleString()}ms.` });
        }
        return $_('jobs.errors_dispatcher_ok', { default: 'Notification dispatch and DB pool look healthy.' });
    }

    function startupStatus(): string {
        return startupWarnings.length > 0 ? 'warning' : 'ok';
    }

    function startupSummary(): string {
        if (startupWarnings.length <= 0) {
            return $_('jobs.errors_startup_ok', { default: 'No startup warnings are currently recorded.' });
        }
        const first = startupWarnings[0] ?? {};
        const phase = asText((first as Record<string, unknown>).phase, 'unknown phase');
        return $_('jobs.errors_startup_summary', { values: { count: startupWarnings.length.toLocaleString(), phase }, default: `${startupWarnings.length.toLocaleString()} startup warnings recorded. Latest phase: ${phase}.` });
    }

    function namingStatus(): string {
        const models = health?.ml?.models ?? {};
        const verdicts = Object.values(models).map(model => model?.labels?.verdict);
        // A label file that no longer matches what was published names every
        // detection from it wrongly, so it outranks anything else here.
        if (verdicts.includes('changed')) return 'critical';
        if (verdicts.includes('missing')) return 'degraded';
        return health?.naming?.species_reference?.available ? 'ok' : 'unknown';
    }

    function namingSummary(): string {
        const models = health?.ml?.models ?? {};
        const changed = Object.entries(models)
            .filter(([, model]) => model?.labels?.verdict === 'changed')
            .map(([name]) => name);
        if (changed.length > 0) {
            return $_('jobs.errors_naming_labels_changed', {
                values: { models: changed.join(', ') },
                default: 'The label file for {models} does not match the checksum it was published with. Species names taken from it are not trustworthy.'
            });
        }
        const taxa = asNumber(health?.naming?.species_reference?.taxon_count);
        if (!health?.naming?.species_reference?.available) {
            return $_('jobs.errors_naming_no_reference', {
                default: 'No bundled species reference, so names come from the network only.'
            });
        }
        return $_('jobs.errors_naming_ok', {
            values: { count: taxa.toLocaleString() },
            default: '{count} species can be named without the network.'
        });
    }

    function namingLocales(): string {
        const locales = health?.naming?.localized_names?.locales ?? {};
        const names = Object.keys(locales);
        if (names.length === 0) {
            return $_('jobs.errors_naming_no_locales', { default: 'English only' });
        }
        return names.sort().join(', ');
    }

    function catalogSpecies(): string {
        const catalog = health?.naming?.species_catalog;
        if (!catalog?.available) {
            return $_('common.unknown', { default: 'unknown' });
        }
        return asNumber(catalog.species_count).toLocaleString();
    }

    // The catalogue redistributes work under CC BY terms. Attribution the
    // owner is never shown is not attribution, so the citation is rendered as
    // the source gave it rather than summarised.
    //
    // Rendered without an each-key on purpose: the list is short, static for a
    // given release, and never reordered, while a duplicate key throws. A
    // manifest that listed one source twice would take down the page whose
    // whole job is to work when something is wrong.
    function catalogSources(): Array<{ heading: string; citation: string }> {
        const sources = health?.naming?.species_catalog?.active_release?.sources ?? [];
        return sources
            .filter((source) => Boolean(source?.id))
            .map((source) => {
                const version = String(source.version ?? '').trim();
                const licence = String(source.licence ?? '').trim();
                const heading = [String(source.id).trim(), version].filter(Boolean).join(' ');
                return {
                    heading: licence ? `${heading} (${licence})` : heading,
                    citation: String(source.citation ?? '').trim()
                };
            });
    }

    function catalogSummary(): string | null {
        const catalog = health?.naming?.species_catalog;
        if (!catalog?.available) {
            return $_('jobs.errors_naming_catalog_missing', {
                default: 'No species catalogue yet. Names come from the bundled reference and model label files.'
            });
        }
        if (asNumber(catalog.species_count) === 0) {
            return $_('jobs.errors_naming_catalog_empty', {
                default: 'The species catalogue is empty. Names come from the bundled reference and model label files.'
            });
        }
        const artifacts = catalog.artifacts ?? [];
        const unresolved = artifacts.reduce((total, artifact) => total + asNumber(artifact?.unresolved_outputs), 0);
        if (unresolved > 0) {
            return $_('jobs.errors_naming_catalog_gaps', {
                values: { unresolved: unresolved.toLocaleString() },
                default: '{unresolved} model output classes have no catalogue identity yet and keep their original label text.'
            });
        }
        if (artifacts.length > 0) {
            return $_('jobs.errors_naming_catalog_ok', {
                default: 'Every mapped model output resolves to a catalogue identity.'
            });
        }
        return null;
    }

    function startedAgoText(): string {
        if (instanceWindow === null) return $_('common.unknown', { default: 'unknown' });
        const minutes = Math.floor(instanceWindow / 60000);
        if (minutes < 60) return $_('about.instance.uptime_minutes', { values: { count: minutes }, default: '{count} min' });
        const hours = Math.floor(minutes / 60);
        return $_('about.instance.uptime_hours', { values: { count: hours }, default: '{count} h' });
    }

    function goToDetection(eventId: string): void {
        if (!eventId) return;
        window.location.hash = `#/events?event=${encodeURIComponent(eventId)}`;
    }

    function refreshedAgoText(): string | null {
        if (!lastRefreshedAt) return null;
        const diff = Math.floor((Date.now() - lastRefreshedAt) / 1000);
        if (diff < 10) return $_('jobs.errors_updated_just_now', { default: 'Updated just now' });
        if (diff < 60) return $_('jobs.errors_updated_seconds', { values: { count: diff }, default: `Updated ${diff}s ago` });
        return $_('jobs.errors_updated_minutes', { values: { count: Math.floor(diff / 60) }, default: `Updated ${Math.floor(diff / 60)}m ago` });
    }
</script>

<div class="space-y-6">
    <!-- ── Section header ─────────────────────────────────────────── -->
    <section class="card-base overflow-hidden">
        <div class="border-b border-slate-200/70 dark:border-slate-800/70 px-6 py-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.errors_title', { default: 'Errors' })}</h3>
                    <p class="mt-1 text-xs text-slate-500">{$_('jobs.errors_health_subtitle', { default: 'Live system health for your bird detection setup.' })}</p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                    {#if refreshedAgoText()}
                        <span class="text-xs font-semibold text-slate-400">{refreshedAgoText()}</span>
                    {/if}
                    <button
                        type="button"
                        class="btn btn-secondary px-3 py-2 text-xs"
                        onclick={clearWorkspace}
                        disabled={clearing || refreshing}
                    >
                        {clearing ? $_('jobs.errors_clearing', { default: 'Clearing…' }) : $_('jobs.errors_clear', { default: 'Clear Live Errors' })}
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
            <div class="rounded-3xl border p-6 {heroToneClass(overallStatusLabel())}">
                <div class="flex flex-wrap items-start justify-between gap-4">
                    <div class="min-w-0 flex-1">
                        <div class="flex flex-wrap items-center gap-2">
                            <span class={`inline-flex rounded-full border px-3 py-1 text-xs font-black uppercase tracking-[0.2em] ${toneClass(overallStatusLabel())}`}>
                                {overallStatusLabel()}
                            </span>
                        </div>
                        <h4 class="mt-4 text-2xl font-black tracking-tight text-slate-900 dark:text-white">{$_('jobs.errors_system_status', { default: 'System Status' })}</h4>
                        <p class="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-200">
                            {overallSummary()}
                        </p>
                        <p class="mt-3 text-xs font-semibold text-slate-500 dark:text-slate-300">{latestHealthLine()}</p>
                    </div>
                </div>
            </div>

            {#if frigateMediaAdvisory.elevated}
                <!-- ── Frigate media-unavailability advisory (Event Not Found guidance) ── -->
                <div class="mt-6 rounded-2xl border border-amber-300/70 bg-amber-50/80 p-4 text-amber-900 dark:border-amber-500/40 dark:bg-amber-950/30 dark:text-amber-200">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.frigate_media_advisory_title', { default: 'Frigate often has no snapshot for a detection' })}</h4>
                            <p class="mt-1 text-sm font-semibold">{$_('jobs.frigate_media_advisory_body', { values: { percent: frigateMediaDropPercent, dropped: frigateMediaAdvisory.dropped.toLocaleString(), started: frigateMediaAdvisory.started.toLocaleString() }, default: `${frigateMediaDropPercent}% of recent detections (${frigateMediaAdvisory.dropped.toLocaleString()} of ${frigateMediaAdvisory.started.toLocaleString()}) were dropped because Frigate had no snapshot, thumbnail, or recording for them. This usually means briefly-tracked birds that never persist as Frigate events, or short recording retention.` })}</p>
                            <a href={FRIGATE_MISSING_DOCS_URL} target="_blank" rel="noopener noreferrer" class="mt-2 inline-block text-xs font-black uppercase tracking-widest underline underline-offset-2 hover:opacity-80">
                                {$_('jobs.frigate_media_advisory_link', { default: 'How to reduce this →' })}
                            </a>
                        </div>
                    </div>
                </div>
            {/if}

            <!-- ── What happened: one thread of kept visits and filtered frames ── -->
            <section class="mt-8 border-t border-slate-200/70 pt-6 dark:border-slate-700/50" data-health-timeline>
                <header class="flex flex-wrap items-end justify-between gap-3 pb-1">
                    <div class="min-w-0">
                        <h3 class="font-display text-xl font-bold text-slate-950 dark:text-white">
                            {$_('jobs.errors_activity_title', { default: 'What happened' })}
                        </h3>
                        <p class="text-sm text-slate-500 dark:text-slate-400">
                            {$_('jobs.errors_activity_subtitle', {
                                default: 'Visits recorded and frames filtered out, in the order they happened'
                            })}
                        </p>
                    </div>
                    <span class="shrink-0 rounded-full border border-slate-200 px-2.5 py-1 text-xs font-semibold tabular-nums text-slate-500 dark:border-slate-700 dark:text-slate-400">
                        {$_('jobs.errors_activity_window', {
                            values: { started: startedAgoText() },
                            default: 'Since this instance started, {started}'
                        })}
                    </span>
                </header>

                {#if instanceWindow === null}
                    <p class="mt-4 text-sm text-slate-500 dark:text-slate-400">
                        {$_('jobs.errors_activity_no_window', {
                            default: 'This instance has not reported when it started, so activity cannot be placed in a window yet.'
                        })}
                    </p>
                {:else}
                    <div class="mt-3">
                        <FieldLog
                            rows={timelineRows}
                            showHeader={false}
                            emptyMessage={$_('jobs.errors_activity_empty', {
                                values: { started: startedAgoText() },
                                default: 'Nothing has been recorded or filtered since this instance started {started} ago.'
                            })}
                            hiddenCount={timelineHidden}
                            hiddenLabel={$_('jobs.errors_activity_earlier', {
                                values: { count: timelineHidden.toLocaleString() },
                                default: '{count} earlier events in this window'
                            })}
                            loading={detectionsStore.isLoading && timelineRows.length === 0}
                            onselect={(detection) => goToDetection(detection.frigate_event)}
                        />
                    </div>
                {/if}
            </section>

            <!-- ── Subsystem detail ────────────────────────────────── -->
            <details class="mt-8 border-t border-slate-200/70 pt-4 dark:border-slate-700/50" data-subsystem-detail>
                <summary class="group flex min-h-11 cursor-pointer items-center justify-between gap-3 py-2 text-xs font-black uppercase tracking-[0.18em] text-slate-500 focus-ring dark:text-slate-400">
                    <span>{$_('jobs.errors_subsystems_title', { default: 'Subsystem detail' })}</span>
                    <svg class="h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200 group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                </summary>
                <div class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">

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
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_started', { default: 'Started' })}</span><span>{asNumber(health?.event_pipeline?.started_events).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_completed', { default: 'Completed' })}</span><span>{asNumber(health?.event_pipeline?.completed_events).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_dropped', { default: 'Dropped' })}</span><span>{asNumber(health?.event_pipeline?.dropped_events).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_critical', { default: 'Critical' })}</span><span>{asNumber(health?.event_pipeline?.critical_failures).toLocaleString()}</span></div>
                            </div>
                        </div>
                    </div>
                </article>

                <!-- Filtered detections (expected, configuration-driven drops) -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(filteredStatus())}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L15 12.414V19a1 1 0 01-.553.894l-4 2A1 1 0 019 21v-8.586L3.293 6.707A1 1 0 013 6V4z" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.errors_filtered_title', { default: 'Filtered Detections' })}</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{expectedDropCount(health?.event_pipeline).toLocaleString()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{filteredSummary()}</p>
                            {#if expectedDropReasons(health?.event_pipeline).length > 0}
                                <dl class="mt-4 grid grid-cols-1 gap-2 text-xs font-semibold">
                                    {#each expectedDropReasons(health?.event_pipeline) as entry (entry.reason)}
                                        <div class="flex items-baseline justify-between gap-3">
                                            <dt class="min-w-0 truncate uppercase tracking-wider opacity-80">{filteredReasonLabel(entry.reason)}</dt>
                                            <dd class="shrink-0">{entry.count.toLocaleString()}</dd>
                                        </div>
                                    {/each}
                                </dl>
                                {#if recentFilteredDetections(health?.event_pipeline).length > 0}
                                    <div class="mt-4 border-t border-current/15 pt-3">
                                        <p class="text-xs font-black uppercase tracking-wider opacity-70">{$_('jobs.errors_filtered_recent', { default: 'Most recent' })}</p>
                                        <ul class="mt-2 space-y-1.5 text-xs font-semibold">
                                            {#each recentFilteredDetections(health?.event_pipeline) as entry (entry.eventId)}
                                                <li
                                                    class="flex items-baseline justify-between gap-3"
                                                    title={`${filteredReasonLabel(entry.reason)}${entry.timestamp ? ` · ${formatDateTime(Date.parse(entry.timestamp))}` : ''} · ${entry.eventId}`}
                                                >
                                                    <span class="min-w-0 truncate italic">{entry.label ?? $_('common.unknown_species', { default: 'Unknown species' })}</span>
                                                    <span class="shrink-0 tabular-nums opacity-80">{filteredScoreLabel(entry.score)}</span>
                                                </li>
                                            {/each}
                                        </ul>
                                    </div>
                                {/if}
                                <p class="mt-3 text-xs font-semibold opacity-70">{$_('jobs.errors_filtered_hint', { default: 'Adjust the confidence threshold in Settings → Detection to keep more of these.' })}</p>
                            {/if}
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
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_in_flight', { default: 'In Flight' })}</span><span>{asNumber(health?.mqtt?.in_flight).toLocaleString()} / {asNumber(health?.mqtt?.in_flight_capacity).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_reconnects', { default: 'Reconnects' })}</span><span>{asNumber(health?.mqtt?.topic_liveness_reconnects).toLocaleString()}</span></div>
                                <div class="col-span-2"><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_last_reconnect', { default: 'Last Reconnect Reason' })}</span><span>{asText(health?.mqtt?.last_reconnect_reason, 'None')}</span></div>
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
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.errors_card_live_classification', { default: 'Live Classification' })}</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{liveClassificationStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{liveClassificationSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_queued', { default: 'Queued' })}</span><span>{asNumber(health?.ml?.live_image?.queued).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_in_flight', { default: 'In Flight' })}</span><span>{asNumber(health?.ml?.live_image?.in_flight).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_capacity', { default: 'Capacity' })}</span><span>{asNumber(health?.ml?.live_image?.max_concurrent).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_abandoned', { default: 'Abandoned' })}</span><span>{asNumber(health?.ml?.live_image?.abandoned).toLocaleString()}</span></div>
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
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.errors_card_video_classification', { default: 'Video Classification' })}</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{videoClassifierCard.status}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{videoClassifierCard.summary}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_pending', { default: 'Pending' })}</span><span>{videoClassifierCard.pending.toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_active', { default: 'Active' })}</span><span>{videoClassifierCard.active.toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_failures', { default: 'Failures' })}</span><span>{videoClassifierCard.failureCount.toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_open_until', { default: 'Open Until' })}</span><span>{videoClassifierCard.openUntil}</span></div>
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
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.errors_card_background_maintenance', { default: 'Background Maintenance' })}</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{backgroundStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{backgroundSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_queued', { default: 'Queued' })}</span><span>{asNumber(health?.ml?.background_image?.queued).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_in_flight', { default: 'In Flight' })}</span><span>{asNumber(health?.ml?.background_image?.in_flight).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_abandoned', { default: 'Abandoned' })}</span><span>{asNumber(health?.ml?.background_image?.abandoned).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_throttled', { default: 'Throttled' })}</span><span>{health?.ml?.background_image?.background_throttled ? $_('common.yes', { default: 'Yes' }) : $_('common.no', { default: 'No' })}</span></div>
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
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.errors_card_notifications_db', { default: 'Notifications & DB' })}</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{dispatcherStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{dispatcherSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_dropped_jobs', { default: 'Dropped Jobs' })}</span><span>{asNumber(health?.notification_dispatcher?.dropped_jobs).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_queue_size', { default: 'Queue Size' })}</span><span>{asNumber(health?.notification_dispatcher?.queue_size).toLocaleString()} / {asNumber(health?.notification_dispatcher?.queue_max).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_db_wait_max', { default: 'DB Wait Max' })}</span><span>{asNumber(health?.db_pool?.acquire_wait_max_ms).toLocaleString()}ms</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_db_timeouts', { default: 'DB Timeouts' })}</span><span>{asNumber(health?.db_pool?.acquire_timeouts).toLocaleString()}</span></div>
                            </div>
                        </div>
                    </div>
                </article>

                <!-- Naming sources -->
                <article class="rounded-3xl border p-5 shadow-sm {toneClass(namingStatus())}">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 shrink-0 opacity-70">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M7 7h.01M7 3h5a1.99 1.99 0 011.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.99 1.99 0 013 12V7a4 4 0 014-4z" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.errors_card_naming', { default: 'Naming Sources' })}</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{namingStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{namingSummary()}</p>
                            <div class="mt-4 grid grid-cols-2 gap-3 text-xs font-semibold">
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_offline_species', { default: 'Offline Species' })}</span><span>{asNumber(health?.naming?.species_reference?.taxon_count).toLocaleString()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_languages', { default: 'Languages' })}</span><span>{namingLocales()}</span></div>
                                <div><span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_metric_catalog', { default: 'Catalogue species' })}</span><span>{catalogSpecies()}</span></div>
                            </div>
                            {#if catalogSummary()}
                                <p class="mt-3 text-xs font-semibold opacity-80">{catalogSummary()}</p>
                            {/if}
                            {#if catalogSources().length > 0}
                                <div class="mt-4 border-t border-current/20 pt-3">
                                    <span class="block text-xs uppercase tracking-wider opacity-80">{$_('jobs.errors_catalog_sources', { default: 'Catalogue sources' })}</span>
                                    <ul class="mt-2 space-y-2 text-xs">
                                        {#each catalogSources() as source}
                                            <li>
                                                <span class="font-semibold">{source.heading}</span>
                                                {#if source.citation}
                                                    <span class="mt-0.5 block opacity-70">{source.citation}</span>
                                                {/if}
                                            </li>
                                        {/each}
                                    </ul>
                                    <p class="mt-3 text-xs opacity-70">{$_('jobs.errors_catalog_rollback', { default: 'The catalogue is a separate file from your detection history. Rolling one back changes names, never your recorded sightings, and a backup of the data directory covers both.' })}</p>
                                </div>
                            {/if}
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
                                <h4 class="text-sm font-black uppercase tracking-[0.18em]">{$_('jobs.errors_card_startup_warnings', { default: 'Startup Warnings' })}</h4>
                                <span class="shrink-0 rounded-full border border-current/30 px-2 py-0.5 text-xs font-black uppercase tracking-wider">{startupStatus()}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold">{startupSummary()}</p>
                            <div class="mt-4 space-y-2 text-xs font-semibold">
                                {#if startupWarnings.length === 0}
                                    <p class="opacity-80">{$_('jobs.errors_no_startup_warnings', { default: 'No startup warnings captured in the current workspace snapshot.' })}</p>
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
            </details>
        </div>
    </section>

    <!-- ── Current Issues + Recent Diagnostics ────────────────────── -->
    <div class="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_1fr]">
        <section class="card-base p-6">
            <div class="mb-4 flex items-center justify-between gap-3">
                <div>
                    <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.current_issues_title', { default: 'Current Issues' })}</h3>
                    <p class="mt-1 text-xs text-slate-500">{$_('jobs.errors_active_incidents_desc', { default: 'Active incidents that need attention.' })}</p>
                </div>
                <span class="text-xs font-black uppercase tracking-[0.2em] text-slate-400">{currentIssues.length.toLocaleString()} open</span>
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
                                <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">{formatDateTime(incident.lastSeenAt)}</span>
                            </div>
                            <p class="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{incident.title}</p>
                            <p class="mt-1 text-xs text-slate-500 dark:text-slate-300">{incident.summary}</p>
                        </article>
                    {/each}
                {/if}

                {#if recentIncidents.length > 0}
                    <div class="pt-3">
                        <h4 class="text-xs font-black uppercase tracking-wider text-slate-400">{$_('jobs.recent_incidents_title', { default: 'Recent Incidents' })}</h4>
                        <div class="mt-3 space-y-2">
                            {#each recentIncidents.slice(0, 4) as incident (incident.id)}
                                <article class="rounded-2xl border border-slate-200/70 bg-slate-50/70 px-4 py-3 dark:border-slate-700/50 dark:bg-slate-900/40">
                                    <div class="flex items-center justify-between gap-2">
                                        <span class={`inline-flex rounded-full border px-2 py-0.5 text-xs font-black uppercase tracking-[0.2em] ${severityToneClass(incident.severity)}`}>
                                            {incident.status}
                                        </span>
                                        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">{formatDateTime(incident.lastSeenAt)}</span>
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
                    <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.errors_backend_diagnostics_title', { default: 'Recent Backend Diagnostics' })}</h3>
                    <p class="mt-1 text-xs text-slate-500">{$_('jobs.errors_backend_diagnostics_desc', { default: 'Newest warnings and errors from the backend workspace snapshot.' })}</p>
                </div>
                <span class="text-xs font-black uppercase tracking-[0.2em] text-slate-400">{backendEvents.length.toLocaleString()} events</span>
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
                                <span class="text-xs font-semibold uppercase tracking-wider opacity-70">{formatDateTime(Date.parse(event.timestamp))}</span>
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

    <!-- ── Diagnostics export ──────────────────────────────────────
         Engineer-facing plumbing: useful when reporting a problem, noise on a
         page whose job is to say whether the feeder is working. It sits behind
         the same disclosure the subsystem detail uses. -->
    <details class="card-base p-6" data-diagnostics-export>
        <summary class="group flex min-h-11 cursor-pointer flex-wrap items-center justify-between gap-3 text-xs font-black uppercase tracking-widest text-slate-500 focus-ring dark:text-slate-400">
            <span class="flex items-center gap-2">
                <svg class="h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200 group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                {$_('jobs.errors_export_title', { default: 'Diagnostics export' })}
            </span>
            <span class="font-semibold normal-case tracking-normal text-slate-400">
                {$_('jobs.errors_export_count', {
                    values: { count: bundles.length.toLocaleString() },
                    default: '{count} saved'
                })}
            </span>
        </summary>

        <p class="mt-4 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
            {$_('jobs.errors_export_desc', {
                default: 'A bundle captures workspace health, backend diagnostics, classifier status, startup warnings and incidents as one JSON file. Attach one when you report a problem.'
            })}
        </p>

        <textarea
            class="input-base mt-4 min-h-16 w-full text-sm"
            rows="2"
            bind:value={reportNotes}
            placeholder={$_('jobs.errors_export_notes_placeholder', { default: 'What went wrong? Included in the bundle.' })}
            aria-label={$_('jobs.errors_export_notes_placeholder', { default: 'What went wrong? Included in the bundle.' })}
        ></textarea>

        <div class="mt-3 flex flex-wrap items-center gap-2">
            <input
                class="input-base h-11 min-w-0 flex-1 text-sm sm:max-w-sm"
                type="text"
                bind:value={captureLabel}
                placeholder={$_('jobs.error_bundles_label_placeholder', { default: 'Optional bundle label' })}
                aria-label={$_('jobs.error_bundles_label_placeholder', { default: 'Optional bundle label' })}
            />
            <button type="button" class="btn btn-primary min-h-11 px-4 text-xs" onclick={captureBundle}>
                {$_('jobs.error_bundles_capture', { default: 'Capture Bundle' })}
            </button>
            <button type="button" class="btn btn-secondary min-h-11 px-4 text-xs" onclick={downloadCurrentJson}>
                {$_('jobs.errors_export_download_now', { default: 'Download without saving' })}
            </button>
        </div>

        {#if bundles.length === 0}
            <p class="mt-4 text-sm text-slate-500 dark:text-slate-400">
                {$_('jobs.errors_no_bundles', { default: 'No captured bundles available yet.' })}
            </p>
        {:else}
            <ul class="mt-5 divide-y divide-slate-200/70 border-t border-slate-200/70 dark:divide-slate-700/50 dark:border-slate-700/50">
                {#each bundles as bundle (bundle.id)}
                    <li class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3">
                        <div class="min-w-0 flex-1">
                            <p class="truncate text-sm font-semibold text-slate-900 dark:text-white">{bundle.label}</p>
                            <p class="mt-0.5 text-xs tabular-nums text-slate-500 dark:text-slate-400">
                                {formatDateTime(bundle.createdAt)} · {bundleSummaryText(bundle)}
                            </p>
                            {#if bundleNotesPreview(bundle)}
                                <p class="mt-1 truncate text-xs text-slate-600 dark:text-slate-300">{bundleNotesPreview(bundle)}</p>
                            {/if}
                        </div>
                        <div class="flex shrink-0 items-center gap-1">
                            <button type="button" class="btn btn-ghost min-h-11 px-3 text-xs" onclick={() => downloadBundle(bundle)}>
                                {$_('jobs.error_bundles_download', { default: 'Download' })}
                            </button>
                            <button type="button" class="btn btn-ghost min-h-11 px-3 text-xs" onclick={() => jobDiagnosticsStore.removeBundle(bundle.id)}>
                                {$_('jobs.error_bundles_delete', { default: 'Delete' })}
                            </button>
                        </div>
                    </li>
                {/each}
            </ul>
            <button type="button" class="btn btn-ghost mt-3 min-h-11 px-3 text-xs" onclick={() => jobDiagnosticsStore.clearBundles()}>
                {$_('jobs.error_bundles_clear', { default: 'Clear Bundles' })}
            </button>
        {/if}
    </details>
</div>

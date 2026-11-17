<script lang="ts">
    import { fetchVisits } from '../api/visits';
    import { chainGuarded, guardedValue, mapGuarded, type Guarded } from '../api/core';
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
        recentFaultDetections,
        recentFilteredDetections,
        keyedPipelineDetections
    } from '../utils/pipeline-health';
    import { getFrigateMediaAdvisory, getVideoClassifierCardState } from '../errors/health';
    import { STATUS_SURFACE, STATUS_TONE, statusLabelKey, statusTone } from '../utils/status-tone';
    import { connectionProblems, frigateCardStatus, healthVerdict, mqttCardStatus, pipelineCardStatus, type ConnectionProblem } from '../utils/connection-health';
    import { diagnosticWordsKey } from '../utils/diagnostic-words';
    import { connectionCauseMessage } from '../api/error-message';
    import { serviceConnectionsStore } from '../stores/service_connections.svelte';
    import { systemStatusStore } from '../stores/system_status.svelte';
    import { followRevisions } from '../app/revision-follower';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { fromServerVisit } from '../utils/visit-grouping';
    import {
        buildHealthTimeline,
        hiddenEventCount,
        instanceWindowMs,
        representedEventCount
    } from '../utils/health-timeline';
    import HealthActivityTimeline from '../components/HealthActivityTimeline.svelte';
    import SystemHealthPanel from '../components/settings/SystemHealthPanel.svelte';
    import Panel from '../components/ui/Panel.svelte';
    import StateBlock from '../components/ui/StateBlock.svelte';
    import StatusChip from '../components/ui/StatusChip.svelte';

    interface Props {
        onNavigate?: (path: string) => void;
    }

    let { onNavigate }: Props = $props();

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
    // The pushed status, the same reading the sidebar, the banner and the Dashboard show, so no two
    // of them disagree; the workspace's own reading stands in until the first status arrives.
    const pushedStatus = $derived(systemStatusStore.snapshot);
    let connections = $derived(pushedStatus?.connections ?? workspacePayload?.connections ?? null);
    let problems = $derived(connectionProblems(connections));
    // Everything open, from the one workspace reading: the failed connections, then any incident
    // not yet resolved. The verdict card lists these, so a count elsewhere can never disagree.
    let openItems = $derived([
        ...problems.map((problem) => ({ key: problem, problem, incident: null })),
        ...currentIssues.map((incident) => ({ key: `incident:${incident.id}`, problem: null, incident }))
    ]);
    let videoClassifierCard = $derived(getVideoClassifierCardState(health));
    let frigateMediaAdvisory = $derived(getFrigateMediaAdvisory(health));
    let frigateMediaDropPercent = $derived(Math.round(frigateMediaAdvisory.rate * 100));
    let backendEvents = $derived(faultDiagnostics(workspacePayload?.backend_diagnostics?.events ?? []));
    let startupWarnings = $derived(workspacePayload?.startup_warnings ?? []);
    let captureLabel = $state('');
    let reportNotes = $state('');
    let exporting = $state(false);
    let exportError = $state('');
    let refreshing = $state(false);
    let clearing = $state(false);
    let clearError = $state('');
    /**
     * Whether the verdict is a measurement. Before the first reading nothing is claimed; a failed
     * first read says so; a failed refresh keeps the last reading and says how old it is. The store
     * changes this only when a read settles, so a retry in flight never makes kept data look current
     * and a later successful read (a clear-and-refresh, or the shell's own sync) makes it fresh.
     */
    const readState = $derived(incidentWorkspaceStore.readFreshness);
    // The raw reason the latest read failed: kept for the technical details, never the page's own sentence.
    const refreshError = $derived(incidentWorkspaceStore.readSettled.error ?? '');

    let workspaceCapturedAt = $derived.by(() => {
        const raw = workspacePayload?.backend_diagnostics?.captured_at;
        if (typeof raw !== 'string' || raw.length === 0) return null;
        const parsed = Date.parse(raw);
        return Number.isFinite(parsed) ? parsed : null;
    });
    const lastReadAt = $derived(incidentWorkspaceStore.readSettled.readAt ?? workspaceCapturedAt);

    // The health counters are measured from startup, so the visits shown beside them
    // use the same window rather than a rolling day (layout-patterns 1.1).
    const instanceWindow = $derived(instanceWindowMs(health?.startup_started_at as string | undefined));
    let serverVisits = $state<ReturnType<typeof fromServerVisit>[]>([]);
    const keptVisits = $derived(serverVisits);
    const timelineRows = $derived(
        buildHealthTimeline({
            visits: keptVisits,
            filtered: recentFilteredDetections(health?.event_pipeline, 25),
            faults: recentFaultDetections(health?.event_pipeline, 25),
            limit: 25
        })
    );
    const timelineHidden = $derived(
        hiddenEventCount(
            asNumber(health?.event_pipeline?.started_events),
            representedEventCount(timelineRows)
        )
    );

    // The timeline is the server's visits and the pipeline's own records, read with the workspace;
    // Health shows no part of the recent history list, so it never reads it.
    onMount(() => {
        // The counters, verdicts and incidents move without a new fault being recorded (a recovery,
        // events counted). The pushed status names them by a revision; Health reads on opening and
        // again when it moves, and a failed read is retried with the shared backoff until it lands.
        const follower = followRevisions(refreshWorkspace, systemStatusStore.snapshot?.health_revision ?? null);
        follower.start();
        const stop = systemStatusStore.subscribe((snapshot) => follower.observe(snapshot.health_revision));
        return () => {
            stop();
            follower.stop();
        };
    });

    $effect(() => {
        return pageRefreshAction.register(async () => { await refreshWorkspace(); });
    });

    /** Bounds Health's visit read, body included, so a stalled answer never holds the follower. */
    const HEALTH_VISITS_TIMEOUT_MS = 15_000;

    /** Reads the workspace and the visits beside it; false when either read failed, so it is retried. */
    function refreshWorkspace(signal?: AbortSignal): Guarded<boolean> {
        refreshing = true;
        const read = chainGuarded(incidentWorkspaceStore.refresh(200, signal), () => {
            if (workspacePayload?.connections) serviceConnectionsStore.ingest(workspacePayload.connections);
            const started = workspacePayload?.health?.startup_started_at;
            if (typeof started !== 'string') {
                serverVisits = [];
                return guardedValue(true);
            }
            const window = { startTime: started, endTime: new Date().toISOString() };
            const visits = fetchVisits({ ...window, limit: 25, requestKey: 'health:visits', timeoutMs: HEALTH_VISITS_TIMEOUT_MS, signal });
            return mapGuarded(visits, (result) => {
                serverVisits = result.visits.map((visit) => fromServerVisit(visit, window));
                return true;
            });
        });
        return mapGuarded(
            read,
            (ok) => {
                refreshing = false;
                return ok;
            },
            (error) => {
                refreshing = false;
                const message = error instanceof Error ? error.message : 'Failed to refresh incident workspace';
                jobDiagnosticsStore.recordError({
                    source: 'runtime',
                    component: 'incident_workspace',
                    reasonCode: 'refresh_failed',
                    message,
                    severity: 'warning',
                    context: { scope: 'Errors.svelte' }
                });
                return false;
            }
        );
    }

    async function clearWorkspace() {
        clearing = true;
        clearError = '';
        try {
            await incidentWorkspaceStore.clearRemote();
            jobDiagnosticsStore.clear();
            await incidentWorkspaceStore.refresh();
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to clear incident workspace';
            clearError = message;
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

    async function exportCurrent(save: boolean) {
        if (exporting) return;
        exporting = true;
        exportError = '';
        try {
            // A page may have been open for hours. Capture the server now, rather
            // than attaching the workspace from the last page visit to a new report.
            await incidentWorkspaceStore.refresh();
            if (save) {
                const bundle = jobDiagnosticsStore.captureBundle(
                    captureLabel.trim() || undefined,
                    reportNotes.trim() || undefined,
                    buildExportOptions()
                );
                if (bundle) captureLabel = '';
            } else {
                jobDiagnosticsStore.downloadJson(undefined, buildExportOptions());
            }
        } catch (error) {
            exportError = error instanceof Error ? error.message : $_('jobs.errors_export_failed');
        } finally {
            exporting = false;
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
        return $_('jobs.error_bundles_stats', {
            values: {
                groups: bundle.summary.error_groups,
                events: bundle.summary.total_events,
                snapshots: bundle.summary.health_snapshots
            },
            default: '{groups, plural, one {# group} other {# groups}} · {events, plural, one {# event} other {# events}} · {snapshots, plural, one {# snapshot} other {# snapshots}}'
        });
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

    function asText(value: unknown, fallback: string): string {
        if (typeof value !== 'string') return fallback;
        const trimmed = value.trim();
        return trimmed.length > 0 ? trimmed : fallback;
    }

    /**
     * The hero carries the verdict, so the whole card takes the colour rather than a pill on
     * a neutral ground. The tones come from one helper: brand for work in flight, amber for a
     * state a person should look at, rose for a failure, green for healthy and slate for a
     * state we have not measured (layout-patterns 1.3, 1.5).
     */
    function heroToneClass(value: string): string {
        return STATUS_SURFACE[statusTone(value)];
    }

    /** A reported status in words, in sentence case; a word we do not know is shown as sent. */
    function statusLabel(value: string): string {
        const key = statusLabelKey(value);
        return key ? $_(key, { default: value }) : value.trim();
    }

    function overallStatus(): string {
        return pushedStatus?.overall.state ?? asText(health?.status, 'unknown');
    }

    /** The hero's verdict: never healthy while the broker or Frigate is down or unread. */
    function verdict(): string {
        if (!workspacePayload) return 'unknown';
        return withOpenIncidents(healthVerdict(overallStatus(), connections));
    }

    const GENERIC_DIAGNOSTIC_TITLE = 'A processing step failed in a way YA-WAMF does not recognise.';

    /**
     * A reason code in the reader's words, with what to try. The backend's message can carry an
     * exception's text, paths and URLs, so it is never the title: an unknown code gets the generic
     * cause, a next step that does not pretend to know the cause, and its message stays under
     * Technical details.
     */
    function diagnosticWords(reasonCode: string | null | undefined): { title: string; next: string | null } {
        const key = diagnosticWordsKey(reasonCode);
        const title = $_(`jobs.diagnostic_words.${key}.title`, { default: '' })
            || $_('jobs.diagnostic_words.generic.title', { default: GENERIC_DIAGNOSTIC_TITLE });
        const next = $_(`jobs.diagnostic_words.${key}.next`, { default: '' });
        return { title, next: next || null };
    }

    /** The raw words of an open or earlier incident, for its Technical details only. */
    function incidentDetails(incident: { title: string; summary: string; primaryReasonCode: string }): string[] {
        const title = incident.title.trim();
        const summary = incident.summary.trim();
        return [incident.primaryReasonCode, title, ...(summary && summary !== title ? [summary] : [])].filter(Boolean);
    }

    /** An open incident is never shown beside a healthy verdict. */
    function withOpenIncidents(status: string): string {
        if (currentIssues.length === 0) return status;
        const value = status.toLowerCase();
        return value === 'ok' || value === 'healthy' ? 'degraded' : status;
    }

    /** One short item per failed connection: what is wrong, then what to do. */
    function problemItem(problem: ConnectionProblem): { title: string; next: string } {
        const server = connections ? `${connections.mqtt.server}:${connections.mqtt.port}` : '';
        const url = connections?.frigate.url ?? '';
        switch (problem) {
            case 'mqtt_down':
                return {
                    title: $_('jobs.errors_problem.mqtt_down', { values: { server }, default: 'The MQTT broker at {server} is not connected, so no new visits can be recorded.' }),
                    next: $_('jobs.errors_problem.mqtt_down_next', { default: 'Check its address in Settings → Cameras & connection and that the broker is running.' })
                };
            case 'mqtt_not_configured':
                return {
                    title: $_('jobs.errors_problem.mqtt_not_configured', { default: 'No MQTT broker is set, so no visits can be recorded.' }),
                    next: $_('jobs.errors_problem.mqtt_not_configured_next', { default: 'Add one in Settings → Cameras & connection.' })
                };
            case 'mqtt_stopped':
                return {
                    title: $_('jobs.errors_problem.mqtt_stopped', { default: 'The MQTT service is not running, so no new visits can be recorded.' }),
                    next: $_('jobs.errors_problem.mqtt_stopped_next', { default: 'Restart YA-WAMF to start it again.' })
                };
            case 'frigate_down':
                return {
                    title: $_('jobs.errors_problem.frigate_down', { values: { url }, default: 'Frigate at {url} is not answering, so new visits cannot be saved.' }),
                    next: $_('jobs.errors_problem.frigate_down_next', { default: 'Check its address in Settings → Cameras & connection and that Frigate is running.' })
                };
        }
    }

    function overallSummary(): string {
        const status = overallStatus().toLowerCase();
        if ((status === 'ok' || status === 'healthy') && connections === null) {
            return $_('jobs.errors_summary_connections_unread', { default: 'Nothing inside YA-WAMF reports a fault, but the MQTT broker and Frigate connections could not be read.' });
        }
        if (status === 'ok' || status === 'healthy') {
            return $_('jobs.errors_summary_healthy', { default: 'Everything YA-WAMF checks is working.' });
        }
        if (statusTone(status) === 'unknown') {
            return $_('jobs.errors_summary_unknown', { default: 'This reading did not say whether YA-WAMF is working, so no state is claimed.' });
        }
        if (status === 'degraded') {
            return $_('jobs.errors_summary_degraded', { default: 'Some parts are busy or recovering. YA-WAMF is still working.' });
        }
        return $_('jobs.errors_summary_faults', { default: 'Something is failing and needs your attention. The problems are listed below.' });
    }

    /** When the verdict was measured; the pill beside it already says what it is. */
    function latestHealthLine(): string {
        if (!workspaceCapturedAt) return $_('jobs.errors_no_snapshot', { default: 'No health reading yet.' });
        return $_('jobs.errors_read_at', { values: { at: formatDateTime(workspaceCapturedAt) }, default: 'Read at {at}' });
    }

    function eventPipelineStatus(): string {
        return pipelineCardStatus(eventPipelineVerdict(health?.event_pipeline, overallStatus()), connections);
    }

    function eventPipelineSummary(): string {
        const pipeline = health?.event_pipeline ?? {};
        const criticalFailureActive = pipeline.critical_failure_active === true;
        const criticalFailures = asNumber(pipeline.critical_failures);
        const faults = faultDropCount(pipeline);
        if (eventPipelineStatus() === 'unknown') {
            return $_('jobs.errors_pipeline_unmeasured', { default: 'Nothing can arrive while the MQTT broker is not connected, so these counts do not show whether processing works.' });
        }
        if (criticalFailureActive) return $_('jobs.errors_pipeline_critical', { values: { count: criticalFailures }, default: '{count, plural, one {# critical failure recorded.} other {# critical failures recorded.}}' });
        if (criticalFailures > 0) return $_('jobs.errors_pipeline_historical', { values: { count: criticalFailures }, default: '{count, plural, one {# earlier failure recorded; processing has since recovered.} other {# earlier failures recorded; processing has since recovered.}}' });
        if (faults > 0) return $_('jobs.errors_pipeline_dropped', { values: { count: faults }, default: '{count, plural, one {# Frigate event was dropped by a fault.} other {# Frigate events were dropped by a fault.}}' });
        if (asNumber(pipeline.started_events) === 0) return $_('jobs.errors_pipeline_idle', { default: 'Nothing has arrived from Frigate since this instance started.' });
        return $_('jobs.errors_pipeline_ok', { default: 'What Frigate sends is being processed normally.' });
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
            values: { count },
            default: '{count, plural, one {# Frigate event did not pass your identification settings.} other {# Frigate events did not pass your identification settings.}} This is the filter working, not a fault.'
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
        return mqttCardStatus(connections, asText(health?.mqtt?.pressure_level, 'unknown'));
    }

    function at(value: string | null | undefined): string {
        const parsed = value ? Date.parse(value) : Number.NaN;
        return Number.isFinite(parsed) ? formatDateTime(parsed) : $_('common.unknown', { default: 'unknown' });
    }

    function mqttSummary(): string {
        if (!connections) {
            return $_('jobs.errors_connections_unread', { default: 'The connection could not be read. Refresh to try again.' });
        }
        const link = connections.mqtt;
        const server = `${link.server}:${link.port}`;
        if (link.state === 'disconnected') {
            return $_('jobs.errors_mqtt_disconnected', { values: { server, at: at(link.last_attempt_at) }, default: 'Not connected to {server}. Last tried {at}; it keeps retrying.' });
        }
        if (link.state === 'connecting') {
            return $_('jobs.errors_mqtt_connecting', { values: { server }, default: 'Connecting to {server}.' });
        }
        if (link.state === 'not_configured') {
            return $_('jobs.errors_problem.mqtt_not_configured', { default: 'No MQTT broker is set, so no visits can be recorded.' });
        }
        if (link.state === 'stopped') {
            return $_('jobs.errors_problem.mqtt_stopped', { default: 'The MQTT service is not running, so no new visits can be recorded.' });
        }
        const connected = $_('jobs.errors_mqtt_connected', { values: { server, at: at(link.connected_since) }, default: 'Connected to {server} since {at}.' });
        return `${connected} ${mqttLoadSummary()}`;
    }

    function frigateStatus(): string {
        return frigateCardStatus(connections);
    }

    function frigateFailure(kind: string | null | undefined): string {
        switch (kind) {
            case 'timeout':
                return $_('jobs.errors_frigate_failure.timeout', { default: 'it took too long to answer' });
            case 'unauthorized':
                return $_('jobs.errors_frigate_failure.unauthorized', { default: 'it refused the access token' });
            case 'server_error':
                return $_('jobs.errors_frigate_failure.server_error', { default: 'it reported an error of its own' });
            default:
                return $_('jobs.errors_frigate_failure.connection', { default: 'the address could not be reached' });
        }
    }

    function frigateSummary(): string {
        if (!connections) {
            return $_('jobs.errors_connections_unread', { default: 'The connection could not be read. Refresh to try again.' });
        }
        const frigate = connections.frigate;
        if (frigate.state === 'unreachable') {
            return $_('jobs.errors_frigate_unreachable', { values: { url: frigate.url, at: at(frigate.checked_at), reason: frigateFailure(frigate.last_failure) }, default: 'Frigate at {url} did not answer at {at}: {reason}.' });
        }
        if (frigate.state === 'reachable') {
            return $_('jobs.errors_frigate_reachable', { values: { url: frigate.url, at: at(frigate.checked_at) }, default: 'Frigate at {url} answered at {at}.' });
        }
        return $_('jobs.errors_frigate_unchecked', { values: { url: frigate.url }, default: 'Frigate at {url} has not been asked anything since this instance started.' });
    }

    function frigateAvailability(): string | null {
        const availability = connections?.frigate.availability;
        if (availability === 'online') return $_('jobs.errors_frigate_announced_online', { default: 'Frigate announces itself online over MQTT.' });
        if (availability === 'offline') return $_('jobs.errors_frigate_announced_offline', { default: 'Frigate announces itself offline over MQTT.' });
        return null;
    }

    /** The broker's last failure in words, from its cause code; its own text stays for the details. */
    function mqttFailureCause(): string | null {
        const link = connections?.mqtt;
        if (!link || link.state !== 'disconnected' || !link.last_error) return null;
        const worded = link.last_error_cause
            ? connectionCauseMessage(link.last_error_cause, 'mqtt', `${link.server}:${link.port}`)
            : null;
        return worded ?? $_('jobs.errors_mqtt_cause_unknown', { default: 'The broker client gave a reason YA-WAMF does not recognise. It is shown under Technical details.' });
    }

    function videoSummary(): string {
        if (videoClassifierCard.paused) {
            return videoClassifierCard.pausedUntil
                ? $_('jobs.errors_video_paused_until', { values: { at: at(videoClassifierCard.pausedUntil), count: videoClassifierCard.failureCount }, default: 'Video analysis is paused until {at}, after {count, plural, one {# failure} other {# failures}} in a row.' })
                : $_('jobs.errors_video_paused', { values: { count: videoClassifierCard.failureCount }, default: 'Video analysis is paused after {count, plural, one {# failure} other {# failures}} in a row.' });
        }
        return $_('jobs.errors_video_not_paused', { values: { queued: videoClassifierCard.pending.toLocaleString(), running: videoClassifierCard.active.toLocaleString() }, default: 'Video analysis is not paused: {queued} waiting, {running} running.' });
    }

    function mqttLoadSummary(): string {
        const mqtt = health?.mqtt ?? {};
        const pressure = asText(mqtt.pressure_level, 'unknown').toLowerCase();
        const inFlight = asNumber(mqtt.in_flight);
        const capacity = asNumber(mqtt.in_flight_capacity);
        if (pressure === 'critical' || pressure === 'high') {
            return $_('jobs.errors_mqtt_pressure', { values: { pressure, inFlight: inFlight.toLocaleString(), capacity: capacity.toLocaleString() }, default: `The MQTT connection is under {pressure} load: {inFlight} of {capacity} messages being handled.` });
        }
        const reconnects = asNumber(mqtt.topic_liveness_reconnects);
        return reconnects > 0
            ? $_('jobs.errors_mqtt_reconnected', { values: { count: reconnects }, default: 'MQTT is working again after {count, plural, one {# reconnect} other {# reconnects}}.' })
            : $_('jobs.errors_mqtt_ok', { default: 'Messages are handled as they arrive.' });
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
            return $_('jobs.errors_live_class_recovering', { values: { running: running.toLocaleString(), maxConcurrent: maxConcurrent.toLocaleString() }, default: `Naming is recovering: {running} of {maxConcurrent} running.` });
        }
        if (queued > 0) {
            return $_('jobs.errors_live_class_queued', { values: { queued: queued.toLocaleString(), running: running.toLocaleString(), maxConcurrent: maxConcurrent.toLocaleString() }, default: `{queued} waiting to be named, behind {running} of {maxConcurrent} running.` });
        }
        return $_('jobs.errors_live_class_ok', { default: 'Nothing is waiting to be named.' });
    }

    function backgroundStatus(): string {
        const background = health?.ml?.background_image ?? {};
        if (background.background_throttled) return 'degraded';
        return asText(background.status, 'unknown');
    }

    function backgroundSummary(): string {
        const background = health?.ml?.background_image ?? {};
        if (background.background_throttled) {
            return $_('jobs.errors_background_throttled', { values: { queued: asNumber(background.queued).toLocaleString() }, default: `Background work is held back, with {queued} waiting, so new visits are named first.` });
        }
        return $_('jobs.errors_background_plain', { values: { queued: asNumber(background.queued).toLocaleString(), running: asNumber(background.in_flight).toLocaleString() }, default: 'Background work: {queued} waiting, {running} running.' });
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
            return $_('jobs.errors_dispatcher_dropped', { values: { count: droppedJobs }, default: '{count, plural, one {# notification was not sent because too many were waiting.} other {# notifications were not sent because too many were waiting.}}' });
        }
        if (dbWait >= 5000) {
            return $_('jobs.errors_dispatcher_db_wait', { values: { ms: dbWait.toLocaleString() }, default: `The longest wait for the database was {ms} ms.` });
        }
        return $_('jobs.errors_dispatcher_ok', { default: 'Notifications are being sent and the database is answering.' });
    }

    function startupStatus(): string {
        return startupWarnings.length > 0 ? 'warning' : 'ok';
    }

    function startupSummary(): string {
        if (startupWarnings.length <= 0) {
            return $_('jobs.errors_startup_ok', { default: 'YA-WAMF started without warnings.' });
        }
        const first = startupWarnings[0] ?? {};
        const phase = asText((first as Record<string, unknown>).phase, $_('jobs.errors_unknown_phase', { default: 'Unknown step' }));
        return $_('jobs.errors_startup_summary', { values: { count: startupWarnings.length, phase }, default: '{count, plural, one {# start-up warning recorded.} other {# start-up warnings recorded.}} Latest step: {phase}.' });
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
            values: { count: taxa },
            default: '{count, plural, one {# species can be named without the network.} other {# species can be named without the network.}}'
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
        if (minutes < 60) return $_('about.instance.uptime_minutes', { values: { count: minutes }, default: '{count} min' });
        const hours = Math.floor(minutes / 60);
        return $_('about.instance.uptime_hours', { values: { count: hours }, default: '{count} h' });
    }

    function goToDetection(eventId: string): void {
        if (!eventId) return;
        onNavigate?.(`/events?event=${encodeURIComponent(eventId)}`);
    }
</script>

{#snippet subsystemHead(title: string, chip: string, tone: string, rawStatus: string)}
    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 class="text-sm font-bold text-strong">{title}</h4>
        <!-- The state in words; the tone and its icon only repeat it. -->
        <StatusChip tone={STATUS_TONE[statusTone(tone)]} label={chip} title={rawStatus} class="shrink-0" />
    </div>
{/snippet}

{#snippet metricList(metrics: Array<{ label: string; value: string }>)}
    <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
        {#each metrics as metric (metric.label)}
            <div class="min-w-0">
                <dt class="wrap-break-word text-muted">{metric.label}</dt>
                <dd class="wrap-break-word font-semibold tabular-nums text-strong">{metric.value}</dd>
            </div>
        {/each}
    </dl>
{/snippet}

{#snippet technicalDetails(lines: string[])}
    <details class="group mt-1">
        <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 text-xs font-semibold text-ink focus-ring">
            <svg class="h-3.5 w-3.5 shrink-0 transition-transform duration-200 group-open:rotate-90" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
            {$_('common.technical_details', { default: 'Technical details' })}
        </summary>
        <div class="space-y-1 pb-1 font-mono text-xs wrap-anywhere text-ink">
            {#each lines as line, index (index)}
                <p>{line}</p>
            {/each}
        </div>
    </details>
{/snippet}

<div class="space-y-6">
    <!-- One card for the system: whether it is working, then what the host is doing, then the
         detail behind the verdict. What happened follows as its own card. -->
    <SystemHealthPanel statusRead={readState !== 'reading'}>
        {#snippet status()}
            <div class="space-y-4" data-health-status data-health-read-state={readState}>
                <!-- Held at its usual height while the first reading is on its way, so its arrival moves nothing. -->
                <div class="flex min-h-28 flex-wrap items-start gap-x-4 gap-y-2 rounded-2xl border px-4 py-4 sm:px-5 {heroToneClass(verdict())}">
                    {#if readState !== 'reading' && readState !== 'failed'}
                        <span class="inline-flex shrink-0" data-health-status-pill>
                            <StatusChip tone={STATUS_TONE[statusTone(verdict())]} label={statusLabel(verdict())} title={verdict()} size="md" />
                        </span>
                    {/if}
                    <div class="min-w-0 flex-1 wrap-break-word">
                        <h3 class="font-display text-lg font-bold text-strong">{$_('jobs.errors_system_status', { default: 'System status' })}</h3>
                        {#if readState === 'reading'}
                            <p class="text-sm text-ink" data-health-reading>{$_('jobs.errors_reading', { default: 'Reading the latest health…' })}</p>
                        {:else if readState === 'failed'}
                            <!-- Nothing was measured, so nothing is claimed: no pill and no fault count. -->
                            <p class="text-sm font-semibold text-strong" data-health-read-failed>{$_('jobs.errors_read_failed', { default: 'The health reading could not be loaded, so this page claims no state.' })}</p>
                            <p class="text-sm text-ink">{$_('jobs.errors_read_failed_next', { default: 'Refresh to try again. If it keeps failing, check that the YA-WAMF backend is running.' })}</p>
                            {@render technicalDetails([refreshError])}
                        {:else}
                            {#if openItems.length > 0}
                                <ul class="mt-1 space-y-2" data-health-problems>
                                    {#each openItems as item (item.key)}
                                        {#if item.problem}
                                            {@const text = problemItem(item.problem)}
                                            <li class="wrap-break-word text-sm" data-health-problem={item.problem}>
                                                <p class="font-semibold text-strong">{text.title}</p>
                                                <p class="text-ink">{text.next}</p>
                                            </li>
                                        {:else if item.incident}
                                            {@const text = diagnosticWords(item.incident.primaryReasonCode)}
                                            <li class="wrap-break-word text-sm" data-health-open-incident>
                                                <p class="font-semibold text-strong">{text.title}</p>
                                                {#if text.next}<p class="text-ink">{text.next}</p>{/if}
                                                {@render technicalDetails(incidentDetails(item.incident))}
                                            </li>
                                        {/if}
                                    {/each}
                                </ul>
                            {:else}
                                <p class="text-sm text-ink">{overallSummary()}</p>
                            {/if}
                            {#if readState === 'stale' && lastReadAt}
                                <p class="mt-2 text-sm font-semibold text-strong" data-health-stale>
                                    {$_('jobs.errors_read_stale', { values: { at: formatDateTime(lastReadAt) }, default: 'The latest refresh failed, so this is the reading from {at}. Refresh to try again.' })}
                                </p>
                                {@render technicalDetails([refreshError])}
                            {/if}
                            <!-- Two lines on a phone, where the dated reading wraps; held so its arrival moves nothing. -->
                            <p class="mt-1 min-h-8 text-xs text-ink sm:min-h-4">{latestHealthLine()}</p>
                        {/if}
                    </div>
                </div>
                {#if frigateMediaAdvisory.elevated}
                    <!-- ── Frigate media-unavailability advisory (Event Not Found guidance) ── -->
                    <div class="rounded-2xl border border-status-attention-line bg-status-attention-soft p-4 text-status-attention">
                        <div class="flex items-start gap-3">
                            <div class="mt-0.5 shrink-0">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                                </svg>
                            </div>
                            <div class="min-w-0 flex-1">
                                <h4 class="eyebrow text-inherit">{$_('jobs.frigate_media_advisory_title', { default: 'Frigate often has no snapshot for an event' })}</h4>
                                <p class="mt-1 text-sm font-semibold">{$_('jobs.frigate_media_advisory_body', { values: { percent: frigateMediaDropPercent, dropped: frigateMediaAdvisory.dropped.toLocaleString(), started: frigateMediaAdvisory.started.toLocaleString() }, default: `{percent}% of recent Frigate events ({dropped} of {started}) were dropped because Frigate had no snapshot, thumbnail or recording for them. This usually means birds tracked too briefly for Frigate to keep, or recordings kept for too short a time.` })}</p>
                                <a href={FRIGATE_MISSING_DOCS_URL} target="_blank" rel="noopener noreferrer" class="mt-2 inline-block text-xs font-bold underline underline-offset-2 hover:no-underline">
                                    {$_('jobs.frigate_media_advisory_link', { default: 'How to reduce this →' })}
                                </a>
                            </div>
                        </div>
                    </div>
                {/if}
            </div>
        {/snippet}

        {#snippet details()}
        <!-- ── Subsystem detail: one ruled list on the card's own surface. Each row is told apart by
             its heading and says its state in a worded chip; nothing is tinted and no text is dimmed. ── -->
        <details class="border-t border-line-soft pt-4" data-subsystem-detail>
            <summary class="group flex min-h-11 cursor-pointer items-center justify-between gap-3 py-2 eyebrow focus-ring">
                <span>{$_('jobs.errors_subsystems_title', { default: 'Detail by part' })}</span>
                <svg class="h-4 w-4 shrink-0 text-muted transition-transform duration-200 group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
            </summary>
            {#if !workspacePayload}
                <StateBlock class="mt-2" state="not-measured" cause={$_('jobs.errors_subsystems_unread', { default: 'Nothing to show until a health reading has loaded.' })} />
            {:else}
            <ul class="mt-2 divide-y divide-line-soft" data-health-subsystems>
                <li class="py-4" data-health-subsystem="pipeline">
                    {@render subsystemHead($_('jobs.pipeline_title', { default: 'Pipeline' }), statusLabel(eventPipelineStatus()), eventPipelineStatus(), eventPipelineStatus())}
                    <p class="mt-1 text-sm text-ink">{eventPipelineSummary()}</p>
                    {@render metricList([
                        { label: $_('jobs.errors_metric_started', { default: 'Started' }), value: asNumber(health?.event_pipeline?.started_events).toLocaleString() },
                        { label: $_('jobs.errors_metric_completed', { default: 'Completed' }), value: asNumber(health?.event_pipeline?.completed_events).toLocaleString() },
                        { label: $_('jobs.errors_metric_dropped', { default: 'Dropped' }), value: asNumber(health?.event_pipeline?.dropped_events).toLocaleString() },
                        { label: $_('jobs.errors_metric_critical', { default: 'Critical' }), value: asNumber(health?.event_pipeline?.critical_failures).toLocaleString() }
                    ])}
                </li>

                <!-- Filtering is the detection settings working, not a state: its chip is a count in neutral ink. -->
                <li class="py-4" data-health-subsystem="filtered">
                    {@render subsystemHead($_('jobs.errors_filtered_title', { default: 'Filtered out' }), expectedDropCount(health?.event_pipeline).toLocaleString(), 'unknown', filteredStatus())}
                    <p class="mt-1 text-sm text-ink">{filteredSummary()}</p>
                    {#if expectedDropReasons(health?.event_pipeline).length > 0}
                        <dl class="mt-2 grid grid-cols-1 gap-1 text-xs sm:max-w-md">
                            {#each expectedDropReasons(health?.event_pipeline) as entry (entry.reason)}
                                <div class="flex items-baseline justify-between gap-3">
                                    <dt class="min-w-0 wrap-break-word text-ink">{filteredReasonLabel(entry.reason)}</dt>
                                    <dd class="shrink-0 font-semibold tabular-nums text-strong">{entry.count.toLocaleString()}</dd>
                                </div>
                            {/each}
                        </dl>
                        {#if recentFilteredDetections(health?.event_pipeline).length > 0}
                            <p class="mt-3 text-xs font-bold text-ink">{$_('jobs.errors_filtered_recent', { default: 'Most recent' })}</p>
                            <ul class="mt-1 space-y-1 text-xs sm:max-w-md">
                                {#each keyedPipelineDetections(recentFilteredDetections(health?.event_pipeline)) as { key, entry } (key)}
                                    <li
                                        class="flex items-baseline justify-between gap-3"
                                        title={`${filteredReasonLabel(entry.reason)}${entry.timestamp ? ` · ${formatDateTime(Date.parse(entry.timestamp))}` : ''} · ${entry.eventId}`}
                                    >
                                        <span class="min-w-0 wrap-break-word italic text-strong">{entry.label ?? $_('common.unknown_species', { default: 'Unknown species' })}</span>
                                        <span class="shrink-0 tabular-nums text-ink">{filteredScoreLabel(entry.score)}</span>
                                    </li>
                                {/each}
                            </ul>
                        {/if}
                        <p class="mt-2 text-xs text-ink">{$_('jobs.errors_filtered_hint', { default: 'Lower the minimum confidence floor in Settings → Identifying birds to keep more of these as Unknown bird.' })}</p>
                    {/if}
                </li>

                <!-- MQTT: the connection first, then how hard its handlers are working. -->
                <li class="py-4" data-health-card="mqtt" data-health-card-status={mqttStatus()}>
                    {@render subsystemHead('MQTT', statusLabel(mqttStatus()), mqttStatus(), mqttStatus())}
                    <p class="mt-1 wrap-break-word text-sm text-ink">{mqttSummary()}</p>
                    {#if mqttFailureCause()}
                        <p class="mt-1 wrap-break-word text-sm text-ink" data-health-mqtt-cause>{mqttFailureCause()}</p>
                        {@render technicalDetails([connections?.mqtt.last_error ?? ''])}
                    {/if}
                    {@render metricList([
                        { label: $_('jobs.errors_metric_handling', { default: 'Messages being handled' }), value: $_('jobs.errors_metric_of', { values: { count: asNumber(health?.mqtt?.in_flight).toLocaleString(), total: asNumber(health?.mqtt?.in_flight_capacity).toLocaleString() }, default: '{count} of {total}' }) },
                        { label: $_('jobs.errors_metric_reconnects', { default: 'Reconnects' }), value: asNumber(health?.mqtt?.topic_liveness_reconnects).toLocaleString() },
                        { label: $_('jobs.errors_metric_last_reconnect', { default: 'Last reconnect reason' }), value: asText(health?.mqtt?.last_reconnect_reason, $_('jobs.errors_no_reconnect_reason', { default: 'None recorded' })) }
                    ])}
                </li>

                <!-- Frigate: whether its API answered the latest request. -->
                <li class="py-4" data-health-card="frigate" data-health-card-status={frigateStatus()}>
                    {@render subsystemHead($_('jobs.errors_card_frigate', { default: 'Frigate' }), statusLabel(frigateStatus()), frigateStatus(), frigateStatus())}
                    <p class="mt-1 wrap-break-word text-sm text-ink">{frigateSummary()}</p>
                    {#if frigateAvailability()}
                        <p class="mt-1 text-sm text-ink">{frigateAvailability()}</p>
                    {/if}
                </li>

                <li class="py-4" data-health-subsystem="live">
                    {@render subsystemHead($_('jobs.errors_card_live_classification', { default: 'Naming new visits' }), statusLabel(liveClassificationStatus()), liveClassificationStatus(), liveClassificationStatus())}
                    <p class="mt-1 text-sm text-ink">{liveClassificationSummary()}</p>
                    {@render metricList([
                        { label: $_('jobs.errors_metric_waiting', { default: 'Waiting' }), value: asNumber(health?.ml?.live_image?.queued).toLocaleString() },
                        { label: $_('jobs.errors_metric_being_named', { default: 'Being named now' }), value: asNumber(health?.ml?.live_image?.in_flight).toLocaleString() },
                        { label: $_('jobs.errors_metric_at_once', { default: 'At most at once' }), value: asNumber(health?.ml?.live_image?.max_concurrent).toLocaleString() },
                        { label: $_('jobs.errors_metric_given_up', { default: 'Given up' }), value: asNumber(health?.ml?.live_image?.abandoned).toLocaleString() }
                    ])}
                </li>

                <li class="py-4" data-health-subsystem="video">
                    {@render subsystemHead($_('jobs.errors_card_video_classification', { default: 'Video analysis' }), statusLabel(videoClassifierCard.status), videoClassifierCard.status, videoClassifierCard.status)}
                    <p class="mt-1 text-sm text-ink">{videoSummary()}</p>
                    {@render metricList([
                        { label: $_('jobs.errors_metric_waiting', { default: 'Waiting' }), value: videoClassifierCard.pending.toLocaleString() },
                        { label: $_('jobs.errors_metric_running', { default: 'Running' }), value: videoClassifierCard.active.toLocaleString() },
                        { label: $_('jobs.errors_metric_failures_in_a_row', { default: 'Failures in a row' }), value: videoClassifierCard.failureCount.toLocaleString() }
                    ])}
                </li>

                <li class="py-4" data-health-subsystem="background">
                    {@render subsystemHead($_('jobs.errors_card_background_maintenance', { default: 'Background work' }), statusLabel(backgroundStatus()), backgroundStatus(), backgroundStatus())}
                    <p class="mt-1 text-sm text-ink">{backgroundSummary()}</p>
                    {@render metricList([
                        { label: $_('jobs.errors_metric_waiting', { default: 'Waiting' }), value: asNumber(health?.ml?.background_image?.queued).toLocaleString() },
                        { label: $_('jobs.errors_metric_running', { default: 'Running' }), value: asNumber(health?.ml?.background_image?.in_flight).toLocaleString() },
                        { label: $_('jobs.errors_metric_given_up', { default: 'Given up' }), value: asNumber(health?.ml?.background_image?.abandoned).toLocaleString() },
                        { label: $_('jobs.errors_metric_held_back', { default: 'Held back for live work' }), value: health?.ml?.background_image?.background_throttled ? $_('common.yes', { default: 'Yes' }) : $_('common.no', { default: 'No' }) }
                    ])}
                </li>

                <li class="py-4" data-health-subsystem="dispatch">
                    {@render subsystemHead($_('jobs.errors_card_notifications_db', { default: 'Notifications and database' }), statusLabel(dispatcherStatus()), dispatcherStatus(), dispatcherStatus())}
                    <p class="mt-1 text-sm text-ink">{dispatcherSummary()}</p>
                    {@render metricList([
                        { label: $_('jobs.errors_metric_notifications_dropped', { default: 'Notifications dropped' }), value: asNumber(health?.notification_dispatcher?.dropped_jobs).toLocaleString() },
                        { label: $_('jobs.errors_metric_waiting_to_send', { default: 'Waiting to send' }), value: $_('jobs.errors_metric_of', { values: { count: asNumber(health?.notification_dispatcher?.queue_size).toLocaleString(), total: asNumber(health?.notification_dispatcher?.queue_max).toLocaleString() }, default: '{count} of {total}' }) },
                        { label: $_('jobs.errors_metric_db_longest_wait', { default: 'Longest wait for the database' }), value: `${asNumber(health?.db_pool?.acquire_wait_max_ms).toLocaleString()} ms` },
                        { label: $_('jobs.errors_metric_db_waits_timed_out', { default: 'Database waits that timed out' }), value: asNumber(health?.db_pool?.acquire_timeouts).toLocaleString() }
                    ])}
                </li>

                <li class="py-4" data-health-subsystem="naming">
                    {@render subsystemHead($_('jobs.errors_card_naming', { default: 'Naming sources' }), statusLabel(namingStatus()), namingStatus(), namingStatus())}
                    <p class="mt-1 text-sm text-ink">{namingSummary()}</p>
                    {@render metricList([
                        { label: $_('jobs.errors_metric_offline_species', { default: 'Offline species' }), value: asNumber(health?.naming?.species_reference?.taxon_count).toLocaleString() },
                        { label: $_('jobs.errors_metric_languages', { default: 'Languages' }), value: namingLocales() },
                        { label: $_('jobs.errors_metric_catalog', { default: 'Catalogue species' }), value: catalogSpecies() }
                    ])}
                    {#if catalogSummary()}
                        <p class="mt-2 text-xs text-ink">{catalogSummary()}</p>
                    {/if}
                    {#if catalogSources().length > 0}
                        <p class="mt-3 text-xs font-bold text-ink">{$_('jobs.errors_catalog_sources', { default: 'Catalogue sources' })}</p>
                        <ul class="mt-1 space-y-2 text-xs">
                            {#each catalogSources() as source}
                                <li>
                                    <span class="font-semibold text-strong">{source.heading}</span>
                                    {#if source.citation}
                                        <span class="mt-0.5 block text-ink">{source.citation}</span>
                                    {/if}
                                </li>
                            {/each}
                        </ul>
                        <p class="mt-2 text-xs text-ink">{$_('jobs.errors_catalog_rollback', { default: 'The catalogue is a separate file from your visit history. Rolling one back changes names, never your recorded visits, and a backup of the data folder covers both.' })}</p>
                    {/if}
                </li>

                <li class="py-4" data-health-subsystem="startup">
                    {@render subsystemHead($_('jobs.errors_card_startup_warnings', { default: 'Startup warnings' }), statusLabel(startupStatus()), startupStatus(), startupStatus())}
                    <p class="mt-1 text-sm text-ink">{startupSummary()}</p>
                    {#if startupWarnings.length > 0}
                        <ul class="mt-2 space-y-2 text-xs">
                            {#each startupWarnings.slice(0, 2) as warning}
                                <li>
                                    <p class="text-ink">{asText((warning as Record<string, unknown>).phase, $_('jobs.errors_unknown_phase', { default: 'Unknown step' }))}</p>
                                    <p class="font-semibold wrap-break-word text-strong">{asText((warning as Record<string, unknown>).error, $_('jobs.errors_unknown_warning', { default: 'Unknown warning' }))}</p>
                                </li>
                            {/each}
                        </ul>
                    {/if}
                </li>
            </ul>
            {/if}
        </details>
        {/snippet}
    </SystemHealthPanel>

    <!-- Everything below the System card comes from the same reading as the verdict, or sits
         beneath it, so it is shown with that reading: the verdict's length then moves nothing.
         ── What happened: one thread of kept visits and filtered frames ── -->
    {#if readState !== 'reading'}
    <Panel
        title={$_('jobs.errors_activity_title', { default: 'What happened' })}
        description={$_('jobs.errors_activity_subtitle', {
            default: 'Recorded visits, filtered events and faults, in the order they happened'
        })}
        data-health-timeline
    >
        {#snippet actions()}
            <span class="min-w-0 rounded-2xl border border-line px-2.5 py-1 text-xs font-semibold tabular-nums text-muted">
                {$_('jobs.errors_activity_window', {
                    values: { started: startedAgoText() },
                    default: 'Since this instance started, {started}'
                })}
            </span>
        {/snippet}

        {#if !workspacePayload}
            <!-- Shown only after the first reading failed: without it the start time is unknown. -->
            <StateBlock class="mt-4" state="not-measured" cause={$_('jobs.errors_activity_unread', { default: 'Activity cannot be shown until a health reading has loaded.' })} />
        {:else if instanceWindow === null}
            <StateBlock
                class="mt-4"
                compact
                state="not-measured"
                cause={$_('jobs.errors_activity_no_window', {
                    default: 'This instance has not reported when it started, so activity cannot be placed in a window yet.'
                })}
            />
        {:else}
            <div class="mt-3">
                <HealthActivityTimeline
                    rows={timelineRows}
                    emptyMessage={$_('jobs.errors_activity_empty', {
                        values: { started: startedAgoText() },
                        default: 'No visits, filtered events or faults have been reported since this instance started {started} ago.'
                    })}
                    hiddenCount={timelineHidden}
                    hiddenLabel={$_('jobs.errors_activity_earlier', {
                        values: { count: timelineHidden },
                        default: '{count, plural, one {# earlier event in this window} other {# earlier events in this window}}'
                    })}
                    loading={refreshing && timelineRows.length === 0}
                    onselect={(detection) => goToDetection(detection.frigate_event)}
                />
            </div>
        {/if}
    </Panel>

    <!-- ── Earlier incidents + backend warnings ────────────────────── -->
    <div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel
            title={$_('jobs.earlier_incidents_title', { default: 'Earlier incidents' })}
            description={$_('jobs.earlier_incidents_desc', { default: 'Problems that have since cleared. What is open now is listed with the system status above.' })}
            data-health-earlier-incidents
        >
            <!-- The clearing action sits with the history it clears, not above the live status. -->
            {#snippet actions()}
                <button
                    type="button"
                    class="btn btn-secondary min-h-11 px-3 py-2 text-xs"
                    onclick={clearWorkspace}
                    disabled={clearing || refreshing}
                    aria-describedby="health-clear-effect"
                    data-health-clear
                >
                    {clearing ? $_('jobs.errors_clearing', { default: 'Clearing…' }) : $_('jobs.errors_clear', { default: 'Clear error history' })}
                </button>
                <span id="health-clear-effect" class="sr-only">{$_('jobs.errors_clear_effect', { default: 'Removes recorded errors and incidents now. Live checks carry on.' })}</span>
            {/snippet}
            {#if clearError}
                <p class="mt-4 text-sm font-semibold text-status-fail" role="alert">{$_('jobs.errors_clear_failed', { default: 'The error history could not be cleared. Try again; if it keeps failing, check that YA-WAMF is running.' })}</p>
            {/if}
            {#if recentIncidents.length === 0}
                <StateBlock class="mt-4" state="empty" cause={$_('jobs.earlier_incidents_empty', { default: 'Nothing has cleared since the error history was last cleared.' })} />
            {:else}
                <ul class="mt-4 divide-y divide-line-soft">
                    {#each recentIncidents.slice(0, 6) as incident (incident.id)}
                        <li class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2.5">
                            <p class="min-w-0 flex-1 basis-48 text-sm font-semibold text-strong">{diagnosticWords(incident.primaryReasonCode).title}</p>
                            <span class="text-xs tabular-nums text-muted">{formatDateTime(incident.lastSeenAt)}</span>
                        </li>
                    {/each}
                </ul>
            {/if}
        </Panel>

        <Panel
            title={$_('jobs.errors_backend_diagnostics_title', { default: 'Backend warnings and errors' })}
            description={$_('jobs.errors_backend_diagnostics_desc', { default: 'The newest the backend has recorded since the error history was last cleared.' })}
            data-health-backend-diagnostics
        >
            {#if backendEvents.length === 0}
                <StateBlock class="mt-4" state="empty" cause={$_('jobs.errors_backend_empty', { default: 'The backend has recorded no warnings or errors since the error history was last cleared. Connection problems are listed at the top of this page, not here.' })} />
            {:else}
                <!-- One ruled row per diagnostic: the state in a worded chip, the cause in the reader's
                     language where it is known, and the backend's own words under Technical details. -->
                <ul class="mt-4 divide-y divide-line-soft">
                    {#each backendEvents.slice(0, 8) as event (event.id)}
                        {@const worded = diagnosticWords(event.reason_code)}
                        <li class="py-3" data-health-diagnostic>
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <StatusChip tone={STATUS_TONE[statusTone(event.severity ?? 'warning')]} label={statusLabel(event.severity ?? 'warning')} title={event.severity} />
                                <span class="text-xs tabular-nums text-ink">{formatDateTime(Date.parse(event.timestamp))}</span>
                            </div>
                            <p class="mt-2 wrap-break-word text-sm font-semibold text-strong" data-health-diagnostic-title>{worded.title}</p>
                            {#if worded.next}
                                <p class="mt-0.5 text-sm text-ink">{worded.next}</p>
                            {/if}
                            {#if (event.count ?? 1) > 1 && event.first_seen && event.last_seen}
                                <!-- The backend keeps repeats of one fault as one entry; this says how often and over what span. -->
                                <p class="mt-1 text-xs tabular-nums text-ink" data-diagnostic-repeats>
                                    {$_('jobs.errors_repeated', {
                                        values: {
                                            count: (event.count ?? 1).toLocaleString(),
                                            first: formatDateTime(Date.parse(event.first_seen)),
                                            last: formatDateTime(Date.parse(event.last_seen))
                                        },
                                        default: '×{count}, first {first}, last {last}'
                                    })}
                                </p>
                            {/if}
                            {@render technicalDetails([
                                `${event.component} · ${event.reason_code}`,
                                event.message,
                                ...(event.event_id ? [`event ${event.event_id}`] : []),
                                ...(event.correlation_key ? [event.correlation_key] : [])
                            ])}
                        </li>
                    {/each}
                </ul>
            {/if}
        </Panel>
    </div>

    <!-- ── Diagnostics export ──────────────────────────────────────
         Engineer-facing plumbing: useful when reporting a problem, noise on a
         page whose job is to say whether the feeder is working. It sits behind
         the same disclosure the subsystem detail uses. -->
    <details class="panel" data-diagnostics-export>
        <summary class="group flex min-h-11 cursor-pointer flex-wrap items-center justify-between gap-3 text-xs font-bold text-muted focus-ring">
            <span class="flex items-center gap-2">
                <svg class="h-4 w-4 shrink-0 text-muted transition-transform duration-200 group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                {$_('jobs.errors_export_title', { default: 'Diagnostics export' })}
            </span>
            <span class="font-semibold normal-case tracking-normal text-muted">
                {$_('jobs.errors_export_count', {
                    values: { count: bundles.length.toLocaleString() },
                    default: '{count} saved'
                })}
            </span>
        </summary>

        <p class="mt-4 max-w-2xl text-sm text-muted">
            {$_('jobs.errors_export_desc', {
                default: 'A bundle captures this page, the backend’s warnings and errors, the model’s status, start-up warnings and incidents as one JSON file. Attach one when you report a problem.'
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
            <button type="button" class="btn btn-primary min-h-11 px-4 text-xs" onclick={() => exportCurrent(true)} disabled={exporting || refreshing || clearing}>
                {$_('jobs.error_bundles_capture', { default: 'Capture Bundle' })}
            </button>
            <button type="button" class="btn btn-secondary min-h-11 px-4 text-xs" onclick={() => exportCurrent(false)} disabled={exporting || refreshing || clearing}>
                {$_('jobs.errors_export_download_now', { default: 'Download without saving' })}
            </button>
        </div>

        {#if exportError}
            <p class="mt-3 text-sm text-status-fail" role="alert">{exportError}</p>
        {/if}

        {#if bundles.length === 0}
            <StateBlock class="mt-4" variant="inline" state="empty" cause={$_('jobs.errors_no_bundles', { default: 'No captured bundles available yet.' })} />
        {:else}
            <ul class="mt-5 divide-y divide-line border-t border-line">
                {#each bundles as bundle (bundle.id)}
                    <li class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3">
                        <div class="min-w-0 flex-1">
                            <p class="wrap-break-word text-sm font-semibold text-strong">{bundle.label}</p>
                            <p class="mt-0.5 text-xs tabular-nums text-muted">
                                {formatDateTime(bundle.createdAt)} · {bundleSummaryText(bundle)}
                            </p>
                            {#if bundleNotesPreview(bundle)}
                                <p class="mt-1 wrap-break-word text-xs text-muted">{bundleNotesPreview(bundle)}</p>
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
    {/if}
</div>

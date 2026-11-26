<script lang="ts">
    import { settingsSectionName } from '../../settings/settings-place';
    import Separator from '../Separator.svelte';
    import { onDestroy, onMount } from 'svelte';
    import { sessionTests } from '../../settings/session-tests.svelte';
    import { _ } from 'svelte-i18n';
    import { testFrigateConnection, type RecordingClipCapability } from '../../api/system';
    import { testMQTTPublish } from '../../api/maintenance';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import { runSequentialDiagnostic, type DiagnosticStage, type DiagnosticResult } from '../../utils/diagnostic-runner';
    import { appApiPath } from '../../app/url-base';
    import { authStore } from '../../stores/auth.svelte';
    import { FRIGATE_LOGO_URL } from '../../assets';
    import SecretInput from './_primitives/SecretInput.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import ClassificationImageSourceSetting from './ClassificationImageSourceSetting.svelte';
    import CameraWatchRow from './CameraWatchRow.svelte';
    import {
        applyCameraWatchMode,
        cameraWatchRows,
        setCameraRole,
        setGardenMotion,
        watchEveryCameraForBirds,
        watchesEveryCameraForBirds,
        type CameraRole,
        type CameraWatchContext,
        type CameraWatchMode,
        type CameraWatchSettings
    } from '../../utils/camera-watch';
    import type { ClassificationImageSource } from '../../api/settings';

    let {
        frigateUrl = $bindable(''),
        frigateIngestLabels = $bindable('bird'),
        frigateExternalUrl = $bindable(''),
        mqttServer = $bindable(''),
        mqttPort = $bindable(1883),
        mqttAuth = $bindable(false),
        mqttUsername = $bindable(''),
        mqttPassword = $bindable(''),
        mqttPasswordSaved = $bindable(false),
        classificationImageSource = $bindable<ClassificationImageSource>('frigate_snapshot'),
        recordingFrameDelaySeconds = $bindable(12),
        clipsEnabled = $bindable(true),
        recordingClipEnabled = $bindable(false),
        recordingClipBeforeSeconds = $bindable(30),
        recordingClipAfterSeconds = $bindable(90),
        selectedCameras = $bindable<string[]>([]),
        gardenCameras = $bindable<string[]>([]),
        gardenMotionCameras = $bindable<string[]>([]),
        betaGardenAnimals = false,
        cameraRoles = $bindable<Record<string, CameraRole>>({}),
        nestDedupeMinutes = $bindable(30),
        frigateCameras = null,
        frigateCamerasFailed = false,
        recordingClipCapability = null,
        recordingClipCapabilityLoading = false,
        camerasLoading,
        loadCameras,
        region
    }: {
        frigateUrl: string;
        frigateIngestLabels: string;
        frigateExternalUrl: string;
        mqttServer: string;
        mqttPort: number;
        mqttAuth: boolean;
        mqttUsername: string;
        mqttPassword: string;
        mqttPasswordSaved: boolean;
        classificationImageSource: ClassificationImageSource;
        recordingFrameDelaySeconds?: number;
        clipsEnabled: boolean;
        recordingClipEnabled: boolean;
        recordingClipBeforeSeconds: number;
        recordingClipAfterSeconds: number;
        selectedCameras: string[];
        gardenCameras: string[];
        gardenMotionCameras: string[];
        betaGardenAnimals?: boolean;
        cameraRoles: Record<string, CameraRole>;
        nestDedupeMinutes: number;
        /** Cameras read from Frigate, or null until the list has been read. */
        frigateCameras: string[] | null;
        frigateCamerasFailed: boolean;
        recordingClipCapability: RecordingClipCapability | null;
        recordingClipCapabilityLoading: boolean;
        camerasLoading: boolean;
        loadCameras: () => Promise<void>;
        /** Which cards to show: the ones most owners need (`main`), or the rest under More options (`more`). */
        region: 'main' | 'more';
    } = $props();

    const showMain = $derived(region === 'main');
    const showMore = $derived(region === 'more');

    const watchSettings = $derived<CameraWatchSettings>({
        cameras: selectedCameras,
        gardenCameras,
        gardenMotionCameras,
        cameraRoles
    });
    const watchContext = $derived<CameraWatchContext>({ frigateCameras, gardenEnabled: betaGardenAnimals });
    const watchRows = $derived(cameraWatchRows(watchSettings, watchContext));

    function commitWatch(next: CameraWatchSettings): void {
        selectedCameras = [...next.cameras];
        gardenCameras = [...next.gardenCameras];
        gardenMotionCameras = [...next.gardenMotionCameras];
        cameraRoles = { ...next.cameraRoles };
    }

    function chooseWatchMode(camera: string, mode: CameraWatchMode): void {
        const change = applyCameraWatchMode(watchSettings, camera, mode, watchContext);
        // A blocked choice is disabled and worded on the row, so there is nothing to apply.
        if (change.ok) commitWatch(change.settings);
    }

    // Connection test uses the shared DiagnosticDialog: two genuinely independent
    // checks — reaching the Frigate API, then publishing to the MQTT broker.
    let fcTestOpen = $state(false);
    let fcRunning = $state(false);
    let fcStages = $state<DiagnosticStage[]>([]);
    let fcResult = $state<DiagnosticResult | null>(null);
    let fcRunId = $state(0);

    async function runConnectionDiagnostic(): Promise<void> {
        fcTestOpen = true;
        fcRunning = true;
        fcResult = null;
        fcRunId += 1;
        fcResult = await runSequentialDiagnostic(
            [
                {
                    id: 'frigate',
                    label: $_('settings.frigate.stage_frigate', { default: 'Frigate API' }),
                    nextStep: $_('settings.frigate.stage_frigate_next', { values: { section: settingsSectionName('cameras', $_) }, default: 'Check the server URL in {section}, and that Frigate is running.' }),
                    run: async () => {
                        const r = await testFrigateConnection(frigateUrl.trim());
                        return {
                            status: r.status,
                            message: r.status === 'ok'
                                ? $_('settings.frigate.stage_frigate_ok', { default: 'Connected to Frigate {version}', values: { version: `v${r.version}` } })
                                : $_('settings.frigate.stage_frigate_bad', { default: 'Frigate returned an unexpected status.' })
                        };
                    }
                },
                {
                    id: 'mqtt',
                    label: $_('settings.frigate.stage_mqtt', { default: 'MQTT broker publish' }),
                    nextStep: $_('settings.frigate.stage_mqtt_next', { values: { section: settingsSectionName('cameras', $_) }, default: 'Check the broker address, port and sign-in in {section}.' }),
                    run: () => testMQTTPublish({
                        server: mqttServer.trim(),
                        port: mqttPort,
                        auth: mqttAuth,
                        username: mqttUsername.trim(),
                        password: mqttPassword
                    })
                }
            ],
            (stages) => (fcStages = stages),
            { independent: true }
        );
        fcRunning = false;
        // The status column states a test's result only when it ran during this visit.
        for (const key of ['frigate', 'mqtt'] as const) {
            const stage = fcStages.find((candidate) => candidate.id === key);
            if (stage && (stage.state === 'passed' || stage.state === 'warning' || stage.state === 'failed')) {
                sessionTests.record(key, stage.state !== 'failed');
            }
        }
    }

    // The test sits on the section's first screen, so the status column can run it from there.
    onMount(() => (region === 'more' ? undefined : sessionTests.provide(['frigate', 'mqtt'], runConnectionDiagnostic)));

    let previewCamera = $state<string | null>(null);
    let previewVisible = $state(false);
    let previewTimestamp = $state(0);
    let previewLoading = $state(false);
    let previewError = $state<string | null>(null);
    let previewBlobUrl = $state<string | null>(null);
    let previewTimer: ReturnType<typeof setInterval> | null = null;

    function getRecordingCapabilityReason(reason: string | null | undefined): string {
        switch (reason) {
            case 'config_unavailable':
                return $_('settings.frigate.full_visit_reason_config_unavailable', { default: 'Frigate config could not be read.' });
            case 'no_matching_cameras':
                return $_('settings.frigate.full_visit_reason_no_matching_cameras', { default: 'No selected cameras match the current Frigate config.' });
            case 'recordings_disabled':
                return $_('settings.frigate.full_visit_reason_recordings_disabled', { default: 'Recording is disabled for the selected cameras. Enable recording and retain at least one continuous day.' });
            case 'continuous_retention_disabled':
                return $_('settings.frigate.full_visit_reason_continuous_retention_disabled', { default: 'Frigate is not retaining a continuous timeline. Set record.continuous.days to at least 1; event-only clips can start late or end early.' });
            case 'record_stream_missing':
                return $_('settings.frigate.full_visit_reason_record_stream_missing', { default: 'A selected camera has no recording stream. Add record to its FFmpeg input roles and retain at least one continuous day.' });
            case 'camera_disabled':
                return $_('settings.frigate.full_visit_reason_camera_disabled', { default: 'A selected camera is disabled in Frigate. Enable it before using full clips.' });
            case 'camera_not_found':
                return $_('settings.frigate.full_visit_reason_camera_not_found', { default: 'A selected camera is no longer present in Frigate. Sync the camera list and review your selection.' });
            case 'partial_camera_coverage':
                return $_('settings.frigate.full_visit_reason_partial_camera_coverage', { default: 'Only some selected cameras have continuous recording coverage. Full-visit clips stay unavailable until every selected camera is covered.' });
            case 'camera_configuration_incomplete':
                return $_('settings.frigate.full_visit_reason_camera_configuration_incomplete', { default: 'The selected cameras have more than one recording configuration issue. Review each camera below.' });
            case 'retention_unknown':
                return $_('settings.frigate.full_visit_reason_retention_unknown', { default: 'Continuous recording retention could not be determined. Validate the Frigate recording config before enabling full clips.' });
            default:
                return $_('settings.frigate.full_visit_reason_unknown', { default: 'Capability could not be confirmed.' });
        }
    }

    function getRecordingCameraIssue(reason: string): string {
        switch (reason) {
            case 'camera_disabled':
                return $_('settings.frigate.full_visit_issue_camera_disabled', { default: 'camera disabled' });
            case 'camera_not_found':
                return $_('settings.frigate.full_visit_issue_camera_not_found', { default: 'not found in Frigate' });
            case 'recordings_disabled':
                return $_('settings.frigate.full_visit_issue_recordings_disabled', { default: 'recording disabled' });
            case 'record_stream_missing':
                return $_('settings.frigate.full_visit_issue_record_stream_missing', { default: 'record stream missing' });
            case 'continuous_retention_disabled':
                return $_('settings.frigate.full_visit_issue_continuous_retention_disabled', { default: 'continuous retention off' });
            case 'retention_unknown':
                return $_('settings.frigate.full_visit_issue_retention_unknown', { default: 'retention unknown' });
            default:
                return $_('settings.frigate.full_visit_issue_unknown', { default: 'configuration needs attention' });
        }
    }

    let canToggleRecordingClips = $derived(
        recordingClipEnabled || (clipsEnabled && !!recordingClipCapability?.supported)
    );

    function toggleRecordingClips(next?: boolean): void {
        const target = next ?? !recordingClipEnabled;
        if (recordingClipEnabled && !target) {
            recordingClipEnabled = false;
            return;
        }
        if (!clipsEnabled || !recordingClipCapability?.supported) return;
        recordingClipEnabled = target;
    }

    function startPreview(camera: string) {
        if (!frigateUrl) {
            previewError = $_('settings.cameras.preview_missing_url', { default: 'Set a Frigate URL to preview.' });
            return;
        }
        previewCamera = camera;
        previewVisible = true;
        previewLoading = true;
        previewError = null;
        previewTimestamp = Date.now();
        if (!previewTimer) {
            previewTimer = setInterval(() => {
                previewTimestamp = Date.now();
            }, 2000);
        }
    }

    function stopPreview(camera: string) {
        if (previewCamera !== camera) return;
        previewVisible = false;
        previewCamera = null;
        previewLoading = false;
        previewError = null;
        if (previewBlobUrl) {
            URL.revokeObjectURL(previewBlobUrl);
            previewBlobUrl = null;
        }
        if (previewTimer) {
            clearInterval(previewTimer);
            previewTimer = null;
        }
    }

    function togglePreview(camera: string) {
        if (previewVisible && previewCamera === camera) {
            stopPreview(camera);
            return;
        }
        startPreview(camera);
    }

    async function fetchPreview(camera: string) {
        if (!frigateUrl || !previewVisible) return;
        const token = authStore.token;
        previewLoading = true;
        previewError = null;
        try {
            const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
            const resp = await fetch(`${appApiPath(`/frigate/camera/${encodeURIComponent(camera)}/latest.jpg`)}?cache=${previewTimestamp}`, {
                headers
            });
            if (!resp.ok) {
                previewError = $_('settings.cameras.preview_failed', { default: 'Preview unavailable.' });
                previewLoading = false;
                return;
            }
            const blob = await resp.blob();
            if (previewBlobUrl) {
                URL.revokeObjectURL(previewBlobUrl);
            }
            previewBlobUrl = URL.createObjectURL(blob);
        } catch {
            previewError = $_('settings.cameras.preview_failed', { default: 'Preview unavailable.' });
        } finally {
            previewLoading = false;
        }
    }

    $effect(() => {
        if (!previewVisible || !previewCamera) return;
        fetchPreview(previewCamera);
    });

    onDestroy(() => {
        if (previewTimer) clearInterval(previewTimer);
        if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    });
</script>

<div class="space-y-8">

    {#snippet cameraPreview(camera: string)}
        <div class="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/95 shadow-lg shadow-slate-900/10 dark:border-slate-700/60 dark:bg-slate-900/95 dark:shadow-black/30">
            <div class="flex items-center justify-between gap-2 px-4 py-2">
                <span class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.cameras.preview_label', { default: 'Camera preview for {camera}', values: { camera } })}</span>
                <div class="flex items-center gap-2">
                    <span class="text-xs font-semibold text-brand-700 dark:text-brand-300">{$_('settings.cameras.preview_live', { default: 'LIVE' })}</span>
                    <button
                        type="button"
                        class="focus-ring flex h-11 w-11 items-center justify-center rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                        aria-label={$_('settings.cameras.preview_close')}
                        onclick={() => stopPreview(camera)}
                    >
                        <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                        </svg>
                    </button>
                </div>
            </div>
            <div class="bg-slate-100 dark:bg-slate-800/60">
                <div class="relative aspect-video w-full">
                    {#if previewBlobUrl}
                        <img class="absolute inset-0 h-full w-full object-contain" alt={$_('settings.cameras.preview_label', { default: 'Camera preview for {camera}', values: { camera } })} src={previewBlobUrl} />
                    {/if}
                    {#if previewLoading}
                        <div role="status" class="absolute inset-0 flex items-center justify-center bg-white/70 text-xs font-semibold text-slate-600 dark:text-slate-400 dark:bg-slate-900/70">
                            {$_('settings.cameras.preview_loading', { default: 'Loading preview…' })}
                        </div>
                    {/if}
                    {#if previewError}
                        <div role="alert" class="absolute inset-0 flex items-center justify-center bg-white/80 px-3 text-center text-xs font-semibold text-rose-700 dark:text-rose-300 dark:bg-slate-900/80">
                            {previewError}
                        </div>
                    {/if}
                </div>
            </div>
        </div>
    {/snippet}

    {#if showMain}
    <SettingsCard id="settings-group-frigate" title={$_('settings.frigate.title')}>
        <SettingsRow
            labelId="setting-frigate-url"
            label={$_('settings.frigate.url')}
            layout="stacked"
        >
            <SettingsInput
                id="frigate-url"
                field="frigate_url"
                type="url"
                value={frigateUrl}
                placeholder={$_('settings.frigate.url_placeholder')}
                ariaLabel={$_('settings.frigate.url')}
                oninput={(v) => (frigateUrl = v)}
            />
        </SettingsRow>
    </SettingsCard>
    {/if}

    {#if showMore}
    <!-- The rest of Frigate, under the section's More options: what it sends, where its pages are,
         which frame is identified and the clips kept. -->
    <SettingsCard id="settings-group-frigate-more" title={$_('settings.frigate.more_title', { default: 'Frigate details' })} nested>

        <SettingsRow
            labelId="setting-frigate-ingest-labels"
            label={$_('settings.frigate.ingest_labels', { default: 'Frigate labels to act on' })}
            description={$_('settings.frigate.ingest_labels_desc', { default: 'Comma-separated. Add the labels your Frigate model uses for birds (e.g. bird, duck, goose); everything listed flows through the bird identification pipeline.' })}
            layout="stacked"
        >
            <SettingsInput
                id="frigate-ingest-labels"
                field="frigate_ingest_labels"
                type="text"
                value={frigateIngestLabels}
                placeholder="bird"
                ariaLabel={$_('settings.frigate.ingest_labels', { default: 'Frigate labels to act on' })}
                oninput={(v) => (frigateIngestLabels = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-frigate-external-url"
            label={$_('settings.frigate.external_url')}
            description={$_('settings.frigate.external_url_desc')}
            layout="stacked"
        >
            <SettingsInput
                id="frigate-external-url"
                field="frigate_external_url"
                type="url"
                value={frigateExternalUrl}
                placeholder={$_('settings.frigate.external_url_placeholder')}
                ariaLabel={$_('settings.frigate.external_url')}
                oninput={(v) => (frigateExternalUrl = v)}
            />
        </SettingsRow>


        <ClassificationImageSourceSetting bind:value={classificationImageSource} bind:delay={recordingFrameDelaySeconds} />


        <SettingsRow
            labelId="setting-clips-enabled"
            label={$_('settings.frigate.fetch_clips')}
            description={$_('settings.frigate.fetch_clips_desc')}
        >
            <SettingsToggle
                checked={clipsEnabled}
                labelledBy="setting-clips-enabled"
                srLabel={$_('settings.frigate.fetch_clips')}
                onchange={(v) => (clipsEnabled = v)}
            />
        </SettingsRow>

        <AdvancedSection
            id="connection-full-visit"
            title={$_('settings.connection.full_visit_advanced_title', { default: 'Full clips' })}
        >
        <SettingsRow
            labelId="setting-recording-clips"
            label={$_('settings.frigate.full_visit_clips', { default: 'Full clips' })}
            description={$_('settings.frigate.full_visit_clips_desc', { default: 'Serve a longer clip from Frigate’s recordings around each capture.' })}
        >
            <SettingsToggle
                checked={recordingClipEnabled}
                labelledBy="setting-recording-clips"
                srLabel={$_('settings.frigate.full_visit_clips', { default: 'Full clips' })}
                disabled={!canToggleRecordingClips}
                onchange={(v) => toggleRecordingClips(v)}
            />
        </SettingsRow>

        <div
            data-full-visit-capability
            role="status"
            aria-live="polite"
            class="flex gap-3 border-t border-slate-200 px-1 pt-4 text-xs dark:border-slate-700/70"
        >
            <span
                class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full
                       {recordingClipCapability?.supported
                           ? 'bg-success-500/10 text-success-700 dark:text-success-300'
                           : recordingClipCapabilityLoading || !recordingClipCapability
                             ? 'bg-slate-500/10 text-slate-600 dark:text-slate-400'
                             : 'bg-attention-500/10 text-attention-700 dark:text-attention-300'}"
                aria-hidden="true"
            >
                {#if recordingClipCapability?.supported}
                    <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6" /></svg>
                {:else if recordingClipCapabilityLoading}
                    <svg class="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.6" /></svg>
                {:else}
                    <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.3 3.7 2.4 17.3A2 2 0 0 0 4.1 20h15.8a2 2 0 0 0 1.7-2.7L13.7 3.7a2 2 0 0 0-3.4 0Z" /></svg>
                {/if}
            </span>

            <div class="min-w-0 flex-1 space-y-1 text-slate-600 dark:text-slate-400">
                {#if recordingClipCapabilityLoading}
                    <p>{$_('settings.frigate.full_visit_loading', { default: 'Checking saved Frigate recording support...' })}</p>
                {:else if recordingClipCapability}
                    {#if recordingClipCapability.supported}
                        <p class="font-semibold text-slate-800 dark:text-slate-200">
                            {$_('settings.frigate.full_visit_supported', {
                                default: '{count, plural, one {Continuous coverage is ready for the selected camera.} other {Continuous coverage is ready for all # selected cameras.}}',
                                values: { count: recordingClipCapability.eligible_cameras.length }
                            })}
                        </p>
                    {:else}
                        <p class="font-semibold leading-relaxed text-attention-800 dark:text-attention-200">
                            {getRecordingCapabilityReason(recordingClipCapability.reason)}
                        </p>
                    {/if}

                    {#if Object.keys(recordingClipCapability.ineligible_cameras).length > 0}
                        <ul class="flex flex-wrap gap-x-3 gap-y-1 pt-1" aria-label={$_('settings.frigate.full_visit_attention_cameras', { default: 'Cameras needing attention' })}>
                            {#each Object.entries(recordingClipCapability.ineligible_cameras) as [camera, reason]}
                                <li>
                                    <span class="font-semibold text-slate-700 dark:text-slate-300">{camera}</span>
                                    <Separator />
                                    <span>{getRecordingCameraIssue(reason)}</span>
                                </li>
                            {/each}
                        </ul>
                    {/if}

                    {#if recordingClipCapability.supported && recordingClipCapability.retention_days !== null}
                        <p>
                            {$_('settings.frigate.full_visit_retention', {
                                default: 'Guaranteed continuous retention: {days, plural, one {# day} other {# days}}',
                                values: { days: recordingClipCapability.retention_days }
                            })}
                        </p>
                    {/if}
                {:else}
                    <p>{$_('settings.frigate.full_visit_unavailable', { default: 'Capability information is unavailable right now.' })}</p>
                {/if}
            </div>
        </div>

        {#if recordingClipEnabled}
                <div class="grid grid-cols-2 gap-3">
                    <SettingsRow
                        labelId="setting-recording-before"
                        label={$_('settings.frigate.full_visit_before', { default: 'Seconds before' })}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="recording-clip-before"
                            field="recording_clip_before_seconds"
                            type="number"
                            min={0}
                            max={3600}
                            value={recordingClipBeforeSeconds}
                            ariaLabel={$_('settings.frigate.full_visit_before', { default: 'Seconds before' })}
                            oninput={(v) => (recordingClipBeforeSeconds = Number(v) || 0)}
                        />
                    </SettingsRow>
                    <SettingsRow
                        labelId="setting-recording-after"
                        label={$_('settings.frigate.full_visit_after', { default: 'Seconds after' })}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="recording-clip-after"
                            field="recording_clip_after_seconds"
                            type="number"
                            min={0}
                            max={3600}
                            value={recordingClipAfterSeconds}
                            ariaLabel={$_('settings.frigate.full_visit_after', { default: 'Seconds after' })}
                            oninput={(v) => (recordingClipAfterSeconds = Number(v) || 0)}
                        />
                    </SettingsRow>
                </div>
        {/if}
        </AdvancedSection>
    </SettingsCard>
    {/if}

    {#if showMain}
    <SettingsCard
        id="settings-group-connection-mqtt-section"
        title={$_('settings.connection.mqtt_section', { default: 'MQTT broker' })}
    >
        <!-- Address and port are one setting: its name and help left, both fields right, side by side
             with matching labels, on the section's one control edge. -->
        <div class="settings-row space-y-3 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row data-mqtt-address>
            <div id="setting-mqtt-broker" class="min-w-0">
                <span class="block text-base font-semibold text-slate-900 dark:text-white">{$_('settings.connection.mqtt_where', { default: 'Address and port' })}</span>
                <span id="setting-mqtt-broker-desc" class="mt-1 block max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.connection.mqtt_title')}</span>
            </div>
            <!-- The port wraps under the address when enlarged text leaves no room beside it. -->
            <div class="flex min-w-0 flex-wrap gap-3">
                <label class="block min-w-0 flex-1 basis-40 space-y-1.5">
                    <span class="block text-sm text-slate-600 dark:text-slate-400">{$_('settings.connection.mqtt_host', { default: 'Address' })}</span>
                    <SettingsInput
                        id="mqtt-server"
                        field="mqtt_server"
                        type="text"
                        value={mqttServer}
                        placeholder={$_('settings.frigate.mqtt_broker_placeholder')}
                        ariaLabel={`${$_('settings.frigate.mqtt_broker')}: ${$_('settings.connection.mqtt_host', { default: 'Address' })}`}
                        describedBy="setting-mqtt-broker-desc"
                        oninput={(v) => (mqttServer = v)}
                    />
                </label>
                <label class="block w-24 shrink-0 space-y-1.5">
                    <span class="block text-sm text-slate-600 dark:text-slate-400">{$_('settings.frigate.mqtt_port')}</span>
                    <SettingsInput
                        id="mqtt-port"
                        field="mqtt_port"
                        type="number"
                        value={mqttPort}
                        ariaLabel={$_('settings.frigate.mqtt_port')}
                        oninput={(v) => (mqttPort = Number(v) || 0)}
                    />
                </label>
            </div>
        </div>

        <SettingsRow
            labelId="setting-mqtt-auth"
            label={$_('settings.frigate.mqtt_auth')}
        >
            <SettingsToggle
                checked={mqttAuth}
                labelledBy="setting-mqtt-auth"
                srLabel={$_('settings.frigate.mqtt_auth')}
                onchange={(v) => (mqttAuth = v)}
            />
        </SettingsRow>

        {#if mqttAuth}
            <div class="settings-stack">
                <SettingsRow
                    labelId="setting-mqtt-username"
                    label={$_('settings.frigate.mqtt_user')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="mqtt-username"
                        field="mqtt_username"
                        type="text"
                        value={mqttUsername}
                        ariaLabel={$_('settings.frigate.mqtt_user')}
                        oninput={(v) => (mqttUsername = v)}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-mqtt-password"
                    label={$_('settings.frigate.mqtt_pass')}
                    layout="stacked"
                >
                    <SecretInput
                        id="mqtt-password"
                        value={mqttPassword}
                        saved={mqttPasswordSaved}
                        ariaLabel={$_('settings.frigate.mqtt_pass')}
                        oninput={(v) => (mqttPassword = v)}
                    />
                </SettingsRow>
            </div>
        {/if}

        <!-- After both connections, since it tests both: the Frigate API and an MQTT publish. The one
             primary action on the tab. -->
        <div>
            <button
                type="button"
                onclick={runConnectionDiagnostic}
                disabled={fcRunning}
                data-settings-test="connection"
                class="btn btn-primary min-h-11 px-4 whitespace-normal"
            >
                {fcRunning ? $_('common.testing') : $_('settings.frigate.test_connection_both', { default: 'Test Frigate and MQTT' })}
            </button>
        </div>
    </SettingsCard>

    <SettingsCard
        id="settings-group-cameras"
        title={$_('settings.cameras.title', { default: 'Cameras to watch' })}
        description={betaGardenAnimals
            ? $_('settings.cameras.watch_desc_garden', { default: 'Choose what each Frigate camera is watched for: birds, Garden animals or both.' })
            : $_('settings.cameras.watch_desc', { default: 'Choose which Frigate cameras are watched for birds.' })}
    >
        <!-- The page scrolls; a second scroller inside the card hid the first camera under the
             card header and cut off the nest window below the list. -->
        <div
            id="settings-camera-list"
            class="focus-ring settings-stack focus:outline-hidden"
            role="group"
            aria-label={$_('settings.cameras.title', { default: 'Cameras to watch' })}
            tabindex="-1"
            data-camera-list
        >
            <!-- One header row: what the list is and whom it watches on the left, its two actions on the right. -->
            <div class="flex flex-wrap items-start justify-between gap-3" data-camera-list-header>
                <p class="min-w-0 flex-1 basis-56 text-sm text-slate-600 dark:text-slate-400" data-bird-scope>
                    {$_('settings.cameras.sync_help', { default: 'The list comes from Frigate. Sync again after adding a camera there.' })}
                    {#if watchesEveryCameraForBirds(watchSettings)}
                        {$_('settings.cameras.every_camera_on', { default: 'Every Frigate camera is watched for birds, including cameras added to Frigate later.' })}
                    {:else}
                        <span id="camera-bird-scope-chosen">{$_('settings.cameras.every_camera_off', { default: 'Only the cameras chosen here are watched for birds. A camera added to Frigate later is not watched until you choose it.' })}</span>
                    {/if}
                </p>
                <div class="flex max-w-full flex-wrap gap-2">
                    <button
                        type="button"
                        onclick={loadCameras}
                        disabled={camerasLoading}
                        class="btn btn-secondary min-h-11 max-w-full px-4 whitespace-normal"
                    >
                        {camerasLoading ? $_('settings.cameras.syncing') : $_('settings.frigate.sync_cameras')}
                    </button>
                    {#if !watchesEveryCameraForBirds(watchSettings)}
                        <button
                            type="button"
                            class="btn btn-secondary min-h-11 max-w-full px-4 whitespace-normal"
                            aria-describedby="camera-bird-scope-chosen"
                            onclick={() => commitWatch(watchEveryCameraForBirds(watchSettings))}
                        >
                            {$_('settings.cameras.watch_every_camera', { default: 'Watch every camera for birds' })}
                        </button>
                    {/if}
                </div>
            </div>
            {#if !betaGardenAnimals}
                <p class="text-sm text-slate-600 dark:text-slate-400" data-camera-garden-hint>{$_('settings.cameras.garden_beta_hint', { default: 'To watch for Garden animals as well, turn on Garden animals in Settings → Identifying birds.' })}</p>
            {/if}
            {#if frigateCameras === null}
                <!-- One neutral notice: the list is being read, or could not be, and saved cameras are shown. -->
                <p class="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300" role="status" data-camera-list-state>
                    <svg class="mt-0.5 h-4 w-4 shrink-0 text-slate-600 dark:text-slate-400" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="10" cy="10" r="7.5" /><path d="M10 9v4.5M10 6.5h.01" /></svg>
                    <span class="min-w-0">
                        {frigateCamerasFailed
                            ? $_('settings.cameras.list_unread', { default: 'The camera list could not be read from Frigate. Saved cameras are shown; choose Sync cameras to try again.' })
                            : $_('settings.cameras.list_loading', { default: 'Reading the camera list from Frigate…' })}
                    </span>
                </p>
            {/if}
            {#if watchRows.length > 0 && !frigateUrl}
                <p id="camera-preview-needs-url" class="text-xs text-slate-600 dark:text-slate-300">{$_('settings.cameras.preview_needs_url', { default: 'Enter the Frigate URL above to preview a camera.' })}</p>
            {/if}
            {#if watchRows.length === 0}
                {#if frigateCameras !== null}
                    <div>
                        <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.cameras.none_found')}</p>
                        <p class="mt-1 text-xs text-slate-600 dark:text-slate-400">{$_('settings.cameras.none_found_help', { default: 'Frigate reported no cameras. Check the Frigate URL above, then choose Sync cameras.' })}</p>
                    </div>
                {/if}
            {:else}
                <ul class="divide-y divide-line-soft" aria-label={$_('settings.cameras.title', { default: 'Cameras to watch' })}>
                    {#each watchRows as row (row.camera)}
                        <CameraWatchRow
                            {row}
                            gardenEnabled={betaGardenAnimals}
                            previewOpen={previewVisible && previewCamera === row.camera}
                            previewUnavailableId={frigateUrl ? undefined : 'camera-preview-needs-url'}
                            onmode={(mode) => chooseWatchMode(row.camera, mode)}
                            onrole={(role) => commitWatch(setCameraRole(watchSettings, row.camera, role))}
                            onmotion={(collect) => commitWatch(setGardenMotion(watchSettings, row.camera, collect))}
                            onpreview={() => togglePreview(row.camera)}
                        >
                            {#snippet preview()}
                                {@render cameraPreview(row.camera)}
                            {/snippet}
                        </CameraWatchRow>
                    {/each}
                </ul>
            {/if}
        {#if Object.values(cameraRoles).includes('nest')}
                <!-- A settings row like the rest; the field may narrow so enlarged text never pushes it out. -->
                <div class="settings-row space-y-3 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row data-nest-dedupe>
                    <div class="min-w-0">
                        <p class="text-base font-semibold text-slate-900 dark:text-white">{$_('settings.cameras.nest_dedupe_label', { default: 'Nest dedupe window' })}</p>
                        <p class="mt-1 max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.cameras.nest_dedupe_help', { default: 'Counts repeat visits by the same species to a nest camera as one per N minutes.' })}</p>
                    </div>
                    <div class="flex min-w-0 items-center gap-2">
                        <input
                            type="number"
                            min={1}
                            max={720}
                            bind:value={nestDedupeMinutes}
                            class="input-base w-24 min-w-0 text-right tabular-nums"
                            aria-label={$_('settings.cameras.nest_dedupe_label', { default: 'Nest dedupe window' })}
                        />
                        <span class="shrink-0 text-sm text-slate-600 dark:text-slate-400">{$_('settings.cameras.nest_dedupe_unit', { default: 'min' })}</span>
                    </div>
                </div>
            {/if}
        </div>
    </SettingsCard>
    {/if}

</div>

{#if fcTestOpen}
    <DiagnosticDialog
        title={$_('settings.frigate.test_title', { default: 'Frigate & MQTT connection test' })}
        subtitle={$_('settings.frigate.test_subtitle', { default: 'Checks that the Frigate API answers and that the MQTT broker accepts a publish.' })}
        stages={fcStages}
        busy={fcRunning}
        result={fcResult}
        runId={fcRunId}
        retryLabel={$_('settings.frigate.test_again', { default: 'Test again' })}
        onClose={() => (fcTestOpen = false)}
        onRetry={runConnectionDiagnostic}
    />
{/if}

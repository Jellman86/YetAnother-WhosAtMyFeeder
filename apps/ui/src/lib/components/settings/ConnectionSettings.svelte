<script lang="ts">
    import { onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import type { VersionInfo } from '../../api';
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

    let {
        frigateUrl = $bindable(''),
        mqttServer = $bindable(''),
        mqttPort = $bindable(1883),
        mqttAuth = $bindable(false),
        mqttUsername = $bindable(''),
        mqttPassword = $bindable(''),
        mqttPasswordSaved = $bindable(false),
        clipsEnabled = $bindable(true),
        recordingClipEnabled = $bindable(false),
        recordingClipBeforeSeconds = $bindable(30),
        recordingClipAfterSeconds = $bindable(90),
        selectedCameras = $bindable<string[]>([]),
        cameraRoles = $bindable<Record<string, 'feeder' | 'nest'>>({}),
        nestDedupeMinutes = $bindable(30),
        telemetryEnabled = $bindable(false),
        telemetryHealthEnabled = $bindable(false),
        availableCameras = $bindable<string[]>([]),
        recordingClipCapability = null,
        recordingClipCapabilityLoading = false,
        camerasLoading,
        telemetryInstallationId,
        telemetryPlatform,
        telemetryPayloadPreview,
        versionInfo,
        loadCameras,
        toggleCamera
    }: {
        frigateUrl: string;
        mqttServer: string;
        mqttPort: number;
        mqttAuth: boolean;
        mqttUsername: string;
        mqttPassword: string;
        mqttPasswordSaved: boolean;
        clipsEnabled: boolean;
        recordingClipEnabled: boolean;
        recordingClipBeforeSeconds: number;
        recordingClipAfterSeconds: number;
        selectedCameras: string[];
        cameraRoles: Record<string, 'feeder' | 'nest'>;
        nestDedupeMinutes: number;
        telemetryEnabled: boolean;
        telemetryHealthEnabled: boolean;
        availableCameras: string[];
        recordingClipCapability: RecordingClipCapability | null;
        recordingClipCapabilityLoading: boolean;
        camerasLoading: boolean;
        telemetryInstallationId: string | undefined;
        telemetryPlatform: string | undefined;
        telemetryPayloadPreview: Record<string, unknown> | undefined;
        versionInfo: VersionInfo;
        loadCameras: () => Promise<void>;
        toggleCamera: (camera: string) => void;
    } = $props();

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
                    run: () => testMQTTPublish({
                        server: mqttServer.trim(),
                        port: mqttPort,
                        auth: mqttAuth,
                        username: mqttUsername.trim(),
                        password: mqttPassword
                    })
                }
            ],
            (stages) => (fcStages = stages)
        );
        fcRunning = false;
    }

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
                return $_('settings.frigate.full_visit_reason_camera_disabled', { default: 'A selected camera is disabled in Frigate. Enable it before using full-visit clips.' });
            case 'camera_not_found':
                return $_('settings.frigate.full_visit_reason_camera_not_found', { default: 'A selected camera is no longer present in Frigate. Sync the camera list and review your selection.' });
            case 'partial_camera_coverage':
                return $_('settings.frigate.full_visit_reason_partial_camera_coverage', { default: 'Only some selected cameras have continuous recording coverage. Full-visit clips stay unavailable until every selected camera is covered.' });
            case 'camera_configuration_incomplete':
                return $_('settings.frigate.full_visit_reason_camera_configuration_incomplete', { default: 'The selected cameras have more than one recording configuration issue. Review each camera below.' });
            case 'retention_unknown':
                return $_('settings.frigate.full_visit_reason_retention_unknown', { default: 'Continuous recording retention could not be determined. Validate the Frigate recording config before enabling full visits.' });
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

    function nestedValue(source: Record<string, unknown> | undefined, path: string): unknown {
        return path.split('.').reduce<unknown>((current, key) => {
            if (!current || typeof current !== 'object') return undefined;
            return (current as Record<string, unknown>)[key];
        }, source);
    }

    function formatTelemetryValue(value: unknown): string {
        if (typeof value === 'boolean') return value ? $_('common.yes', { default: 'Yes' }) : $_('common.no', { default: 'No' });
        if (value === null || value === undefined || value === '') return '...';
        return String(value);
    }

    const telemetryRuntimeRows = $derived([
        ['settings.telemetry.payload_model_runtime', 'runtime.model_runtime'],
        ['settings.telemetry.payload_provider_configured', 'runtime.inference_provider_configured'],
        ['settings.telemetry.payload_provider_active', 'runtime.inference_provider_active'],
        ['settings.telemetry.payload_backend_active', 'runtime.inference_backend_active'],
        ['settings.telemetry.payload_execution_mode', 'runtime.image_execution_mode'],
        ['settings.telemetry.payload_crop_tier', 'runtime.bird_crop_detector_tier'],
        ['settings.telemetry.payload_cuda_available', 'hardware.cuda_available'],
        ['settings.telemetry.payload_nvidia_gpu_detected', 'hardware.nvidia_gpu_detected'],
        ['settings.telemetry.payload_openvino_available', 'hardware.openvino_available'],
        ['settings.telemetry.payload_intel_gpu_available', 'hardware.intel_gpu_available'],
        ['settings.telemetry.payload_intel_npu_available', 'hardware.intel_npu_available'],
        ['settings.telemetry.payload_openvino_compile', 'hardware.openvino_gpu_compile_ok'],
        ['settings.telemetry.payload_openvino_device', 'hardware.openvino_gpu_compile_device'],
        ['settings.telemetry.payload_gpu_fallback', 'hardware.openvino_gpu_fallback_active'],
        ['settings.telemetry.payload_deployment_mode', 'deployment.mode'],
        ['settings.telemetry.payload_image_flavor', 'deployment.image_flavor'],
        ['settings.telemetry.payload_image_arch', 'deployment.image_arch']
    ]);

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

<div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch">
    {#snippet frigateIcon()}
        <img src={FRIGATE_LOGO_URL} alt="Frigate Logo" class="w-6 h-6 object-contain" />
    {/snippet}
    {#snippet camerasIcon()}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z" /><circle cx="12" cy="13" r="3" /></svg>
    {/snippet}

    <SettingsCard title={$_('settings.frigate.title')} iconSnippet={frigateIcon}>
        <SettingsRow
            labelId="setting-frigate-url"
            label={$_('settings.frigate.url')}
            layout="stacked"
        >
            <SettingsInput
                id="frigate-url"
                type="url"
                value={frigateUrl}
                placeholder={$_('settings.frigate.url_placeholder')}
                ariaLabel={$_('settings.frigate.url')}
                oninput={(v) => (frigateUrl = v)}
            />
        </SettingsRow>

        <div class="grid grid-cols-2 gap-3">
            <button
                type="button"
                onclick={runConnectionDiagnostic}
                disabled={fcRunning}
                aria-label={$_('settings.frigate.test_connection')}
                class="px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-brand-500 hover:bg-brand-600 text-white transition-all shadow-lg shadow-brand-500/20 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-400 dark:focus:ring-offset-slate-900 disabled:opacity-50"
            >
                {fcRunning ? $_('common.testing') : $_('settings.frigate.test_connection')}
            </button>
            <button
                type="button"
                onclick={loadCameras}
                disabled={camerasLoading}
                aria-label={$_('settings.frigate.sync_cameras')}
                class="px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-400 dark:focus:ring-offset-slate-900 disabled:opacity-50"
            >
                {camerasLoading ? $_('settings.cameras.syncing') : $_('settings.frigate.sync_cameras')}
            </button>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3">
            <SettingsRow
                labelId="setting-mqtt-broker"
                label={$_('settings.frigate.mqtt_broker')}
                description={$_('settings.connection.mqtt_title')}
                layout="stacked"
            >
                <SettingsInput
                    id="mqtt-server"
                    type="text"
                    value={mqttServer}
                    placeholder={$_('settings.frigate.mqtt_broker_placeholder')}
                    ariaLabel={$_('settings.frigate.mqtt_broker')}
                    oninput={(v) => (mqttServer = v)}
                />
            </SettingsRow>
            <SettingsRow
                labelId="setting-mqtt-port"
                label={$_('settings.frigate.mqtt_port')}
                layout="stacked"
            >
                <SettingsInput
                    id="mqtt-port"
                    type="number"
                    value={mqttPort}
                    ariaLabel={$_('settings.frigate.mqtt_port')}
                    oninput={(v) => (mqttPort = Number(v) || 0)}
                />
            </SettingsRow>
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
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 animate-in fade-in zoom-in-95">
                <SettingsRow
                    labelId="setting-mqtt-username"
                    label={$_('settings.frigate.mqtt_user')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="mqtt-username"
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
            title={$_('settings.connection.full_visit_advanced_title', { default: 'Full-visit clips (from recordings)' })}
        >
        <SettingsRow
            labelId="setting-recording-clips"
            label={$_('settings.frigate.full_visit_clips', { default: 'Full-visit clips' })}
            description={$_('settings.frigate.full_visit_clips_desc', { default: 'Serve a longer clip window from Frigate recordings around each detection.' })}
        >
            <SettingsToggle
                checked={recordingClipEnabled}
                labelledBy="setting-recording-clips"
                srLabel={$_('settings.frigate.full_visit_clips', { default: 'Full-visit clips' })}
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
                           ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                           : recordingClipCapabilityLoading || !recordingClipCapability
                             ? 'bg-slate-500/10 text-slate-500 dark:text-slate-400'
                             : 'bg-amber-500/10 text-amber-700 dark:text-amber-300'}"
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
                                default: 'Continuous coverage is ready for all {count} selected camera(s).',
                                values: { count: recordingClipCapability.eligible_cameras.length }
                            })}
                        </p>
                    {:else}
                        <p class="font-semibold leading-relaxed text-amber-800 dark:text-amber-200">
                            {getRecordingCapabilityReason(recordingClipCapability.reason)}
                        </p>
                    {/if}

                    {#if Object.keys(recordingClipCapability.ineligible_cameras).length > 0}
                        <ul class="flex flex-wrap gap-x-3 gap-y-1 pt-1" aria-label={$_('settings.frigate.full_visit_attention_cameras', { default: 'Cameras needing attention' })}>
                            {#each Object.entries(recordingClipCapability.ineligible_cameras) as [camera, reason]}
                                <li>
                                    <span class="font-semibold text-slate-700 dark:text-slate-300">{camera}</span>
                                    <span aria-hidden="true"> · </span>
                                    <span>{getRecordingCameraIssue(reason)}</span>
                                </li>
                            {/each}
                        </ul>
                    {/if}

                    {#if recordingClipCapability.supported && recordingClipCapability.retention_days !== null}
                        <p>
                            {$_('settings.frigate.full_visit_retention', {
                                default: 'Guaranteed continuous retention: {days} day(s)',
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

    <SettingsCard accent iconSnippet={camerasIcon} title={$_('settings.cameras.title')}>
        <div class="space-y-3 max-h-[36rem] overflow-y-auto pr-2 custom-scrollbar">
            {#if availableCameras.length === 0}
                <div class="p-8 text-center bg-slate-50 dark:bg-slate-900/30 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700">
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-widest">{$_('settings.cameras.none_found')}</p>
                </div>
            {:else}
                <div class="grid grid-cols-1 gap-2">
                    {#each availableCameras as camera}
                        {@const selected = selectedCameras.includes(camera)}
                        {@const role = cameraRoles[camera] === 'nest' ? 'nest' : 'feeder'}
                        <div
                            class="relative flex flex-col gap-3 p-4 rounded-2xl border-2 transition-all group
                                   {selected
                                       ? 'border-brand-500 bg-brand-500/5 text-brand-700 dark:text-brand-400'
                                       : 'border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/30 text-slate-500 hover:border-brand-500/30'}"
                        >
                            <div class="flex items-center gap-2">
                                <button
                                    type="button"
                                    aria-pressed={selected}
                                    aria-label={selected ? $_('settings.cameras.deselect', { default: 'Deselect {camera}', values: { camera } }) : $_('settings.cameras.select', { default: 'Select {camera}', values: { camera } })}
                                    class="flex min-h-11 min-w-0 flex-1 items-center justify-between gap-3 rounded-xl px-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
                                    onclick={() => toggleCamera(camera)}
                                >
                                    <span class="min-w-0 truncate text-sm font-bold">{camera}</span>
                                    <span class="w-6 h-6 shrink-0 rounded-full border-2 flex items-center justify-center transition-all {selected ? 'bg-brand-500 border-brand-500 scale-110' : 'border-slate-300 dark:border-slate-600 group-hover:border-brand-500/50'}" aria-hidden="true">
                                    {#if selected}<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" /></svg>{/if}
                                    </span>
                                </button>
                                <button
                                    type="button"
                                    class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-white hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-300"
                                    aria-label={$_('settings.cameras.preview', { default: 'Preview {camera}', values: { camera } })}
                                    aria-expanded={previewVisible && previewCamera === camera}
                                    disabled={!frigateUrl}
                                    onclick={() => togglePreview(camera)}
                                >
                                    <svg class={`w-4 h-4 transition-transform ${previewVisible && previewCamera === camera ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                                    </svg>
                                </button>
                            </div>
                            {#if selected}
                                <div class="flex items-center justify-between gap-2 px-1">
                                    <span class="text-xs font-black uppercase tracking-widest text-slate-400">{$_('settings.cameras.role_label', { default: 'Role' })}</span>
                                    <div class="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-0.5">
                                        <button
                                            type="button"
                                            onclick={() => {
                                                const next = { ...cameraRoles };
                                                delete next[camera];
                                                cameraRoles = next;
                                            }}
                                            class="min-h-11 px-3 py-1 rounded-md text-xs font-black uppercase tracking-widest transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {role === 'feeder' ? 'bg-brand-500 text-white' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'}"
                                            aria-pressed={role === 'feeder'}
                                            title={$_('settings.cameras.role_feeder_help', { default: 'Feeder cam — every Frigate event is treated as a fresh visit (default).' })}
                                        >
                                            {$_('settings.cameras.role_feeder', { default: 'Feeder' })}
                                        </button>
                                        <button
                                            type="button"
                                            onclick={() => {
                                                cameraRoles = { ...cameraRoles, [camera]: 'nest' };
                                            }}
                                            class="min-h-11 px-3 py-1 rounded-md text-xs font-black uppercase tracking-widest transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {role === 'nest' ? 'bg-brand-500 text-white' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'}"
                                            aria-pressed={role === 'nest'}
                                            title={$_('settings.cameras.role_nest_help', { default: 'Nest box cam — collapses repeat detections of the same species into one per dedupe window so a continuously-present nesting bird does not flood the feed.' })}
                                        >
                                            {$_('settings.cameras.role_nest', { default: 'Nest' })}
                                        </button>
                                    </div>
                                </div>
                            {/if}
                            {#if previewVisible && previewCamera === camera}
                                <div class="rounded-2xl border border-slate-200/80 dark:border-slate-700/60 bg-white/95 dark:bg-slate-900/95 overflow-hidden shadow-lg shadow-slate-900/10 dark:shadow-black/30">
                                    <div class="px-4 py-2 flex items-center justify-between gap-2">
                                        <span class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('settings.cameras.preview_label', { default: 'Camera preview for {camera}', values: { camera } })}</span>
                                        <div class="flex items-center gap-2">
                                            <span class="text-xs font-semibold text-accent-500">{$_('settings.cameras.preview_live', { default: 'LIVE' })}</span>
                                            <button
                                                type="button"
                                                class="flex h-11 w-11 items-center justify-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                                                aria-label={$_('settings.cameras.preview_close')}
                                                onclick={() => stopPreview(camera)}
                                            >
                                                <svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                                                </svg>
                                            </button>
                                        </div>
                                    </div>
                                    <div class="bg-slate-100 dark:bg-slate-800/60">
                                        <div class="relative w-full aspect-video">
                                            {#if previewBlobUrl}
                                                <img class="absolute inset-0 w-full h-full object-contain" alt={$_('settings.cameras.preview_label', { default: 'Camera preview for {camera}', values: { camera } })} src={previewBlobUrl} />
                                            {/if}
                                            {#if previewLoading}
                                                <div role="status" class="absolute inset-0 flex items-center justify-center bg-white/70 dark:bg-slate-900/70 text-xs font-semibold text-slate-500">
                                                    {$_('settings.cameras.preview_loading', { default: 'Loading preview…' })}
                                                </div>
                                            {/if}
                                            {#if previewError}
                                                <div role="alert" class="absolute inset-0 flex items-center justify-center bg-white/80 dark:bg-slate-900/80 text-xs font-semibold text-rose-500 text-center px-3">
                                                    {previewError}
                                                </div>
                                            {/if}
                                        </div>
                                    </div>
                                </div>
                            {/if}
                        </div>
                    {/each}
                </div>
            {/if}
            {#if Object.values(cameraRoles).includes('nest')}
                <div class="rounded-xl border border-slate-200/70 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-900/40 p-3 flex items-center justify-between gap-3">
                    <div class="min-w-0">
                        <p class="text-xs font-black text-slate-700 dark:text-slate-200">{$_('settings.cameras.nest_dedupe_label', { default: 'Nest dedupe window' })}</p>
                        <p class="text-xs text-slate-500 font-bold mt-0.5">{$_('settings.cameras.nest_dedupe_help', { default: 'Collapses repeat detections of the same species on a nest cam to one per N minutes.' })}</p>
                    </div>
                    <div class="flex items-center gap-1 shrink-0">
                        <input
                            type="number"
                            min={1}
                            max={720}
                            bind:value={nestDedupeMinutes}
                            class="w-20 h-11 px-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm font-mono font-bold text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-brand-500 outline-none text-right"
                            aria-label={$_('settings.cameras.nest_dedupe_label', { default: 'Nest dedupe window' })}
                        />
                        <span class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('settings.cameras.nest_dedupe_unit', { default: 'min' })}</span>
                    </div>
                </div>
            {/if}
        </div>
    </SettingsCard>

    <div class="md:col-span-2">
        <AdvancedSection
            id="connection-telemetry"
            title={$_('settings.telemetry.title')}
            description={$_('settings.telemetry.desc')}
        >
            <SettingsRow
                labelId="setting-telemetry"
                label={$_('settings.telemetry.title')}
                description={$_('settings.telemetry.appreciation_tooltip')}
            >
                <SettingsToggle
                    checked={telemetryEnabled}
                    labelledBy="setting-telemetry"
                    srLabel={$_('settings.telemetry.title')}
                    onchange={(v) => (telemetryEnabled = v)}
                />
            </SettingsRow>

            <SettingsRow
                labelId="setting-telemetry-health"
                label={$_('settings.telemetry.health_title')}
                description={$_('settings.telemetry.health_desc')}
            >
                <SettingsToggle
                    checked={telemetryHealthEnabled}
                    labelledBy="setting-telemetry-health"
                    srLabel={$_('settings.telemetry.health_title')}
                    onchange={(v) => (telemetryHealthEnabled = v)}
                />
            </SettingsRow>

            {#if telemetryEnabled || telemetryHealthEnabled}
                <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 animate-in fade-in slide-in-from-top-2">
                    <p class="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">{$_('settings.telemetry.transparency')}</p>
                    <div class="space-y-2 text-xs font-mono text-slate-600 dark:text-slate-400">
                        <div class="flex justify-between"><span>{$_('settings.telemetry.install_id')}:</span><span class="text-slate-900 dark:text-white select-all">{telemetryInstallationId || '...'}</span></div>
                        <div class="flex justify-between"><span>{$_('settings.telemetry.version')}:</span><span>{versionInfo.version}</span></div>
                        <div class="flex justify-between"><span>{$_('settings.telemetry.platform')}:</span><span>{telemetryPlatform || '...'}</span></div>
                        {#if telemetryEnabled}
                            <div class="flex justify-between"><span>{$_('settings.telemetry.includes')}:</span><span>{$_('settings.telemetry.includes_value')}</span></div>
                        {/if}
                        {#if telemetryHealthEnabled}
                            <div class="flex justify-between"><span>{$_('settings.telemetry.health_includes')}:</span><span>{$_('settings.telemetry.health_includes_value')}</span></div>
                        {/if}
                        <div class="flex justify-between"><span>{$_('settings.telemetry.geography')}:</span><span>{$_('settings.telemetry.geography_value')}</span></div>
                        <div class="flex justify-between"><span>{$_('settings.telemetry.frequency')}:</span><span>{$_('settings.telemetry.frequency_value')}</span></div>
                    </div>
                    {#if telemetryEnabled}
                        <div class="mt-4 pt-4 border-t border-slate-200/70 dark:border-slate-700/70">
                            <p class="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">{$_('settings.telemetry.runtime_snapshot')}</p>
                            <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-xs font-mono text-slate-600 dark:text-slate-400">
                                {#each telemetryRuntimeRows as [labelKey, valuePath]}
                                    <div class="flex justify-between gap-3 min-w-0">
                                        <span class="truncate">{$_(labelKey)}:</span>
                                        <span class="text-right text-slate-900 dark:text-white break-all">{formatTelemetryValue(nestedValue(telemetryPayloadPreview, valuePath))}</span>
                                    </div>
                                {/each}
                            </div>
                        </div>
                    {/if}
                    <p class="text-xs text-slate-400 mt-3 italic">{$_('settings.telemetry.privacy_notice')}</p>
                    <a
                        href="https://yawamf-telemetry.ya-wamf.workers.dev/dashboard"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="inline-flex items-center gap-1 mt-3 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline"
                    >
                        {$_('settings.telemetry.dashboard_link', { default: 'View the public telemetry dashboard' })} →
                    </a>
                </div>
            {/if}
        </AdvancedSection>
    </div>
</div>

{#if fcTestOpen}
    <DiagnosticDialog
        title={$_('settings.frigate.test_title', { default: 'Frigate & MQTT connection test' })}
        subtitle={$_('settings.frigate.test_subtitle', { default: 'Checks that the Frigate API answers and that the MQTT broker accepts a publish.' })}
        stages={fcStages}
        busy={fcRunning}
        result={fcResult}
        runId={fcRunId}
        retryLabel={$_('settings.frigate.test_connection')}
        onClose={() => (fcTestOpen = false)}
        onRetry={runConnectionDiagnostic}
    />
{/if}

<style>
    .custom-scrollbar::-webkit-scrollbar { width: 4px; }
    .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
    .custom-scrollbar::-webkit-scrollbar-thumb { background: #94a3b833; border-radius: 10px; }
</style>

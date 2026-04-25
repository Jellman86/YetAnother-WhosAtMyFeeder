<script lang="ts">
    import { onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import type { VersionInfo } from '../../api';
    import type { RecordingClipCapability } from '../../api/system';
    import { authStore } from '../../stores/auth.svelte';
    import { FRIGATE_LOGO_URL } from '../../assets';
    import SecretSavedBadge from './SecretSavedBadge.svelte';
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
        telemetryEnabled = $bindable(false),
        availableCameras = $bindable<string[]>([]),
        recordingClipCapability = null,
        recordingClipCapabilityLoading = false,
        camerasLoading,
        testing,
        testingBirdNET = $bindable(false),
        telemetryInstallationId,
        telemetryPlatform,
        versionInfo,
        testConnection,
        loadCameras,
        handleTestBirdNET,
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
        telemetryEnabled: boolean;
        availableCameras: string[];
        recordingClipCapability: RecordingClipCapability | null;
        recordingClipCapabilityLoading: boolean;
        camerasLoading: boolean;
        testing: boolean;
        testingBirdNET: boolean;
        telemetryInstallationId: string | undefined;
        telemetryPlatform: string | undefined;
        versionInfo: VersionInfo;
        testConnection: () => Promise<void>;
        loadCameras: () => Promise<void>;
        handleTestBirdNET: () => Promise<void>;
        toggleCamera: (camera: string) => void;
    } = $props();

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
                return $_('settings.frigate.full_visit_reason_recordings_disabled', { default: 'Continuous recordings are not enabled for the selected cameras.' });
            case 'retention_unknown':
                return $_('settings.frigate.full_visit_reason_retention_unknown', { default: 'Recording retention could not be determined.' });
            default:
                return $_('settings.frigate.full_visit_reason_unknown', { default: 'Capability could not be confirmed.' });
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
            const resp = await fetch(`/api/frigate/camera/${encodeURIComponent(camera)}/latest.jpg?cache=${previewTimestamp}`, {
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
                onclick={testConnection}
                disabled={testing}
                aria-label={$_('settings.frigate.test_connection')}
                class="px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-400 dark:focus:ring-offset-slate-900 disabled:opacity-50"
            >
                {testing ? $_('common.testing') : $_('settings.frigate.test_connection')}
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

        <button
            type="button"
            onclick={handleTestBirdNET}
            disabled={testingBirdNET}
            aria-label={$_('settings.frigate.test_mqtt')}
            class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-all border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-400 dark:focus:ring-offset-slate-900 disabled:opacity-50"
        >
            {testingBirdNET ? $_('settings.connection.simulating') : $_('settings.frigate.test_mqtt')}
        </button>

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
                    <div class="space-y-2">
                        {#if mqttPasswordSaved}
                            <div class="flex justify-end"><SecretSavedBadge /></div>
                        {/if}
                        <SettingsInput
                            id="mqtt-password"
                            type="password"
                            autocomplete="off"
                            value={mqttPassword}
                            ariaLabel={$_('settings.frigate.mqtt_pass')}
                            oninput={(v) => (mqttPassword = v)}
                        />
                    </div>
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

        <div class="rounded-2xl border px-4 py-3 text-xs space-y-2 {recordingClipCapability?.supported ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200' : 'border-amber-400/30 bg-amber-500/10 text-amber-800 dark:text-amber-200'}">
            <div class="flex items-center justify-between gap-3">
                <span class="font-black uppercase tracking-widest text-[10px]">
                    {$_('settings.frigate.full_visit_capability', { default: 'Capability' })}
                </span>
                {#if recordingClipCapabilityLoading}
                    <span class="text-[10px] font-semibold uppercase tracking-widest">{$_('common.loading', { default: 'Loading' })}</span>
                {:else if recordingClipCapability?.supported}
                    <span class="text-[10px] font-semibold uppercase tracking-widest">{$_('common.enabled', { default: 'Enabled' })}</span>
                {:else}
                    <span class="text-[10px] font-semibold uppercase tracking-widest">{$_('common.disabled', { default: 'Disabled' })}</span>
                {/if}
            </div>

            {#if recordingClipCapabilityLoading}
                <p>{$_('settings.frigate.full_visit_loading', { default: 'Checking saved Frigate recording support...' })}</p>
            {:else if recordingClipCapability}
                {#if recordingClipCapability.supported}
                    <p>
                        {$_('settings.frigate.full_visit_supported', {
                            default: 'Continuous recordings are available for {count} selected camera(s).',
                            values: { count: recordingClipCapability.eligible_cameras.length }
                        })}
                    </p>
                {:else}
                    <p>{getRecordingCapabilityReason(recordingClipCapability.reason)}</p>
                {/if}
                {#if recordingClipCapability.eligible_cameras.length > 0}
                    <p class="text-[11px] opacity-90">
                        {$_('settings.frigate.full_visit_cameras', {
                            default: 'Eligible cameras: {cameras}',
                            values: { cameras: recordingClipCapability.eligible_cameras.join(', ') }
                        })}
                    </p>
                {/if}
                {#if recordingClipCapability.retention_days !== null}
                    <p class="text-[11px] opacity-90">
                        {$_('settings.frigate.full_visit_retention', {
                            default: 'Detected recording retention: {days} day(s)',
                            values: { days: recordingClipCapability.retention_days }
                        })}
                    </p>
                {/if}
            {:else}
                <p>{$_('settings.frigate.full_visit_unavailable', { default: 'Capability information is unavailable right now.' })}</p>
            {/if}
        </div>

        <AdvancedSection
            id="connection-advanced"
            title={$_('settings.connection.advanced_title', { default: 'Tuning' })}
        >
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

    <SettingsCard icon="📷" title={$_('settings.cameras.title')}>
        <div class="space-y-3 max-h-[36rem] overflow-y-auto pr-2 custom-scrollbar">
            {#if availableCameras.length === 0}
                <div class="p-8 text-center bg-slate-50 dark:bg-slate-900/30 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700">
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-widest">{$_('settings.cameras.none_found')}</p>
                </div>
            {:else}
                <div class="grid grid-cols-1 gap-2">
                    {#each availableCameras as camera}
                        {@const selected = selectedCameras.includes(camera)}
                        <div
                            role="button"
                            tabindex="0"
                            aria-label={selected ? $_('settings.cameras.deselect', { default: 'Deselect {camera}', values: { camera } }) : $_('settings.cameras.select', { default: 'Select {camera}', values: { camera } })}
                            class="relative flex flex-col gap-3 p-4 rounded-2xl border-2 transition-all group cursor-pointer
                                   {selected
                                       ? 'border-teal-500 bg-teal-500/5 text-teal-700 dark:text-teal-400'
                                       : 'border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/30 text-slate-500 hover:border-teal-500/30'}"
                            onclick={() => toggleCamera(camera)}
                            onkeydown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    toggleCamera(camera);
                                }
                            }}
                        >
                            <div class="flex items-center justify-between gap-3">
                                <div class="flex items-center gap-3">
                                    <span class="font-bold text-sm">{camera}</span>
                                    <button
                                        type="button"
                                        class="transition text-slate-500 hover:text-teal-600 dark:text-slate-400 dark:hover:text-teal-300"
                                        aria-label={$_('settings.cameras.preview', { default: 'Preview {camera}', values: { camera } })}
                                        disabled={!frigateUrl}
                                        onclick={(e) => { e.stopPropagation(); togglePreview(camera); }}
                                    >
                                        <svg class={`w-4 h-4 transition-transform ${previewVisible && previewCamera === camera ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                                        </svg>
                                    </button>
                                </div>
                                <div class="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all {selected ? 'bg-teal-500 border-teal-500 scale-110' : 'border-slate-300 dark:border-slate-600 group-hover:border-teal-500/50'}">
                                    {#if selected}<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" /></svg>{/if}
                                </div>
                            </div>
                            {#if previewVisible && previewCamera === camera}
                                <div class="rounded-2xl border border-slate-200/80 dark:border-slate-700/60 bg-white/95 dark:bg-slate-900/95 overflow-hidden shadow-lg shadow-slate-900/10 dark:shadow-black/30">
                                    <div class="px-4 py-2 flex items-center justify-between gap-2">
                                        <span class="text-[9px] font-black uppercase tracking-widest text-slate-500">{$_('settings.cameras.preview_label', { default: 'Live Preview' })}</span>
                                        <div class="flex items-center gap-2">
                                            <span class="text-[9px] font-semibold text-emerald-500">{$_('settings.cameras.preview_live', { default: 'LIVE' })}</span>
                                            <button
                                                type="button"
                                                class="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                                                aria-label={$_('settings.cameras.preview_close')}
                                                onclick={() => stopPreview(camera)}
                                            >
                                                <svg class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                                                </svg>
                                            </button>
                                        </div>
                                    </div>
                                    <div class="bg-slate-100 dark:bg-slate-800/60">
                                        <div class="relative w-full h-36">
                                            {#if previewBlobUrl}
                                                <img class="w-full h-36 object-cover" alt="" src={previewBlobUrl} />
                                            {/if}
                                            {#if previewLoading}
                                                <div class="absolute inset-0 flex items-center justify-center bg-white/70 dark:bg-slate-900/70 text-[10px] font-semibold text-slate-500">
                                                    {$_('settings.cameras.preview_loading', { default: 'Loading preview…' })}
                                                </div>
                                            {/if}
                                            {#if previewError}
                                                <div class="absolute inset-0 flex items-center justify-center bg-white/80 dark:bg-slate-900/80 text-[10px] font-semibold text-rose-500 text-center px-3">
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
        </div>
    </SettingsCard>

    <div class="md:col-span-2">
        <SettingsCard
            icon="📊"
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

            {#if telemetryEnabled}
                <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 animate-in fade-in slide-in-from-top-2">
                    <p class="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">{$_('settings.telemetry.transparency')}</p>
                    <div class="space-y-2 text-[10px] font-mono text-slate-600 dark:text-slate-400">
                        <div class="flex justify-between"><span>{$_('settings.telemetry.install_id')}:</span><span class="text-slate-900 dark:text-white select-all">{telemetryInstallationId || '...'}</span></div>
                        <div class="flex justify-between"><span>{$_('settings.telemetry.version')}:</span><span>{versionInfo.version}</span></div>
                        <div class="flex justify-between"><span>{$_('settings.telemetry.platform')}:</span><span>{telemetryPlatform || '...'}</span></div>
                        <div class="flex justify-between"><span>{$_('settings.telemetry.includes')}:</span><span>{$_('settings.telemetry.includes_value')}</span></div>
                        <div class="flex justify-between"><span>{$_('settings.telemetry.geography')}:</span><span>{$_('settings.telemetry.geography_value')}</span></div>
                        <div class="flex justify-between"><span>{$_('settings.telemetry.frequency')}:</span><span>{$_('settings.telemetry.frequency_value')}</span></div>
                    </div>
                    <p class="text-[9px] text-slate-400 mt-3 italic">{$_('settings.telemetry.privacy_notice')}</p>
                </div>
            {/if}
        </SettingsCard>
    </div>
</div>

<style>
    .custom-scrollbar::-webkit-scrollbar { width: 4px; }
    .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
    .custom-scrollbar::-webkit-scrollbar-thumb { background: #94a3b833; border-radius: 10px; }
</style>

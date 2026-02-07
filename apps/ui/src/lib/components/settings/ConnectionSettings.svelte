<script lang="ts">
    import { onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import type { VersionInfo } from '../../api';
    import { authStore } from '../../stores/auth.svelte';

    // Props
    let {
        frigateUrl = $bindable(''),
        mqttServer = $bindable(''),
        mqttPort = $bindable(1883),
        mqttAuth = $bindable(false),
        mqttUsername = $bindable(''),
        mqttPassword = $bindable(''),
        clipsEnabled = $bindable(true),
        selectedCameras = $bindable<string[]>([]),
        telemetryEnabled = $bindable(false),
        availableCameras = $bindable<string[]>([]),
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
        clipsEnabled: boolean;
        selectedCameras: string[];
        telemetryEnabled: boolean;
        availableCameras: string[];
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

    function getFrigateBase() {
        return frigateUrl ? frigateUrl.replace(/\/+$/, '') : '';
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
    <!-- Frigate Connection -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md h-full flex flex-col">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.frigate.title')}</h3>
        </div>

        <div class="space-y-6">
            <div>
                <label for="frigate-url" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.frigate.url')}</label>
                <input
                    id="frigate-url"
                    type="url"
                    bind:value={frigateUrl}
                    placeholder="http://frigate:5000"
                    aria-label="{$_('settings.frigate.url')}"
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all"
                />
            </div>

            <div class="grid grid-cols-2 gap-3">
                <button
                    onclick={testConnection}
                    disabled={testing}
                    aria-label="{$_('settings.frigate.test_connection')}"
                    class="flex-1 px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 disabled:opacity-50"
                >
                    {testing ? $_('common.testing') : $_('settings.frigate.test_connection')}
                </button>
                <button
                    onclick={loadCameras}
                    disabled={camerasLoading}
                    aria-label="{$_('settings.frigate.sync_cameras')}"
                    class="flex-1 px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-all disabled:opacity-50"
                >
                    {camerasLoading ? $_('settings.cameras.syncing') : $_('settings.frigate.sync_cameras')}
                </button>
            </div>

            <button
                onclick={handleTestBirdNET}
                disabled={testingBirdNET}
                aria-label={$_('settings.frigate.test_mqtt')}
                class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 transition-all border border-indigo-500/20 disabled:opacity-50"
            >
                {testingBirdNET ? $_('settings.connection.simulating') : $_('settings.frigate.test_mqtt')}
            </button>

            <div class="pt-6 border-t border-slate-100 dark:border-slate-700/50">
                <h4 class="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-4">{$_('settings.connection.mqtt_title')}</h4>
                <div class="space-y-4">
                    <div class="grid grid-cols-3 gap-4">
                        <div class="col-span-2">
                            <label for="mqtt-server" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.frigate.mqtt_broker')}</label>
                            <input
                                id="mqtt-server"
                                type="text"
                                bind:value={mqttServer}
                                placeholder="mosquitto"
                                aria-label="{$_('settings.frigate.mqtt_broker')}"
                                class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                            />
                        </div>
                        <div>
                            <label for="mqtt-port" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.frigate.mqtt_port')}</label>
                            <input
                                id="mqtt-port"
                                type="number"
                                bind:value={mqttPort}
                                aria-label="{$_('settings.frigate.mqtt_port')}"
                                class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                            />
                        </div>
                    </div>

                    <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                        <span id="mqtt-auth-label" class="text-xs font-bold text-slate-900 dark:text-white">{$_('settings.frigate.mqtt_auth')}</span>
                        <button
                            role="switch"
                            aria-checked={mqttAuth}
                            aria-labelledby="mqtt-auth-label"
                            onclick={() => mqttAuth = !mqttAuth}
                            onkeydown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    mqttAuth = !mqttAuth;
                                }
                            }}
                            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {mqttAuth ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                        >
                            <span class="sr-only">{$_('settings.frigate.mqtt_auth')}</span>
                            <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {mqttAuth ? 'translate-x-5' : 'translate-x-0'}"></span>
                        </button>
                    </div>

                    {#if mqttAuth}
                        <div class="grid grid-cols-2 gap-4 animate-in fade-in zoom-in-95">
                            <div>
                                <label for="mqtt-username" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.frigate.mqtt_user')}</label>
                                <input
                                    id="mqtt-username"
                                    type="text"
                                    bind:value={mqttUsername}
                                    aria-label="{$_('settings.frigate.mqtt_user')}"
                                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                                />
                            </div>
                            <div>
                                <label for="mqtt-password" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.frigate.mqtt_pass')}</label>
                                <input
                                    id="mqtt-password"
                                    type="password"
                                    bind:value={mqttPassword}
                                    aria-label="{$_('settings.frigate.mqtt_pass')}"
                                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                                />
                            </div>
                        </div>
                    {/if}
                </div>
            </div>

            <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                <div id="clips-enabled-label">
                    <span class="block text-sm font-bold text-slate-900 dark:text-white">{$_('settings.frigate.fetch_clips')}</span>
                    <span class="block text-[10px] text-slate-500 font-medium">{$_('settings.frigate.fetch_clips_desc')}</span>
                </div>
                <button
                    role="switch"
                    aria-checked={clipsEnabled}
                    aria-labelledby="clips-enabled-label"
                    onclick={() => clipsEnabled = !clipsEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            clipsEnabled = !clipsEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none {clipsEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.frigate.fetch_clips')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out {clipsEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>
        </div>
    </section>

    <!-- Camera Selection -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md h-full flex flex-col">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-blue-500/10 flex items-center justify-center text-blue-600 dark:text-blue-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.cameras.title')}</h3>
        </div>

        <div class="space-y-3 flex-1 min-h-0 overflow-y-auto pr-2 custom-scrollbar">
            {#if availableCameras.length === 0}
                <div class="p-8 text-center bg-slate-50 dark:bg-slate-900/30 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700">
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-widest">{$_('settings.cameras.none_found')}</p>
                </div>
            {:else}
                <div class="grid grid-cols-1 gap-2">
                    {#each availableCameras as camera}
                        <div
                            role="button"
                            tabindex="0"
                            aria-label="{selectedCameras.includes(camera) ? $_('settings.cameras.deselect', { default: 'Deselect {camera}', values: { camera } }) : $_('settings.cameras.select', { default: 'Select {camera}', values: { camera } })}"
                            class="relative flex flex-col gap-3 p-4 rounded-2xl border-2 transition-all group cursor-pointer
                                   {selectedCameras.includes(camera)
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
                                        aria-label="{$_('settings.cameras.preview', { default: 'Preview {camera}', values: { camera } })}"
                                        disabled={!frigateUrl}
                                        onclick={(e) => {
                                            e.stopPropagation();
                                            togglePreview(camera);
                                        }}
                                    >
                                        <svg class={`w-4 h-4 transition-transform ${previewVisible && previewCamera === camera ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                                        </svg>
                                    </button>
                                </div>
                                <div class="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all {selectedCameras.includes(camera) ? 'bg-teal-500 border-teal-500 scale-110' : 'border-slate-300 dark:border-slate-600 group-hover:border-teal-500/50'}">
                                    {#if selectedCameras.includes(camera)}<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" /></svg>{/if}
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
                                                aria-label="Close preview"
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
    </section>

    <!-- Telemetry -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md md:col-span-2">
        <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
                </div>
                <div id="telemetry-label">
                    <div class="flex items-center gap-2">
                        <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.telemetry.title')}</h3>
                        <button
                            type="button"
                            class="text-slate-400 hover:text-indigo-500 dark:text-slate-500 dark:hover:text-indigo-300 transition"
                            title={$_('settings.telemetry.appreciation_tooltip')}
                            aria-label={$_('settings.telemetry.appreciation_tooltip')}
                        >
                            <svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                <path fill-rule="evenodd" d="M18 10A8 8 0 11 2 10a8 8 0 0116 0zm-8-3a1 1 0 00-.993.883L9 8v4a1 1 0 001.993.117L11 12V8a1 1 0 00-1-1zm0 8a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5z" clip-rule="evenodd" />
                            </svg>
                        </button>
                    </div>
                    <p class="text-[10px] font-bold text-slate-500 mt-0.5">{$_('settings.telemetry.desc')}</p>
                </div>
            </div>
            <button
                role="switch"
                aria-checked={telemetryEnabled}
                aria-labelledby="telemetry-label"
                onclick={() => telemetryEnabled = !telemetryEnabled}
                onkeydown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        telemetryEnabled = !telemetryEnabled;
                    }
                }}
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {telemetryEnabled ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
            >
                <span class="sr-only">{$_('settings.telemetry.title')}</span>
                <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {telemetryEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
            </button>
        </div>

        {#if telemetryEnabled}
            <div class="mt-4 p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 animate-in fade-in slide-in-from-top-2">
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
    </section>
</div>

<style>
    .custom-scrollbar::-webkit-scrollbar {
        width: 4px;
    }
    .custom-scrollbar::-webkit-scrollbar-track {
        background: transparent;
    }
    .custom-scrollbar::-webkit-scrollbar-thumb {
        background: #94a3b833;
        border-radius: 10px;
    }
</style>

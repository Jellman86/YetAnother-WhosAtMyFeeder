<script lang="ts">
    import { onMount } from 'svelte';
    import {
        fetchSettings,
        updateSettings,
        testFrigateConnection,
        fetchFrigateConfig,
        fetchClassifierStatus,
        downloadDefaultModel,
        fetchWildlifeModelStatus,
        downloadWildlifeModel,
        fetchMaintenanceStats,
        runCleanup,
        runBackfill,
        fetchCacheStats,
        runCacheCleanup,
        type ClassifierStatus,
        type WildlifeModelStatus,
        type MaintenanceStats,
        type BackfillResult,
        type CacheStats,
        type CacheCleanupResult
    } from '../api';
    import { theme, type Theme } from '../stores/theme';
    import { settingsStore } from '../stores/settings';
    import ModelManager from './models/ModelManager.svelte';
    import SettingsTabs from '../components/settings/SettingsTabs.svelte';

    let frigateUrl = $state('');
    let mqttServer = $state('');
    let mqttPort = $state(1883);
    let mqttAuth = $state(false);
    let mqttUsername = $state('');
    let mqttPassword = $state('');
    let audioTopic = $state('birdnet/text');
    let cameraAudioMapping = $state<Record<string, string>>({});
    let clipsEnabled = $state(true);
    let threshold = $state(0.7);
    let trustFrigateSublabel = $state(true);
    let displayCommonNames = $state(true);
    let selectedCameras = $state<string[]>([]);
    let retentionDays = $state(0);
    let blockedLabels = $state<string[]>([]);
    let newBlockedLabel = $state('');

    // Location Settings
    let locationLat = $state<number | null>(null);
    let locationLon = $state<number | null>(null);
    let locationAuto = $state(true);

    // LLM Settings
    let llmEnabled = $state(false);
    let llmProvider = $state('gemini');
    let llmApiKey = $state('');
    let llmModel = $state('gemini-1.5-flash');

    let availableCameras = $state<string[]>([]);
    let camerasLoading = $state(false);

    let loading = $state(true);
    let saving = $state(false);
    let testing = $state(false);
    let message = $state<{ type: 'success' | 'error'; text: string } | null>(null);
    let currentTheme: Theme = $state('system');

    let classifierStatus = $state<ClassifierStatus | null>(null);
    let downloadingModel = $state(false);

    let wildlifeStatus = $state<WildlifeModelStatus | null>(null);
    let downloadingWildlifeModel = $state(false);

    let maintenanceStats = $state<MaintenanceStats | null>(null);
    let cleaningUp = $state(false);

    // Media cache state
    let cacheEnabled = $state(true);
    let cacheSnapshots = $state(true);
    let cacheClips = $state(true);
    let cacheRetentionDays = $state(0);
    let cacheStats = $state<CacheStats | null>(null);
    let cleaningCache = $state(false);

    // Backfill state
    let backfillDateRange = $state<'day' | 'week' | 'month' | 'custom'>('week');
    let backfillStartDate = $state('');
    let backfillEndDate = $state('');
    let backfilling = $state(false);
    let backfillResult = $state<BackfillResult | null>(null);

    // Tab navigation
    let activeTab = $state('connection');

    theme.subscribe(t => currentTheme = t);

    onMount(async () => {
        await Promise.all([
            loadSettings(),
            loadCameras(),
            loadClassifierStatus(),
            loadWildlifeStatus(),
            loadMaintenanceStats(),
            loadCacheStats()
        ]);
    });

    async function loadMaintenanceStats() {
        try {
            maintenanceStats = await fetchMaintenanceStats();
        } catch (e) {
            console.error('Failed to load maintenance stats', e);
        }
    }

    async function handleCleanup() {
        cleaningUp = true;
        message = null;
        try {
            const result = await runCleanup();
            if (result.status === 'completed') {
                message = { type: 'success', text: `Cleanup complete! Deleted ${result.deleted_count} old detections.` };
            } else {
                message = { type: 'success', text: result.message || 'No cleanup needed.' };
            }
            await loadMaintenanceStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Cleanup failed' };
        } finally {
            cleaningUp = false;
        }
    }

    async function loadCacheStats() {
        try {
            cacheStats = await fetchCacheStats();
        } catch (e) {
            console.error('Failed to load cache stats', e);
        }
    }

    async function handleCacheCleanup() {
        cleaningCache = true;
        message = null;
        try {
            const result = await runCacheCleanup();
            if (result.status === 'completed') {
                const freed = result.bytes_freed > 1024 * 1024
                    ? `${(result.bytes_freed / (1024 * 1024)).toFixed(1)} MB`
                    : `${(result.bytes_freed / 1024).toFixed(1)} KB`;
                message = { type: 'success', text: `Cache cleanup complete! Deleted ${result.snapshots_deleted} snapshots, ${result.clips_deleted} clips (${freed} freed).` };
            } else {
                message = { type: 'success', text: result.message || 'No cleanup needed.' };
            }
            await loadCacheStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Cache cleanup failed' };
        } finally {
            cleaningCache = false;
        }
    }

    async function handleBackfill() {
        backfilling = true;
        message = null;
        backfillResult = null;
        try {
            const result = await runBackfill({
                date_range: backfillDateRange,
                start_date: backfillDateRange === 'custom' ? backfillStartDate : undefined,
                end_date: backfillDateRange === 'custom' ? backfillEndDate : undefined
            });
            backfillResult = result;
            message = { type: 'success', text: result.message };
            await loadMaintenanceStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Backfill failed' };
        } finally {
            backfilling = false;
        }
    }

    async function loadClassifierStatus() {
        try {
            classifierStatus = await fetchClassifierStatus();
        } catch (e) {
            console.error('Failed to load classifier status', e);
        }
    }

    async function loadWildlifeStatus() {
        try {
            wildlifeStatus = await fetchWildlifeModelStatus();
        } catch (e) {
            console.error('Failed to load wildlife status', e);
        }
    }

    async function handleDownloadWildlifeModel() {
        downloadingWildlifeModel = true;
        message = null;
        try {
            const result = await downloadWildlifeModel();
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
                await loadWildlifeStatus();
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to download wildlife model' };
        } finally {
            downloadingWildlifeModel = false;
        }
    }

    async function loadSettings() {
        loading = true;
        message = null;
        try {
            const settings = await fetchSettings();
            frigateUrl = settings.frigate_url;
            mqttServer = settings.mqtt_server;
            mqttPort = settings.mqtt_port;
            mqttAuth = settings.mqtt_auth;
            mqttUsername = settings.mqtt_username || '';
            mqttPassword = settings.mqtt_password || '';
            audioTopic = settings.audio_topic || 'birdnet/text';
            cameraAudioMapping = settings.camera_audio_mapping || {};
            if (typeof cameraAudioMapping !== 'object' || Array.isArray(cameraAudioMapping)) {
                cameraAudioMapping = {};
            }
            clipsEnabled = settings.clips_enabled ?? true;
            threshold = settings.classification_threshold;
            trustFrigateSublabel = settings.trust_frigate_sublabel ?? true;
            displayCommonNames = settings.display_common_names ?? true;
            selectedCameras = settings.cameras || [];
            retentionDays = settings.retention_days || 0;
            blockedLabels = settings.blocked_labels || [];
            // Media cache settings
            cacheEnabled = settings.media_cache_enabled ?? true;
            cacheSnapshots = settings.media_cache_snapshots ?? true;
            cacheClips = settings.media_cache_clips ?? true;
            cacheRetentionDays = settings.media_cache_retention_days ?? 0;
            // Location settings
            locationLat = settings.location_latitude ?? null;
            locationLon = settings.location_longitude ?? null;
            locationAuto = settings.location_automatic ?? true;
            // LLM settings
            llmEnabled = settings.llm_enabled ?? false;
            llmProvider = settings.llm_provider ?? 'gemini';
            llmApiKey = settings.llm_api_key ?? '';
            llmModel = settings.llm_model ?? 'gemini-1.5-flash';
        } catch (e) {
            message = { type: 'error', text: 'Failed to load settings' };
        } finally {
            loading = false;
        }
    }

    async function loadCameras() {
        camerasLoading = true;
        try {
            const config = await fetchFrigateConfig();
            if (config && config.cameras) {
                availableCameras = Object.keys(config.cameras);
            }
        } catch (e) {
            console.error('Failed to load cameras from Frigate', e);
            if (selectedCameras.length > 0 && availableCameras.length === 0) {
                 availableCameras = [...selectedCameras];
            }
        } finally {
            camerasLoading = false;
        }
    }

    async function saveSettings() {
        saving = true;
        message = null;
        try {
            await updateSettings({
                frigate_url: frigateUrl,
                mqtt_server: mqttServer,
                mqtt_port: mqttPort,
                mqtt_auth: mqttAuth,
                mqtt_username: mqttUsername,
                mqtt_password: mqttPassword,
                audio_topic: audioTopic,
                camera_audio_mapping: cameraAudioMapping,
                clips_enabled: clipsEnabled,
                classification_threshold: threshold,
                trust_frigate_sublabel: trustFrigateSublabel,
                display_common_names: displayCommonNames,
                cameras: selectedCameras,
                retention_days: retentionDays,
                blocked_labels: blockedLabels,
                media_cache_enabled: cacheEnabled,
                media_cache_snapshots: cacheSnapshots,
                media_cache_clips: cacheClips,
                media_cache_retention_days: cacheRetentionDays,
                location_latitude: locationLat,
                location_longitude: locationLon,
                location_automatic: locationAuto,
                llm_enabled: llmEnabled,
                llm_provider: llmProvider,
                llm_api_key: llmApiKey,
                llm_model: llmModel
            });
            // Update store
            await settingsStore.load();
            message = { type: 'success', text: 'Settings saved successfully!' };
            await Promise.all([loadMaintenanceStats(), loadCacheStats()]);
        } catch (e) {
            message = { type: 'error', text: 'Failed to save settings' };
        } finally {
            saving = false;
        }
    }

    async function testConnection() {
        testing = true;
        message = null;
        try {
            const result = await testFrigateConnection();
            if (result.status === 'ok') {
                message = { type: 'success', text: `Connected to Frigate v${result.version} at ${result.frigate_url}` };
            } else {
                message = { type: 'error', text: 'Frigate returned unexpected status' };
            }
        } catch (e: any) {
            const errorMsg = e.message || 'Failed to connect to Frigate';
            message = { type: 'error', text: errorMsg };
        } finally {
            testing = false;
        }
    }

    function toggleCamera(camera: string) {
        if (selectedCameras.includes(camera)) {
            selectedCameras = selectedCameras.filter(c => c !== camera);
        } else {
            selectedCameras = [...selectedCameras, camera];
        }
    }

    function setTheme(t: Theme) {
        theme.set(t);
    }

    function addBlockedLabel() {
        const label = newBlockedLabel.trim();
        if (label && !blockedLabels.includes(label)) {
            blockedLabels = [...blockedLabels, label];
            newBlockedLabel = '';
        }
    }

    function removeBlockedLabel(label: string) {
        blockedLabels = blockedLabels.filter(l => l !== label);
    }
</script>

<div class="max-w-2xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Settings</h2>
        <button
            onclick={loadSettings}
            disabled={loading}
            class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-lg
                   text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800
                   border border-slate-200 dark:border-slate-700 shadow-sm
                   hover:bg-slate-50 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white
                   transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
            <svg class="w-4 h-4 {loading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
        </button>
    </div>

    {#if message}
        <div class="p-4 rounded-lg {message.type === 'success'
            ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800'
            : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800'}">
            {message.text}
        </div>
    {/if}

    {#if loading}
        <div class="space-y-4">
            {#each [1, 2, 3] as _}
                <div class="h-24 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"></div>
            {/each}
        </div>
    {:else}
        <!-- Tab Navigation -->
        <SettingsTabs {activeTab} ontabchange={(tab) => activeTab = tab} />

        <!-- Connection Tab -->
        {#if activeTab === 'connection'}
        <!-- Frigate Connection -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                📹 Frigate Connection
            </h3>

            <div class="space-y-4">
                <div>
                    <label for="frigate-url" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                        Frigate URL
                    </label>
                    <input
                        id="frigate-url"
                        type="url"
                        bind:value={frigateUrl}
                        placeholder="http://frigate_host:5000"
                        class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                               focus:ring-2 focus:ring-teal-500 focus:border-transparent
                               placeholder:text-slate-400 dark:placeholder:text-slate-500"
                    />
                </div>

                <div class="flex gap-2">
                     <button
                        onclick={testConnection}
                        disabled={testing}
                        class="px-4 py-2 text-sm font-medium rounded-lg
                               bg-teal-500 hover:bg-teal-600 text-white
                               transition-colors disabled:opacity-50"
                    >
                        {testing ? 'Testing...' : 'Test Frigate Connection'}
                    </button>
                    
                    <button
                        onclick={loadCameras}
                        disabled={camerasLoading}
                        class="px-4 py-2 text-sm font-medium rounded-lg
                               bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300
                               hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors
                               disabled:opacity-50"
                    >
                        {camerasLoading ? 'Fetching Cameras...' : 'Fetch Cameras'}
                    </button>
                </div>

                <div class="flex items-center gap-3 pt-2 border-t border-slate-200 dark:border-slate-700 mt-4">
                     <button 
                        role="switch" 
                        aria-checked={clipsEnabled}
                        aria-label="Toggle Clip Fetching"
                        onclick={() => clipsEnabled = !clipsEnabled}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2
                               {clipsEnabled ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                    >
                        <span 
                            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                                   {clipsEnabled ? 'translate-x-5' : 'translate-x-0'}"
                        ></span>
                    </button>
                    <div>
                        <span class="block text-sm font-medium text-slate-700 dark:text-slate-300">Fetch Video Clips</span>
                        <span class="block text-xs text-slate-500 dark:text-slate-400">Enable fetching and proxying video clips from Frigate. Disable to save bandwidth.</span>
                    </div>
                </div>
            </div>
        </section>

         <!-- Camera Selection -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                📷 Camera Selection
            </h3>
            
            <p class="text-sm text-slate-500 dark:text-slate-400 mb-4">
                Select which cameras to monitor for birds.
            </p>

            {#if availableCameras.length === 0}
                 <div class="text-sm text-slate-500 italic">
                    No cameras found. Please check your Frigate URL and click "Fetch Cameras".
                </div>
            {:else}
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {#each availableCameras as camera}
                        <button
                            class="flex items-center justify-between p-3 rounded-lg border transition-all
                                   {selectedCameras.includes(camera)
                                       ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-400'
                                       : 'border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/50 text-slate-700 dark:text-slate-300 hover:border-teal-300 dark:hover:border-teal-700'}"
                            onclick={() => toggleCamera(camera)}
                        >
                            <span class="font-medium">{camera}</span>
                            {#if selectedCameras.includes(camera)}
                                <span class="text-lg text-teal-500">✓</span>
                            {/if}
                        </button>
                    {/each}
                </div>
            {/if}
        </section>

        <!-- MQTT Settings -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                📡 MQTT Settings
            </h3>

            <div class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="md:col-span-2">
                        <label for="mqtt-server" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            MQTT Server
                        </label>
                        <input
                            id="mqtt-server"
                            type="text"
                            bind:value={mqttServer}
                            placeholder="mosquitto"
                            class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                   bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                   focus:ring-2 focus:ring-teal-500 focus:border-transparent
                                   placeholder:text-slate-400 dark:placeholder:text-slate-500"
                        />
                    </div>
                    <div>
                        <label for="mqtt-port" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Port
                        </label>
                        <input
                            id="mqtt-port"
                            type="number"
                            bind:value={mqttPort}
                            placeholder="1883"
                            class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                   bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                   focus:ring-2 focus:ring-teal-500 focus:border-transparent
                                   placeholder:text-slate-400 dark:placeholder:text-slate-500"
                        />
                    </div>
                </div>

                <div>
                    <label for="audio-topic" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                        Audio Detection Topic (BirdNET-Go)
                    </label>
                    <input
                        id="audio-topic"
                        type="text"
                        bind:value={audioTopic}
                        placeholder="birdnet/text"
                        class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                               focus:ring-2 focus:ring-teal-500 focus:border-transparent
                               placeholder:text-slate-400 dark:placeholder:text-slate-500"
                    />
                </div>

                {#if availableCameras.length > 0}
                    <div class="pt-4 border-t border-slate-200 dark:border-slate-700">
                        <label class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                            Camera to BirdNET ID Mapping (Optional)
                        </label>
                        <p class="text-xs text-slate-500 dark:text-slate-400 mb-3">
                            Enter the "Sensor ID" configured in BirdNET-Go for each camera to enable precise audio correlation.
                        </p>
                        <div class="space-y-3">
                            {#each availableCameras as camera}
                                <div class="flex items-center gap-3">
                                    <span class="text-xs font-medium text-slate-500 w-24 truncate">{camera}</span>
                                    <input
                                        type="text"
                                        placeholder="BirdNET Sensor ID"
                                        bind:value={cameraAudioMapping[camera]}
                                        class="flex-1 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600
                                               bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm"
                                    />
                                </div>
                            {/each}
                        </div>
                    </div>
                {/if}

                <div class="flex items-center gap-3 py-2">
                     <button 
                        role="switch" 
                        aria-checked={mqttAuth}
                        aria-label="Toggle MQTT Authentication"
                        onclick={() => mqttAuth = !mqttAuth}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2
                               {mqttAuth ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                    >
                        <span 
                            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                                   {mqttAuth ? 'translate-x-5' : 'translate-x-0'}"
                        ></span>
                    </button>
                    <span class="text-sm font-medium text-slate-700 dark:text-slate-300">Authentication Required</span>
                </div>

                {#if mqttAuth}
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-4 duration-300">
                        <div>
                            <label for="mqtt-username" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                Username
                            </label>
                            <input
                                id="mqtt-username"
                                type="text"
                                bind:value={mqttUsername}
                                class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                            />
                        </div>
                        <div>
                            <label for="mqtt-password" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                Password
                            </label>
                            <input
                                id="mqtt-password"
                                type="password"
                                bind:value={mqttPassword}
                                class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                            />
                        </div>
                    </div>
                {/if}
            </div>
        </section>

        <!-- Location Settings -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                🌍 Location & Weather
            </h3>
            
            <p class="text-sm text-slate-500 dark:text-slate-400 mb-4">
                Used to fetch local weather data for your detections.
            </p>

            <div class="space-y-4">
                <div class="flex items-center gap-3">
                    <button
                        role="switch"
                        aria-checked={locationAuto}
                        aria-label="Toggle Auto Location"
                        onclick={() => locationAuto = !locationAuto}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2
                               {locationAuto ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                    >
                        <span
                            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                                   {locationAuto ? 'translate-x-5' : 'translate-x-0'}"
                        ></span>
                    </button>
                    <span class="text-sm font-medium text-slate-700 dark:text-slate-300">Detect Automatically (via IP)</span>
                </div>

                {#if !locationAuto}
                    <div class="grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-4 duration-300">
                        <div>
                            <label for="latitude" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                Latitude
                            </label>
                            <input
                                id="latitude"
                                type="number"
                                step="any"
                                bind:value={locationLat}
                                placeholder="e.g. 51.5074"
                                class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                            />
                        </div>
                        <div>
                            <label for="longitude" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                Longitude
                            </label>
                            <input
                                id="longitude"
                                type="number"
                                step="any"
                                bind:value={locationLon}
                                placeholder="e.g. -0.1278"
                                class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                            />
                        </div>
                    </div>
                {/if}
            </div>
        </section>
        {/if}

        <!-- Detection Tab -->
        {#if activeTab === 'detection'}
        <!-- AI Intelligence -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                🤖 AI Intelligence
            </h3>
            
            <p class="text-sm text-slate-500 dark:text-slate-400 mb-4">
                Enable AI-based behavioral analysis and naturalist descriptions for your detections.
            </p>

            <div class="space-y-4">
                <div class="flex items-center gap-3">
                    <button
                        role="switch"
                        aria-checked={llmEnabled}
                        aria-label="Toggle AI Analysis"
                        onclick={() => llmEnabled = !llmEnabled}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2
                               {llmEnabled ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                    >
                        <span
                            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                                   {llmEnabled ? 'translate-x-5' : 'translate-x-0'}"
                        ></span>
                    </button>
                    <span class="text-sm font-medium text-slate-700 dark:text-slate-300">Enable AI Analysis</span>
                </div>

                {#if llmEnabled}
                    <div class="space-y-4 animate-in fade-in slide-in-from-top-4 duration-300">
                        <div>
                            <label for="llm-provider" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                Provider
                            </label>
                            <select
                                id="llm-provider"
                                bind:value={llmProvider}
                                class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                            >
                                <option value="gemini">Google Gemini (Recommended)</option>
                                <option value="openai">OpenAI</option>
                            </select>
                        </div>

                        <div>
                            <label for="llm-api-key" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                API Key
                            </label>
                            <input
                                id="llm-api-key"
                                type="password"
                                bind:value={llmApiKey}
                                placeholder="Enter your API key"
                                class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                            />
                        </div>

                        <div>
                            <label for="llm-model" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                Model
                            </label>
                            <input
                                id="llm-model"
                                type="text"
                                bind:value={llmModel}
                                placeholder={llmProvider === 'gemini' ? 'gemini-1.5-flash' : 'gpt-4o'}
                                class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                            />
                        </div>
                    </div>
                {/if}
            </div>
        </section>

        <!-- Classification Settings -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                🎯 Classification
            </h3>

            <!-- Model Manager -->
            <div class="mb-8">
                <ModelManager />
            </div>

            <!-- Legacy settings below -->
            <div class="border-t border-slate-200 dark:border-slate-700 pt-6">
                <h4 class="text-sm font-semibold text-slate-900 dark:text-white mb-4">Fine Tuning</h4>
                
                <div class="flex items-center gap-3 mb-6 p-3 bg-teal-500/5 dark:bg-teal-500/10 rounded-xl border border-teal-500/20">
                    <button
                        role="switch"
                        aria-checked={trustFrigateSublabel}
                        aria-label="Trust Frigate Sublabels"
                        onclick={() => trustFrigateSublabel = !trustFrigateSublabel}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2
                               {trustFrigateSublabel ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                    >
                        <span
                            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                                   {trustFrigateSublabel ? 'translate-x-5' : 'translate-x-0'}"
                        ></span>
                    </button>
                    <div>
                        <span class="block text-sm font-medium text-slate-700 dark:text-slate-300">Trust Frigate Sublabels</span>
                        <span class="block text-xs text-slate-500 dark:text-slate-400">If Frigate already identified a species (sublabel), use it directly and skip internal classification to save CPU.</span>
                    </div>
                </div>

                <div class="flex items-center gap-3 mb-6 p-3 bg-teal-500/5 dark:bg-teal-500/10 rounded-xl border border-teal-500/20">
                    <button
                        role="switch"
                        aria-checked={displayCommonNames}
                        aria-label="Display Common Names"
                        onclick={() => displayCommonNames = !displayCommonNames}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2
                               {displayCommonNames ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                    >
                        <span
                            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                                   {displayCommonNames ? 'translate-x-5' : 'translate-x-0'}"
                        ></span>
                    </button>
                    <div>
                        <span class="block text-sm font-medium text-slate-700 dark:text-slate-300">Display Common Names</span>
                        <span class="block text-xs text-slate-500 dark:text-slate-400">Automatically look up and display friendly common names for scientific labels.</span>
                    </div>
                </div>

                <div>
                    <label for="threshold" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                        Confidence Threshold: {(threshold * 100).toFixed(0)}%
                    </label>
                    <input
                        id="threshold"
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        bind:value={threshold}
                        class="w-full h-2 rounded-lg appearance-none cursor-pointer
                               bg-slate-200 dark:bg-slate-700
                               accent-teal-500"
                    />
                    <div class="flex justify-between text-xs text-slate-500 dark:text-slate-400 mt-1">
                        <span>0% (All)</span>
                        <span>100% (Strict)</span>
                    </div>
                </div>

                <!-- Blocked Labels -->
                <div class="pt-4 mt-4 border-t border-slate-200 dark:border-slate-700">
                    <label for="blocked-label-input" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                        Blocked Labels
                    </label>
                    <p class="text-xs text-slate-500 dark:text-slate-400 mb-3">
                        Classification results matching these labels will be filtered out (e.g., "background", "unknown").
                    </p>

                    <!-- Add new label -->
                    <div class="flex gap-2 mb-3">
                        <input
                            id="blocked-label-input"
                            type="text"
                            bind:value={newBlockedLabel}
                            placeholder="Enter label to block..."
                            onkeydown={(e) => e.key === 'Enter' && addBlockedLabel()}
                            class="flex-1 px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                   bg-white dark:bg-slate-700 text-slate-900 dark:text-white text-sm
                                   focus:ring-2 focus:ring-teal-500 focus:border-transparent
                                   placeholder:text-slate-400 dark:placeholder:text-slate-500"
                        />
                        <button
                            onclick={addBlockedLabel}
                            disabled={!newBlockedLabel.trim()}
                            class="px-4 py-2 text-sm font-medium rounded-lg
                                   bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300
                                   hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors
                                   disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            Add
                        </button>
                    </div>

                    <!-- Current blocked labels -->
                    {#if blockedLabels.length > 0}
                        <div class="flex flex-wrap gap-2">
                            {#each blockedLabels as label}
                                <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm
                                            bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400
                                            border border-red-200 dark:border-red-800">
                                    {label}
                                    <button
                                        onclick={() => removeBlockedLabel(label)}
                                        class="w-4 h-4 rounded-full hover:bg-red-200 dark:hover:bg-red-800
                                               flex items-center justify-center transition-colors"
                                        title="Remove"
                                    >
                                        <span class="text-xs">×</span>
                                    </button>
                                </span>
                            {/each}
                        </div>
                    {:else}
                        <p class="text-sm text-slate-400 dark:text-slate-500 italic">
                            No labels blocked. Common ones to block: "background", "Background"
                        </p>
                    {/if}
                </div>
            </div>
        </section>
        {/if}

        <!-- Data Tab -->
        {#if activeTab === 'data'}
        <!-- Database Maintenance -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                🗄️ Database Maintenance
            </h3>

            <!-- Stats -->
            {#if maintenanceStats}
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
                        <p class="text-2xl font-bold text-slate-900 dark:text-white">
                            {maintenanceStats.total_detections.toLocaleString()}
                        </p>
                        <p class="text-xs text-slate-500 dark:text-slate-400">Total Detections</p>
                    </div>
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
                        <p class="text-sm font-medium text-slate-900 dark:text-white">
                            {maintenanceStats.oldest_detection
                                ? new Date(maintenanceStats.oldest_detection).toLocaleDateString()
                                : 'N/A'}
                        </p>
                        <p class="text-xs text-slate-500 dark:text-slate-400">Oldest Record</p>
                    </div>
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
                        <p class="text-2xl font-bold text-slate-900 dark:text-white">
                            {retentionDays === 0 ? '∞' : retentionDays}
                        </p>
                        <p class="text-xs text-slate-500 dark:text-slate-400">Retention Days</p>
                    </div>
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
                        <p class="text-2xl font-bold {maintenanceStats.detections_to_cleanup > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-900 dark:text-white'}">
                            {maintenanceStats.detections_to_cleanup.toLocaleString()}
                        </p>
                        <p class="text-xs text-slate-500 dark:text-slate-400">Pending Cleanup</p>
                    </div>
                </div>
            {/if}

            <!-- Retention Setting -->
            <div class="mb-4">
                <label for="retention-days" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                    Data Retention Period
                </label>
                <div class="flex items-center gap-3">
                    <select
                        id="retention-days"
                        bind:value={retentionDays}
                        class="flex-1 px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                               focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                    >
                        <option value={0}>Unlimited (keep forever)</option>
                        <option value={7}>7 days</option>
                        <option value={14}>14 days</option>
                        <option value={30}>30 days</option>
                        <option value={60}>60 days</option>
                        <option value={90}>90 days</option>
                        <option value={180}>180 days</option>
                        <option value={365}>1 year</option>
                    </select>
                </div>
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Detections older than this will be automatically deleted daily at 3 AM.
                </p>
            </div>

            <!-- Manual Cleanup Button -->
            <div class="flex items-center justify-between pt-4 border-t border-slate-200 dark:border-slate-700">
                <div class="text-sm text-slate-500 dark:text-slate-400">
                    {#if maintenanceStats && maintenanceStats.detections_to_cleanup > 0}
                        {maintenanceStats.detections_to_cleanup} detections ready for cleanup
                    {:else}
                        No old detections to clean up
                    {/if}
                </div>
                <button
                    onclick={handleCleanup}
                    disabled={cleaningUp || retentionDays === 0 || (maintenanceStats?.detections_to_cleanup ?? 0) === 0}
                    class="px-4 py-2 text-sm font-medium rounded-lg
                           bg-amber-500 hover:bg-amber-600 text-white
                           transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {cleaningUp ? 'Cleaning...' : 'Run Cleanup Now'}
                </button>
            </div>
        </section>

        <!-- Media Cache -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                💾 Media Cache
            </h3>

            <p class="text-sm text-slate-500 dark:text-slate-400 mb-4">
                Cache snapshots and clips locally to preserve them when Frigate removes events due to retention policies.
            </p>

            <!-- Cache Stats -->
            {#if cacheStats}
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
                        <p class="text-2xl font-bold text-slate-900 dark:text-white">
                            {cacheStats.snapshot_count.toLocaleString()}
                        </p>
                        <p class="text-xs text-slate-500 dark:text-slate-400">Snapshots</p>
                    </div>
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
                        <p class="text-2xl font-bold text-slate-900 dark:text-white">
                            {cacheStats.clip_count.toLocaleString()}
                        </p>
                        <p class="text-xs text-slate-500 dark:text-slate-400">Clips</p>
                    </div>
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
                        <p class="text-2xl font-bold text-slate-900 dark:text-white">
                            {cacheStats.total_size_mb} MB
                        </p>
                        <p class="text-xs text-slate-500 dark:text-slate-400">Total Size</p>
                    </div>
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
                        <p class="text-sm font-medium text-slate-900 dark:text-white">
                            {cacheStats.oldest_file ? new Date(cacheStats.oldest_file).toLocaleDateString() : 'N/A'}
                        </p>
                        <p class="text-xs text-slate-500 dark:text-slate-400">Oldest File</p>
                    </div>
                </div>
            {/if}

            <!-- Cache Enable Toggle -->
            <div class="flex items-center gap-3 py-3 border-b border-slate-200 dark:border-slate-700">
                <button
                    role="switch"
                    aria-checked={cacheEnabled}
                    aria-label="Toggle Media Caching"
                    onclick={() => cacheEnabled = !cacheEnabled}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2
                           {cacheEnabled ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                >
                    <span
                        class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                               {cacheEnabled ? 'translate-x-5' : 'translate-x-0'}"
                    ></span>
                </button>
                <div>
                    <span class="block text-sm font-medium text-slate-700 dark:text-slate-300">Enable Media Caching</span>
                    <span class="block text-xs text-slate-500 dark:text-slate-400">Store media locally for offline access</span>
                </div>
            </div>

            {#if cacheEnabled}
                <div class="space-y-3 py-3 animate-in fade-in slide-in-from-top-4 duration-300">
                    <!-- Cache Snapshots -->
                    <div class="flex items-center gap-3">
                        <button
                            role="switch"
                            aria-checked={cacheSnapshots}
                            aria-label="Cache Snapshots"
                            onclick={() => cacheSnapshots = !cacheSnapshots}
                            class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out
                                   {cacheSnapshots ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                        >
                            <span class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                                   {cacheSnapshots ? 'translate-x-4' : 'translate-x-0'}"></span>
                        </button>
                        <span class="text-sm text-slate-700 dark:text-slate-300">Cache Snapshots</span>
                    </div>

                    <!-- Cache Clips -->
                    <div class="flex items-center gap-3">
                        <button
                            role="switch"
                            aria-checked={cacheClips}
                            aria-label="Cache Clips"
                            onclick={() => cacheClips = !cacheClips}
                            class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out
                                   {cacheClips ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}"
                        >
                            <span class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
                                   {cacheClips ? 'translate-x-4' : 'translate-x-0'}"></span>
                        </button>
                        <span class="text-sm text-slate-700 dark:text-slate-300">Cache Video Clips</span>
                    </div>
                </div>

                <!-- Cache Retention -->
                <div class="pt-3 border-t border-slate-200 dark:border-slate-700">
                    <label for="cache-retention" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                        Cache Retention Period
                    </label>
                    <select
                        id="cache-retention"
                        bind:value={cacheRetentionDays}
                        class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                               focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                    >
                        <option value={0}>Follow detection retention ({retentionDays === 0 ? 'unlimited' : retentionDays + ' days'})</option>
                        <option value={7}>7 days</option>
                        <option value={14}>14 days</option>
                        <option value={30}>30 days</option>
                        <option value={60}>60 days</option>
                        <option value={90}>90 days</option>
                        <option value={180}>180 days</option>
                        <option value={365}>1 year</option>
                    </select>
                </div>

                <!-- Manual Cache Cleanup -->
                <div class="flex items-center justify-between pt-4 mt-4 border-t border-slate-200 dark:border-slate-700">
                    <div class="text-sm text-slate-500 dark:text-slate-400">
                        {#if cacheStats}
                            {cacheStats.total_size_mb} MB cached
                        {:else}
                            No cache data
                        {/if}
                    </div>
                    <button
                        onclick={handleCacheCleanup}
                        disabled={cleaningCache || !cacheEnabled}
                        class="px-4 py-2 text-sm font-medium rounded-lg
                               bg-amber-500 hover:bg-amber-600 text-white
                               transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {cleaningCache ? 'Cleaning...' : 'Clean Old Cache'}
                    </button>
                </div>
            {/if}
        </section>

        <!-- Backfill Detections -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                🔄 Fetch Previous Detections
            </h3>

            <p class="text-sm text-slate-500 dark:text-slate-400 mb-4">
                Fetch historical bird detections from Frigate that may have been missed.
                This will query Frigate's event history, classify any new detections, and add them to your database.
            </p>

            <!-- Date Range Selection -->
            <div class="mb-4">
                <label for="backfill-range" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                    Date Range
                </label>
                <select
                    id="backfill-range"
                    bind:value={backfillDateRange}
                    class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                           bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                           focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                >
                    <option value="day">Last 24 Hours</option>
                    <option value="week">Last Week</option>
                    <option value="month">Last Month</option>
                    <option value="custom">Custom Range</option>
                </select>
            </div>

            <!-- Custom Date Range -->
            {#if backfillDateRange === 'custom'}
                <div class="grid grid-cols-2 gap-4 mb-4 animate-in fade-in slide-in-from-top-4 duration-300">
                    <div>
                        <label for="backfill-start" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Start Date
                        </label>
                        <input
                            id="backfill-start"
                            type="date"
                            bind:value={backfillStartDate}
                            class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                   bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                   focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                        />
                    </div>
                    <div>
                        <label for="backfill-end" class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            End Date
                        </label>
                        <input
                            id="backfill-end"
                            type="date"
                            bind:value={backfillEndDate}
                            class="w-full px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600
                                   bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                   focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                        />
                    </div>
                </div>
            {/if}

            <!-- Backfill Result -->
            {#if backfillResult}
                <div class="mb-4 p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50 border border-slate-200 dark:border-slate-600">
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                        <div>
                            <p class="text-lg font-bold text-slate-900 dark:text-white">{backfillResult.processed}</p>
                            <p class="text-xs text-slate-500 dark:text-slate-400">Processed</p>
                        </div>
                        <div>
                            <p class="text-lg font-bold text-emerald-600 dark:text-emerald-400">{backfillResult.new_detections}</p>
                            <p class="text-xs text-slate-500 dark:text-slate-400">New</p>
                        </div>
                        <div>
                            <p class="text-lg font-bold text-slate-500 dark:text-slate-400">{backfillResult.skipped}</p>
                            <p class="text-xs text-slate-500 dark:text-slate-400">Already Existed</p>
                        </div>
                        <div>
                            <p class="text-lg font-bold {backfillResult.errors > 0 ? 'text-red-600 dark:text-red-400' : 'text-slate-500 dark:text-slate-400'}">{backfillResult.errors}</p>
                            <p class="text-xs text-slate-500 dark:text-slate-400">Errors</p>
                        </div>
                    </div>
                </div>
            {/if}

            <!-- Backfill Button -->
            <button
                onclick={handleBackfill}
                disabled={backfilling || (backfillDateRange === 'custom' && (!backfillStartDate || !backfillEndDate))}
                class="w-full px-4 py-3 text-sm font-medium rounded-lg
                       bg-teal-500 hover:bg-teal-600 text-white
                       transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                       flex items-center justify-center gap-2"
            >
                {#if backfilling}
                    <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Fetching Detections...
                {:else}
                    Fetch Previous Detections
                {/if}
            </button>

            <p class="mt-2 text-xs text-slate-500 dark:text-slate-400 text-center">
                This may take a while depending on the number of events in Frigate.
            </p>
        </section>
        {/if}

        <!-- Appearance Tab -->
        {#if activeTab === 'appearance'}
        <!-- Appearance -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                🎨 Appearance
            </h3>

            <div>
                <span class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">
                    Theme
                </span>
                <div class="flex gap-2">
                    {#each [
                        { value: 'light', label: 'Light', icon: '☀️' },
                        { value: 'dark', label: 'Dark', icon: '🌙' },
                        { value: 'system', label: 'System', icon: '💻' }
                    ] as opt}
                        <button
                            onclick={() => setTheme(opt.value as Theme)}
                            class="flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all
                                   {currentTheme === opt.value
                                       ? 'bg-teal-500 text-white shadow-md'
                                       : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'}"
                        >
                            <span class="block text-lg mb-1">{opt.icon}</span>
                            {opt.label}
                        </button>
                    {/each}
                </div>
            </div>
        </section>
        {/if}

        <!-- Save Button (always visible) -->
        <div class="flex justify-end">
            <button
                onclick={saveSettings}
                disabled={saving}
                class="px-6 py-3 rounded-lg font-semibold text-white
                       bg-teal-500 hover:bg-teal-600 active:bg-teal-700
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors shadow-md hover:shadow-lg"
            >
                {saving ? 'Saving...' : 'Save Settings'}
            </button>
        </div>
    {/if}
</div>

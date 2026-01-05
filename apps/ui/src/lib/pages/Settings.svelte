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
        fetchTaxonomyStatus,
        startTaxonomySync,
        testBirdWeather,
        testBirdNET,
        type ClassifierStatus,
        type WildlifeModelStatus,
        type MaintenanceStats,
        type BackfillResult,
        type CacheStats,
        type CacheCleanupResult,
        type TaxonomySyncStatus
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
    let minConfidence = $state(0.4);
    let trustFrigateSublabel = $state(true);
    let displayCommonNames = $state(true);
    let scientificNamePrimary = $state(false);
    let selectedCameras = $state<string[]>([]);
    let retentionDays = $state(0);
    let blockedLabels = $state<string[]>([]);
    let newBlockedLabel = $state('');

    // Taxonomy Sync State
    let taxonomyStatus = $state<TaxonomySyncStatus | null>(null);
    let syncingTaxonomy = $state(false);
    let taxonomyPollInterval: any;

    // Location Settings
    let locationLat = $state<number | null>(null);
    let locationLon = $state<number | null>(null);
    let locationAuto = $state(true);

    // BirdWeather Settings
    let birdweatherEnabled = $state(false);
    let birdweatherStationToken = $state('');

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
    let testingBirdWeather = $state(false);
    let testingBirdNET = $state(false);
    let message = $state<{ type: 'success' | 'error'; text: string } | null>(null);
    let currentTheme: Theme = $state('system');

    // Dirty state check
    let isDirty = $derived.by(() => {
        const s = $settingsStore;
        if (!s) return false;
        
        const checks = [
            { key: 'frigateUrl', val: frigateUrl, store: s.frigate_url },
            { key: 'mqttServer', val: mqttServer, store: s.mqtt_server },
            { key: 'mqttPort', val: mqttPort, store: s.mqtt_port },
            { key: 'mqttAuth', val: mqttAuth, store: s.mqtt_auth },
            { key: 'mqttUsername', val: mqttUsername, store: s.mqtt_username || '' },
            { key: 'mqttPassword', val: mqttPassword, store: s.mqtt_password || '' },
            { key: 'audioTopic', val: audioTopic, store: s.audio_topic || 'birdnet/text' },
            { key: 'clipsEnabled', val: clipsEnabled, store: s.clips_enabled ?? true },
            { key: 'threshold', val: threshold, store: s.classification_threshold },
            { key: 'trustFrigateSublabel', val: trustFrigateSublabel, store: s.trust_frigate_sublabel ?? true },
            { key: 'displayCommonNames', val: displayCommonNames, store: s.display_common_names ?? true },
            { key: 'scientificNamePrimary', val: scientificNamePrimary, store: s.scientific_name_primary ?? false },
            { key: 'selectedCameras', val: JSON.stringify(selectedCameras), store: JSON.stringify(s.cameras || []) },
            { key: 'retentionDays', val: retentionDays, store: s.retention_days || 0 },
            { key: 'blockedLabels', val: JSON.stringify(blockedLabels), store: JSON.stringify(s.blocked_labels || []) },
            { key: 'cacheEnabled', val: cacheEnabled, store: s.media_cache_enabled ?? true },
            { key: 'cacheSnapshots', val: cacheSnapshots, store: s.media_cache_snapshots ?? true },
            { key: 'cacheClips', val: cacheClips, store: s.media_cache_clips ?? true },
            { key: 'cacheRetentionDays', val: cacheRetentionDays, store: s.media_cache_retention_days ?? 0 },
            { key: 'locationLat', val: locationLat, store: s.location_latitude ?? null },
            { key: 'locationLon', val: locationLon, store: s.location_longitude ?? null },
            { key: 'locationAuto', val: locationAuto, store: s.location_automatic ?? true },
            { key: 'birdweatherEnabled', val: birdweatherEnabled, store: s.birdweather_enabled ?? false },
            { key: 'birdweatherStationToken', val: birdweatherStationToken, store: s.birdweather_station_token || '' },
            { key: 'llmEnabled', val: llmEnabled, store: s.llm_enabled ?? false },
            { key: 'llmProvider', val: llmProvider, store: s.llm_provider ?? 'gemini' },
            { key: 'llmApiKey', val: llmApiKey, store: s.llm_api_key || '' },
            { key: 'llmModel', val: llmModel, store: s.llm_model ?? 'gemini-1.5-flash' },
            { key: 'cameraAudioMapping', val: JSON.stringify(cameraAudioMapping), store: JSON.stringify(s.camera_audio_mapping || {}) },
            { key: 'minConfidence', val: minConfidence, store: s.classification_min_confidence ?? 0.4 }
        ];

        const dirtyItem = checks.find(c => c.val !== c.store);
        if (dirtyItem) {
            console.log(`Dirty Setting: ${dirtyItem.key}`, { current: dirtyItem.val, saved: dirtyItem.store });
            return true;
        }
        return false;
    });

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
            loadCacheStats(),
            loadTaxonomyStatus()
        ]);

        taxonomyPollInterval = setInterval(loadTaxonomyStatus, 3000);
    });

    import { onDestroy } from 'svelte';
    onDestroy(() => {
        if (taxonomyPollInterval) clearInterval(taxonomyPollInterval);
    });

    async function loadTaxonomyStatus() {
        try {
            taxonomyStatus = await fetchTaxonomyStatus();
        } catch (e) {
            console.error('Failed to load taxonomy status', e);
        }
    }

    async function handleStartTaxonomySync() {
        if (taxonomyStatus?.is_running) return;
        syncingTaxonomy = true;
        try {
            await startTaxonomySync();
            await loadTaxonomyStatus();
        } catch (e: any) {
            alert('Failed to start taxonomy sync: ' + e.message);
        } finally {
            syncingTaxonomy = false;
        }
    }

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

    async function loadSettings(silent = false) {
        if (!silent) loading = true;
        if (!silent) message = null;
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
            minConfidence = settings.classification_min_confidence ?? 0.4;
            trustFrigateSublabel = settings.trust_frigate_sublabel ?? true;
            displayCommonNames = settings.display_common_names ?? true;
            scientificNamePrimary = settings.scientific_name_primary ?? false;
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
            // BirdWeather settings
            birdweatherEnabled = settings.birdweather_enabled ?? false;
            birdweatherStationToken = settings.birdweather_station_token ?? '';
            // LLM settings
            llmEnabled = settings.llm_enabled ?? false;
            llmProvider = settings.llm_provider ?? 'gemini';
            llmApiKey = settings.llm_api_key ?? '';
            llmModel = settings.llm_model ?? 'gemini-1.5-flash';
        } catch (e) {
            message = { type: 'error', text: 'Failed to load settings' };
        } finally {
            if (!silent) loading = false;
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
                classification_min_confidence: minConfidence,
                trust_frigate_sublabel: trustFrigateSublabel,
                display_common_names: displayCommonNames,
                scientific_name_primary: scientificNamePrimary,
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
                birdweather_enabled: birdweatherEnabled,
                birdweather_station_token: birdweatherStationToken,
                llm_enabled: llmEnabled,
                llm_provider: llmProvider,
                llm_api_key: llmApiKey,
                llm_model: llmModel
            });
            // Update store
            await settingsStore.load();
            // Sync local state to handle server-side normalization (e.g. stripped slashes)
            await loadSettings(true);
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

    async function handleTestBirdWeather() {
        testingBirdWeather = true;
        message = null;
        try {
            const result = await testBirdWeather(birdweatherStationToken);
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to test BirdWeather' };
        } finally {
            testingBirdWeather = false;
        }
    }

    async function handleTestBirdNET() {
        testingBirdNET = true;
        message = null;
        try {
            const result = await testBirdNET();
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to test BirdNET-Go' };
        } finally {
            testingBirdNET = false;
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

<div class="max-w-4xl mx-auto space-y-8 pb-20">
    <!-- Header -->
    <div class="flex items-center justify-between">
        <div>
            <h2 class="text-3xl font-black text-slate-900 dark:text-white tracking-tight">Settings</h2>
            <p class="text-sm text-slate-500 dark:text-slate-400 font-medium">Configure and manage your YA-WAMF instance</p>
        </div>
        <button
            onclick={loadSettings}
            disabled={loading}
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-bold rounded-xl
                   text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-800
                   border border-slate-200 dark:border-slate-700 shadow-sm
                   hover:bg-slate-50 dark:hover:bg-slate-700 hover:text-teal-600 dark:hover:text-teal-400
                   transition-all disabled:opacity-50"
        >
            <svg class="w-4 h-4 {loading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
        </button>
    </div>

    <!-- Status Messages -->
    {#if message}
        <div class="p-4 rounded-2xl animate-in slide-in-from-top-2 {message.type === 'success'
            ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20'
            : 'bg-red-500/10 text-red-700 dark:text-red-400 border border-red-500/20'}">
            <div class="flex items-center gap-3">
                {#if message.type === 'success'}
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg>
                {:else}
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                {/if}
                <span class="font-bold text-sm">{message.text}</span>
            </div>
        </div>
    {/if}

    {#if loading}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            {#each [1, 2, 3, 4] as _}
                <div class="h-48 bg-slate-100 dark:bg-slate-800/50 rounded-3xl animate-pulse border border-slate-200 dark:border-slate-700/50"></div>
            {/each}
        </div>
    {:else}
        <!-- Tab Navigation -->
        <SettingsTabs {activeTab} ontabchange={(tab) => activeTab = tab} />

        <div class="space-y-6">
            <!-- Connection Tab -->
            {#if activeTab === 'connection'}
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
                    <!-- Frigate Connection -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
                        <div class="flex items-center gap-3 mb-6">
                            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                            </div>
                            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Frigate NVR</h3>
                        </div>

                        <div class="space-y-6">
                            <div>
                                <label for="frigate-url" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Server URL</label>
                                <input
                                    id="frigate-url"
                                    type="url"
                                    bind:value={frigateUrl}
                                    placeholder="http://frigate:5000"
                                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all"
                                />
                            </div>

                            <div class="grid grid-cols-2 gap-3">
                                <button onclick={testConnection} disabled={testing} class="flex-1 px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 disabled:opacity-50">
                                    {testing ? 'Testing...' : 'Test Connection'}
                                </button>
                                <button onclick={loadCameras} disabled={camerasLoading} class="flex-1 px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-all disabled:opacity-50">
                                    {camerasLoading ? 'Scanning...' : 'Sync Cameras'}
                                </button>
                            </div>

                            <button onclick={handleTestBirdNET} disabled={testingBirdNET} class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 transition-all border border-indigo-500/20 disabled:opacity-50">
                                {testingBirdNET ? 'Simulating...' : 'Test MQTT Pipeline'}
                            </button>

                            <div class="pt-6 border-t border-slate-100 dark:border-slate-700/50">
                                <h4 class="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-4">MQTT Settings (Frigate Events)</h4>
                                <div class="space-y-4">
                                    <div class="grid grid-cols-3 gap-4">
                                        <div class="col-span-2">
                                            <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">MQTT Broker</label>
                                            <input type="text" bind:value={mqttServer} placeholder="mosquitto" class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none" />
                                        </div>
                                        <div>
                                            <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Port</label>
                                            <input type="number" bind:value={mqttPort} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none" />
                                        </div>
                                    </div>

                                    <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                                        <span class="text-xs font-bold text-slate-900 dark:text-white">Use Authentication</span>
                                        <button onclick={() => mqttAuth = !mqttAuth} class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {mqttAuth ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"><span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {mqttAuth ? 'translate-x-5' : 'translate-x-0'}"></span></button>
                                    </div>

                                    {#if mqttAuth}
                                        <div class="grid grid-cols-2 gap-4 animate-in fade-in zoom-in-95">
                                            <div><label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">User</label><input type="text" bind:value={mqttUsername} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" /></div>
                                            <div><label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Pass</label><input type="password" bind:value={mqttPassword} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" /></div>
                                        </div>
                                    {/if}
                                </div>
                            </div>

                            <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                                <div>
                                    <span class="block text-sm font-bold text-slate-900 dark:text-white">Fetch Video Clips</span>
                                    <span class="block text-[10px] text-slate-500 font-medium">Use Frigate recordings for reclassification</span>
                                </div>
                                <button 
                                    onclick={() => clipsEnabled = !clipsEnabled}
                                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none {clipsEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                                >
                                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out {clipsEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                                </button>
                            </div>
                        </div>
                    </section>

                    <!-- Camera Selection -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
                        <div class="flex items-center gap-3 mb-6">
                            <div class="w-10 h-10 rounded-2xl bg-blue-500/10 flex items-center justify-center text-blue-600 dark:text-blue-400">
                                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /></svg>
                            </div>
                            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Active Cameras</h3>
                        </div>
                        
                        <div class="space-y-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                            {#if availableCameras.length === 0}
                                <div class="p-8 text-center bg-slate-50 dark:bg-slate-900/30 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700">
                                    <p class="text-xs font-bold text-slate-400 uppercase tracking-widest">No Cameras Found</p>
                                </div>
                            {:else}
                                <div class="grid grid-cols-1 gap-2">
                                    {#each availableCameras as camera}
                                        <button
                                            class="flex items-center justify-between p-4 rounded-2xl border-2 transition-all group
                                                   {selectedCameras.includes(camera)
                                                       ? 'border-teal-500 bg-teal-500/5 text-teal-700 dark:text-teal-400'
                                                       : 'border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/30 text-slate-500 hover:border-teal-500/30'}"
                                            onclick={() => toggleCamera(camera)}
                                        >
                                            <span class="font-bold text-sm">{camera}</span>
                                            <div class="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all {selectedCameras.includes(camera) ? 'bg-teal-500 border-teal-500 scale-110' : 'border-slate-300 dark:border-slate-600 group-hover:border-teal-500/50'}">
                                                {#if selectedCameras.includes(camera)}<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" /></svg>{/if}
                                            </div>
                                        </button>
                                    {/each}
                                </div>
                            {/if}
                        </div>
                    </section>
                </div>
            {/if}

            <!-- Integrations Tab -->
            {#if activeTab === 'integrations'}
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
                    <!-- BirdNET-Go -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
                        <div class="flex items-center gap-3 mb-6">
                            <div class="w-10 h-10 rounded-2xl bg-amber-500/10 flex items-center justify-center text-amber-600 dark:text-amber-400">
                                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                            </div>
                            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">BirdNET-Go</h3>
                        </div>

                        <div class="space-y-6">
                            <div>
                                <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">MQTT Topic</label>
                                <input type="text" bind:value={audioTopic} placeholder="birdnet/text" class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none" />
                            </div>

                            <button onclick={handleTestBirdNET} disabled={testingBirdNET} class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-amber-500 hover:bg-amber-600 text-white transition-all shadow-lg shadow-amber-500/20 disabled:opacity-50">
                                {testingBirdNET ? 'Simulating...' : 'Test Audio detection'}
                            </button>

                            <div class="pt-4 border-t border-slate-100 dark:border-slate-700/50">
                                <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4">Sensor Mapping (Optional)</label>
                                <div class="space-y-3">
                                    {#each Object.keys(cameraAudioMapping) as camera}
                                        <div class="flex items-center gap-3">
                                            <span class="text-[10px] font-black text-slate-400 w-24 truncate uppercase">{camera}</span>
                                            <input type="text" bind:value={cameraAudioMapping[camera]} placeholder="Sensor ID" class="flex-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-xs font-bold" />
                                        </div>
                                    {/each}
                                    {#if availableCameras.length > 0 && Object.keys(cameraAudioMapping).length === 0}
                                        <p class="text-[10px] text-slate-400 font-bold italic">Add your Frigate cameras to map them to audio sensors.</p>
                                    {/if}
                                </div>
                            </div>
                        </div>
                    </section>

                    <!-- BirdWeather -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
                        <div class="flex items-center justify-between mb-6">
                            <div class="flex items-center gap-3">
                                <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" /></svg>
                                </div>
                                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">BirdWeather</h3>
                            </div>
                            <button onclick={() => birdweatherEnabled = !birdweatherEnabled} class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {birdweatherEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"><span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {birdweatherEnabled ? 'translate-x-5' : 'translate-x-0'}"></span></button>
                        </div>

                        <div class="space-y-6">
                            <div>
                                <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Station Token</label>
                                <input type="password" bind:value={birdweatherStationToken} placeholder="Your BirdWeather token" class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" />
                                <p class="mt-2 text-[10px] text-slate-500 font-bold italic">Available in your station settings under "BirdWeather Token".</p>
                            </div>
                            <button onclick={handleTestBirdWeather} disabled={testingBirdWeather || !birdweatherStationToken} class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50">
                                {testingBirdWeather ? 'Verifying...' : 'Test Connection'}
                            </button>
                        </div>
                    </section>

                    <!-- AI Intelligence -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
                        <div class="flex items-center justify-between mb-6">
                            <div class="flex items-center gap-3">
                                <div class="w-10 h-10 rounded-2xl bg-brand-500/10 flex items-center justify-center text-brand-500">
                                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                </div>
                                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">AI Insights</h3>
                            </div>
                            <button onclick={() => llmEnabled = !llmEnabled} class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {llmEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"><span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {llmEnabled ? 'translate-x-5' : 'translate-x-0'}"></span></button>
                        </div>

                        <div class="space-y-6">
                            <div class="grid grid-cols-2 gap-4">
                                <div><label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Provider</label><select bind:value={llmProvider} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"><option value="gemini">Google Gemini</option><option value="openai">OpenAI</option></select></div>
                                <div><label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Model</label><input type="text" bind:value={llmModel} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" /></div>
                            </div>
                            <div>
                                <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">API Key</label>
                                <input type="password" bind:value={llmApiKey} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" />
                            </div>
                        </div>
                    </section>

                    <!-- Location & Weather -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
                        <div class="flex items-center justify-between mb-6">
                            <div class="flex items-center gap-3">
                                <div class="w-10 h-10 rounded-2xl bg-orange-500/10 flex items-center justify-center text-orange-600 dark:text-orange-400">
                                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
                                </div>
                                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Location</h3>
                            </div>
                            <button onclick={() => locationAuto = !locationAuto} class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {locationAuto ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"><span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {locationAuto ? 'translate-x-5' : 'translate-x-0'}"></span></button>
                        </div>

                        <div class="space-y-6">
                            <p class="text-xs font-bold text-slate-500 leading-relaxed uppercase tracking-wider">Used for localized weather context during detections.</p>
                            {#if !locationAuto}
                                <div class="grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-2">
                                    <div><label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Latitude</label><input type="number" step="any" bind:value={locationLat} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" /></div>
                                    <div><label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Longitude</label><input type="number" step="any" bind:value={locationLon} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" /></div>
                                </div>
                            {:else}
                                <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 text-teal-600 dark:text-teal-400 text-xs font-black uppercase tracking-widest text-center">Auto-detect via IP enabled</div>
                            {/if}
                        </div>
                    </section>
                </div>
            {/if}

            <!-- Detection Tab -->
            {#if activeTab === 'detection'}
                <div class="space-y-6">
                    <!-- Classification Model -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
                        <div class="flex items-center gap-3 mb-8">
                            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                            </div>
                            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Classification Engine</h3>
                        </div>
                        <ModelManager />
                    </section>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <!-- Tuning -->
                        <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
                            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400 mb-6">Fine Tuning</h4>
                            
                            <div class="space-y-8">
                                <div>
                                    <div class="flex justify-between mb-4">
                                        <label class="text-sm font-black text-slate-900 dark:text-white">Confidence Threshold</label>
                                        <span class="px-2 py-1 bg-teal-500 text-white text-[10px] font-black rounded-lg">{(threshold * 100).toFixed(0)}%</span>
                                    </div>
                                    <input type="range" min="0" max="1" step="0.05" bind:value={threshold} class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-teal-500" />
                                    <div class="flex justify-between mt-2"><span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Loose</span><span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Strict</span></div>
                                </div>

                                <div>
                                    <div class="flex justify-between mb-4">
                                        <label class="text-sm font-black text-slate-900 dark:text-white">Minimum Confidence Floor</label>
                                        <span class="px-2 py-1 bg-amber-500 text-white text-[10px] font-black rounded-lg">{(minConfidence * 100).toFixed(0)}%</span>
                                    </div>
                                    <input type="range" min="0" max="1" step="0.05" bind:value={minConfidence} class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-amber-500" />
                                    <div class="flex justify-between mt-2">
                                        <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Capture All</span>
                                        <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Reject Unsure</span>
                                    </div>
                                    <p class="mt-3 text-[10px] text-slate-500 font-bold leading-tight">Events below this floor are ignored completely. Events between floor and threshold are saved as "Unknown Bird".</p>
                                </div>

                                <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 flex items-center justify-between gap-4">
                                    <div class="flex-1">
                                        <span class="block text-sm font-black text-slate-900 dark:text-white">Trust Frigate Sublabels</span>
                                        <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">Skip internal classification if Frigate identified species</span>
                                    </div>
                                    <button onclick={() => trustFrigateSublabel = !trustFrigateSublabel} class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {trustFrigateSublabel ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"><span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {trustFrigateSublabel ? 'translate-x-5' : 'translate-x-0'}"></span></button>
                                </div>
                            </div>
                        </section>

                        <!-- Naming -->
                        <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
                            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400 mb-6">Bird Naming Style</h4>
                            
                            <div class="flex flex-col gap-3">
                                {#each [
                                    { id: 'standard', title: 'Standard', sub: 'Common names primary, scientific subtitles.', active: displayCommonNames && !scientificNamePrimary, action: () => { displayCommonNames = true; scientificNamePrimary = false; } },
                                    { id: 'hobbyist', title: 'Hobbyist', sub: 'Scientific names primary, common subtitles.', active: displayCommonNames && scientificNamePrimary, action: () => { displayCommonNames = true; scientificNamePrimary = true; } },
                                    { id: 'scientific', title: 'Strictly Scientific', sub: 'Only show scientific names. Hides common names.', active: !displayCommonNames, action: () => { displayCommonNames = false; } }
                                ] as mode}
                                    <button onclick={mode.action} class="flex items-center gap-4 p-4 rounded-2xl border-2 text-left transition-all {mode.active ? 'border-teal-500 bg-teal-500/5' : 'border-slate-100 dark:border-slate-700/50 hover:border-teal-500/20'}">
                                        <div class="w-5 h-5 rounded-full border-2 flex items-center justify-center {mode.active ? 'border-teal-500 bg-teal-500' : 'border-slate-300 dark:border-slate-600'}">
                                            {#if mode.active}<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M5 13l4 4L19 7" /></svg>{/if}
                                        </div>
                                        <div>
                                            <p class="text-sm font-black text-slate-900 dark:text-white leading-none">{mode.title}</p>
                                            <p class="text-[10px] font-bold text-slate-500 mt-1">{mode.sub}</p>
                                        </div>
                                    </button>
                                {/each}
                            </div>
                        </section>
                    </div>

                    <!-- Blocked Labels -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
                        <div class="flex items-center justify-between mb-6">
                            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400">Blocked Labels</h4>
                            <span class="px-2 py-0.5 bg-red-500/10 text-red-500 text-[9px] font-black rounded uppercase">Ignored by Discovery</span>
                        </div>
                        
                        <div class="flex gap-2 mb-6">
                            <input bind:value={newBlockedLabel} onkeydown={(e) => e.key === 'Enter' && addBlockedLabel()} placeholder="e.g. background" class="flex-1 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" />
                            <button onclick={addBlockedLabel} disabled={!newBlockedLabel.trim()} class="px-6 py-3 bg-slate-900 dark:bg-slate-700 text-white text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-slate-800 transition-all">Add</button>
                        </div>

                        <div class="flex flex-wrap gap-2">
                            {#each blockedLabels as label}
                                <span class="group flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300">
                                    {label}
                                    <button onclick={() => removeBlockedLabel(label)} class="text-slate-400 hover:text-red-500 transition-colors">✕</button>
                                </span>
                            {/each}
                            {#if blockedLabels.length === 0}<p class="text-xs font-bold text-slate-400 italic">No labels blocked yet.</p>{/if}
                        </div>
                    </section>
                </div>
            {/if}

            <!-- Data Tab -->
            {#if activeTab === 'data'}
                <div class="space-y-6">
                    <!-- Maintenance Stats -->
                    {#if maintenanceStats}
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {#each [
                                { label: 'Total Records', val: maintenanceStats.total_detections.toLocaleString(), color: 'text-teal-500' },
                                { label: 'Oldest Seen', val: maintenanceStats.oldest_detection ? new Date(maintenanceStats.oldest_detection).toLocaleDateString() : 'N/A', color: 'text-blue-500' },
                                { label: 'Retention', val: retentionDays === 0 ? '∞' : `${retentionDays} Days`, color: 'text-indigo-500' },
                                { label: 'Pending GC', val: maintenanceStats.detections_to_cleanup.toLocaleString(), color: maintenanceStats.detections_to_cleanup > 0 ? 'text-amber-500' : 'text-slate-400' }
                            ] as stat}
                                <div class="bg-white dark:bg-slate-800/50 p-6 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 shadow-sm text-center">
                                    <p class="text-2xl font-black {stat.color} tracking-tight">{stat.val}</p>
                                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{stat.label}</p>
                                </div>
                            {/each}
                        </div>
                    {/if}

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
                        <!-- Retention & Cleanup -->
                        <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
                            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight mb-6">Retention Policy</h3>
                            <div class="space-y-6">
                                <div>
                                    <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">History Duration</label>
                                    <select bind:value={retentionDays} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all"><option value={0}>Keep Everything (∞)</option><option value={7}>1 Week</option><option value={14}>2 Weeks</option><option value={30}>1 Month</option><option value={90}>3 Months</option><option value={365}>1 Year</option></select>
                                </div>
                                <div class="pt-4 border-t border-slate-100 dark:border-slate-700/50 flex flex-col gap-3">
                                    <button onclick={handleCleanup} disabled={cleaningUp || retentionDays === 0 || (maintenanceStats?.detections_to_cleanup ?? 0) === 0} class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-amber-500 hover:bg-amber-600 text-white transition-all shadow-lg shadow-amber-500/20 disabled:opacity-50">{cleaningUp ? 'Cleaning...' : 'Purge Old Records'}</button>
                                    <p class="text-[10px] text-center text-slate-400 font-bold italic">Automatic cleanup runs daily at 3 AM</p>
                                </div>
                            </div>
                        </section>

                        <!-- Media Cache -->
                        <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
                            <div class="flex items-center justify-between mb-6">
                                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Media Cache</h3>
                                <button onclick={() => cacheEnabled = !cacheEnabled} class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {cacheEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"><span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {cacheEnabled ? 'translate-x-5' : 'translate-x-0'}"></span></button>
                            </div>
                            
                            {#if cacheEnabled}
                                <div class="space-y-6 animate-in fade-in slide-in-from-top-2">
                                    <div class="grid grid-cols-2 gap-3">
                                        <button onclick={() => cacheSnapshots = !cacheSnapshots} class="p-4 rounded-2xl border-2 transition-all text-center {cacheSnapshots ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"><p class="text-xs font-black uppercase tracking-widest">Snapshots</p></button>
                                        <button onclick={() => cacheClips = !cacheClips} class="p-4 rounded-2xl border-2 transition-all text-center {cacheClips ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"><p class="text-xs font-black uppercase tracking-widest">Video Clips</p></button>
                                    </div>
                                    <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                                        <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">Cache Size</span>
                                        <span class="text-sm font-black text-slate-900 dark:text-white">{cacheStats?.total_size_mb ?? 0} MB</span>
                                    </div>
                                    <button onclick={handleCacheCleanup} disabled={cleaningCache} class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-900 dark:bg-slate-700 text-white hover:bg-slate-800 transition-all">{cleaningCache ? 'Cleaning...' : 'Clear Cached Files'}</button>
                                </div>
                            {/if}
                        </section>
                    </div>

                    <!-- Taxonomy Sync -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
                        <div class="flex items-center justify-between mb-6">
                            <div>
                                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Taxonomy Repair</h3>
                                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">Connect scientific and common names</p>
                            </div>
                            {#if taxonomyStatus?.is_running}
                                <div class="flex items-center gap-2 px-3 py-1 rounded-full bg-teal-500/10 text-teal-600 animate-pulse">
                                    <div class="w-1.5 h-1.5 rounded-full bg-teal-500"></div>
                                    <span class="text-[10px] font-black uppercase tracking-widest">Syncing</span>
                                </div>
                            {/if}
                        </div>

                        {#if taxonomyStatus && (taxonomyStatus.is_running || taxonomyStatus.total > 0)}
                            <div class="mb-6 space-y-3">
                                <div class="flex justify-between text-[10px] font-black uppercase tracking-widest">
                                    <span class="text-slate-400">{taxonomyStatus.current_item || 'Repairing Database'}</span>
                                    <span class="text-teal-500">{taxonomyStatus.processed} / {taxonomyStatus.total}</span>
                                </div>
                                <div class="w-full h-3 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden border border-slate-200 dark:border-slate-700">
                                    <div class="h-full bg-gradient-to-r from-teal-500 to-emerald-400 transition-all duration-1000 ease-out" style="width: {(taxonomyStatus.processed / (taxonomyStatus.total || 1)) * 100}%"></div>
                                </div>
                            </div>
                        {/if}

                        <button onclick={handleStartTaxonomySync} disabled={taxonomyStatus?.is_running || syncingTaxonomy} class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 flex items-center justify-center gap-3">
                            {#if syncingTaxonomy || taxonomyStatus?.is_running}<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>{/if}
                            Run Full Taxonomy Repair
                        </button>
                    </section>

                    <!-- Missed Detections (Backfill) -->
                    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
                        <div class="flex items-center gap-3 mb-6">
                            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg></div>
                            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Missed Detections</h3>
                        </div>
                        <p class="text-xs font-bold text-slate-500 leading-relaxed uppercase tracking-wider mb-6">Query Frigate history to fetch and classify past events.</p>
                        
                        <div class="space-y-6">
                            <div>
                                <label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Time Window</label>
                                <select bind:value={backfillDateRange} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"><option value="day">Last 24 Hours</option><option value="week">Last Week</option><option value="month">Last Month</option><option value="custom">Custom Range</option></select>
                            </div>

                            {#if backfillDateRange === 'custom'}
                                <div class="grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-2">
                                    <div><label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Start</label><input type="date" bind:value={backfillStartDate} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" /></div>
                                    <div><label class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">End</label><input type="date" bind:value={backfillEndDate} class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm" /></div>
                                </div>
                            {/if}

                            {#if backfillResult}
                                <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 grid grid-cols-4 gap-2 text-center">
                                    <div><p class="text-sm font-black text-slate-900 dark:text-white">{backfillResult.processed}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Total</p></div>
                                    <div><p class="text-sm font-black text-emerald-500">{backfillResult.new_detections}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">New</p></div>
                                    <div><p class="text-sm font-black text-slate-400">{backfillResult.skipped}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Skip</p></div>
                                    <div><p class="text-sm font-black text-red-500">{backfillResult.errors}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Err</p></div>
                                </div>
                            {/if}

                            <button onclick={handleBackfill} disabled={backfilling} class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 flex items-center justify-center gap-3">
                                {#if backfilling}<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>{/if}
                                {backfilling ? 'Analyzing Frigate...' : 'Scan History'}
                            </button>
                        </div>
                    </section>
                </div>
            {/if}

            <!-- Appearance Tab -->
            {#if activeTab === 'appearance'}
                <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
                    <div class="flex items-center gap-3 mb-8">
                        <div class="w-10 h-10 rounded-2xl bg-pink-500/10 flex items-center justify-center text-pink-600 dark:text-pink-400">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" /></svg>
                        </div>
                        <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Theme & Look</h3>
                    </div>

                    <div class="grid grid-cols-3 gap-4">
                        {#each [
                            { value: 'light', label: 'Light', icon: '☀️' },
                            { value: 'dark', label: 'Dark', icon: '🌙' },
                            { value: 'system', label: 'System', icon: '💻' }
                        ] as opt}
                            <button
                                onclick={() => setTheme(opt.value as Theme)}
                                class="flex flex-col items-center gap-3 p-6 rounded-2xl border-2 transition-all
                                       {currentTheme === opt.value
                                           ? 'bg-teal-500 border-teal-500 text-white shadow-xl shadow-teal-500/20'
                                           : 'bg-white dark:bg-slate-900/50 border-slate-100 dark:border-slate-700/50 text-slate-500 hover:border-teal-500/30'}"
                            >
                                <span class="text-3xl">{opt.icon}</span>
                                <span class="text-xs font-black uppercase tracking-widest">{opt.label}</span>
                            </button>
                        {/each}
                    </div>
                </section>
            {/if}
        </div>

        <!-- Floating Action Button: Save -->
        {#if isDirty}
            <div class="fixed bottom-8 left-1/2 -translate-x-1/2 w-full max-w-4xl px-4 z-40 animate-in slide-in-from-bottom-10 duration-500">
                <div class="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-4 rounded-3xl border border-slate-200/50 dark:border-white/5 shadow-2xl flex items-center justify-between gap-6 ring-1 ring-teal-500/20">
                    <div class="flex-1 hidden sm:block">
                        <p class="text-xs font-black text-teal-600 dark:text-teal-400 uppercase tracking-widest ml-4">Unsaved Changes</p>
                    </div>
                    <button
                        onclick={saveSettings}
                        disabled={saving}
                        class="flex-1 sm:flex-none px-12 py-4 rounded-2xl font-black uppercase tracking-widest text-xs text-white
                               bg-teal-500 hover:bg-teal-600 active:scale-95
                               disabled:opacity-50 disabled:cursor-not-allowed
                               transition-all shadow-xl shadow-teal-500/40"
                    >
                        {saving ? 'Saving...' : 'Apply Settings'}
                    </button>
                </div>
            </div>
        {/if}
    {/if}
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
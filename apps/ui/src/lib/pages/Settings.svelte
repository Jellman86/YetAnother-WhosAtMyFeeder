<script lang="ts">
    import { onMount } from 'svelte';
    import {
        fetchSettings,
        updateSettings,
        testFrigateConnection,
        fetchFrigateConfig,
        fetchClassifierStatus,
        downloadDefaultModel,
        fetchMaintenanceStats,
        runCleanup,
        type ClassifierStatus,
        type MaintenanceStats
    } from '../api';
    import { theme, type Theme } from '../stores/theme';

    let frigateUrl = $state('');
    let mqttServer = $state('');
    let mqttPort = $state(1883);
    let mqttAuth = $state(false);
    let mqttUsername = $state('');
    let mqttPassword = $state('');
    let threshold = $state(0.7);
    let selectedCameras = $state<string[]>([]);
    let retentionDays = $state(0);

    let availableCameras = $state<string[]>([]);
    let camerasLoading = $state(false);

    let loading = $state(true);
    let saving = $state(false);
    let testing = $state(false);
    let message = $state<{ type: 'success' | 'error'; text: string } | null>(null);
    let currentTheme: Theme = $state('system');

    let classifierStatus = $state<ClassifierStatus | null>(null);
    let downloadingModel = $state(false);

    let maintenanceStats = $state<MaintenanceStats | null>(null);
    let cleaningUp = $state(false);

    theme.subscribe(t => currentTheme = t);

    onMount(async () => {
        await Promise.all([
            loadSettings(),
            loadCameras(),
            loadClassifierStatus(),
            loadMaintenanceStats()
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

    async function loadClassifierStatus() {
        try {
            classifierStatus = await fetchClassifierStatus();
        } catch (e) {
            console.error('Failed to load classifier status', e);
        }
    }

    async function handleDownloadModel() {
        downloadingModel = true;
        message = null;
        try {
            const result = await downloadDefaultModel();
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
                // Reload classifier status
                await loadClassifierStatus();
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to download model' };
        } finally {
            downloadingModel = false;
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
            threshold = settings.classification_threshold;
            selectedCameras = settings.cameras || [];
            retentionDays = settings.retention_days || 0;
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
            // If we fail to load cameras, we still show the selected ones if they exist
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
                classification_threshold: threshold,
                cameras: selectedCameras,
                retention_days: retentionDays
            });
            message = { type: 'success', text: 'Settings saved successfully!' };
            await loadMaintenanceStats();  // Refresh stats after save
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
</script>

<div class="max-w-2xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Settings</h2>
        <button
            onclick={loadSettings}
            disabled={loading}
            class="text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
        >
            ↻ Refresh
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
                               bg-brand-500 hover:bg-brand-600 text-white
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

        <!-- Classification Settings -->
        <section class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-6 shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                🎯 Classification
            </h3>

            <!-- Model Status -->
            {#if classifierStatus}
                <div class="mb-4 p-3 rounded-lg {classifierStatus.enabled
                    ? 'bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800'
                    : 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800'}">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                            {#if classifierStatus.enabled}
                                <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                                <span class="text-sm font-medium text-emerald-700 dark:text-emerald-400">
                                    Model Loaded ({classifierStatus.labels_count} species)
                                </span>
                            {:else}
                                <span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                                <span class="text-sm font-medium text-amber-700 dark:text-amber-400">
                                    Classification Disabled
                                </span>
                            {/if}
                        </div>
                        {#if !classifierStatus.enabled}
                            <button
                                onclick={handleDownloadModel}
                                disabled={downloadingModel}
                                class="px-3 py-1.5 text-sm font-medium rounded-lg
                                       bg-brand-500 hover:bg-brand-600 text-white
                                       transition-colors disabled:opacity-50 flex items-center gap-2"
                            >
                                {#if downloadingModel}
                                    <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    Downloading...
                                {:else}
                                    Download Default Model
                                {/if}
                            </button>
                        {/if}
                    </div>
                    {#if classifierStatus.error && !downloadingModel}
                        <p class="mt-2 text-xs text-amber-600 dark:text-amber-400">
                            {classifierStatus.error}
                        </p>
                    {/if}
                    {#if downloadingModel}
                        <p class="mt-2 text-xs text-slate-500 dark:text-slate-400">
                            Downloading Google AIY Bird Classifier (~20MB)...
                        </p>
                    {/if}
                </div>
            {/if}

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
        </section>

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

        <!-- Save Button -->
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
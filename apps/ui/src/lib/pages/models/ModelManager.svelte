<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { fetchAvailableModels, fetchInstalledModels, downloadModel, fetchDownloadStatus, activateModel, type ModelMetadata, type InstalledModel, type DownloadProgress } from '../../api';

    let availableModels = $state<ModelMetadata[]>([]);
    let installedModels = $state<InstalledModel[]>([]);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let downloadStatuses = $state<Record<string, DownloadProgress>>({});
    let activating = $state<string | null>(null); 

    let pollInterval: any;

    onMount(async () => {
        await loadData();
        // Start polling for downloads
        pollInterval = setInterval(pollDownloads, 2000);
    });

    onDestroy(() => {
        if (pollInterval) clearInterval(pollInterval);
    });

    async function loadData() {
        loading = true;
        error = null;
        try {
            const [available, installed] = await Promise.all([
                fetchAvailableModels(),
                fetchInstalledModels()
            ]);
            availableModels = available;
            installedModels = installed;
        } catch (e) {
            console.error(e);
            error = "Failed to load models";
        } finally {
            loading = false;
        }
    }

    async function pollDownloads() {
        const activeIds = Object.keys(downloadStatuses).filter(id => 
            downloadStatuses[id].status === 'downloading' || downloadStatuses[id].status === 'pending'
        );

        for (const id of activeIds) {
            try {
                const status = await fetchDownloadStatus(id);
                if (status) {
                    downloadStatuses[id] = status;
                    if (status.status === 'completed') {
                        // Refresh installed list
                        installedModels = await fetchInstalledModels();
                    }
                }
            } catch (e) {
                console.error(`Failed to poll status for ${id}`, e);
            }
        }
    }

    function isInstalled(modelId: string): boolean {
        return installedModels.some(m => m.id === modelId);
    }

    function isActive(modelId: string): boolean {
        return installedModels.some(m => m.id === modelId && m.is_active);
    }

    async function handleDownload(model: ModelMetadata) {
        if (downloadStatuses[model.id]?.status === 'downloading') return;
        
        try {
            await downloadModel(model.id);
            // Initialize local status to trigger polling
            downloadStatuses[model.id] = {
                model_id: model.id,
                status: 'downloading',
                progress: 0
            };
        } catch (e) {
            console.error(e);
            alert("Failed to start download");
        }
    }

    async function handleActivate(modelId: string) {
        if (activating) return;
        activating = modelId;
        try {
            await activateModel(modelId);
            installedModels = await fetchInstalledModels();
        } catch (e) {
            console.error(e);
            alert("Failed to activate model");
        } finally {
            activating = null;
        }
    }
</script>

<div class="space-y-6">
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Model Manager</h2>
        <button 
            onclick={loadData}
            class="p-2 text-slate-500 hover:text-teal-500 transition-colors"
            title="Refresh"
        >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
        </button>
    </div>

    {#if loading}
        <div class="flex justify-center py-12">
            <div class="w-8 h-8 border-4 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
    {:else if error}
        <div class="p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-800">
            {error}
        </div>
    {:else}
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {#each availableModels as model}
                {@const installed = isInstalled(model.id)}
                {@const active = isActive(model.id)}
                {@const download = downloadStatuses[model.id]}
                
                <div class="bg-white dark:bg-slate-800 rounded-xl border-2 transition-all duration-200 flex flex-col
                            {active ? 'border-teal-500 shadow-lg shadow-teal-500/10' : 'border-slate-200 dark:border-slate-700'}">
                    
                    <div class="p-5 flex-1">
                        <div class="flex justify-between items-start mb-2">
                            <h3 class="text-lg font-bold text-slate-900 dark:text-white">{model.name}</h3>
                            {#if active}
                                <span class="px-2 py-1 text-xs font-bold bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300 rounded-full">
                                    ACTIVE
                                </span>
                            {/if}
                        </div>
                        
                        <p class="text-sm text-slate-500 dark:text-slate-400 mb-4 h-10 line-clamp-2">
                            {model.description}
                        </p>

                        <div class="grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-400 mb-4">
                            <div class="flex flex-col p-2 bg-slate-50 dark:bg-slate-700/50 rounded-lg">
                                <span class="text-slate-400 dark:text-slate-500">Architecture</span>
                                <span class="font-medium">{model.architecture}</span>
                            </div>
                            <div class="flex flex-col p-2 bg-slate-50 dark:bg-slate-700/50 rounded-lg">
                                <span class="text-slate-400 dark:text-slate-500">Size</span>
                                <span class="font-medium">{model.file_size_mb} MB</span>
                            </div>
                            <div class="flex flex-col p-2 bg-slate-50 dark:bg-slate-700/50 rounded-lg">
                                <span class="text-slate-400 dark:text-slate-500">Accuracy</span>
                                <span class="font-medium {model.accuracy_tier === 'High' ? 'text-emerald-600 dark:text-emerald-400' : ''}">
                                    {model.accuracy_tier}
                                </span>
                            </div>
                            <div class="flex flex-col p-2 bg-slate-50 dark:bg-slate-700/50 rounded-lg">
                                <span class="text-slate-400 dark:text-slate-500">Speed</span>
                                <span class="font-medium {model.inference_speed === 'Fast' ? 'text-emerald-600 dark:text-emerald-400' : ''}">
                                    {model.inference_speed}
                                </span>
                            </div>
                        </div>

                        {#if download && (download.status === 'downloading' || download.status === 'pending')}
                            <div class="mt-4">
                                <div class="flex justify-between text-xs mb-1">
                                    <span class="text-teal-600 dark:text-teal-400 font-medium">Downloading...</span>
                                    <span class="text-slate-500">{download.progress.toFixed(0)}%</span>
                                </div>
                                <div class="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
                                    <div class="bg-teal-500 h-full transition-all duration-300" style="width: {download.progress}%"></div>
                                </div>
                            </div>
                        {/if}
                    </div>

                    <div class="p-4 border-t border-slate-100 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 rounded-b-xl">
                        {#if installed}
                            {#if active}
                                <button
                                    disabled
                                    class="w-full px-4 py-2 text-sm font-medium text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-900/20 rounded-lg opacity-75 cursor-default"
                                >
                                    Currently Active
                                </button>
                            {:else}
                                <button
                                    onclick={() => handleActivate(model.id)}
                                    disabled={activating !== null}
                                    class="w-full px-4 py-2 text-sm font-medium text-white bg-teal-500 hover:bg-teal-600 rounded-lg transition-colors disabled:opacity-50"
                                >
                                    {activating === model.id ? 'Activating...' : 'Activate'}
                                </button>
                            {/if}
                        {:else if download?.status === 'downloading' || download?.status === 'pending'}
                            <button
                                disabled
                                class="w-full px-4 py-2 text-sm font-medium text-slate-400 bg-slate-100 dark:bg-slate-700 rounded-lg cursor-default flex items-center justify-center gap-2"
                            >
                                <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Downloading...
                            </button>
                        {:else}
                            <button
                                onclick={() => handleDownload(model)}
                                class="w-full px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-600 rounded-lg transition-colors flex items-center justify-center gap-2"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                </svg>
                                Download
                            </button>
                        {/if}
                    </div>
                </div>
            {/each}
        </div>
    {/if}
</div>
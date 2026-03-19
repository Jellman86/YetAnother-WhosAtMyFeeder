<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { fetchAvailableModels, fetchInstalledModels, downloadModel, fetchDownloadStatus, activateModel, checkHealth, fetchClassifierStatus, getVisibleTieredModelLineup, type ModelMetadata, type InstalledModel, type DownloadProgress, type ClassifierStatus } from '../../api';
    import { jobProgressStore } from '../../stores/job_progress.svelte';
    import { startModelDownloadProgress, syncModelDownloadProgress } from './model_download_progress';

    let availableModels = $state<ModelMetadata[]>([]);
    let installedModels = $state<InstalledModel[]>([]);
    let health = $state<any>(null);
    let classifierStatus = $state<ClassifierStatus | null>(null);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let downloadStatuses = $state<Record<string, DownloadProgress>>({});
    let activating = $state<string | null>(null); 
    let showAdvancedModels = $state(false);


    function formatMetadataLabel(value: string): string {
        return value
            .split(/[_-]+/g)
            .filter(Boolean)
            .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase())
            .join(' ');
    }

    function tierLabel(tier: string): string {
        switch (tier) {
            case 'cpu_only':
                return 'CPU only';
            default:
                return formatMetadataLabel(tier);
        }
    }

    function scopeLabel(scope: string): string {
        switch (scope) {
            case 'birds_only':
                return 'Birds only';
            case 'wildlife_wide':
                return 'Broad wildlife';
            default:
                return formatMetadataLabel(scope);
        }
    }

    function statusLabel(status: string): string {
        return formatMetadataLabel(status);
    }

    function tierChipClass(tier: string): string {
        switch (tier) {
            case 'cpu_only':
                return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20';
            case 'large':
                return 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/20';
            case 'advanced':
                return 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20';
            default:
                return 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';
        }
    }

    function statusChipClass(status: string): string {
        switch (status) {
            case 'stable':
                return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20';
            case 'beta':
                return 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/20';
            case 'experimental':
                return 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20';
            default:
                return 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';
        }
    }

    function formatRamLabel(model: ModelMetadata): string | null {
        if (model.estimated_ram_mb == null) return null;
        if (model.estimated_ram_mb >= 1024) {
            const ramGb = model.estimated_ram_mb / 1024;
            const formatted = Number.isInteger(ramGb) ? ramGb.toFixed(0) : ramGb.toFixed(1);
            return `~${formatted} GB RAM`;
        }
        return `~${model.estimated_ram_mb} MB RAM`;
    }

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
            const [available, installed, healthData, classifierData] = await Promise.all([
                fetchAvailableModels(),
                fetchInstalledModels(),
                checkHealth(),
                fetchClassifierStatus().catch((e) => {
                    console.warn("Failed to load classifier status in model manager", e);
                    return null;
                })
            ]);
            availableModels = getVisibleTieredModelLineup(available, true);
            installedModels = installed;
            health = healthData;
            classifierStatus = classifierData;
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
                const model = availableModels.find((entry) => entry.id === id);
                if (status) {
                    downloadStatuses[id] = status;
                    if (model) {
                        syncModelDownloadProgress(jobProgressStore, model, status);
                    }
                    if (status.status === 'completed') {
                        // Refresh installed list
                        installedModels = await fetchInstalledModels();
                    }
                } else {
                    const errorStatus = {
                        model_id: id,
                        status: 'error' as const,
                        progress: downloadStatuses[id]?.progress ?? 0,
                        error: 'Download status unavailable'
                    };
                    downloadStatuses[id] = errorStatus;
                    if (model) {
                        syncModelDownloadProgress(jobProgressStore, model, errorStatus);
                    }
                }
            } catch (e) {
                console.error(`Failed to poll status for ${id}`, e);
                const model = availableModels.find((entry) => entry.id === id);
                const message = e instanceof Error ? e.message : 'Failed to refresh download status';
                const errorStatus = {
                    model_id: id,
                    status: 'error' as const,
                    progress: downloadStatuses[id]?.progress ?? 0,
                    error: message
                };
                downloadStatuses[id] = errorStatus;
                if (model) {
                    syncModelDownloadProgress(jobProgressStore, model, errorStatus);
                }
            }
        }
    }

    function isInstalled(modelId: string): boolean {
        return installedModels.some(m => m.id === modelId);
    }

    function isActive(modelId: string): boolean {
        return installedModels.some(m => m.id === modelId && m.is_active);
    }

    function getProviderSupport(model: ModelMetadata): string[] {
        if (Array.isArray(model.supported_inference_providers) && model.supported_inference_providers.length > 0) {
            return model.supported_inference_providers;
        }
        if (model.runtime === 'onnx') return ['cpu', 'cuda', 'intel_cpu', 'intel_gpu'];
        if (model.runtime === 'tflite') return ['cpu'];
        return ['cpu'];
    }

    function providerLabel(provider: string): string {
        switch (provider) {
            case 'cpu':
                return 'CPU';
            case 'cuda':
                return 'NVIDIA CUDA';
            case 'intel_cpu':
                return 'Intel CPU (OpenVINO)';
            case 'intel_gpu':
                return 'Intel GPU (OpenVINO)';
            default:
                return provider;
        }
    }

    function providerChipClass(provider: string): string {
        switch (provider) {
            case 'cuda':
                return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20';
            case 'intel_gpu':
                return 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-500/20';
            case 'intel_cpu':
                return 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20';
            default:
                return 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';
        }
    }

    function getDynamicProviderChips(model: ModelMetadata, active: boolean): Array<{ label: string; className: string; title: string }> {
        if (!active) return [];

        const compileDevice = (classifierStatus?.openvino_model_compile_device || '').toUpperCase();
        const compileForIntelGpuFailed = classifierStatus?.openvino_model_compile_ok === false && compileDevice === 'GPU';
        const compileForIntelCpuFailed = classifierStatus?.openvino_model_compile_ok === false && compileDevice === 'CPU';
        const providerOrder = ['cpu', 'cuda', 'intel_cpu', 'intel_gpu'];
        const activeProvider = classifierStatus?.active_provider ?? null;
        const supportedProviders = getProviderSupport(model);

        return providerOrder
            .filter((p) => supportedProviders.includes(p))
            .map((provider) => {
                const baseLabel = providerLabel(provider);
                const isActive = activeProvider === provider;

                if (isActive) {
                    return {
                        label: `${baseLabel}: Active`,
                        className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
                        title: 'Currently active inference provider'
                    };
                }

                if (provider === 'cpu') {
                    return {
                        label: `${baseLabel}: Available`,
                        className: 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20',
                        title: 'CPU fallback path is available'
                    };
                }

                if (provider === 'cuda') {
                    const available = classifierStatus?.cuda_available ?? false;
                    return {
                        label: `${baseLabel}: ${available ? 'Available' : 'Unavailable'}`,
                        className: available
                            ? 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20'
                            : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
                        title: available ? 'CUDA provider is available on this host' : 'CUDA provider is not available on this host'
                    };
                }

                if (provider === 'intel_cpu') {
                    if (compileForIntelCpuFailed) {
                        return {
                            label: `${baseLabel}: Fallback`,
                            className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
                            title: 'OpenVINO CPU compile failed and fallback is active'
                        };
                    }
                    const available = classifierStatus?.intel_cpu_available ?? false;
                    return {
                        label: `${baseLabel}: ${available ? 'Available' : 'Unavailable'}`,
                        className: available
                            ? 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-500/20'
                            : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
                        title: available ? 'OpenVINO CPU is available on this host' : 'OpenVINO CPU is not available on this host'
                    };
                }

                if (compileForIntelGpuFailed) {
                    return {
                        label: `${baseLabel}: Fallback`,
                        className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
                        title: 'OpenVINO GPU compile failed and fallback is active'
                    };
                }
                const available = classifierStatus?.intel_gpu_available ?? false;
                return {
                    label: `${baseLabel}: ${available ? 'Available' : 'Unavailable'}`,
                    className: available
                        ? 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-500/20'
                        : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
                    title: available ? 'OpenVINO GPU is available on this host' : 'OpenVINO GPU is not available on this host'
                };
            });
    }

    async function handleDownload(model: ModelMetadata) {
        if (downloadStatuses[model.id]?.status === 'downloading' || downloadStatuses[model.id]?.status === 'pending') return;

        try {
            const result = await downloadModel(model.id);
            if (result.status !== 'pending') {
                const errorStatus = {
                    model_id: model.id,
                    status: 'error' as const,
                    progress: 0,
                    error: result.message || 'Failed to start download'
                };
                downloadStatuses[model.id] = errorStatus;
                syncModelDownloadProgress(jobProgressStore, model, errorStatus);
                return;
            }
            startModelDownloadProgress(jobProgressStore, model);
            // Initialize local status to trigger polling
            downloadStatuses[model.id] = {
                model_id: model.id,
                status: 'downloading',
                progress: 0
            };
        } catch (e) {
            console.error(e);
            const message = e instanceof Error ? e.message : 'Failed to start download';
            const errorStatus = {
                model_id: model.id,
                status: 'error' as const,
                progress: 0,
                error: message
            };
            downloadStatuses[model.id] = errorStatus;
            syncModelDownloadProgress(jobProgressStore, model, errorStatus);
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
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div class="flex flex-col gap-1"><h2 class="text-2xl font-bold text-slate-900 dark:text-white">Model Manager</h2><p class="text-sm text-slate-500 dark:text-slate-400">Tiered models are sorted by readiness, with advanced options collapsed by default.</p></div>
        
        {#if health}
            <div class="flex items-center gap-2">
                <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700" title="TFLite Runtime Status">
                    <span class="w-2 h-2 rounded-full {health.ml.runtimes.tflite.installed ? 'bg-emerald-500' : 'bg-red-500'}"></span>
                    <span class="text-xs font-bold text-slate-600 dark:text-slate-400">TFLite</span>
                </div>
                <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700" title="ONNX Runtime Status">
                    <span class="w-2 h-2 rounded-full {health.ml.runtimes.onnx.installed ? 'bg-emerald-500' : 'bg-red-500'}"></span>
                    <span class="text-xs font-bold text-slate-600 dark:text-slate-400">ONNX</span>
                </div>
                <button 
                    onclick={loadData}
                    class="p-2 text-slate-500 hover:text-teal-500 transition-colors"
                    title="Refresh"
                >
                    <svg class="w-5 h-5 {loading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                </button>
            </div>
        {/if}
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
        {@const visibleModels = getVisibleTieredModelLineup(availableModels, showAdvancedModels)}
        {@const advancedCount = availableModels.filter((model) => model.advanced_only).length}
        <div class="space-y-6">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                    <h3 class="text-sm font-black uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Tiered model lineup</h3>
                    <p class="text-sm text-slate-500 dark:text-slate-400">
                        Recommended models are shown first. Advanced options stay collapsed until you open them.
                    </p>
                </div>
                <div class="flex items-center gap-2 flex-wrap justify-end">
                    {#if advancedCount > 0}
                        <button
                            onclick={() => showAdvancedModels = !showAdvancedModels}
                            class="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-xs font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                        >
                            {showAdvancedModels ? 'Hide advanced models' : `Show advanced models (${advancedCount})`}
                        </button>
                    {/if}
                    <span class="shrink-0 px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300">
                        {visibleModels.length} model{visibleModels.length === 1 ? '' : 's'}
                    </span>
                </div>
            </div>

            {#if !showAdvancedModels && advancedCount > 0}
                <div class="rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50/40 dark:bg-amber-900/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
                    Advanced models are hidden by default. Reveal them when you need the larger ONNX options.
                </div>
            {/if}

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {#each visibleModels as model}
{@const installed = isInstalled(model.id)}
                {@const active = isActive(model.id)}
                {@const download = downloadStatuses[model.id]}
                {@const inProgress = download?.status === 'downloading' || download?.status === 'pending'}
                {@const dynamicProviderChips = getDynamicProviderChips(model, active)}
                
                <div class="bg-white dark:bg-slate-800 rounded-xl border-2 transition-all duration-200 flex flex-col
                            {active ? 'border-teal-500 shadow-lg shadow-teal-500/10' : 'border-slate-200 dark:border-slate-700'}">
                    
                    <div class="p-5 flex-1">
                        <div class="flex justify-between items-start gap-2 mb-2 min-w-0">
                            <h3 class="min-w-0 text-lg font-bold text-slate-900 dark:text-white break-words leading-tight">{model.name}</h3>
                            {#if active}
                                <span class="shrink-0 px-2 py-1 text-xs font-bold bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300 rounded-full">
                                    ACTIVE
                                </span>
                            {/if}
                        </div>
                        
                        <p class="text-sm text-slate-500 dark:text-slate-400 mb-3 h-10 line-clamp-2">
                            {model.description}
                        </p>

                        <div class="mb-4 flex flex-wrap gap-2">
                            <span class={`px-2.5 py-1 rounded-full border text-[10px] font-black tracking-tight ${tierChipClass(model.tier)}`}>
                                {tierLabel(model.tier)}
                            </span>
                            <span class="px-2.5 py-1 rounded-full border border-slate-300 dark:border-slate-600 text-[10px] font-black tracking-tight text-slate-700 dark:text-slate-200">
                                {scopeLabel(model.taxonomy_scope)}
                            </span>
                            <span class={`px-2.5 py-1 rounded-full border text-[10px] font-black tracking-tight ${statusChipClass(model.status)}`}>
                                {statusLabel(model.status)}
                            </span>
                            {#if formatRamLabel(model)}
                                <span class="px-2.5 py-1 rounded-full border border-slate-300 dark:border-slate-600 text-[10px] font-black tracking-tight text-slate-700 dark:text-slate-200">
                                    {formatRamLabel(model)}
                                </span>
                            {/if}
                        </div>

                        <div class="mb-4 space-y-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-700/30 p-3">
                            <div>
                                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Recommended For</p>
                                <p class="mt-1 text-xs font-medium text-slate-700 dark:text-slate-200">{model.recommended_for}</p>
                            </div>
                            {#if model.notes}
                                <div>
                                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Notes</p>
                                    <p class="mt-1 text-[11px] font-medium leading-relaxed text-slate-600 dark:text-slate-300">{model.notes}</p>
                                </div>
                            {/if}
                        </div>

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

                        <div class="mb-4 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-700/30 p-2.5">
                            <div class="flex items-center justify-between gap-2 mb-2">
                                <span class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Runtime</span>
                                <span class="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200">
                                    {(model.runtime || 'cpu').toUpperCase()}
                                </span>
                            </div>
                            <div class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">
                                Inference Provider Pills
                            </div>
                            {#if active}
                                {#if dynamicProviderChips.length > 0}
                                    <div class="flex flex-wrap items-center gap-2 min-w-0">
                                        {#each dynamicProviderChips as chip}
                                            <span class={`max-w-full px-2 py-1 rounded-full border text-[10px] font-black tracking-tight whitespace-normal break-words text-center ${chip.className}`} title={chip.title}>
                                                {chip.label}
                                            </span>
                                        {/each}
                                    </div>
                                {:else}
                                    <p class="text-[10px] font-bold text-slate-500 dark:text-slate-400">
                                        OpenVINO host verification is shown for the active ONNX model.
                                    </p>
                                {/if}
                            {:else}
                                <div class="flex flex-wrap gap-1.5">
                                    {#each getProviderSupport(model) as provider}
                                        <span class={`max-w-full px-2 py-1 rounded-full border text-[10px] font-black tracking-tight whitespace-normal break-words text-center ${providerChipClass(provider)}`}>
                                            {providerLabel(provider)}
                                        </span>
                                    {/each}
                                </div>
                            {/if}
                        </div>

                        {#if inProgress}
                            <div class="mt-4">
                                <div class="flex justify-between text-xs mb-1">
                                    <span class="text-teal-600 dark:text-teal-400 font-medium">
                                        {installed ? 'Re-downloading...' : 'Downloading...'}
                                    </span>
                                    <span class="text-slate-500">{download.progress.toFixed(0)}%</span>
                                </div>
                                <div class="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
                                    <div class="bg-teal-500 h-full transition-all duration-300" style="width: {download.progress}%"></div>
                                </div>
                            </div>
                        {/if}
                        {#if download?.status === 'error' && download.error}
                            <div class="mt-4 p-2 rounded-lg border border-red-200 dark:border-red-800 bg-red-50/70 dark:bg-red-900/20 text-[11px] font-medium text-red-700 dark:text-red-300">
                                {download.error}
                            </div>
                        {/if}
                    </div>

                    <div class="p-4 border-t border-slate-100 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 rounded-b-xl">
                        {#if inProgress}
                            <button
                                disabled
                                class="w-full px-4 py-2 text-sm font-medium text-slate-400 bg-slate-100 dark:bg-slate-700 rounded-lg cursor-default flex items-center justify-center gap-2"
                            >
                                <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                {installed ? 'Re-downloading...' : 'Downloading...'}
                            </button>
                        {:else if installed}
                            <div class="space-y-2">
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
                                <button
                                    onclick={() => handleDownload(model)}
                                    class="w-full px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-600 rounded-lg transition-colors flex items-center justify-center gap-2"
                                >
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                    </svg>
                                    Re-download
                                </button>
                            </div>
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
        </div>
    {/if}
</div>

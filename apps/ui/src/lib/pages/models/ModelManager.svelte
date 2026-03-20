<script lang="ts">
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import { onMount, onDestroy } from 'svelte';
    import { fetchAvailableModels, fetchInstalledModels, downloadModel, fetchDownloadStatus, activateModel, checkHealth, fetchClassifierStatus, getVisibleTieredModelLineup, type ModelMetadata, type InstalledModel, type DownloadProgress, type ClassifierStatus } from '../../api';
    import { jobProgressStore } from '../../stores/job_progress.svelte';
    import { startModelDownloadProgress, syncModelDownloadProgress } from './model_download_progress';
    import {
        CROP_MODEL_OVERRIDE_VALUES,
        CROP_SOURCE_OVERRIDE_VALUES,
        getCropVariantOverrideEntries,
        normalizeCropModelOverride,
        normalizeCropSourceOverride,
        type CropModelOverride,
        type CropSourceOverride,
    } from '../../settings/crop-overrides';

    let {
        cropModelOverrides = $bindable<Record<string, CropModelOverride>>({}),
        cropSourceOverrides = $bindable<Record<string, CropSourceOverride>>({}),
    }: {
        cropModelOverrides: Record<string, CropModelOverride>;
        cropSourceOverrides: Record<string, CropSourceOverride>;
    } = $props();

    let availableModels = $state<ModelMetadata[]>([]);
    let installedModels = $state<InstalledModel[]>([]);
    let health = $state<any>(null);
    let classifierStatus = $state<ClassifierStatus | null>(null);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let downloadStatuses = $state<Record<string, DownloadProgress>>({});
    let activating = $state<string | null>(null);
    let selectedModelId = $state<string | null>(null); 
    let showAdvancedModels = $state(false);
    let cropDetectorStatus = $state<ClassifierStatus['crop_detector'] | null>(null);

    function t(key: string, fallback: string, values?: Record<string, string | number>): string {
        return get(_)(key, values ? { values, default: fallback } : { default: fallback });
    }

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
                return t('settings.detection.model_manager_tier_cpu_only', 'CPU only');
            default:
                return formatMetadataLabel(tier);
        }
    }

    function cropOverrideLabel(value: CropModelOverride): string {
        switch (value) {
            case 'on':
                return 'Force on';
            case 'off':
                return 'Force off';
            default:
                return 'Use model default';
        }
    }

    function cropSourceLabel(value: CropSourceOverride): string {
        switch (value) {
            case 'standard':
                return 'Standard source';
            case 'high_quality':
                return 'High-quality snapshot';
            default:
                return 'Use model default';
        }
    }

    function cropDefaultEnabledLabel(cropGenerator: ModelMetadata['crop_generator'] | undefined): string {
        return cropGenerator?.enabled ? 'On' : 'Off';
    }

    function cropDefaultSourceLabel(cropGenerator: ModelMetadata['crop_generator'] | undefined): string {
        return normalizeCropSourceOverride(cropGenerator?.source_preference) === 'high_quality'
            ? 'High-quality snapshot'
            : 'Standard source';
    }

    function getCropModelOverrideValue(key: string): CropModelOverride {
        return normalizeCropModelOverride(cropModelOverrides[key]);
    }

    function getCropSourceOverrideValue(key: string): CropSourceOverride {
        return normalizeCropSourceOverride(cropSourceOverrides[key]);
    }

    function setCropModelOverride(key: string, value: string): void {
        const normalized = normalizeCropModelOverride(value);
        const next = { ...cropModelOverrides };
        if (normalized === 'default') {
            delete next[key];
        } else {
            next[key] = normalized;
        }
        cropModelOverrides = next;
    }

    function setCropSourceOverride(key: string, value: string): void {
        const normalized = normalizeCropSourceOverride(value);
        const next = { ...cropSourceOverrides };
        if (normalized === 'default') {
            delete next[key];
        } else {
            next[key] = normalized;
        }
        cropSourceOverrides = next;
    }

    function scopeLabel(scope: string): string {
        switch (scope) {
            case 'birds_only':
                return t('settings.detection.model_manager_scope_birds_only', 'Birds only');
            case 'wildlife_wide':
                return t('settings.detection.model_manager_scope_wildlife_wide', 'Broad wildlife');
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
            availableModels = available;
            installedModels = installed;
            health = healthData;
            classifierStatus = classifierData;
            cropDetectorStatus = classifierData?.crop_detector ?? null;
            
            if (!selectedModelId && installed.length > 0) {
                const activeModel = installed.find(m => m.is_active);
                if (activeModel) selectedModelId = activeModel.id;
            }
            if (!selectedModelId && available.length > 0) {
                const classModels = available.filter(m => (m.artifact_kind || 'classifier') === 'classifier');
                if (classModels.length > 0) selectedModelId = classModels[0].id;
            }
        } catch (e) {
            console.error(e);
            error = t('settings.detection.model_manager_load_error', 'Failed to load models');
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
                        error: t('settings.detection.model_manager_status_unavailable', 'Download status unavailable')
                    };
                    downloadStatuses[id] = errorStatus;
                    if (model) {
                        syncModelDownloadProgress(jobProgressStore, model, errorStatus);
                    }
                }
            } catch (e) {
                console.error(`Failed to poll status for ${id}`, e);
                const model = availableModels.find((entry) => entry.id === id);
                const message = e instanceof Error ? e.message : t('settings.detection.model_manager_status_refresh_failed', 'Failed to refresh download status');
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

    function isCropDetectorInstalled(): boolean {
        return installedModels.some((model) => model.id === 'bird_crop_detector');
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
                return t('settings.detection.model_manager_provider_cpu', 'CPU');
            case 'cuda':
                return t('settings.detection.model_manager_provider_cuda', 'NVIDIA CUDA');
            case 'intel_cpu':
                return t('settings.detection.model_manager_provider_intel_cpu', 'Intel CPU (OpenVINO)');
            case 'intel_gpu':
                return t('settings.detection.model_manager_provider_intel_gpu', 'Intel GPU (OpenVINO)');
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
                        label: `${baseLabel}: ${t('settings.detection.model_manager_provider_active_suffix', 'Active')}`,
                        className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
                        title: t('settings.detection.active_provider_label', 'Active')
                    };
                }

                if (provider === 'cpu') {
                    return {
                        label: `${baseLabel}: ${t('settings.detection.model_manager_provider_available_suffix', 'Available')}`,
                        className: 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20',
                        title: t('settings.detection.model_manager_provider_cpu_fallback_title', 'CPU fallback path is available')
                    };
                }

                if (provider === 'cuda') {
                    const available = classifierStatus?.cuda_available ?? false;
                    return {
                        label: `${baseLabel}: ${available ? t('settings.detection.model_manager_provider_available_suffix', 'Available') : t('settings.detection.model_manager_provider_unavailable_suffix', 'Unavailable')}`,
                        className: available
                            ? 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20'
                            : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
                        title: available ? t('settings.detection.model_manager_provider_cuda_available_title', 'CUDA provider is available on this host') : t('settings.detection.model_manager_provider_cuda_unavailable_title', 'CUDA provider is not available on this host')
                    };
                }

                if (provider === 'intel_cpu') {
                    if (compileForIntelCpuFailed) {
                        return {
                            label: `${baseLabel}: ${t('settings.detection.model_manager_provider_fallback_suffix', 'Fallback')}`,
                            className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
                            title: t('settings.detection.model_manager_provider_openvino_cpu_fallback_title', 'OpenVINO CPU compile failed and fallback is active')
                        };
                    }
                    const available = classifierStatus?.intel_cpu_available ?? false;
                    return {
                        label: `${baseLabel}: ${available ? t('settings.detection.model_manager_provider_available_suffix', 'Available') : t('settings.detection.model_manager_provider_unavailable_suffix', 'Unavailable')}`,
                        className: available
                            ? 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-500/20'
                            : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
                        title: available ? t('settings.detection.model_manager_provider_openvino_cpu_available_title', 'OpenVINO CPU is available on this host') : t('settings.detection.model_manager_provider_openvino_cpu_unavailable_title', 'OpenVINO CPU is not available on this host')
                    };
                }

                if (compileForIntelGpuFailed) {
                    return {
                        label: `${baseLabel}: ${t('settings.detection.model_manager_provider_fallback_suffix', 'Fallback')}`,
                        className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
                        title: t('settings.detection.model_manager_provider_openvino_gpu_fallback_title', 'OpenVINO GPU compile failed and fallback is active')
                    };
                }
                const available = classifierStatus?.intel_gpu_available ?? false;
                return {
                    label: `${baseLabel}: ${available ? t('settings.detection.model_manager_provider_available_suffix', 'Available') : t('settings.detection.model_manager_provider_unavailable_suffix', 'Unavailable')}`,
                    className: available
                        ? 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-500/20'
                        : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
                    title: available ? t('settings.detection.model_manager_provider_openvino_gpu_available_title', 'OpenVINO GPU is available on this host') : t('settings.detection.model_manager_provider_openvino_gpu_unavailable_title', 'OpenVINO GPU is not available on this host')
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
                    error: result.message || t('settings.detection.model_manager_start_failed', 'Failed to start download')
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
            const message = e instanceof Error ? e.message : t('settings.detection.model_manager_start_failed', 'Failed to start download');
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
            alert(t('settings.detection.model_manager_activate_error', 'Failed to activate model'));
        } finally {
            activating = null;
        }
    }
</script>

<div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div class="flex flex-col gap-1"><h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('settings.detection.model_manager_title', { default: 'Model Manager' })}</h2><p class="text-sm text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_subtitle', { default: 'Tiered models are sorted by readiness, with advanced options collapsed by default.' })}</p></div>
        
        {#if health}
            <div class="flex items-center gap-2">
                <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700" title={$_('settings.detection.model_manager_runtime_tflite', { default: 'TFLite Runtime Status' })}>
                    <span class="w-2 h-2 rounded-full {health.ml.runtimes.tflite.installed ? 'bg-emerald-500' : 'bg-red-500'}"></span>
                    <span class="text-xs font-bold text-slate-600 dark:text-slate-400">TFLite</span>
                </div>
                <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700" title={$_('settings.detection.model_manager_runtime_onnx', { default: 'ONNX Runtime Status' })}>
                    <span class="w-2 h-2 rounded-full {health.ml.runtimes.onnx.installed ? 'bg-emerald-500' : 'bg-red-500'}"></span>
                    <span class="text-xs font-bold text-slate-600 dark:text-slate-400">ONNX</span>
                </div>
                <button 
                    onclick={loadData}
                    class="p-2 text-slate-500 hover:text-teal-500 transition-colors"
                    title={$_('settings.detection.model_manager_refresh', { default: 'Refresh' })}
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
        {@const cropDetectorModel = availableModels.find((model) => model.id === 'bird_crop_detector')}
        {@const classifierModels = availableModels.filter((model) => (model.artifact_kind || 'classifier') === 'classifier')}
        {@const cropDetectorDownload = cropDetectorModel ? downloadStatuses[cropDetectorModel.id] : undefined}
        {@const cropDetectorInstalled = isCropDetectorInstalled()}
        {@const cropDetectorReady = Boolean(cropDetectorStatus?.enabled_for_runtime || cropDetectorInstalled)}
        {@const visibleModels = getVisibleTieredModelLineup(classifierModels, showAdvancedModels)}
        {@const advancedCount = classifierModels.filter((model) => model.advanced_only).length}
        <div class="space-y-6">
            {#if cropDetectorModel}
                <div class="rounded-xl border-2 border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                    <div class="p-5">
                        <div class="flex items-start justify-between gap-3">
                            <div>
                                <h3 class="text-lg font-bold text-slate-900 dark:text-white">Bird Crop Detector</h3>
                                <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
                                    Shared detector dependency for crop-enabled bird models. Download it once to unlock crop-assisted classification.
                                </p>
                            </div>
                            <span class={`px-2.5 py-1 rounded-full border text-[10px] font-black tracking-tight ${cropDetectorReady ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20' : 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20'}`}>
                                {cropDetectorReady ? 'Installed' : 'Not installed'}
                            </span>
                        </div>

                        <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                            <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-700/30 p-3">
                                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Status</p>
                                <p class="mt-1 text-xs font-medium text-slate-700 dark:text-slate-200">
                                    {cropDetectorStatus?.reason || (cropDetectorInstalled ? 'installed' : 'not_installed')}
                                </p>
                            </div>
                            <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-700/30 p-3">
                                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Runtime</p>
                                <p class="mt-1 text-xs font-medium text-slate-700 dark:text-slate-200">
                                    {cropDetectorStatus?.healthy ? 'Healthy' : 'Unavailable'}
                                </p>
                            </div>
                            <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-700/30 p-3">
                                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Artifact</p>
                                <p class="mt-1 text-xs font-medium text-slate-700 dark:text-slate-200">
                                    {cropDetectorModel.file_size_mb} MB
                                </p>
                            </div>
                        </div>

                        {#if cropDetectorDownload?.status === 'downloading' || cropDetectorDownload?.status === 'pending'}
                            <div class="mt-4">
                                <div class="flex justify-between text-xs mb-1">
                                    <span class="text-teal-600 dark:text-teal-400 font-medium">Downloading detector...</span>
                                    <span class="text-slate-500">{cropDetectorDownload.progress.toFixed(0)}%</span>
                                </div>
                                <div class="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
                                    <div class="bg-teal-500 h-full transition-all duration-300" style="width: {cropDetectorDownload.progress}%"></div>
                                </div>
                            </div>
                        {/if}

                        <div class="mt-4 flex flex-wrap gap-3">
                            <button
                                onclick={() => handleDownload(cropDetectorModel)}
                                disabled={cropDetectorDownload?.status === 'downloading' || cropDetectorDownload?.status === 'pending'}
                                class="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-600 rounded-lg transition-colors disabled:opacity-50"
                            >
                                {cropDetectorInstalled ? 'Re-download detector' : 'Download detector'}
                            </button>
                            {#if !cropDetectorReady}
                                <p class="text-sm text-slate-500 dark:text-slate-400">
                                    Crop-enabled models require the bird crop detector before crop generation can be used.
                                </p>
                            {/if}
                        </div>
                    </div>
                </div>
            {/if}

            <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between mb-6">
                <div class="flex-1">
                    <h3 class="text-sm font-black uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_lineup_title', { default: 'Tiered model lineup' })}</h3>
                    <p class="text-sm text-slate-500 dark:text-slate-400 mb-3">
                        {$_('settings.detection.model_manager_lineup_desc', { default: 'Recommended models are shown first. Advanced options stay collapsed until you open them.' })}
                    </p>
                    <div class="w-full sm:max-w-md relative">
                        <select
                            bind:value={selectedModelId}
                            class="w-full appearance-none pl-4 pr-10 py-3 rounded-xl border-2 border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white font-bold text-sm shadow-sm focus:border-teal-500 focus:ring-0 outline-none transition-colors"
                        >
                            {#each visibleModels as m}
                                <option value={m.id}>
                                    {m.name} {isActive(m.id) ? '— Active' : isInstalled(m.id) ? '— Installed' : ''}
                                </option>
                            {/each}
                        </select>
                        <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-slate-500">
                            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
                        </div>
                    </div>
                </div>
                <div class="flex items-center gap-2 flex-wrap justify-start sm:justify-end pb-1">
                    {#if advancedCount > 0}
                        <button
                            onclick={() => { 
                                showAdvancedModels = !showAdvancedModels; 
                                if (!showAdvancedModels) {
                                    const m = visibleModels.find(x => x.id === selectedModelId);
                                    if (m && m.advanced_only) {
                                        selectedModelId = visibleModels.find(x => !x.advanced_only)?.id || null;
                                    }
                                }
                            }}
                            class="px-4 py-2.5 rounded-xl border-2 border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-bold text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
                        >
                            {showAdvancedModels
                                ? $_('settings.detection.model_manager_hide_advanced', { default: 'Hide advanced models' })
                                : $_('settings.detection.model_manager_show_advanced', { values: { count: advancedCount }, default: 'Show advanced models ({count})' })}
                        </button>
                    {/if}
                </div>
            </div>

            {#if !showAdvancedModels && advancedCount > 0}
                <div class="mb-6 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50/40 dark:bg-amber-900/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
                    {$_('settings.detection.model_manager_advanced_hidden', { default: 'Advanced models are hidden by default. Reveal them when you need the larger ONNX options.' })}
                </div>
            {/if}

            {#if selectedModelId}
                {@const model = visibleModels.find(m => m.id === selectedModelId) || visibleModels[0]}
                {#if model}
                {@const installed = isInstalled(model.id)}
                {@const active = isActive(model.id)}
                {@const download = downloadStatuses[model.id]}
                {@const inProgress = download?.status === 'downloading' || download?.status === 'pending'}
                {@const dynamicProviderChips = getDynamicProviderChips(model, active)}
                {@const variantEntries = getCropVariantOverrideEntries(model)}
                {@const cropControlsDisabled = !cropDetectorReady}
                
                <div class="bg-white dark:bg-slate-800 rounded-xl border-2 transition-all duration-200 flex flex-col
                            {active ? 'border-teal-500 shadow-lg shadow-teal-500/10' : 'border-slate-200 dark:border-slate-700'}">
                    
                    <div class="p-6 grid grid-cols-1 lg:grid-cols-2 gap-8">
                        <!-- Left Col: Model details -->
                        <div class="flex flex-col gap-5">
                            <div>
                                <div class="flex items-center gap-3 mb-2">
                                    <h3 class="text-2xl font-bold text-slate-900 dark:text-white leading-tight">{model.name}</h3>
                                    {#if active}
                                        <span class="shrink-0 px-2.5 py-1 text-[10px] font-black tracking-wider bg-teal-100 dark:bg-teal-900/40 text-teal-700 dark:text-teal-300 rounded-full border border-teal-200 dark:border-teal-800/50">
                                            {$_('settings.detection.model_manager_active', { default: 'ACTIVE' })}
                                        </span>
                                    {/if}
                                </div>
                                <p class="text-sm text-slate-500 dark:text-slate-400">
                                    {model.description}
                                </p>
                            </div>

                            <div class="flex flex-wrap gap-2">
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

                            <div class="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-700/30 p-4 space-y-3">
                                <div>
                                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_recommended_for', { default: 'Recommended For' })}</p>
                                    <p class="mt-1.5 text-sm font-medium text-slate-700 dark:text-slate-200">{model.recommended_for}</p>
                                </div>
                                {#if model.notes}
                                    <div>
                                        <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_notes', { default: 'Notes' })}</p>
                                        <p class="mt-1.5 text-xs font-medium leading-relaxed text-slate-600 dark:text-slate-300">{model.notes}</p>
                                    </div>
                                {/if}
                            </div>

                            <div class="grid grid-cols-2 gap-3 text-sm text-slate-600 dark:text-slate-400">
                                <div class="flex flex-col p-3 bg-slate-50 dark:bg-slate-700/50 rounded-xl">
                                    <span class="text-xs font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">{$_('settings.detection.model_manager_architecture', { default: 'Architecture' })}</span>
                                    <span class="font-bold text-slate-700 dark:text-slate-200 mt-1">{model.architecture}</span>
                                </div>
                                <div class="flex flex-col p-3 bg-slate-50 dark:bg-slate-700/50 rounded-xl">
                                    <span class="text-xs font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">{$_('settings.detection.model_manager_size', { default: 'Size' })}</span>
                                    <span class="font-bold text-slate-700 dark:text-slate-200 mt-1">{model.file_size_mb} MB</span>
                                </div>
                                <div class="flex flex-col p-3 bg-slate-50 dark:bg-slate-700/50 rounded-xl">
                                    <span class="text-xs font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">{$_('settings.detection.model_manager_accuracy', { default: 'Accuracy' })}</span>
                                    <span class="font-bold mt-1 {model.accuracy_tier === 'High' ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-700 dark:text-slate-200'}">
                                        {model.accuracy_tier}
                                    </span>
                                </div>
                                <div class="flex flex-col p-3 bg-slate-50 dark:bg-slate-700/50 rounded-xl">
                                    <span class="text-xs font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">{$_('settings.detection.model_manager_speed', { default: 'Speed' })}</span>
                                    <span class="font-bold mt-1 {model.inference_speed === 'Fast' ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-700 dark:text-slate-200'}">
                                        {model.inference_speed}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <!-- Right Col: Config / Runtime -->
                        <div class="flex flex-col gap-5">
                            <div class="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-700/30 p-4">
                                <div class="flex items-center justify-between gap-2 mb-4">
                                    <span class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_runtime', { default: 'Runtime' })}</span>
                                    <span class="text-[10px] font-black uppercase tracking-widest px-3 py-1 rounded-full border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 shadow-sm">
                                        {(model.runtime || 'cpu').toUpperCase()}
                                    </span>
                                </div>
                                <div class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-3">
                                    {$_('settings.detection.model_manager_provider_pills', { default: 'Inference Provider Pills' })}
                                </div>
                                {#if active}
                                    {#if dynamicProviderChips.length > 0}
                                        <div class="flex flex-wrap items-center gap-2 min-w-0">
                                            {#each dynamicProviderChips as chip}
                                                <span class={`px-3 py-1.5 rounded-lg border text-[10px] font-black tracking-tight whitespace-normal break-words text-center ${chip.className}`} title={chip.title}>
                                                    {chip.label}
                                                </span>
                                            {/each}
                                        </div>
                                    {:else}
                                        <p class="text-[10px] font-bold text-slate-500 dark:text-slate-400">
                                            {$_('settings.detection.model_manager_host_verification', { default: 'OpenVINO host verification is shown for the active ONNX model.' })}
                                        </p>
                                    {/if}
                                {:else}
                                    <div class="flex flex-wrap gap-2">
                                        {#each getProviderSupport(model) as provider}
                                            <span class={`px-3 py-1.5 rounded-lg border text-[10px] font-black tracking-tight whitespace-normal break-words text-center ${providerChipClass(provider)}`}>
                                                {providerLabel(provider)}
                                            </span>
                                        {/each}
                                    </div>
                                {/if}
                            </div>

                            <div class="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-700/30 p-4">
                                <div class="mb-4">
                                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                        Crop behavior
                                    </p>
                                    <p class="mt-1.5 text-xs font-medium leading-relaxed text-slate-600 dark:text-slate-300">
                                        Model default: <strong>{cropDefaultEnabledLabel(model.crop_generator)}</strong>. Force this model on or off if the shipped default does not fit your feeder.
                                    </p>
                                </div>
                                <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <label class="flex flex-col gap-2">
                                        <span class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                            Crop behavior
                                        </span>
                                        <select
                                            value={getCropModelOverrideValue(model.id)}
                                            onchange={(event) => setCropModelOverride(model.id, (event.currentTarget as HTMLSelectElement).value)}
                                            disabled={cropControlsDisabled}
                                            class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-bold text-slate-900 shadow-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-white"
                                        >
                                            {#each CROP_MODEL_OVERRIDE_VALUES as option}
                                                <option value={option}>{cropOverrideLabel(option)}</option>
                                            {/each}
                                        </select>
                                    </label>
                                    <label class="flex flex-col gap-2">
                                        <span class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                            Crop source
                                        </span>
                                        <select
                                            value={getCropSourceOverrideValue(model.id)}
                                            onchange={(event) => setCropSourceOverride(model.id, (event.currentTarget as HTMLSelectElement).value)}
                                            disabled={cropControlsDisabled}
                                            class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-bold text-slate-900 shadow-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-white"
                                        >
                                            {#each CROP_SOURCE_OVERRIDE_VALUES as option}
                                                <option value={option}>{cropSourceLabel(option)}</option>
                                            {/each}
                                        </select>
                                    </label>
                                </div>
                                <p class="mt-3 text-xs font-medium leading-relaxed text-slate-500 dark:text-slate-400">
                                    Source default: <strong>{cropDefaultSourceLabel(model.crop_generator)}</strong>.
                                </p>
                                {#if cropControlsDisabled}
                                    <p class="mt-3 text-xs font-medium leading-relaxed text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 p-2 rounded border border-amber-200 dark:border-amber-800/50">
                                        Crop behavior requires the bird crop detector to be installed first.
                                    </p>
                                {/if}

                                {#if variantEntries.length > 0}
                                    <details class="mt-4 rounded-xl border border-slate-200/80 bg-white/70 px-4 py-3 dark:border-slate-600/80 dark:bg-slate-800/60">
                                        <summary class="cursor-pointer text-xs font-black uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                                            Regional variant overrides
                                        </summary>
                                        <div class="mt-4 space-y-4">
                                            {#each variantEntries as variant}
                                                {@const variantMeta = model.region_variants?.[variant.region]}
                                                <div class="rounded-xl border border-slate-200/80 bg-slate-50/80 p-4 dark:border-slate-600/80 dark:bg-slate-900/40">
                                                    <div class="mb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                                                        <div>
                                                            <p class="text-sm font-black text-slate-900 dark:text-white">{variant.label}</p>
                                                            <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                                                                {variant.id}
                                                            </p>
                                                        </div>
                                                        <div class="text-left sm:text-right text-xs font-bold text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-800 p-2 rounded shadow-sm border border-slate-100 dark:border-slate-700">
                                                            <div>Default crop: <span class="text-slate-700 dark:text-slate-300">{cropDefaultEnabledLabel(variantMeta?.crop_generator)}</span></div>
                                                            <div>Default source: <span class="text-slate-700 dark:text-slate-300">{cropDefaultSourceLabel(variantMeta?.crop_generator)}</span></div>
                                                        </div>
                                                    </div>
                                                    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 mt-4">
                                                        <label class="flex flex-col gap-2">
                                                            <span class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                                                Crop behavior
                                                            </span>
                                                            <select
                                                                value={getCropModelOverrideValue(variant.id)}
                                                                onchange={(event) => setCropModelOverride(variant.id, (event.currentTarget as HTMLSelectElement).value)}
                                                                disabled={cropControlsDisabled}
                                                                class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-bold text-slate-900 shadow-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-white"
                                                            >
                                                                {#each CROP_MODEL_OVERRIDE_VALUES as option}
                                                                    <option value={option}>{cropOverrideLabel(option)}</option>
                                                                {/each}
                                                            </select>
                                                        </label>
                                                        <label class="flex flex-col gap-2">
                                                            <span class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                                                Crop source
                                                            </span>
                                                            <select
                                                                value={getCropSourceOverrideValue(variant.id)}
                                                                onchange={(event) => setCropSourceOverride(variant.id, (event.currentTarget as HTMLSelectElement).value)}
                                                                disabled={cropControlsDisabled}
                                                                class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-bold text-slate-900 shadow-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-white"
                                                            >
                                                                {#each CROP_SOURCE_OVERRIDE_VALUES as option}
                                                                    <option value={option}>{cropSourceLabel(option)}</option>
                                                                {/each}
                                                            </select>
                                                        </label>
                                                    </div>
                                                </div>
                                            {/each}
                                        </div>
                                    </details>
                                {/if}
                            </div>
                        </div>
                    </div>

                    <!-- Bottom Bar: Actions & Progress -->
                    <div class="p-6 border-t border-slate-100 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 rounded-b-xl flex flex-col gap-4">
                        {#if inProgress}
                            <div class="w-full">
                                <div class="flex justify-between text-sm mb-2">
                                    <span class="text-teal-600 dark:text-teal-400 font-bold flex items-center gap-2">
                                        <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        {installed
                                            ? $_('settings.detection.model_manager_redownloading', { default: 'Re-downloading...' })
                                            : $_('settings.detection.model_manager_downloading', { default: 'Downloading...' })}
                                    </span>
                                    <span class="text-slate-600 dark:text-slate-300 font-medium">{download.progress.toFixed(0)}%</span>
                                </div>
                                <div class="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2.5 overflow-hidden">
                                    <div class="bg-teal-500 h-full transition-all duration-300" style="width: {download.progress}%"></div>
                                </div>
                            </div>
                        {:else}
                            {#if download?.status === 'error' && download.error}
                                <div class="w-full p-3 rounded-lg border border-red-200 dark:border-red-800 bg-red-50/70 dark:bg-red-900/20 text-sm font-medium text-red-700 dark:text-red-300">
                                    {download.error}
                                </div>
                            {/if}

                            <div class="flex flex-col sm:flex-row gap-3 w-full justify-end">
                                {#if installed}
                                    <button
                                        onclick={() => handleDownload(model)}
                                        class="px-6 py-2.5 text-sm font-bold text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-600 rounded-xl transition-colors flex items-center justify-center gap-2"
                                    >
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                        </svg>
                                        {$_('settings.detection.model_manager_redownload', { default: 'Re-download' })}
                                    </button>
                                    {#if active}
                                        <button
                                            disabled
                                            class="px-6 py-2.5 text-sm font-bold text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-900/20 rounded-xl opacity-75 cursor-default border border-teal-200 dark:border-teal-800/50"
                                        >
                                            {$_('settings.detection.model_manager_currently_active', { default: 'Currently Active' })}
                                        </button>
                                    {:else}
                                        <button
                                            onclick={() => handleActivate(model.id)}
                                            disabled={activating !== null}
                                            class="px-6 py-2.5 text-sm font-bold text-white bg-teal-500 hover:bg-teal-600 rounded-xl transition-colors disabled:opacity-50 shadow-sm"
                                        >
                                            {activating === model.id
                                                ? $_('settings.detection.model_manager_activating', { default: 'Activating...' })
                                                : $_('settings.detection.model_manager_activate', { default: 'Activate Model' })}
                                        </button>
                                    {/if}
                                {:else}
                                    <button
                                        onclick={() => handleDownload(model)}
                                        class="w-full sm:w-auto px-6 py-2.5 text-sm font-bold text-white bg-slate-900 dark:bg-slate-100 dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-white rounded-xl transition-colors flex items-center justify-center gap-2 shadow-sm"
                                    >
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                        </svg>
                                        {$_('settings.detection.model_manager_download', { default: 'Download Model' })}
                                    </button>
                                {/if}
                            </div>
                        {/if}
                    </div>
                </div>
                {/if}
            {/if}
        </div>
    {/if}
</div>

<script lang="ts">
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import { onMount, onDestroy } from 'svelte';
    import { fetchAvailableModels, fetchInstalledModels, downloadModel, fetchDownloadStatus, activateModel, deleteModel, validateModel, checkHealth, fetchClassifierStatus, getVisibleTieredModelLineup, groupTieredModelLineup, categorizeModel, MODEL_CATEGORY_INFO, type ModelMetadata, type InstalledModel, type DownloadProgress, type ClassifierStatus, type HealthStatus } from '../../api';
    import { jobProgressStore } from '../../stores/job_progress.svelte';
    import { startModelDownloadProgress, syncModelDownloadProgress } from './model_download_progress';
    import { getRuntimeProviderOrder } from '../../settings/inference-providers';
    import DiagnosticDialog from '../../components/DiagnosticDialog.svelte';
    import type { DiagnosticStage, DiagnosticResult } from '../../utils/diagnostic-runner';
    let availableModels = $state<ModelMetadata[]>([]);
    let installedModels = $state<InstalledModel[]>([]);
    let health = $state<HealthStatus | null>(null);
    let classifierStatus = $state<ClassifierStatus | null>(null);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let downloadStatuses = $state<Record<string, DownloadProgress>>({});
    let activating = $state<string | null>(null);
    let selectedModelId = $state<string | null>(null);

    // Guided install wizard: download (with live progress) → validate on hardware →
    // enable. Reused for an already-downloaded model by skipping the download stage.
    let wizardModel = $state<ModelMetadata | null>(null);
    let wizardStages = $state<DiagnosticStage[]>([]);
    let wizardBusy = $state(false);
    let wizardResult = $state<DiagnosticResult | null>(null);
    let wizardRunId = $state(0);
    let wizardDownload = $state(false);
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

    function statusLabel(status: string | undefined): string {
        return formatMetadataLabel(status ?? 'stable');
    }

    function tierChipClass(tier: string): string {
        switch (tier) {
            case 'cpu_only':
                return 'bg-accent-500/10 text-accent-700 dark:text-accent-300 border-accent-500/20';
            case 'large':
                return 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/20';
            case 'advanced':
                return 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20';
            default:
                return 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';
        }
    }

    function statusChipClass(status: string | undefined): string {
        switch (status ?? 'stable') {
            case 'stable':
                return 'bg-accent-500/10 text-accent-700 dark:text-accent-300 border-accent-500/20';
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

    let pollInterval: ReturnType<typeof setInterval> | undefined;
    let pollingDownloads = false;

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
        if (pollingDownloads || document.hidden) return;
        pollingDownloads = true;
        const activeIds = Object.keys(downloadStatuses).filter(id => 
            downloadStatuses[id].status === 'downloading' || downloadStatuses[id].status === 'pending'
        );

        try {
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
        } finally {
            pollingDownloads = false;
        }
    }

    function getInstalledModel(modelId: string): InstalledModel | undefined {
        return installedModels.find(m => m.id === modelId);
    }

    function isInstalled(modelId: string): boolean {
        return Boolean(getInstalledModel(modelId));
    }

    function isReady(modelId: string): boolean {
        const installed = getInstalledModel(modelId);
        return Boolean(installed && installed.ready !== false);
    }

    function isActive(modelId: string): boolean {
        return installedModels.some(m => m.id === modelId && m.is_active && m.ready !== false);
    }

    function isValidated(modelId: string): boolean {
        const installed = getInstalledModel(modelId);
        // Default to permissive if the field is absent (older backend) so we never
        // block selection on a contract the server does not yet report.
        return Boolean(installed && installed.validated !== false);
    }

    function isCropDetectorInstalled(modelId: string): boolean {
        return installedModels.some((model) => model.id === modelId);
    }

    function getProviderSupport(model: ModelMetadata): string[] {
        if (Array.isArray(model.supported_inference_providers) && model.supported_inference_providers.length > 0) {
            return model.supported_inference_providers;
        }
        // Older registries may not declare a provider contract. CPU is the only
        // path that can be advertised safely without per-model validation.
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
            case 'intel_npu':
                return t('settings.detection.model_manager_provider_intel_npu', 'Intel NPU (OpenVINO)');
            default:
                return formatMetadataLabel(provider);
        }
    }

    function providerChipClass(provider: string): string {
        switch (provider) {
            case 'cuda':
                return 'bg-accent-500/10 text-accent-700 dark:text-accent-300 border-accent-500/20';
            case 'intel_gpu':
                return 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-500/20';
            case 'intel_npu':
                return 'bg-violet-500/10 text-violet-700 dark:text-violet-300 border-violet-500/20';
            case 'intel_cpu':
                return 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20';
            default:
                return 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';
        }
    }

    function getDynamicProviderChips(model: ModelMetadata, active: boolean): Array<{ label: string; className: string; title: string }> {
        if (!active) return [];

        const activeProvider = classifierStatus?.active_provider ?? null;
        return getRuntimeProviderOrder(classifierStatus, getProviderSupport(model))
            .map((provider) => {
                const baseLabel = providerLabel(provider);
                const isActive = activeProvider === provider;

                if (isActive) {
                    return {
                        label: `${baseLabel}: ${t('settings.detection.model_manager_provider_active_suffix', 'Active')}`,
                        className: 'bg-accent-500/10 text-accent-700 dark:text-accent-300 border-accent-500/20',
                        title: t('settings.detection.active_provider_label', 'Active')
                    };
                }
                return {
                    label: `${baseLabel}: ${t('settings.detection.model_manager_provider_fallback_suffix', 'Fallback')}`,
                    className: 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20',
                    title: t('settings.detection.model_manager_provider_fallback_title', 'Automatic fallback in the order shown')
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

    let deleting = $state<string | null>(null);

    function formatBytes(bytes: number): string {
        if (!Number.isFinite(bytes) || bytes <= 0) return '';
        const gb = bytes / 1_000_000_000;
        if (gb >= 1) return `${gb.toFixed(1)} GB`;
        return `${Math.round(bytes / 1_000_000)} MB`;
    }

    async function handleDelete(model: InstalledModel | ModelMetadata) {
        if (deleting) return;
        const name = 'name' in model && model.name ? model.name : model.id;
        // Irreversible and large, so the confirmation names the model and says
        // what getting it back costs.
        const confirmed = confirm(
            t('settings.detection.model_manager_delete_confirm', 'Delete {name}? This removes the files from disk. You can download it again later.')
                .replace('{name}', String(name))
        );
        if (!confirmed) return;
        deleting = model.id;
        try {
            const result = await deleteModel(model.id);
            installedModels = await fetchInstalledModels();
            const freed = formatBytes(result.bytes_freed ?? 0);
            if (freed) {
                deleteNotice = t('settings.detection.model_manager_delete_done', 'Deleted. {size} reclaimed.').replace('{size}', freed);
            }
        } catch (e) {
            console.error(e);
            const detail = e instanceof Error ? e.message : '';
            alert(detail || t('settings.detection.model_manager_delete_error', 'Failed to delete model'));
        } finally {
            deleting = null;
        }
    }

    let deleteNotice = $state<string | null>(null);

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

    // Poll a download to completion, reporting percent, so the wizard can show live
    // progress. Resolves on completion; throws on error.
    async function pollWizardDownload(modelId: string, onPct: (pct: number) => void): Promise<void> {
        for (;;) {
            await new Promise((resolve) => setTimeout(resolve, 1500));
            const status = await fetchDownloadStatus(modelId);
            if (!status) continue;
            onPct(status.progress ?? 0);
            if (status.status === 'completed') return;
            if (status.status === 'error') {
                throw new Error(status.error || t('settings.detection.model_manager_start_failed', 'Download failed'));
            }
        }
    }

    // One guided flow: download the model (with progress), validate it on this
    // hardware, then enable it. `download: false` reuses it for an already-installed
    // model that only needs validating — the download stage is shown as skipped.
    async function runInstallWizard(model: ModelMetadata, opts: { download: boolean }) {
        if (wizardBusy) return;
        wizardModel = model;
        wizardDownload = opts.download;
        wizardResult = null;
        wizardBusy = true;
        wizardRunId += 1;

        const checking = t('common.testing', 'Checking…');
        const skipped = t('diagnostics.step_skipped', 'Not run because an earlier step failed.');
        const stages: DiagnosticStage[] = [
            {
                id: 'download',
                label: t('settings.detection.model_manager_install_stage_download', 'Download model'),
                state: opts.download ? 'pending' : 'skipped',
                message: opts.download
                    ? ''
                    : t('settings.detection.model_manager_install_already_downloaded', 'Already downloaded.')
            },
            { id: 'validate', label: t('settings.detection.model_manager_validate_stage_run', 'Validate & tune on your hardware'), state: 'pending', message: '' },
            { id: 'enable', label: t('settings.detection.model_manager_validate_stage_enable', 'Enable for selection'), state: 'pending', message: '' }
        ];
        wizardStages = stages;
        const set = (i: number, patch: Partial<DiagnosticStage>) => {
            stages[i] = { ...stages[i], ...patch };
            wizardStages = [...stages];
        };
        const fail = async (i: number, message: string) => {
            set(i, { state: 'failed', message });
            for (let j = i + 1; j < stages.length; j++) set(j, { state: 'skipped', message: skipped });
            wizardResult = { ok: false, message };
            wizardBusy = false;
            installedModels = await fetchInstalledModels();
        };

        // Stage 1 — download
        if (opts.download) {
            set(0, { state: 'running', message: t('settings.detection.model_manager_installing_pct', 'Downloading… {pct}%', { pct: 0 }) });
            try {
                const started = await downloadModel(model.id);
                if (started.status !== 'pending') {
                    throw new Error(started.message || t('settings.detection.model_manager_start_failed', 'Failed to start download'));
                }
                await pollWizardDownload(model.id, (pct) =>
                    set(0, { state: 'running', message: t('settings.detection.model_manager_installing_pct', 'Downloading… {pct}%', { pct: Math.round(pct) }) })
                );
                set(0, { state: 'passed', message: t('settings.detection.model_manager_install_downloaded', 'Downloaded and verified.') });
                installedModels = await fetchInstalledModels();
            } catch (e) {
                await fail(0, e instanceof Error ? e.message : t('settings.detection.model_manager_start_failed', 'Download failed'));
                return;
            }
        }

        // Stage 2 — validate on this hardware and pick the fastest device. The backend
        // sweeps just this model across the providers owned by the running image
        // (CPU / CUDA / Intel), records what passed, and selects the fastest result.
        set(1, { state: 'running', message: t('settings.detection.model_manager_device_sweeping', 'Comparing your devices…') });
        try {
            const result = await validateModel(model.id);
            if (!result.ok) {
                await fail(1, result.reason);
                return;
            }
            const ms = result.latency_ms ? ` · ${Math.round(result.latency_ms)} ms/frame` : '';
            const msg = result.best_provider
                ? t('settings.detection.model_manager_device_set', 'Fastest verified provider: {provider}{ms} — it will be applied when this model is enabled.', { provider: result.best_provider, ms })
                : t('settings.detection.model_manager_validate_ran_ok', 'Ran on {provider}{ms} and produced valid output.', { provider: result.provider, ms });
            set(1, { state: 'passed', message: msg });
        } catch (e) {
            await fail(1, e instanceof Error ? e.message : t('settings.detection.model_manager_validate_failed', 'Validation failed.'));
            return;
        }

        // Stage 3 — enable for selection
        set(2, { state: 'running', message: checking });
        try {
            await activateModel(model.id);
            set(2, { state: 'passed', message: t('settings.detection.model_manager_validate_enabled', 'This model is now active.') });
            wizardResult = { ok: true, message: t('settings.detection.model_manager_validate_enabled', 'This model is now active.') };
        } catch (e) {
            await fail(2, e instanceof Error ? e.message : t('settings.detection.model_manager_activate_error', 'Failed to activate model'));
            return;
        }
        wizardBusy = false;
        installedModels = await fetchInstalledModels();
    }

    function handleInstall(model: ModelMetadata) {
        return runInstallWizard(model, { download: true });
    }

    function handleValidate(model: ModelMetadata) {
        return runInstallWizard(model, { download: false });
    }

    function closeWizard() {
        if (wizardBusy) return;
        wizardModel = null;
        wizardStages = [];
        wizardResult = null;
    }
</script>

<div class="space-y-6">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
            <h2 class="text-2xl font-bold text-slate-900 dark:text-white">
                {$_('settings.detection.model_manager_title', { default: 'Model Manager' })}
            </h2>
            <p class="mt-1 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                {$_('settings.detection.model_manager_subtitle', { default: 'Recommended models are shown by default. Lower-performing and niche options are hidden until you need them.' })}
            </p>
        </div>
        <button
            type="button"
            onclick={loadData}
            class="btn btn-secondary min-h-11 px-4 self-start"
            aria-label={$_('settings.detection.model_manager_refresh', { default: 'Refresh' })}
            title={$_('settings.detection.model_manager_refresh', { default: 'Refresh' })}
        >
            <svg class="h-4 w-4 {loading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 0 0 4.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 0 1-15.357-2m15.357 2H15" />
            </svg>
            {$_('settings.detection.model_manager_refresh', { default: 'Refresh' })}
        </button>
    </header>

    {#if loading}
        <div class="flex min-h-32 items-center justify-center" role="status">
            <div class="h-8 w-8 animate-spin rounded-full border-4 border-brand-500 border-t-transparent"></div>
            <span class="sr-only">{$_('common.loading', { default: 'Loading…' })}</span>
        </div>
    {:else if error}
        <div class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300" role="alert">
            {error}
        </div>
    {:else}
        {@const cropDetectorModels = availableModels
            .filter((model) => (model.artifact_kind || 'classifier') === 'crop_detector')
            .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))}
        {@const classifierModels = availableModels.filter((model) => (model.artifact_kind || 'classifier') === 'classifier')}
        {@const visibleModels = getVisibleTieredModelLineup(classifierModels, showAdvancedModels, selectedModelId)}
        {@const modelGroups = groupTieredModelLineup(classifierModels, showAdvancedModels, selectedModelId)}
        {@const advancedCount = classifierModels.filter((model) => model.advanced_only).length}
        {@const selectedCropDetector = cropDetectorModels.find((model) => (model.tier || '').toLowerCase() === 'accurate')
            || cropDetectorModels[0]}
        {@const selectedCropDetectorInstalled = selectedCropDetector ? isCropDetectorInstalled(selectedCropDetector.id) : false}
        {@const selectedCropDetectorDownload = selectedCropDetector ? downloadStatuses[selectedCropDetector.id] : undefined}
        {@const selectedCropDetectorRuntime = selectedCropDetector && cropDetectorStatus?.model_id === selectedCropDetector.id
            ? cropDetectorStatus
            : null}

        <div class="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/80 dark:border-slate-700/80 dark:bg-slate-900/70">
            <div class="border-b border-slate-200/80 bg-gradient-to-r from-brand-50/80 via-accent-50/35 to-white p-5 dark:border-slate-700/80 dark:from-brand-950/30 dark:via-accent-950/10 dark:to-slate-900 sm:p-6">
                <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                    <div class="max-w-2xl flex-1">
                        <label for="classifier-model-select" class="block text-base font-bold text-slate-900 dark:text-white">
                            {$_('settings.detection.model_manager_select_label', { default: 'Choose the identification model' })}
                        </label>
                        <p class="mt-1 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                            {$_('settings.detection.model_manager_lineup_desc', { default: 'Recommended models are shown first. Lower-performing and niche options are collapsed below.' })}
                        </p>
                        <select id="classifier-model-select" bind:value={selectedModelId} class="select-base mt-3 w-full sm:max-w-xl">
                            {#each modelGroups as group (group.category)}
                                <optgroup label={group.info.label}>
                                    {#each group.models as modelOption (modelOption.id)}
                                        {@const installedOption = getInstalledModel(modelOption.id)}
                                        <option value={modelOption.id}>
                                            {modelOption.name} {isActive(modelOption.id) ? '— Active' : installedOption?.ready === false ? '— Repair needed' : installedOption ? '— Installed' : ''}
                                        </option>
                                    {/each}
                                </optgroup>
                            {/each}
                        </select>
                    </div>

                    {#if advancedCount > 0}
                        <button
                            type="button"
                            onclick={() => {
                                showAdvancedModels = !showAdvancedModels;
                                if (!showAdvancedModels) {
                                    const collapsedModels = getVisibleTieredModelLineup(classifierModels, false, selectedModelId);
                                    if (!collapsedModels.some((model) => model.id === selectedModelId)) {
                                        selectedModelId = collapsedModels[0]?.id || null;
                                    }
                                }
                            }}
                            class="btn btn-secondary min-h-11 px-4 shrink-0"
                        >
                            {showAdvancedModels
                                ? $_('settings.detection.model_manager_hide_advanced', { default: 'Show fewer models' })
                                : $_('settings.detection.model_manager_show_advanced', { values: { count: advancedCount }, default: 'Show all models ({count} more)' })}
                        </button>
                    {/if}
                </div>
            </div>

            {#if selectedModelId}
                {@const model = visibleModels.find((entry) => entry.id === selectedModelId) || visibleModels[0]}
                {#if model}
                    {@const installedEntry = getInstalledModel(model.id)}
                    {@const installed = Boolean(installedEntry)}
                    {@const ready = isReady(model.id)}
                    {@const active = isActive(model.id)}
                    {@const validated = isValidated(model.id)}
                    {@const download = downloadStatuses[model.id]}
                    {@const inProgress = download?.status === 'downloading' || download?.status === 'pending'}
                    {@const category = categorizeModel(model)}
                    {@const runtimeProviderOrder = active ? getRuntimeProviderOrder(classifierStatus, getProviderSupport(model)) : []}
                    {@const dynamicProviderChips = getDynamicProviderChips(model, active)}

                    <section aria-labelledby="selected-model-name">
                        <div class="p-5 sm:p-6">
                            <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                                <div class="max-w-3xl">
                                    <div class="flex flex-wrap items-center gap-2">
                                        <h3 id="selected-model-name" class="text-xl font-bold text-slate-900 dark:text-white">
                                            {model.name}
                                        </h3>
                                        {#if active}
                                            <span class="rounded-full bg-brand-100 px-2.5 py-1 text-xs font-semibold text-brand-800 dark:bg-brand-950/60 dark:text-brand-200">
                                                {$_('settings.detection.model_manager_active', { default: 'Active' })}
                                            </span>
                                        {/if}
                                    </div>
                                    <p class="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{model.description}</p>
                                </div>
                                <div class="flex flex-wrap gap-2">
                                    <span class="rounded-full border px-2.5 py-1 text-xs font-semibold {tierChipClass(model.tier)}">
                                        {tierLabel(model.tier)}
                                    </span>
                                    <span class="rounded-full border px-2.5 py-1 text-xs font-semibold {statusChipClass(model.status)}">
                                        {statusLabel(model.status)}
                                    </span>
                                </div>
                            </div>

                            <dl class="mt-6 divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-700 dark:border-slate-700">
                                <div class="grid gap-1 py-4 sm:grid-cols-[11rem_1fr] sm:gap-5">
                                    <dt class="text-sm font-semibold text-slate-500 dark:text-slate-400">
                                        {$_('settings.detection.model_manager_recommended_for', { default: 'Recommended for' })}
                                    </dt>
                                    <dd class="text-sm font-medium text-slate-800 dark:text-slate-100">{model.recommended_for}</dd>
                                </div>
                                {#if active && classifierStatus?.active_provider}
                                    <div class="grid gap-1 py-4 sm:grid-cols-[11rem_1fr] sm:gap-5" aria-live="polite">
                                        <dt class="text-sm font-semibold text-slate-500 dark:text-slate-400">
                                            {$_('settings.detection.model_manager_current_runtime', { default: 'Current runtime' })}
                                        </dt>
                                        <dd class="text-sm text-slate-800 dark:text-slate-100">
                                            <span class="inline-flex items-center gap-2 font-semibold">
                                                <span class="h-2 w-2 rounded-full bg-accent-500" aria-hidden="true"></span>
                                                {providerLabel(classifierStatus.active_provider)}
                                            </span>
                                            {#if runtimeProviderOrder.length > 1}
                                                <span class="mt-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                                                    {$_('settings.detection.model_manager_runtime_order', { default: 'Automatic order' })}:
                                                    {runtimeProviderOrder.map(providerLabel).join(' → ')}
                                                </span>
                                            {/if}
                                        </dd>
                                    </div>
                                {/if}
                                <div class="grid gap-1 py-4 sm:grid-cols-[11rem_1fr] sm:gap-5">
                                    <dt class="text-sm font-semibold text-slate-500 dark:text-slate-400">
                                        {$_('settings.detection.model_manager_best_fit', { default: 'Best fit' })}
                                    </dt>
                                    <dd class="text-sm font-medium text-slate-800 dark:text-slate-100">
                                        {MODEL_CATEGORY_INFO[category].label} · {scopeLabel(model.taxonomy_scope)} · {model.inference_speed}
                                    </dd>
                                </div>
                                <div class="grid gap-1 py-4 sm:grid-cols-[11rem_1fr] sm:gap-5">
                                    <dt class="text-sm font-semibold text-slate-500 dark:text-slate-400">
                                        {$_('settings.detection.model_manager_download_size', { default: 'Download and memory' })}
                                    </dt>
                                    <dd class="text-sm font-medium text-slate-800 dark:text-slate-100">
                                        {model.file_size_mb} MB{formatRamLabel(model) ? ' · ' + formatRamLabel(model) : ''}
                                    </dd>
                                </div>
                            </dl>

                            {#if model.notes}
                                <p class="mt-4 text-sm leading-relaxed text-slate-500 dark:text-slate-400">{model.notes}</p>
                            {/if}

                            {#if model.recommended_threshold != null}
                                <div class="mt-4 border-l-2 border-amber-400 pl-3 text-sm text-slate-600 dark:text-slate-300">
                                    {$_('settings.detection.model_manager_threshold_hint', { default: 'Recommended confidence threshold for this model:' })}
                                    <strong class="text-slate-900 dark:text-white">{Math.round(model.recommended_threshold * 100)}%</strong>
                                </div>
                            {/if}

                            {#if installed && !ready}
                                <div class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-800 dark:border-amber-800/60 dark:bg-amber-900/20 dark:text-amber-200" role="alert">
                                    {$_('settings.detection.model_manager_repair_needed', { default: 'This model install is incomplete. Re-download it to repair the missing labels or configuration before activation.' })}
                                </div>
                            {:else if installed && !active && !validated}
                                <div class="mt-4 rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800 dark:border-sky-800/60 dark:bg-sky-900/20 dark:text-sky-200">
                                    {$_('settings.detection.model_manager_validation_needed', { default: 'Downloaded but not yet validated on your hardware. Validate it to confirm it runs here before you select it.' })}
                                </div>
                            {/if}
                        </div>

                        <details class="group border-t border-slate-200 dark:border-slate-700">
                            <summary class="flex min-h-12 cursor-pointer list-none items-center justify-between gap-4 px-5 py-3 text-sm font-semibold text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:text-slate-200 sm:px-6">
                                <span>{$_('settings.detection.model_manager_technical_details', { default: 'Technical details' })}</span>
                                <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 9 6 6 6-6" />
                                </svg>
                            </summary>
                            <div class="space-y-6 border-t border-slate-200 px-5 py-5 dark:border-slate-700 sm:px-6">
                                <div>
                                    <h4 class="text-sm font-bold text-slate-900 dark:text-white">
                                        {$_('settings.detection.model_manager_crop_policy_automatic', { default: 'Image preparation is automatic' })}
                                    </h4>
                                    <p class="mt-1 max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                                        {$_('settings.detection.model_manager_crop_policy_automatic_desc', { default: 'YA-WAMF uses the crop policy tested for this model. There is nothing to tune when you switch models.' })}
                                    </p>
                                </div>

                                <dl class="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
                                    <div>
                                        <dt class="font-semibold text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_architecture', { default: 'Architecture' })}</dt>
                                        <dd class="mt-1 font-medium text-slate-800 dark:text-slate-100">{model.architecture}</dd>
                                    </div>
                                    <div>
                                        <dt class="font-semibold text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_runtime', { default: 'Runtime' })}</dt>
                                        <dd class="mt-1 font-medium uppercase text-slate-800 dark:text-slate-100">{model.runtime}</dd>
                                    </div>
                                    <div>
                                        <dt class="font-semibold text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_accuracy', { default: 'Accuracy' })}</dt>
                                        <dd class="mt-1 font-medium text-slate-800 dark:text-slate-100">{model.accuracy_tier}</dd>
                                    </div>
                                    <div>
                                        <dt class="font-semibold text-slate-500 dark:text-slate-400">{$_('settings.detection.model_manager_runtime_health', { default: 'Runtime health' })}</dt>
                                        <dd class="mt-1 font-medium text-slate-800 dark:text-slate-100">
                                            {health?.ml
                                                ? (health.ml.runtimes.tflite.installed ? 'TFLite ✓' : 'TFLite —') + ' · ' + (health.ml.runtimes.onnx.installed ? 'ONNX ✓' : 'ONNX —')
                                                : '—'}
                                        </dd>
                                    </div>
                                </dl>

                                <div>
                                    <h4 class="text-sm font-bold text-slate-900 dark:text-white">
                                        {active
                                            ? $_('settings.detection.model_manager_runtime_order', { default: 'Automatic order' })
                                            : $_('settings.detection.model_manager_provider_pills', { default: 'Supported providers' })}
                                    </h4>
                                    <div class="mt-2 flex flex-wrap gap-2">
                                        {#if dynamicProviderChips.length > 0}
                                            {#each dynamicProviderChips as chip}
                                                <span class="rounded-full border px-2.5 py-1 text-xs font-semibold {chip.className}" title={chip.title}>{chip.label}</span>
                                            {/each}
                                        {:else}
                                            {#each getProviderSupport(model) as provider}
                                                <span class="rounded-full border px-2.5 py-1 text-xs font-semibold {providerChipClass(provider)}">{providerLabel(provider)}</span>
                                            {/each}
                                        {/if}
                                    </div>
                                </div>

                            </div>
                        </details>

                        <div class="flex flex-col gap-4 border-t border-slate-200 bg-slate-50/60 p-5 dark:border-slate-700 dark:bg-slate-950/30 sm:p-6">
                            {#if inProgress}
                                <div class="w-full" role="status">
                                    <div class="mb-2 flex justify-between text-sm">
                                        <span class="font-semibold text-brand-700 dark:text-brand-300">
                                            {installed
                                                ? $_('settings.detection.model_manager_redownloading', { default: 'Re-downloading…' })
                                                : $_('settings.detection.model_manager_downloading', { default: 'Downloading…' })}
                                        </span>
                                        <span class="font-medium text-slate-600 dark:text-slate-300">{download.progress.toFixed(0)}%</span>
                                    </div>
                                    <div class="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                        <div class="h-full bg-brand-500 transition-all duration-300" style="width: {download.progress}%"></div>
                                    </div>
                                </div>
                            {:else}
                                {#if download?.status === 'error' && download.error}
                                    <div class="rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300" role="alert">
                                        {download.error}
                                    </div>
                                {/if}
                                <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                                    {#if installed}
                                        <button type="button" onclick={() => handleDownload(model)} class="btn btn-secondary min-h-11 px-4">
                                            {ready
                                                ? $_('settings.detection.model_manager_redownload', { default: 'Re-download' })
                                                : $_('settings.detection.model_manager_repair_download', { default: 'Repair download' })}
                                        </button>
                                        {#if ready && !active && validated}
                                            <button
                                                type="button"
                                                onclick={() => handleActivate(model.id)}
                                                disabled={activating !== null}
                                                class="btn btn-primary min-h-11 px-4"
                                            >
                                                {activating === model.id
                                                    ? $_('settings.detection.model_manager_activating', { default: 'Activating…' })
                                                    : $_('settings.detection.model_manager_activate', { default: 'Use this model' })}
                                            </button>
                                        {:else if ready && !active && !validated}
                                            <button
                                                type="button"
                                                onclick={() => handleValidate(model)}
                                                disabled={wizardBusy}
                                                class="btn btn-primary min-h-11 px-4"
                                            >
                                                {$_('settings.detection.model_manager_validate_to_enable', { default: 'Validate to enable' })}
                                            </button>
                                        {:else if active}
                                            <span class="flex min-h-11 items-center justify-center px-4 text-sm font-semibold text-brand-700 dark:text-brand-300">
                                                {$_('settings.detection.model_manager_currently_active', { default: 'Currently active' })}
                                            </span>
                                        {/if}
                                        {#if !active}
                                            <button
                                                type="button"
                                                onclick={() => handleDelete(model)}
                                                disabled={deleting !== null || wizardBusy}
                                                class="btn btn-ghost min-h-11 px-4 text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-500/10"
                                            >
                                                {deleting === model.id
                                                    ? $_('settings.detection.model_manager_deleting', { default: 'Deleting…' })
                                                    : $_('settings.detection.model_manager_delete', { default: 'Delete files' })}
                                            </button>
                                        {/if}
                                    {:else}
                                        <button type="button" onclick={() => handleInstall(model)} disabled={wizardBusy} class="btn btn-primary min-h-11 px-4">
                                            {$_('settings.detection.model_manager_download_setup', { default: 'Download & set up' })}
                                        </button>
                                    {/if}
                                </div>
                            {/if}
                        </div>
                    </section>
                {/if}
            {/if}

            {#if selectedCropDetector}
                <details class="group border-t border-slate-200 dark:border-slate-700">
                    <summary class="flex min-h-12 cursor-pointer list-none items-center justify-between gap-4 px-5 py-3 text-sm font-semibold text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:text-slate-200 sm:px-6">
                        <span>{$_('settings.detection.model_manager_thumbnail_crop_title', { default: 'Cropped thumbnails' })}</span>
                        <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 9 6 6 6-6" />
                        </svg>
                    </summary>
                    <div class="space-y-5 border-t border-slate-200 px-5 py-5 dark:border-slate-700 sm:px-6">
                        <div class="grid gap-4">
                            <div>
                                <p class="text-sm font-bold text-slate-900 dark:text-white">
                                    {$_('settings.detection.model_manager_thumbnail_crop_quality', { default: 'Automatic best quality' })}
                                </p>
                                <p class="mt-1 max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                                    {$_('settings.detection.model_manager_thumbnail_crop_desc', { default: 'YA-WAMF evaluates the accurate detector, fast fallback, and Frigate tracking hints automatically; the clear full frame is used only if none yields a reliable crop.' })}
                                </p>
                            </div>
                        </div>

                        <div class="flex flex-col gap-4 border-t border-slate-200 pt-4 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between">
                            <p class="text-sm text-slate-600 dark:text-slate-300">
                                <span class="font-semibold text-slate-900 dark:text-white">{selectedCropDetector.name}</span>
                                · {selectedCropDetectorRuntime?.enabled_for_runtime || selectedCropDetectorInstalled
                                    ? $_('settings.detection.model_manager_detector_ready', { default: 'Ready' })
                                    : $_('settings.detection.model_manager_detector_missing', { default: 'Download required' })}
                            </p>
                            <button
                                type="button"
                                onclick={() => handleDownload(selectedCropDetector)}
                                disabled={selectedCropDetectorDownload?.status === 'downloading' || selectedCropDetectorDownload?.status === 'pending'}
                                class="btn btn-secondary min-h-11 shrink-0 px-4"
                            >
                                {selectedCropDetectorInstalled
                                    ? $_('settings.detection.model_manager_redownload', { default: 'Re-download' })
                                    : $_('settings.detection.model_manager_download_detector', { default: 'Download detector' })}
                            </button>
                        </div>
                        {#if selectedCropDetectorDownload?.status === 'downloading' || selectedCropDetectorDownload?.status === 'pending'}
                            <div role="status">
                                <div class="mb-1 flex justify-between text-xs font-semibold">
                                    <span class="text-brand-700 dark:text-brand-300">{$_('settings.detection.model_manager_downloading_detector', { default: 'Downloading detector…' })}</span>
                                    <span class="text-slate-500">{selectedCropDetectorDownload.progress.toFixed(0)}%</span>
                                </div>
                                <div class="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                    <div class="h-full bg-brand-500 transition-all duration-300" style="width: {selectedCropDetectorDownload.progress}%"></div>
                                </div>
                            </div>
                        {/if}
                    </div>
                </details>
            {/if}
        </div>

        {#if !showAdvancedModels && advancedCount > 0}
            <p class="px-1 text-sm text-slate-500 dark:text-slate-400">
                {$_('settings.detection.model_manager_advanced_hidden', { default: 'Legacy and lower-performing models are hidden. Use “Show all models” to see every option.' })}
            </p>
        {/if}
    {/if}
</div>

{#if wizardModel}
    <DiagnosticDialog
        title={$_('settings.detection.model_manager_install_title', { default: 'Set up model' })}
        subtitle={$_('settings.detection.model_manager_install_subtitle', {
            default: 'Download, validate on your hardware, and enable this model.'
        })}
        stages={wizardStages}
        busy={wizardBusy}
        result={wizardResult}
        runId={wizardRunId}
        note={$_('settings.detection.model_manager_install_note', {
            default: 'Each step runs on your hardware. Nothing becomes active until validation passes.'
        })}
        runningLabel={$_('common.working', { default: 'Working…' })}
        onClose={closeWizard}
        onRetry={() => wizardModel && runInstallWizard(wizardModel, { download: wizardDownload })}
    >
        {#snippet summary()}
            {wizardModel?.name}
        {/snippet}
    </DiagnosticDialog>
{/if}

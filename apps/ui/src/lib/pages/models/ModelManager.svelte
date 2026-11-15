<script lang="ts">
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import { onMount, onDestroy } from 'svelte';
    import { fetchAvailableModels, fetchInstalledModels, downloadModel, fetchDownloadStatus, activateModel, deleteModel, validateModel, checkHealth, getVisibleTieredModelLineup, groupTieredModelLineup, categorizeModel, MODEL_CATEGORY_INFO, type ModelMetadata, type InstalledModel, type DownloadProgress, type ClassifierStatus, type HealthStatus } from '../../api';
    import { jobProgressStore } from '../../stores/job_progress.svelte';
    import { confirmAction } from '../../stores/confirm_dialog.svelte';
    import { toastStore } from '../../stores/toast.svelte';
    import { startModelDownloadProgress, syncModelDownloadProgress } from './model_download_progress';
    import { usesSavedFeederLocation } from './model_location_input';
    import { getRuntimeProviderOrder } from '../../settings/inference-providers';
    import { BIRD_FINDER_MODEL_IDS, birdFinderDevice, type BirdFinder, type BirdFinderProvider } from '../../settings/bird-finder';
    import { settingsStore } from '../../stores/settings.svelte';
    import FinderDevicePanel from './FinderDevicePanel.svelte';
    import { toAppPath } from '../../app/url-base';
    import DiagnosticDialog from '../../components/DiagnosticDialog.svelte';
    import type { DiagnosticStage, DiagnosticResult } from '../../utils/diagnostic-runner';
    // The live runtime is owned by the Settings page, so the band, the runtime
    // report and this card always show the same, freshest provider.
    let { executionMode = 'subprocess', autoVideoEnabled = false, birdFinder = $bindable<BirdFinder>('yolox_tiny'), birdFinderProvider = $bindable<BirdFinderProvider>('auto'), classifierStatus, deviceCheckRunning = false, onruntimechange, onopenlocationsettings, oncheckfinderdevices }: {
        executionMode?: string;
        autoVideoEnabled?: boolean;
        /** The finder staged in the settings form; it is saved by Save changes with everything else. */
        birdFinder?: BirdFinder;
        birdFinderProvider?: BirdFinderProvider;
        classifierStatus: ClassifierStatus | null;
        /** A device check owned by the Settings page is running, so another cannot start. */
        deviceCheckRunning?: boolean;
        onruntimechange?: () => Promise<unknown>;
        onopenlocationsettings?: () => void;
        /** Runs the shared device check for one finder and settles when it finishes. */
        oncheckfinderdevices?: (modelId: string) => Promise<void>;
    } = $props();

    // Switching tabs in place keeps unsaved settings edits; a full page load
    // would discard them. Modified clicks still open a new tab as usual.
    function handleLocationSettingsClick(event: MouseEvent): void {
        if (
            !onopenlocationsettings
            || event.button !== 0
            || event.metaKey
            || event.ctrlKey
            || event.shiftKey
            || event.altKey
        ) {
            return;
        }
        event.preventDefault();
        onopenlocationsettings();
    }

    let availableModels = $state<ModelMetadata[]>([]);
    let installedModels = $state<InstalledModel[]>([]);
    let health = $state<HealthStatus | null>(null);
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
    // The model in use is shown on its own; the full list opens on request, or by itself while
    // nothing is in use, since choosing a model is then the first thing to do.
    let catalogueRequested = $state(false);
    const anyModelInUse = $derived(
        installedModels.some((model) => model.is_active && model.ready !== false)
            || (Boolean(classifierStatus?.effective_model_id) && classifierStatus?.active_model_installed === true)
    );
    const catalogueOpen = $derived(catalogueRequested || !anyModelInUse);
    const cropDetectorStatus = $derived(classifierStatus?.crop_detector ?? null);
    // What the running service has saved, as opposed to the form's staged choice.
    const savedBirdFinder = $derived<BirdFinder | null>(
        cropDetectorStatus
            ? (cropDetectorStatus.chosen_model_id === BIRD_FINDER_MODEL_IDS.rfdetr_nano ? 'rfdetr_nano' : 'yolox_tiny')
            : null
    );
    const hostProviders = $derived(classifierStatus?.host_available_providers ?? classifierStatus?.available_providers ?? []);


    // The check writes new device evidence, so the finder cards must re-read it.
    async function checkFinderDevices(modelId: string): Promise<void> {
        if (!oncheckfinderdevices) return;
        await oncheckfinderdevices(modelId);
        try {
            installedModels = await fetchInstalledModels();
        } catch {
            /* the next load shows the result */
        }
    }

    // Until a worker reports what it loaded, the provider is the plan, not a fact.
    const runtimePlanned = $derived(classifierStatus?.runtime_source === 'planned');

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

    // Tier, maturity and execution provider are facts about the model, so every chip is neutral and the
    // word carries the meaning. None of them needs a person, and none is a second accent.
    const FACT_CHIP = 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';

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
            const [available, installed, healthData] = await Promise.all([
                fetchAvailableModels(),
                fetchInstalledModels(),
                checkHealth()
            ]);
            availableModels = available;
            installedModels = installed;
            health = healthData;

            if (!selectedModelId && installed.length > 0) {
                const activeModel = installed.find(m => m.is_active);
                if (activeModel) selectedModelId = activeModel.id;
            }
            const effectiveId = classifierStatus?.effective_model_id;
            if (!selectedModelId && effectiveId && available.some(m => m.id === effectiveId)) {
                selectedModelId = effectiveId;
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

    async function refreshModels(): Promise<void> {
        await Promise.all([loadData(), onruntimechange?.()]);
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

    // In use is what the runtime reports, not only the stored choice: the bundled model runs under
    // its file name, so the model list alone would offer it for download while it identifies birds.
    function isActive(modelId: string): boolean {
        if (classifierStatus?.effective_model_id === modelId && classifierStatus?.active_model_installed === true) return true;
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
                        className: 'bg-success-500/10 text-success-700 dark:text-success-300 border-success-500/20',
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
        const confirmed = await confirmAction({
            title: t('settings.detection.model_manager_delete', 'Delete files'),
            message: t(
                'settings.detection.model_manager_delete_confirm',
                'Delete {name}? This removes the files from disk. You can download it again later.'
            ).replace('{name}', String(name)),
            confirmLabel: t('settings.detection.model_manager_delete', 'Delete files')
        });
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
            toastStore.error(detail || t('settings.detection.model_manager_delete_error', 'Failed to delete model'));
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
            await onruntimechange?.();
        } catch (e) {
            console.error(e);
            toastStore.error(t('settings.detection.model_manager_activate_error', 'Failed to activate model'));
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
                ? t('settings.detection.model_manager_device_set', 'Fastest verified provider: {provider}{ms}. It will be applied when this model is enabled.', { provider: result.best_provider, ms })
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
        await onruntimechange?.();
    }

    function handleInstall(model: ModelMetadata) {
        return runInstallWizard(model, { download: true });
    }

    function handleValidate(model: ModelMetadata) {
        return runInstallWizard(model, { download: false });
    }

    function ramShortLabel(ramMb: number): string {
        if (ramMb >= 1024) {
            const gb = ramMb / 1024;
            return `~${Number.isInteger(gb) ? gb.toFixed(0) : gb.toFixed(1)} GB`;
        }
        return `~${ramMb} MB`;
    }

    // Every RAM meter is drawn against the heaviest model in the lineup, so the
    // bars compare models to each other rather than to an arbitrary maximum.
    function lineupMaxRam(models: ModelMetadata[]): number {
        return models.reduce((max, model) => Math.max(max, model.estimated_ram_mb ?? 0), 0);
    }

    function ramPercent(ramMb: number | null | undefined, maxRam: number): number {
        if (!ramMb || maxRam <= 0) return 0;
        return Math.max(6, Math.round((ramMb / maxRam) * 100));
    }

    // The prediction is model × process mode × concurrency: in-process shares
    // one copy inside the app; isolated workers each hold their own, so the
    // resolved live + background counts are the multiplier.
    function predictedCopies(): { copies: number; live: number; background: number; video: number } {
        if (executionMode === 'in_process') return { copies: 1, live: 0, background: 0, video: 0 };
        const live = classifierStatus?.resolved_live_workers ?? 1;
        const background = classifierStatus?.resolved_background_workers ?? 1;
        // Video analysis runs on its own worker pool sized like the background
        // pool, so with video enabled those copies are real memory too -
        // observed live as a video-0 worker no prediction accounted for.
        const video = autoVideoEnabled ? background : 0;
        return { copies: live + background + video, live, background, video };
    }

    type ModelCardState = 'active' | 'repair' | 'installed' | 'available';

    function modelCardState(modelId: string): ModelCardState {
        if (isActive(modelId)) return 'active';
        const installed = getInstalledModel(modelId);
        if (installed?.ready === false) return 'repair';
        if (installed) return 'installed';
        return 'available';
    }

    function modelCardStateLabel(state: ModelCardState): string {
        switch (state) {
            case 'active':
                return t('settings.detection.model_manager_in_use', 'In use');
            case 'repair':
                return t('settings.detection.model_manager_state_repair', 'Repair needed');
            case 'installed':
                return t('settings.detection.model_manager_state_installed', 'Installed');
            default:
                return t('settings.detection.model_manager_state_available', 'Available');
        }
    }

    function modelCardStateClass(state: ModelCardState): string {
        switch (state) {
            case 'active':
                return 'border-brand-500/30 bg-brand-100 text-brand-800 dark:bg-brand-950/60 dark:text-brand-200';
            case 'repair':
                return 'border-attention-500/30 bg-attention-500/10 text-attention-700 dark:text-attention-300';
            case 'installed':
                return 'border-slate-400/30 bg-slate-500/10 text-slate-700 dark:text-slate-300';
            default:
                return 'border-slate-300/60 bg-transparent text-slate-500 dark:border-slate-600/60 dark:text-slate-400';
        }
    }

    function closeWizard() {
        if (wizardBusy) return;
        wizardModel = null;
        wizardStages = [];
        wizardResult = null;
    }
</script>

<!-- At the narrowest widths with enlarged text a long word may break, rather than push the page sideways. -->
<div class="space-y-6 wrap-anywhere">
    {#if loading}
        <div class="flex min-h-32 items-center justify-center" role="status">
            <div class="h-8 w-8 animate-spin rounded-full border-4 border-brand-500 border-t-transparent motion-reduce:animate-none" aria-hidden="true"></div>
            <span class="sr-only">{$_('common.loading', { default: 'Loading…' })}</span>
        </div>
    {:else if error}
        <div class="text-sm font-semibold text-red-700 dark:text-red-300" role="alert">
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
        {@const maxLineupRam = lineupMaxRam(classifierModels)}
        {@const birdFinderOptions = (['yolox_tiny', 'rfdetr_nano'] as const)
            .map((choice) => ({ choice, model: cropDetectorModels.find((model) => model.id === BIRD_FINDER_MODEL_IDS[choice]) }))
            .filter((option): option is { choice: BirdFinder; model: ModelMetadata } => Boolean(option.model))}
        {@const chosenFinder = birdFinderOptions.find((option) => option.choice === birdFinder)}
        {@const chosenFinderDownload = chosenFinder ? downloadStatuses[chosenFinder.model.id] : undefined}

        <div class="space-y-6">
            <div>
                        <div class="flex flex-wrap items-start justify-between gap-3">
                            <div class="min-w-0 flex-1 basis-64">
                                <h3 id="classifier-model-lineup-label" class="text-base font-bold text-slate-900 dark:text-white">
                                    {$_('settings.detection.identification_title', { default: 'Identification model' })}
                                </h3>
                                <p class="mt-1 max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                                    {$_('settings.detection.identification_desc', { default: 'Names the species in each bird image. Larger models need more memory for every worker copy and take longer per image. Coverage differs: some know birds only, others birds and other wildlife.' })}
                                </p>
                            </div>
                            <button
                                type="button"
                                onclick={refreshModels}
                                class="btn btn-ghost inline-flex min-h-11 items-center gap-1.5 px-3 text-xs font-bold"
                                aria-label={$_('settings.detection.model_manager_refresh', { default: 'Refresh' })}
                                title={$_('settings.detection.model_manager_refresh', { default: 'Refresh' })}
                            >
                                <svg class="h-4 w-4 {loading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 0 0 4.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 0 1-15.357-2m15.357 2H15" />
                                </svg>
                                {$_('settings.detection.model_manager_refresh', { default: 'Refresh' })}
                            </button>
                        </div>
                        <button
                            type="button"
                            class="btn btn-secondary mt-3 min-h-11 px-4"
                            aria-expanded={catalogueOpen}
                            aria-controls="classifier-model-catalogue"
                            onclick={() => (catalogueRequested = !catalogueOpen)}
                            data-model-catalogue-toggle
                        >
                            {catalogueOpen
                                ? $_('settings.detection.model_manager_hide_catalogue', { default: 'Hide the other models' })
                                : $_('settings.detection.model_manager_show_catalogue', { default: 'Choose another model' })}
                        </button>
                        {#if catalogueOpen}
                        <div id="classifier-model-catalogue">
                        <div class="mt-3 space-y-4" role="group" aria-labelledby="classifier-model-lineup-label">
                            {#each modelGroups as group (group.category)}
                                <div>
                                    <p class="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{group.info.label}</p>
                                    <ul class="divide-y divide-line-soft">
                                        {#each group.models as modelOption (modelOption.id)}
                                            {@const cardState = modelCardState(modelOption.id)}
                                            {@const cardSelected = selectedModelId === modelOption.id}
                                            <li>
                                            <button
                                                type="button"
                                                aria-pressed={cardSelected}
                                                onclick={() => (selectedModelId = modelOption.id)}
                                                class="model-card flex min-h-11 w-full cursor-pointer flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus {cardSelected ? 'choice-active' : 'hover:bg-surface-raised'}"
                                            >
                                                <span class="flex min-w-0 flex-1 basis-48 flex-wrap items-center gap-2">
                                                    {#if cardSelected}
                                                        <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 4 4 10-10" /></svg>
                                                    {/if}
                                                    <span class="min-w-0 wrap-break-word text-sm font-semibold leading-snug text-slate-900 dark:text-white">{modelOption.name}</span>
                                                    <!-- Only the exceptions carry a badge; a model with neither is one to download. -->
                                                    {#if cardState !== 'available'}
                                                        <span class="shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold {modelCardStateClass(cardState)}">{modelCardStateLabel(cardState)}</span>
                                                    {/if}
                                                </span>
                                                <span class="flex flex-wrap gap-x-3 gap-y-1">
                                                    <span class="text-xs font-semibold text-slate-600 dark:text-slate-300">{scopeLabel(modelOption.taxonomy_scope)}</span>
                                                    <span class="text-xs text-slate-600 dark:text-slate-300">
                                                        {cardState === 'available'
                                                            ? t('settings.detection.model_manager_card_download', '{size} MB download', { size: modelOption.file_size_mb })
                                                            : t('settings.detection.model_manager_card_on_disk', 'On this host')}{#if modelOption.estimated_ram_mb != null}{' · '}{t('settings.detection.bird_finder_ram', '{ram} RAM', { ram: ramShortLabel(modelOption.estimated_ram_mb) })}{/if}
                                                    </span>
                                                </span>
                                            </button>
                                            </li>
                                        {/each}
                                    </ul>
                                </div>
                            {/each}
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
                        class="mt-4 flex min-h-11 w-full cursor-pointer items-center justify-center text-sm font-semibold text-slate-600 transition-colors hover:text-brand-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus dark:text-slate-300 dark:hover:text-brand-300"
                    >
                        {showAdvancedModels
                            ? $_('settings.detection.model_manager_hide_advanced', { default: 'Show fewer models' })
                            : $_('settings.detection.model_manager_show_advanced', { values: { count: advancedCount }, default: 'Show all models ({count} more)' })}
                    </button>
                {/if}
                        </div>
                        {/if}
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

                    <section aria-labelledby="selected-model-name" class="border-t border-slate-200 pt-6 dark:border-slate-700">
                        <div>
                            <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                                <div class="min-w-0 max-w-3xl">
                                    <div class="flex flex-wrap items-center gap-2">
                                        <h3 id="selected-model-name" class="text-xl font-bold text-slate-900 dark:text-white">
                                            {model.name}
                                        </h3>
                                        {#if active}
                                            <span class="rounded-full bg-brand-100 px-2.5 py-1 text-xs font-semibold text-brand-800 dark:bg-brand-950/60 dark:text-brand-200">
                                                {$_('settings.detection.model_manager_in_use', { default: 'In use' })}
                                            </span>
                                        {/if}
                                    </div>
                                    <p class="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{model.description}</p>
                                </div>
                                <div class="flex flex-wrap gap-2">
                                    <span class="max-w-full rounded-full border px-2.5 py-1 text-xs font-semibold wrap-break-word {FACT_CHIP}">
                                        {statusLabel(model.status)}
                                    </span>
                                </div>
                            </div>

                            {#if active && classifierStatus?.active_provider}
                                <p class="mt-3 text-sm text-slate-800 dark:text-slate-100" aria-live="polite">
                                    <span class="mr-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                                        {runtimePlanned
                                            ? $_('settings.detection.model_manager_planned_runtime', { default: 'Planned runtime' })
                                            : $_('settings.detection.model_manager_current_runtime', { default: 'Current runtime' })}
                                    </span>
                                    <span class="inline-flex max-w-full flex-wrap items-center gap-2 font-semibold">
                                        <span class="h-2 w-2 rounded-full {runtimePlanned ? 'bg-slate-400' : 'bg-brand-500'}" aria-hidden="true"></span>
                                        {providerLabel(classifierStatus.active_provider)}
                                    </span>
                                    {#if runtimePlanned}
                                        <span class="ml-1 text-xs font-medium text-slate-600 dark:text-slate-400">{$_('settings.detection.band_runtime_planned', { default: 'loads on first detection' })}</span>
                                    {/if}
                                    {#if runtimeProviderOrder.length > 1}
                                        <span class="mt-1 block text-xs font-medium text-slate-600 dark:text-slate-400">
                                            {$_('settings.detection.model_manager_runtime_order', { default: 'Automatic order' })}:
                                            {runtimeProviderOrder.map(providerLabel).join(' → ')}
                                        </span>
                                    {/if}
                                </p>
                            {/if}

                            {#if model.estimated_ram_mb != null}
                                {@const prediction = predictedCopies()}
                                {@const predictedTotalMb = model.estimated_ram_mb * prediction.copies}
                                <div class="mt-6">
                                    <div class="flex items-baseline justify-between gap-4">
                                        <span class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.detection.model_manager_memory_title', { default: 'Predicted RAM use' })}</span>
                                        <span class="text-sm font-bold text-slate-800 dark:text-slate-100">
                                            {$_('settings.detection.model_manager_memory_predicted', { values: { total: ramShortLabel(predictedTotalMb).replace(/^~/, '') }, default: '≈ {total}' })}
                                        </span>
                                    </div>
                                    <div class="model-ram-meter mt-2 h-2.5 overflow-hidden rounded-full bg-slate-200/80 dark:bg-slate-700/60">
                                        <div class="h-full rounded-full bg-brand-500" style="width: {ramPercent(predictedTotalMb, maxLineupRam * Math.max(1, prediction.copies))}%"></div>
                                    </div>
                                    <p class="mt-1.5 text-xs font-medium text-slate-600 dark:text-slate-400">
                                        {#if executionMode === 'in_process'}
                                            {$_('settings.detection.model_manager_memory_formula_in_process', {
                                                values: { per: ramShortLabel(model.estimated_ram_mb) },
                                                default: '{per} for one copy shared inside the app (in-process mode)'
                                            })}
                                        {:else if prediction.video > 0}
                                            {$_('settings.detection.model_manager_memory_formula_subprocess_video', {
                                                values: {
                                                    per: ramShortLabel(model.estimated_ram_mb),
                                                    live: prediction.live,
                                                    background: prediction.background,
                                                    video: prediction.video
                                                },
                                                default: '{per} per copy × {live} live + {background} background + {video} video workers (isolated mode)'
                                            })}
                                        {:else}
                                            {$_('settings.detection.model_manager_memory_formula_subprocess', {
                                                values: {
                                                    per: ramShortLabel(model.estimated_ram_mb),
                                                    live: prediction.live,
                                                    background: prediction.background
                                                },
                                                default: '{per} per copy × {live} live + {background} background workers (isolated mode)'
                                            })}
                                        {/if}
                                        · {$_('settings.detection.model_manager_card_download', { values: { size: model.file_size_mb }, default: '{size} MB download' })}
                                    </p>
                                </div>
                            {:else}
                                <p class="mt-4 text-sm font-medium text-slate-600 dark:text-slate-400">
                                    {$_('settings.detection.model_manager_card_download', { values: { size: model.file_size_mb }, default: '{size} MB download' })}
                                </p>
                            {/if}

                            {#if model.recommended_threshold != null}
                                <div class="mt-4 text-sm text-slate-600 dark:text-slate-300">
                                    {$_('settings.detection.model_manager_threshold_hint', { default: 'Recommended confidence threshold for this model:' })}
                                    <strong class="text-slate-900 dark:text-white">{Math.round(model.recommended_threshold * 100)}%</strong>
                                </div>
                            {/if}

                            {#if usesSavedFeederLocation(model)}
                                <div class="mt-4 text-sm text-slate-600 dark:text-slate-300">
                                    <p class="font-semibold text-slate-900 dark:text-white">
                                        {$_('settings.detection.model_manager_location_title', { default: 'Uses your feeder location' })}
                                    </p>
                                    <p class="mt-1 max-w-3xl leading-relaxed">
                                        {$_('settings.detection.model_manager_location_desc', { default: 'This model also uses the feeder coordinates saved in Settings → Integrations → Location. If no valid coordinates are saved, it identifies birds without location. It does not use the date or a location accuracy radius.' })}
                                    </p>
                                    <a
                                        href={toAppPath('/settings/integrations')}
                                        onclick={handleLocationSettingsClick}
                                        class="inline-flex min-h-11 items-center rounded-sm font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus dark:text-brand-300 dark:hover:text-brand-200"
                                    >
                                        {$_('settings.detection.model_manager_location_link', { default: 'Open Location settings' })}
                                    </a>
                                </div>
                            {/if}

                            {#if installed && !ready}
                                <div class="mt-4 text-sm font-semibold text-attention-800 dark:text-attention-200" role="alert">
                                    {$_('settings.detection.model_manager_repair_needed', { default: 'This model install is incomplete. Re-download it to restore the missing species names or model configuration before activation.' })}
                                </div>
                            {:else if installed && !active && !validated}
                                <div class="mt-4 text-sm text-brand-900 dark:text-brand-100">
                                    {$_('settings.detection.model_manager_validation_needed', { default: 'Downloaded but not yet validated on your hardware. Validate it to confirm it runs here before you select it.' })}
                                </div>
                            {/if}
                        </div>

                        <details class="group mt-5 border-t border-slate-200 dark:border-slate-700">
                            <summary class="flex min-h-12 cursor-pointer list-none items-center justify-between gap-4 py-3 text-sm font-semibold text-slate-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:text-slate-200">
                                <span>{$_('settings.detection.model_manager_technical_details', { default: 'Technical details' })}</span>
                                <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 9 6 6 6-6" />
                                </svg>
                            </summary>
                            <div class="space-y-6 py-4">
                                <div>
                                    <h4 class="text-sm font-bold text-slate-900 dark:text-white">
                                        {$_('settings.detection.model_manager_crop_policy_automatic', { default: 'Image preparation is automatic' })}
                                    </h4>
                                    <p class="mt-1 max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                                        {$_('settings.detection.model_manager_crop_policy_automatic_desc', { default: 'YA-WAMF uses the crop policy tested for this model. There is nothing to tune when you switch models.' })}
                                    </p>
                                </div>

                                <dl class="grid grid-cols-1 gap-4 text-sm wrap-break-word sm:grid-cols-2">
                                    <div>
                                        <dt class="font-semibold text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_recommended_for', { default: 'Recommended for' })}</dt>
                                        <dd class="mt-1 font-medium text-slate-800 dark:text-slate-100">{model.recommended_for}</dd>
                                    </div>
                                    <div>
                                        <dt class="font-semibold text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_best_fit', { default: 'Best fit' })}</dt>
                                        <dd class="mt-1 font-medium text-slate-800 dark:text-slate-100">{MODEL_CATEGORY_INFO[category].label} · {scopeLabel(model.taxonomy_scope)} · {model.inference_speed}</dd>
                                    </div>
                                </dl>

                                {#if model.notes}
                                    <p class="text-sm leading-relaxed text-slate-600 dark:text-slate-400">{model.notes}</p>
                                {/if}

                                <dl class="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
                                    <div>
                                        <dt class="font-semibold text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_architecture', { default: 'Architecture' })}</dt>
                                        <dd class="mt-1 font-medium text-slate-800 dark:text-slate-100">{model.architecture}</dd>
                                    </div>
                                    <div>
                                        <dt class="font-semibold text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_runtime', { default: 'Runtime' })}</dt>
                                        <dd class="mt-1 font-medium text-slate-800 dark:text-slate-100">{model.runtime}</dd>
                                    </div>
                                    <div>
                                        <dt class="font-semibold text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_accuracy', { default: 'Accuracy' })}</dt>
                                        <dd class="mt-1 font-medium text-slate-800 dark:text-slate-100">{model.accuracy_tier}</dd>
                                    </div>
                                    <div>
                                        <dt class="font-semibold text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_runtime_health', { default: 'Runtime health' })}</dt>
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
                                                <span class="max-w-full rounded-full border px-2.5 py-1 text-xs font-semibold wrap-break-word {chip.className}" title={chip.title}>{chip.label}</span>
                                            {/each}
                                        {:else}
                                            {#each getProviderSupport(model) as provider}
                                                <span class="max-w-full rounded-full border px-2.5 py-1 text-xs font-semibold wrap-break-word {FACT_CHIP}">{providerLabel(provider)}</span>
                                            {/each}
                                        {/if}
                                    </div>
                                </div>

                            </div>
                        </details>

                        <div class="flex flex-col gap-4 border-t border-slate-200 pt-4 dark:border-slate-700">
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
                                    <div class="text-sm font-semibold text-red-700 dark:text-red-300" role="alert">
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
                                                {$_('settings.detection.model_manager_in_use', { default: 'In use' })}
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
                                    {:else if active}
                                        <span class="flex min-h-11 items-center justify-center px-4 text-sm font-semibold text-brand-700 dark:text-brand-300" data-model-in-use>
                                            {$_('settings.detection.model_manager_in_use', { default: 'In use' })}
                                        </span>
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

            {#if birdFinderOptions.length > 0}
                <section class="border-t border-slate-200 pt-6 dark:border-slate-700">
                    <fieldset class="min-w-0 space-y-3" aria-describedby="bird-finder-desc">
                        <legend class="text-base font-bold text-slate-900 dark:text-white">
                            {$_('settings.detection.bird_finder_title', { default: 'Bird finder' })}
                        </legend>
                        <p id="bird-finder-desc" class="max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                            {$_('settings.detection.bird_finder_role', { default: 'Locates each bird in the camera frame so YA-WAMF can crop and count it. It does not name the species.' })}
                        </p>
                        <div class="space-y-1 *:min-w-0">
                            {#each birdFinderOptions as option (option.choice)}
                                {@const optionInstalled = isCropDetectorInstalled(option.model.id)}
                                {@const optionChosen = birdFinder === option.choice}
                                <label class="flex min-h-11 cursor-pointer gap-3 rounded-lg px-2 py-2 text-sm hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                                    <input
                                        type="radio"
                                        name="bird-finder"
                                        class="mt-1 h-4 w-4 shrink-0 accent-brand-600"
                                        value={option.choice}
                                        checked={optionChosen}
                                        onchange={() => (birdFinder = option.choice)}
                                    />
                                    <span class="min-w-0 flex-1 space-y-1.5 wrap-break-word">
                                        <span class="flex flex-wrap items-center gap-2">
                                            <span class="font-semibold text-slate-900 dark:text-white">
                                                {option.choice === 'rfdetr_nano'
                                                    ? $_('settings.detection.bird_finder_wide', { default: 'Wide frame (RF-DETR Nano)' })
                                                    : $_('settings.detection.bird_finder_standard', { default: 'Standard (YOLOX-Tiny)' })}
                                            </span>
                                            <span class="text-xs font-semibold text-slate-600 dark:text-slate-300">
                                                {option.choice === 'rfdetr_nano'
                                                    ? $_('settings.detection.bird_finder_optional_badge', { default: 'Optional' })
                                                    : $_('settings.detection.bird_finder_default_badge', { default: 'Default' })}
                                            </span>
                                        </span>
                                        <span class="block leading-relaxed text-slate-600 dark:text-slate-300">
                                            {option.choice === 'rfdetr_nano'
                                                ? $_('settings.detection.bird_finder_wide_desc', { default: 'Reads the whole frame and four overlapping tiles, so it finds far more small and distant birds. A 103 MB download, and each frame takes longer.' })
                                                : $_('settings.detection.bird_finder_standard_desc', { default: 'Small and quick. Misses many birds that are small in a wide frame.' })}
                                        </span>
                                        <span class="block text-xs text-slate-600 dark:text-slate-400" data-finder-option-meta>
                                            {t('settings.detection.model_manager_card_download', '{size} MB download', { size: option.model.file_size_mb })}{#if option.model.estimated_ram_mb != null}{' · '}{t('settings.detection.bird_finder_ram', '{ram} RAM', { ram: ramShortLabel(option.model.estimated_ram_mb) })}{/if}{#if !optionInstalled}{' · '}{t('settings.detection.bird_finder_not_downloaded', 'not downloaded yet')}{/if}
                                        </span>
                                    </span>
                                </label>
                            {/each}
                        </div>
                        {#if savedBirdFinder && birdFinder !== savedBirdFinder}
                            <p class="text-sm text-slate-700 dark:text-slate-200" role="status">
                                {$_('settings.detection.bird_finder_pending', { default: 'Save changes to switch the bird finder. The current finder keeps running until then.' })}
                            </p>
                        {:else if cropDetectorStatus?.reason === 'fallback_default_accurate'}
                            <p class="text-sm text-attention-800 dark:text-attention-300" role="status">
                                {$_('settings.detection.bird_finder_fallback', { default: 'The wide-frame finder is not downloaded yet, so the standard finder is still in use. Download it below to switch.' })}
                            </p>
                        {/if}
                        {#if chosenFinder}
                            {@const chosenInstalled = isCropDetectorInstalled(chosenFinder.model.id)}
                            {@const chosenShortName = chosenFinder.choice === 'rfdetr_nano' ? 'RF-DETR Nano' : 'YOLOX-Tiny'}
                            {@const chosenDevice = birdFinderDevice(getInstalledModel(chosenFinder.model.id), hostProviders, chosenFinder.model)}
                            <FinderDevicePanel
                                modelId={chosenFinder.model.id}
                                shortName={chosenShortName}
                                installed={chosenInstalled}
                                evidence={getInstalledModel(chosenFinder.model.id)?.provider_preference_order ?? []}
                                accelerators={chosenDevice.accelerators}
                                {hostProviders}
                                check={cropDetectorStatus?.device_check}
                                savedProvider={settingsStore.settings?.bird_crop_inference_provider ?? birdFinderProvider}
                                finderSaved={savedBirdFinder === null || savedBirdFinder === birdFinder}
                                bind:provider={birdFinderProvider}
                                checkRunning={deviceCheckRunning}
                                downloading={chosenFinderDownload?.status === 'downloading' || chosenFinderDownload?.status === 'pending'}
                                execution={cropDetectorStatus?.last_execution}
                                oncheck={oncheckfinderdevices ? () => checkFinderDevices(chosenFinder.model.id) : undefined}
                                ondownload={() => handleDownload(chosenFinder.model)}
                            />
                            {#if chosenFinderDownload?.status === 'downloading' || chosenFinderDownload?.status === 'pending'}
                                <div role="status">
                                    <div class="mb-1 flex justify-between text-xs font-semibold">
                                        <span class="text-brand-700 dark:text-brand-300">{$_('settings.detection.model_manager_downloading_detector', { default: 'Downloading detector…' })}</span>
                                        <span class="text-slate-600 dark:text-slate-400">{chosenFinderDownload.progress.toFixed(0)}%</span>
                                    </div>
                                    <div class="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                        <div class="h-full bg-brand-500 transition-all duration-300" style="width: {chosenFinderDownload.progress}%"></div>
                                    </div>
                                </div>
                            {:else if chosenFinderDownload?.status === 'error' && chosenFinderDownload.error}
                                <p class="text-sm font-semibold text-red-700 dark:text-red-300" role="alert">{chosenFinderDownload.error}</p>
                            {/if}
                        {/if}
                    </fieldset>
                </section>
            {/if}
        </div>

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

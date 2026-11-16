<script lang="ts">
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import { onMount, onDestroy } from 'svelte';
    import { fetchAvailableModels, fetchInstalledModels, downloadModel, fetchDownloadStatus, activateModel, deleteModel, validateModel, checkHealth, groupTieredModelLineup, categorizeModel, MODEL_CATEGORY_LABEL, type ModelCategory, type ModelMetadata, type InstalledModel, type DownloadProgress, type ClassifierStatus, type HealthStatus } from '../../api';
    import { identificationModelName, identificationStatus, modelFactsLine, recommendIdentificationModel } from '../../settings/identification-models';
    import { identificationReadiness, readinessLabel, setupEmphasis } from '../../settings/model-readiness';
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
    let { executionMode = 'subprocess', autoVideoEnabled = false, birdFinder = $bindable<BirdFinder>('yolox_tiny'), birdFinderProvider = $bindable<BirdFinderProvider>('auto'), classifierStatus, deviceCheckRunning = false, onruntimechange, onopenlocationsettings, oncheckfinderdevices, firstLoadSettled = $bindable(false) }: {
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
        /**
         * True once the first read of the models has settled, and it stays true. How tall the list
         * is depends on what is installed, so the tab shows what follows it only from then on.
         */
        firstLoadSettled?: boolean;
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
    // The catalogue row whose details are open, if any.
    let selectedModelId = $state<string | null>(null);

    // Guided install wizard: download (with live progress) → validate on hardware →
    // enable. Reused for an already-downloaded model by skipping the download stage.
    let wizardModel = $state<ModelMetadata | null>(null);
    let wizardStages = $state<DiagnosticStage[]>([]);
    let wizardBusy = $state(false);
    let wizardResult = $state<DiagnosticResult | null>(null);
    let wizardRunId = $state(0);
    let wizardDownload = $state(false);
    // The model in use (or the chosen one, when its files are missing) is shown on its own, with at
    // most one recommendation. Every other model waits behind one disclosure the owner opens.
    let catalogueOpen = $state(false);
    const currentModelId = $derived(
        classifierStatus?.effective_model_id
            ?? installedModels.find((model) => model.is_active)?.id
            ?? null
    );
    // The chosen model's state, in the one vocabulary the wizard, About and Garden records use.
    const chosenReadiness = $derived.by(() => {
        const download = currentModelId ? downloadStatuses[currentModelId]?.status : undefined;
        const settingUp = wizardBusy && wizardModel?.id === currentModelId;
        return identificationReadiness(identificationStatus(classifierStatus), {
            downloading: download === 'downloading' || download === 'pending' || (settingUp && wizardDownload),
            validating: settingUp && !wizardDownload
        });
    });
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


    function t(key: string, fallback?: string | { default?: string; values?: Record<string, string | number> }, values?: Record<string, string | number>): string {
        if (typeof fallback === 'object') return get(_)(key, fallback);
        return get(_)(key, values ? { values, default: fallback } : { default: fallback });
    }

    function categoryLabel(category: ModelCategory): string {
        return t(MODEL_CATEGORY_LABEL[category].key, MODEL_CATEGORY_LABEL[category].fallback);
    }

    // Why the recommended model fits, in a line; the catalogue's own note for anything else.
    const RECOMMENDATION_REASONS: Record<string, string> = {
        small_birds: 'Knows the birds of your region and stays quick on an ordinary CPU.',
        rope_vit_b14_inat21: 'Names birds and other wildlife with good accuracy at a moderate speed.',
        mobilenet_v2_birds: 'Small enough for this device and needs no graphics hardware.',
    };
    function recommendationReason(model: ModelMetadata): string {
        const id = model.id.split('/')[0];
        const fallback = RECOMMENDATION_REASONS[id];
        return fallback ? t(`settings.models.recommend_reason.${id}`, fallback) : model.recommended_for;
    }

    function formatMetadataLabel(value: string): string {
        return value
            .split(/[_-]+/g)
            .filter(Boolean)
            .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase())
            .join(' ');
    }

    // Tier, maturity and execution provider are facts about the model, so every chip is neutral and the
    // word carries the meaning. None of them needs a person, and none is a second accent.
    const FACT_CHIP = 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';


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

        } catch (e) {
            console.error(e);
            error = t('settings.detection.model_manager_load_error', 'Failed to load models');
        } finally {
            loading = false;
            firstLoadSettled = true;
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

    function ramText(ramMb: number): string {
        return ramShortLabel(ramMb).replace(/^~/, '');
    }

    function ramShortLabel(ramMb: number): string {
        if (ramMb >= 1024) {
            const gb = ramMb / 1024;
            return `~${Number.isInteger(gb) ? gb.toFixed(0) : gb.toFixed(1)} GB`;
        }
        return `~${ramMb} MB`;
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

{#snippet modelHeading(model: ModelMetadata, chip: { label: string; className: string } | null, headingId: string | null)}
    {@const names = identificationModelName(model, t)}
    <span class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        {#if headingId}
            <span id={headingId} class="min-w-0 wrap-break-word text-base font-semibold leading-snug text-slate-900 dark:text-white">{names.name}</span>
        {:else}
            <span class="min-w-0 wrap-break-word text-sm font-semibold leading-snug text-slate-900 dark:text-white">{names.name}</span>
        {/if}
        {#if chip}
            <span class="shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold {chip.className}">{chip.label}</span>
        {/if}
    </span>
    {#if names.technical}
        <span class="block text-xs text-slate-600 dark:text-slate-400" data-model-technical-name>{names.technical}</span>
    {/if}
{/snippet}

{#snippet modelActions(model: ModelMetadata, subject: 'chosen' | 'other' = 'other')}
    <!-- While the chosen model needs a download or a recovery, that is the page's one primary action. -->
    {@const setupClass = setupEmphasis(chosenReadiness, subject) === 'primary' ? 'btn btn-primary min-h-11 px-4' : 'btn btn-secondary min-h-11 px-4'}
    {@const installed = Boolean(getInstalledModel(model.id))}
    {@const ready = isReady(model.id)}
    {@const active = isActive(model.id)}
    {@const validated = isValidated(model.id)}
    {@const download = downloadStatuses[model.id]}
    {@const inProgress = download?.status === 'downloading' || download?.status === 'pending'}
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
                <div class="h-full bg-brand-500 transition-all duration-300 motion-reduce:transition-none" style="width: {download.progress}%"></div>
            </div>
        </div>
    {:else}
        {#if download?.status === 'error' && download.error}
            <p class="text-sm font-semibold text-red-700 dark:text-red-300" role="alert">{download.error}</p>
        {/if}
        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:flex-wrap sm:justify-end">
            {#if installed}
                {#if !active && !getInstalledModel(model.id)?.bundled}
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
                {#if !getInstalledModel(model.id)?.bundled}
                    <button type="button" onclick={() => handleDownload(model)} class="btn btn-secondary min-h-11 px-4">
                        {ready
                            ? $_('settings.detection.model_manager_redownload', { default: 'Re-download' })
                            : $_('settings.detection.model_manager_repair_download', { default: 'Repair download' })}
                    </button>
                {/if}
                {#if ready && !active && validated}
                    <button
                        type="button"
                        onclick={() => handleActivate(model.id)}
                        disabled={activating !== null}
                        class={setupClass}
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
                        class={setupClass}
                    >
                        {$_('settings.detection.model_manager_validate_to_enable', { default: 'Validate to enable' })}
                    </button>
                {/if}
            {:else if !active}
                <button type="button" onclick={() => handleInstall(model)} disabled={wizardBusy} class={setupClass} data-model-setup={setupEmphasis(chosenReadiness, subject)}>
                    {setupEmphasis(chosenReadiness, subject) === 'secondary'
                        ? $_('settings.models.download_switch', { default: 'Download and switch to this model' })
                        : $_('settings.detection.model_manager_download_setup', { default: 'Download and set up' })}
                </button>
            {/if}
        </div>
    {/if}
{/snippet}

{#snippet modelDetail(model: ModelMetadata)}
    {@const installedEntry = getInstalledModel(model.id)}
    {@const installed = Boolean(installedEntry)}
    {@const ready = isReady(model.id)}
    {@const active = isActive(model.id)}
    {@const validated = isValidated(model.id)}
    {@const category = categorizeModel(model)}
    {@const runtimeProviderOrder = active ? getRuntimeProviderOrder(classifierStatus, getProviderSupport(model)) : []}
    {@const dynamicProviderChips = getDynamicProviderChips(model, active)}
    <div class="space-y-3">
        {#if model.description}
            <p class="max-w-prose text-sm leading-relaxed text-slate-600 dark:text-slate-300">{model.description}</p>
        {/if}
        <p class="text-sm text-slate-700 dark:text-slate-200" data-model-facts>
            {modelFactsLine(model, { installed, bundled: installedEntry?.bundled === true, memory: model.estimated_ram_mb == null }, t)}
        </p>
        {#if model.estimated_ram_mb != null}
            {@const prediction = predictedCopies()}
            <p class="text-sm text-slate-600 dark:text-slate-300" data-model-memory>
                {#if executionMode === 'in_process'}
                    {$_('settings.models.memory_in_process', { values: { per: ramText(model.estimated_ram_mb) }, default: 'Uses {per} of memory: one copy, shared inside the app.' })}
                {:else}
                    {$_('settings.models.memory_workers', {
                        values: { total: ramText(model.estimated_ram_mb * prediction.copies), per: ramText(model.estimated_ram_mb), copies: prediction.copies },
                        default: 'Uses {total} of memory in all: {per} for each of the {copies} worker copies.'
                    })}
                {/if}
            </p>
        {/if}
        {#if model.recommended_threshold != null}
            <p class="text-sm text-slate-600 dark:text-slate-300">
                {$_('settings.detection.model_manager_threshold_hint', { default: 'Recommended naming threshold for this model:' })}
                <strong class="font-semibold text-slate-900 dark:text-white">{Math.round(model.recommended_threshold * 100)}%</strong>
            </p>
        {/if}
        {#if usesSavedFeederLocation(model)}
            <div class="text-sm text-slate-600 dark:text-slate-300">
                <p class="font-semibold text-slate-900 dark:text-white">
                    {$_('settings.detection.model_manager_location_title', { default: 'Uses your feeder location' })}
                </p>
                <p class="mt-1 max-w-prose leading-relaxed">
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
            <p class="text-sm font-semibold text-attention-800 dark:text-attention-200" role="alert">
                {$_('settings.detection.model_manager_repair_needed', { default: 'This model install is incomplete. Re-download it to restore the missing species names or model configuration before activation.' })}
            </p>
        {:else if installed && !active && !validated}
            <p class="text-sm text-slate-700 dark:text-slate-200">
                {$_('settings.detection.model_manager_validation_needed', { default: 'Downloaded but not yet validated on your hardware. Validate it to confirm it runs here before you select it.' })}
            </p>
        {/if}

        <details class="group border-t border-line-soft">
            <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 py-2 text-sm font-medium text-slate-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:text-slate-200">
                <span>{$_('settings.detection.model_manager_technical_details', { default: 'Technical details' })}</span>
                <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 9 6 6 6-6" />
                </svg>
            </summary>
            <div class="space-y-4 pb-2 pt-2">
                <dl class="grid grid-cols-1 gap-3 text-sm wrap-break-word sm:grid-cols-2">
                    <div>
                        <dt class="text-slate-600 dark:text-slate-400">{$_('settings.models.technical_name', { default: 'Catalogue name' })}</dt>
                        <dd class="font-medium text-slate-800 dark:text-slate-100">{model.name}</dd>
                    </div>
                    <div>
                        <dt class="text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_best_fit', { default: 'Best fit' })}</dt>
                        <dd class="font-medium text-slate-800 dark:text-slate-100">{categoryLabel(category)} · {model.inference_speed}</dd>
                    </div>
                    <div>
                        <dt class="text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_architecture', { default: 'Architecture' })}</dt>
                        <dd class="font-medium text-slate-800 dark:text-slate-100">{model.architecture}</dd>
                    </div>
                    <div>
                        <dt class="text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_runtime', { default: 'Runtime' })}</dt>
                        <dd class="font-medium text-slate-800 dark:text-slate-100">{model.runtime} · {health?.ml ? (health.ml.runtimes[model.runtime === 'tflite' ? 'tflite' : 'onnx']?.installed ? $_('settings.models.runtime_installed', { default: 'installed' }) : $_('settings.models.runtime_missing', { default: 'not installed' })) : '—'}</dd>
                    </div>
                    <div>
                        <dt class="text-slate-600 dark:text-slate-400">{$_('settings.detection.model_manager_accuracy', { default: 'Accuracy' })}</dt>
                        <dd class="font-medium text-slate-800 dark:text-slate-100">{model.accuracy_tier}</dd>
                    </div>
                    <div>
                        <dt class="text-slate-600 dark:text-slate-400">{$_('settings.models.maturity', { default: 'Maturity' })}</dt>
                        <dd class="font-medium text-slate-800 dark:text-slate-100">{model.status === 'experimental' ? $_('settings.models.maturity_experimental', { default: 'Experimental' }) : $_('settings.models.maturity_stable', { default: 'Stable' })}</dd>
                    </div>
                </dl>
                {#if model.notes}
                    <p class="text-sm leading-relaxed text-slate-600 dark:text-slate-400">{model.notes}</p>
                {/if}
                <p class="text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                    {$_('settings.detection.model_manager_crop_policy_automatic_desc', { default: 'YA-WAMF uses the crop policy tested for this model. There is nothing to tune when you switch models.' })}
                </p>
                <div>
                    <p class="text-sm font-medium text-slate-700 dark:text-slate-200">
                        {active
                            ? $_('settings.detection.model_manager_runtime_order', { default: 'Automatic order' })
                            : $_('settings.detection.model_manager_provider_pills', { default: 'Supported providers' })}
                    </p>
                    <div class="mt-2 flex flex-wrap gap-2">
                        {#if dynamicProviderChips.length > 0}
                            {#each dynamicProviderChips as chip (chip.label)}
                                <span class="max-w-full rounded-full border px-2.5 py-1 text-xs font-semibold wrap-break-word {chip.className}" title={chip.title}>{chip.label}</span>
                            {/each}
                        {:else}
                            {#each getProviderSupport(model) as provider (provider)}
                                <span class="max-w-full rounded-full border px-2.5 py-1 text-xs font-semibold wrap-break-word {FACT_CHIP}">{providerLabel(provider)}</span>
                            {/each}
                        {/if}
                    </div>
                    {#if runtimeProviderOrder.length > 1}
                        <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{runtimeProviderOrder.map(providerLabel).join(' → ')}</p>
                    {/if}
                </div>
            </div>
        </details>
    </div>
{/snippet}

<!-- At the narrowest widths with enlarged text a long word may break, rather than push the page sideways. -->
<div class="space-y-6 wrap-anywhere">
    {#if loading && !firstLoadSettled}
        <!-- The first read only: a refresh keeps the list in place while Refresh spins. -->
        <div class="min-h-80 space-y-4" role="status" data-model-manager-loading>
            <span class="sr-only">{$_('common.loading', { default: 'Loading…' })}</span>
            <div class="h-5 w-48 rounded-sm bg-slate-200/70 motion-safe:animate-pulse dark:bg-slate-700/60" aria-hidden="true"></div>
            <div class="h-32 rounded-xl bg-slate-200/50 motion-safe:animate-pulse dark:bg-slate-700/40" aria-hidden="true"></div>
            <div class="h-11 w-44 rounded-xl bg-slate-200/50 motion-safe:animate-pulse dark:bg-slate-700/40" aria-hidden="true"></div>
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
        {@const modelGroups = groupTieredModelLineup(classifierModels, true, currentModelId)}
        {@const currentModel = currentModelId ? classifierModels.find((entry) => entry.id === currentModelId) ?? getInstalledModel(currentModelId)?.metadata ?? null : null}
        {@const recommended = recommendIdentificationModel(classifierModels, { currentId: currentModel?.id ?? currentModelId, currentInUse: currentModel ? isActive(currentModel.id) : false, imageFlavor: classifierStatus?.image_flavor })}
        {@const birdFinderOptions = (['yolox_tiny', 'rfdetr_nano'] as const)
            .map((choice) => ({ choice, model: cropDetectorModels.find((model) => model.id === BIRD_FINDER_MODEL_IDS[choice]) }))
            .filter((option): option is { choice: BirdFinder; model: ModelMetadata } => Boolean(option.model))}
        {@const chosenFinder = birdFinderOptions.find((option) => option.choice === birdFinder)}
        {@const chosenFinderDownload = chosenFinder ? downloadStatuses[chosenFinder.model.id] : undefined}

        <div class="space-y-6">
            <section aria-labelledby="classifier-model-lineup-label" class="space-y-4" data-identification-model>
                <div class="flex flex-wrap items-start justify-between gap-3">
                    <div class="min-w-0 flex-1 basis-64">
                        <h3 id="classifier-model-lineup-label" class="text-base font-semibold text-slate-900 dark:text-white">
                            {$_('settings.detection.identification_title', { default: 'Identification model' })}
                        </h3>
                        <p class="mt-1 max-w-prose text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                            {$_('settings.models.identification_desc', { default: 'Names the species in each bird picture. Larger models know more species and need more memory.' })}
                        </p>
                    </div>
                    <button
                        type="button"
                        onclick={refreshModels}
                        class="btn btn-secondary inline-flex min-h-11 items-center gap-1.5 px-3"
                    >
                        <svg class="h-4 w-4 {loading ? 'animate-spin motion-reduce:animate-none' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 0 0 4.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 0 1-15.357-2m15.357 2H15" />
                        </svg>
                        {$_('settings.detection.model_manager_refresh', { default: 'Refresh' })}
                    </button>
                </div>

                {#if currentModel}
                    {@const currentActive = isActive(currentModel.id)}
                    <div class="rounded-xl border border-line-soft p-4 sm:p-5" data-current-model data-model-readiness={chosenReadiness}>
                        <p class="mb-2 text-xs font-medium text-slate-600 dark:text-slate-400">
                            {currentActive
                                ? $_('settings.models.current_label', { default: 'In use now' })
                                : $_('settings.models.chosen_state', { values: { state: readinessLabel(chosenReadiness, $_) }, default: 'Chosen · {state}' })}
                        </p>
                        {@render modelHeading(currentModel, currentActive ? { label: $_('settings.detection.model_manager_in_use', { default: 'In use' }), className: modelCardStateClass('active') } : null, 'current-model-name')}
                        <div class="mt-3 space-y-4">
                            {@render modelDetail(currentModel)}
                            {@render modelActions(currentModel, 'chosen')}
                        </div>
                    </div>
                {/if}

                {#if recommended}
                    {@const recommendedInstalled = Boolean(getInstalledModel(recommended.id))}
                    <div class="rounded-xl border border-line-soft p-4 sm:p-5" data-model-recommendation={recommended.id}>
                        <p class="mb-2 text-xs font-medium text-slate-600 dark:text-slate-400">
                            {$_('settings.models.recommended_label', { default: 'Recommended next' })}
                        </p>
                        {@render modelHeading(recommended, null, null)}
                        <p class="mt-2 max-w-prose text-sm leading-relaxed text-slate-700 dark:text-slate-200">{recommendationReason(recommended)}</p>
                        <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">{modelFactsLine(recommended, { installed: recommendedInstalled, bundled: getInstalledModel(recommended.id)?.bundled === true }, t)}</p>
                        <div class="mt-3">
                            {@render modelActions(recommended)}
                        </div>
                    </div>
                {/if}

                <div>
                    <button
                        type="button"
                        class="focus-ring inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-md text-left text-sm font-medium text-brand-700 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200"
                        aria-expanded={catalogueOpen}
                        aria-controls="classifier-model-catalogue"
                        onclick={() => (catalogueOpen = !catalogueOpen)}
                        data-model-catalogue-toggle
                    >
                        <span class="min-w-0 wrap-break-word">
                            {catalogueOpen
                                ? $_('settings.models.catalogue_hide', { default: 'Hide the other models' })
                                : $_('settings.models.catalogue_show', { values: { count: classifierModels.length }, default: 'Choose another model ({count} in the catalogue)' })}
                        </span>
                        <svg class="h-4 w-4 shrink-0 transition-transform duration-200 motion-reduce:transition-none {catalogueOpen ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                    </button>
                    {#if catalogueOpen}
                        <div id="classifier-model-catalogue" class="mt-3 space-y-5" role="group" aria-labelledby="classifier-model-lineup-label">
                            {#each modelGroups as group (group.category)}
                                <div>
                                    <h4 class="mb-1 text-sm font-medium text-slate-700 dark:text-slate-200">{categoryLabel(group.category)}</h4>
                                    <ul class="divide-y divide-line-soft border-y border-line-soft">
                                        {#each group.models as modelOption (modelOption.id)}
                                            {@const cardState = modelCardState(modelOption.id)}
                                            {@const expanded = selectedModelId === modelOption.id}
                                            <li>
                                                <button
                                                    type="button"
                                                    aria-expanded={expanded}
                                                    aria-controls="model-option-{modelOption.id.replace(/[^a-z0-9_-]/gi, '-')}"
                                                    onclick={() => (selectedModelId = expanded ? null : modelOption.id)}
                                                    class="model-card flex min-h-11 w-full cursor-pointer flex-wrap items-center justify-between gap-x-4 gap-y-1 px-2 py-3 text-left transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus {expanded ? 'choice-active' : 'hover:bg-surface-raised'}"
                                                >
                                                    <span class="min-w-0 flex-1 basis-48">
                                                        {@render modelHeading(modelOption, cardState !== 'available' ? { label: modelCardStateLabel(cardState), className: modelCardStateClass(cardState) } : null, null)}
                                                    </span>
                                                    <span class="text-xs text-slate-600 dark:text-slate-300">
                                                        {modelFactsLine(modelOption, { installed: cardState !== 'available', bundled: getInstalledModel(modelOption.id)?.bundled === true }, t)}
                                                    </span>
                                                </button>
                                                {#if expanded}
                                                    <div id="model-option-{modelOption.id.replace(/[^a-z0-9_-]/gi, '-')}" class="space-y-4 px-2 pb-4 pt-1">
                                                        {@render modelDetail(modelOption)}
                                                        {@render modelActions(modelOption)}
                                                    </div>
                                                {/if}
                                            </li>
                                        {/each}
                                    </ul>
                                </div>
                            {/each}
                        </div>
                    {/if}
                </div>
            </section>

            {#if deleteNotice}
                <p class="text-sm text-slate-700 dark:text-slate-200" role="status">{deleteNotice}</p>
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
                                            {t('settings.detection.model_manager_card_download', '{size} MB download', { size: Math.round(option.model.file_size_mb) })}{#if option.model.estimated_ram_mb != null}{' · '}{t('settings.detection.bird_finder_ram', '{ram} RAM', { ram: ramShortLabel(option.model.estimated_ram_mb) })}{/if}{#if !optionInstalled}{' · '}{t('settings.detection.bird_finder_not_downloaded', 'not downloaded yet')}{/if}
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
                                planned={cropDetectorStatus ? { model_id: cropDetectorStatus.model_id, provider: cropDetectorStatus.planned_provider } : null}
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

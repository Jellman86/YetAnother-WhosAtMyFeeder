<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import {
        activateModel,
        downloadModel,
        fetchAvailableModels,
        fetchClassifierStatus,
        fetchDownloadStatus,
        fetchInstalledModels,
        getVisibleTieredModelLineup,
        selectSetupModelId,
        summarizeModelMetadata,
        type ClassifierStatus,
        type InstalledModel,
        type ModelMetadata
    } from '../../api/classifier';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import {
        startModelEvalRun,
        listModelEvalRuns,
        getModelEvalRun,
        type ModelEvalModelSummary
    } from '../../api/model_eval';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import {
        buildInferenceProviderChoices,
        getProviderPreferenceOrder,
        type InferenceProvider,
    } from '../../settings/inference-providers';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';

    let status = $state<ClassifierStatus | null>(null);
    let loadState = $state<WizardLoadStatus>('loading');
    let saving = $state(false);
    let downloading = $state(false);
    let downloadPct = $state(0);
    let validating = $state(false);
    let progress = $state<{ done: number; total: number; label: string; phase: string } | null>(null);
    let results = $state<ModelEvalModelSummary[] | null>(null);
    let availableModels = $state<ModelMetadata[]>([]);
    let installedModels = $state<InstalledModel[]>([]);
    let selectedModelId = $state('');
    let selectedProvider = $state<'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu' | 'intel_npu' | string>('auto');
    let providerTouched = $state(false);
    let errorMsg = $state('');
    let validationMsg = $state('');
    let runId = '';
    let poller: ReturnType<typeof setInterval> | null = null;
    let pollInFlight = false;
    let destroyed = false;
    const VALIDATION_TIMEOUT_MS = 30 * 60 * 1000;
    let validationDeadline = 0;

    let accelerators = $derived([
        { id: 'intel_npu', label: 'Intel NPU', available: status?.intel_npu_available },
        { id: 'intel_gpu', label: 'Intel iGPU', available: status?.intel_gpu_available },
        { id: 'cuda', label: 'NVIDIA CUDA', available: status?.cuda_available },
        { id: 'cpu', label: 'CPU', available: status?.available_providers?.includes('cpu') ?? false }
    ].filter((accelerator) => accelerator.available));
    let verified = $derived(status?.host_device_eligibility?.verified_providers ?? []);
    let activeModel = $derived(setupWizardStore.detailFor('model'));
    let progressPct = $derived(progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0);
    let installedIds = $derived(new Set(installedModels.map((model) => model.id)));
    let selectedInstalledModel = $derived(installedModels.find((model) => model.id === selectedModelId) ?? null);
    let selectedModel = $derived(availableModels.find((model) => model.id === selectedModelId) ?? installedModels.find((model) => model.id === selectedModelId)?.metadata ?? null);
    let selectedModelSummary = $derived(summarizeModelMetadata(selectedModel));
    let selectedValidation = $derived(results?.find((result) => result.model_id === selectedModelId) ?? null);
    let selectedValidatedProviders = $derived(
        selectedValidation
            ? selectedValidation.validated_providers
            : selectedModelId === status?.active_model_id
                ? ((status?.active_model_validated_providers?.length ?? 0) > 0
                    ? status?.active_model_validated_providers
                    : undefined)
                : (selectedInstalledModel?.validated_inference_providers ?? [])
    );
    let selectedProviderPreferenceOrder = $derived(
        selectedModelId === status?.active_model_id
            ? status?.validated_provider_preference_order
            : selectedInstalledModel?.provider_preference_order
    );
    let needsDownload = $derived(!!selectedModelId && !installedIds.has(selectedModelId));
    let selectedModelReady = $derived(
        !!selectedModelId
        && !needsDownload
        && (selectedModelId === status?.active_model_id || selectedInstalledModel?.validated === true)
    );

    function classifierModels(models: InstalledModel[]): InstalledModel[] {
        return models.filter((model) => (model.metadata?.artifact_kind || 'classifier') === 'classifier');
    }

    function providerLabel(provider: InferenceProvider): string {
        const labels: Record<InferenceProvider, string> = {
            auto: $_('settings.detection.provider_auto', { default: 'Auto (recommended)' }),
            cpu: $_('settings.detection.provider_cpu', { default: 'CPU (ONNX Runtime)' }),
            cuda: $_('settings.detection.provider_cuda', { default: 'NVIDIA CUDA' }),
            intel_gpu: $_('settings.detection.provider_intel_gpu', { default: 'Intel GPU (OpenVINO)' }),
            intel_cpu: $_('settings.detection.provider_intel_cpu', { default: 'Intel CPU (OpenVINO)' }),
            intel_npu: $_('settings.detection.provider_intel_npu', { default: 'Intel NPU (OpenVINO)' }),
        };
        return labels[provider];
    }

    let providerChoices = $derived(buildInferenceProviderChoices(
        status,
        selectedProvider,
        selectedModel?.candidate_inference_providers ?? selectedModel?.supported_inference_providers,
        selectedValidatedProviders,
        selectedProviderPreferenceOrder,
    ));
    let providerPreferenceLabel = $derived(
        selectedModelId === status?.active_model_id
            ? getProviderPreferenceOrder(status).map(providerLabel).join(' → ')
            : ''
    );
    let configuredProviderUnavailable = $derived(
        selectedProvider !== 'auto'
        && providerChoices.some((choice) => choice.value === selectedProvider && choice.unavailable)
    );

    async function load(): Promise<void> {
        loadState = 'loading';
        errorMsg = '';
        try {
            const [classifierStatus, available, installed, settings] = await Promise.all([
                fetchClassifierStatus(),
                fetchAvailableModels(),
                fetchInstalledModels(),
                fetchSettings()
            ]);
            status = classifierStatus;
            availableModels = getVisibleTieredModelLineup(
                available,
                true,
                classifierStatus.effective_model_id ?? classifierStatus.active_model_id
            );
            installedModels = classifierModels(installed);
            selectedModelId = selectSetupModelId(classifierStatus, availableModels, installedModels);
            selectedProvider = settings.inference_provider || 'auto';
        } catch {
            status = null;
            loadState = 'error';
            return;
        }
        loadState = 'ready';
    }

    onMount(() => {
        void load();
    });

    onDestroy(() => {
        destroyed = true;
        if (poller) clearInterval(poller);
    });

    function stopPolling() {
        if (poller) clearInterval(poller);
        poller = null;
        validationDeadline = 0;
    }

    function failValidationTimeout(): void {
        stopPolling();
        validating = false;
        progress = null;
        errorMsg = $_('setup.model.validation_timeout', {
            default: 'Hardware validation exceeded 30 minutes. It may still be finishing in Diagnostics; check its status before starting another run.'
        });
    }

    async function poll() {
        if (validationDeadline > 0 && Date.now() >= validationDeadline) {
            failValidationTimeout();
            return;
        }
        if (pollInFlight || document.hidden) return;
        pollInFlight = true;
        try {
            const list = await listModelEvalRuns();
            if (list.active && list.active.run_id === runId) {
                progress = { ...list.active.progress, phase: list.active.phase };
                return;
            }
            const summary = await getModelEvalRun(runId);
            if (!summary.finished_at && !summary.error) return;
            stopPolling();
            if (summary.error) {
                errorMsg = summary.error;
                validating = false;
                progress = null;
                return;
            }
            results = summary.models ?? [];
            const selectedResult = results.find((result) => result.model_id === selectedModelId);
            if (selectedResult && rowOk(selectedResult) && selectedResult.active_provider) {
                selectedProvider = selectedResult.active_provider;
                providerTouched = true;
            }
            validating = false;
            progress = null;
            validationMsg = validationSummary(results);
            installedModels = classifierModels(await fetchInstalledModels());
            await fetchClassifierStatus().then((s) => (status = s)).catch(() => {});
            await setupWizardStore.refresh();
        } catch {
            if (validationDeadline > 0 && Date.now() >= validationDeadline) {
                failValidationTimeout();
            }
            // Otherwise transient; keep polling until it resolves or the deadline.
        } finally {
            pollInFlight = false;
        }
    }

    async function runValidation() {
        errorMsg = '';
        results = null;
        validationMsg = '';
        validating = true;
        progress = { done: 0, total: 0, label: $_('setup.model.starting', { default: 'Starting…' }), phase: 'starting' };
        try {
            const { run_id } = await startModelEvalRun({
                sweep_devices: true,
                compat_only: true,
                model_ids: [selectedModelId],
            });
            runId = run_id;
            validationDeadline = Date.now() + VALIDATION_TIMEOUT_MS;
            poller = setInterval(poll, 2000);
            void poll();
        } catch (err) {
            validating = false;
            progress = null;
            errorMsg = err instanceof Error ? err.message : $_('setup.model.sweep_error', { default: 'Could not start validation.' });
        }
    }

    async function downloadSelectedModel(): Promise<void> {
        if (!selectedModelId || downloading) return;
        errorMsg = '';
        validationMsg = '';
        downloadPct = 0;
        downloading = true;

        try {
            const result = await downloadModel(selectedModelId);
            if (result.status !== 'pending') {
                throw new Error(result.message || $_('settings.detection.model_manager_start_failed', { default: 'Failed to start download' }));
            }

            const deadline = Date.now() + (15 * 60 * 1000);
            let consecutiveStatusFailures = 0;
            while (!destroyed && Date.now() < deadline) {
                await new Promise((resolve) => setTimeout(resolve, 1500));
                try {
                    const downloadStatus = await fetchDownloadStatus(selectedModelId);
                    if (!downloadStatus) continue;
                    consecutiveStatusFailures = 0;
                    downloadPct = Math.round(downloadStatus.progress ?? 0);
                    if (downloadStatus.status === 'error') {
                        throw new Error(downloadStatus.error || $_('settings.detection.model_manager_start_failed', { default: 'Download failed' }));
                    }
                    if (downloadStatus.status === 'completed') {
                        installedModels = classifierModels(await fetchInstalledModels());
                        status = await fetchClassifierStatus();
                        validationMsg = $_('settings.detection.model_manager_install_downloaded', { default: 'Downloaded and verified.' });
                        return;
                    }
                } catch (err) {
                    consecutiveStatusFailures += 1;
                    if (consecutiveStatusFailures >= 3) throw err;
                }
            }

            if (!destroyed) {
                throw new Error($_('setup.model.download_timeout', { default: 'The download is taking longer than expected. Check the connection and try again.' }));
            }
        } catch (err) {
            if (!destroyed) {
                errorMsg = err instanceof Error
                    ? err.message
                    : $_('settings.detection.model_manager_start_failed', { default: 'Failed to start download' });
            }
        } finally {
            downloading = false;
        }
    }

    function rowOk(m: ModelEvalModelSummary): boolean {
        return m.ready && !m.warnings.some((w) => w.severity === 'critical');
    }

    function modelHardwareNote(model: ModelMetadata | null): string {
        if (!model) return '';
        const providers = (model.supported_inference_providers || []).join(', ') || 'CPU';
        const ram = model.estimated_ram_mb ? ` Around ${model.estimated_ram_mb} MB RAM recommended.` : '';
        return `${model.recommended_for} Runtime: ${model.runtime || 'ONNX/TFLite'}; providers: ${providers}.${ram}`;
    }

    function validationSummary(models: ModelEvalModelSummary[]): string {
        if (!models.length) return $_('setup.model.no_results', { default: 'No installed models were evaluated.' });
        const ok = models.filter(rowOk).length;
        return ok === models.length
            ? $_('setup.model.validation_success', { default: 'Hardware validation completed successfully.' })
            : $_('setup.model.validation_partial', { values: { ok, total: models.length }, default: `Hardware validation completed: ${ok}/${models.length} models ready.` });
    }

    function resetValidationResult(): void {
        results = null;
        validationMsg = '';
        errorMsg = '';
        selectedProvider = 'auto';
        providerTouched = false;
    }

    // Continue commits the choices and advances, matching the other wizard steps.
    async function save() {
        if (loadState !== 'ready') return;
        errorMsg = '';
        saving = true;
        try {
            if (selectedModelId && installedIds.has(selectedModelId) && selectedModelId !== status?.active_model_id) {
                await activateModel(selectedModelId);
            }
            if (providerTouched) {
                await updateSettings({ inference_provider: selectedProvider });
            }
            await setupWizardStore.refresh();
            setupWizardStore.completeStep();
        } catch (err) {
            errorMsg = err instanceof Error ? err.message : $_('setup.model.save_error', { default: 'Could not save model choices.' });
        } finally {
            saving = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.model.title', { default: 'Classifier model & hardware' })}
    description={$_('setup.model.description', {
        default: 'YA-WAMF includes a lightweight CPU fallback. Choose a model, download it here if needed, then validate the exact image and hardware path before continuing.'
    })}
    showSkip
    canContinue={loadState === 'ready' && selectedModelReady}
    busy={saving}
    onContinue={save}
>
    <WizardLoadState state={loadState} onRetry={load}>
        <div>
            <label for="setup-model-id" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.model.choose_model', { default: 'Model' })}</label>
            <select id="setup-model-id" bind:value={selectedModelId} onchange={resetValidationResult} disabled={validating || downloading} class="select-base mt-1">
                {#each availableModels as model (model.id)}
                    <option value={model.id}>{model.name}{installedIds.has(model.id) ? '' : ` · ${$_('common.download_required', { default: 'Download required' })}`}</option>
                {/each}
            </select>
            {#if selectedModel}
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{modelHardwareNote(selectedModel)}</p>
                {#if selectedModelSummary}
                    <p class="mt-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">{selectedModelSummary.labels.join(' · ')}</p>
                {/if}
                {#if needsDownload}
                    <p class="mt-1 text-xs font-semibold text-amber-700 dark:text-amber-300">{$_('setup.model.download_required', { default: 'Download and verify this model here before validating it on this hardware.' })}</p>
                {:else if !selectedModelReady}
                    <p class="mt-1 text-xs font-semibold text-amber-700 dark:text-amber-300">{$_('setup.model.validation_required', { default: 'Validate this model on the current image and hardware before continuing.' })}</p>
                {/if}
            {/if}
        </div>

        <div>
            <label for="setup-provider" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('settings.detection.inference_provider', { default: 'Inference Provider' })}</label>
            <select id="setup-provider" bind:value={selectedProvider} onchange={() => (providerTouched = true)} disabled={validating || downloading} class="select-base mt-1">
                {#each providerChoices as choice (choice.value)}
                    <option value={choice.value} disabled={choice.unavailable}>
                        {providerLabel(choice.value)}{choice.unavailable ? ` · ${$_('common.unavailable', { default: 'Unavailable' })}` : ''}
                    </option>
                {/each}
            </select>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('setup.model.provider_hint', { default: 'Only providers available in this image, on this host, and for the selected model are shown.' })}</p>
            {#if providerPreferenceLabel}
                <p aria-live="polite" class="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {$_('settings.detection.provider_runtime_order', {
                        values: { order: providerPreferenceLabel },
                        default: `Current runtime order: ${providerPreferenceLabel}`
                    })}
                </p>
            {/if}
            {#if configuredProviderUnavailable}
                <p role="status" class="mt-1 border-l-2 border-amber-400 py-1 pl-3 text-xs font-semibold leading-relaxed text-amber-800 dark:border-amber-500 dark:text-amber-200">
                    {$_('settings.detection.provider_saved_unavailable', {
                        values: { provider: providerLabel(selectedProvider as InferenceProvider) },
                        default: `${providerLabel(selectedProvider as InferenceProvider)} is saved but unavailable. Choose an available provider or Auto.`
                    })}
                </p>
            {/if}
        </div>

        {#if accelerators.length || verified.length}
            <div>
                <p class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.model.detected', { default: 'Detected accelerators' })}</p>
                {#if accelerators.length}
                    <div class="mt-1.5 flex flex-wrap gap-2">
                        {#each accelerators as acc (acc.id)}
                            <span class="inline-flex items-center gap-1 rounded-full bg-accent-100 px-2.5 py-1 text-xs font-semibold text-accent-800 dark:bg-accent-900/30 dark:text-accent-200">
                                <span aria-hidden="true">✓</span> {acc.label}
                            </span>
                        {/each}
                    </div>
                {/if}
                {#if verified.length}
                    <p class="mt-2 text-xs text-success-700 dark:text-success-300">{$_('setup.model.verified', { values: { list: verified.join(', ') }, default: `Validated providers: ${verified.join(', ')}` })}</p>
                {/if}
            </div>
        {/if}

        {#if downloading}
            <div
                role="progressbar"
                aria-label={$_('settings.detection.model_manager_install_stage_download', { default: 'Download model' })}
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={downloadPct}
                class="space-y-2 rounded-lg bg-brand-50 p-3 dark:bg-brand-950/20"
            >
                <div class="flex items-center justify-between text-sm">
                    <span class="font-medium text-brand-800 dark:text-brand-200">{$_('settings.detection.model_manager_installing_pct', { values: { pct: downloadPct }, default: `Downloading… ${downloadPct}%` })}</span>
                    <span class="text-xs tabular-nums text-brand-600 dark:text-brand-400">{downloadPct}%</span>
                </div>
                <div class="h-2 w-full overflow-hidden rounded-full bg-brand-100 dark:bg-brand-900/40">
                    <div class="h-full rounded-full bg-brand-500 transition-all duration-500" style="width: {downloadPct}%"></div>
                </div>
            </div>
        {:else if needsDownload}
            <button type="button" class="btn btn-secondary px-5 py-2.5" onclick={downloadSelectedModel} disabled={!selectedModelId}>
                {$_('settings.detection.model_manager_install_stage_download', { default: 'Download model' })}
            </button>
        {:else if validating && progress}
            <div
                role="progressbar"
                aria-label={$_('setup.model.validate', { default: 'Validate on my hardware' })}
                aria-valuemin="0"
                aria-valuemax={progress.total > 0 ? progress.total : undefined}
                aria-valuenow={progress.total > 0 ? progress.done : undefined}
                aria-valuetext={progress.label}
                class="space-y-2 rounded-lg bg-brand-50 p-3 dark:bg-brand-950/20"
            >
                <div class="flex items-center justify-between text-sm">
                    <span class="font-medium text-brand-800 dark:text-brand-200">{progress.label}</span>
                    {#if progress.total > 0}<span class="text-xs text-brand-600 dark:text-brand-400">{progress.done}/{progress.total}</span>{/if}
                </div>
                <div class="h-2 w-full overflow-hidden rounded-full bg-brand-100 dark:bg-brand-900/40">
                    <div class="h-full rounded-full bg-brand-500 transition-all duration-500" style="width: {progress.total > 0 ? progressPct : 15}%"></div>
                </div>
                <p class="text-xs capitalize text-brand-600 dark:text-brand-400">{progress.phase.replace(/_/g, ' ')}</p>
            </div>
        {:else}
            <button type="button" class="btn btn-secondary px-5 py-2.5" onclick={runValidation} disabled={!selectedModelId}>
                {results ? $_('setup.model.revalidate', { default: 'Re-run validation' }) : $_('setup.model.validate', { default: 'Validate on my hardware' })}
            </button>
        {/if}

        {#if errorMsg}
            <div role="alert" class="rounded-md bg-amber-50 p-2 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-200">{errorMsg}</div>
        {/if}
        {#if validationMsg}
            <div role="status" class="rounded-md bg-success-50 p-2 text-sm text-success-800 dark:bg-success-900/20 dark:text-success-200">{validationMsg}</div>
        {/if}

        {#if results}
            {#if results.length === 0}
                <p class="text-sm text-slate-500 dark:text-slate-400">{$_('setup.model.no_results', { default: 'No installed models were evaluated.' })}</p>
            {:else}
                <ul class="divide-y divide-slate-200 overflow-hidden rounded-lg border border-slate-200 dark:divide-slate-700 dark:border-slate-700">
                    {#each results as m (m.model_id)}
                        <li class="flex items-center justify-between gap-3 p-2.5">
                            <div class="min-w-0">
                                <p class="truncate text-sm font-medium text-slate-800 dark:text-slate-100">{m.model_id}</p>
                                <p class="text-xs text-slate-500 dark:text-slate-400">
                                    {m.active_provider ? providerLabel(m.active_provider as InferenceProvider) : (m.device ?? 'CPU')}{#if m.mean_latency_ms} · {m.mean_latency_ms.toFixed(0)} ms{/if}
                                </p>
                            </div>
                            <span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold {rowOk(m) ? 'bg-success-100 text-success-800 dark:bg-success-900/30 dark:text-success-200' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200'}">
                                {rowOk(m) ? $_('setup.model.row_ok', { default: 'Runs' }) : $_('setup.model.row_warn', { default: 'Check' })}
                            </span>
                        </li>
                    {/each}
                </ul>
                <p class="text-xs text-slate-500 dark:text-slate-400">{$_('setup.model.results_hint', { default: 'Full per-device compile, latency, and accuracy detail is in Diagnostics → Model evaluation.' })}</p>
            {/if}
        {/if}
    </WizardLoadState>
</WizardStepLayout>

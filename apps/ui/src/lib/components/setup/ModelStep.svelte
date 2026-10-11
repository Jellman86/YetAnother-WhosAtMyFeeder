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
        type DownloadProgress,
        type InstalledModel,
        type ModelMetadata
    } from '../../api/classifier';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import {
        startModelEvalRun,
        listModelEvalRuns,
        getModelEvalRun,
        getModelEvalDeviceMatrix,
        type DeviceMatrix,
        type ModelEvalModelSummary
    } from '../../api/model_eval';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import {
        buildInferenceProviderChoices,
        getProviderPreferenceOrder,
        parseInferenceProvider,
        type InferenceProvider,
    } from '../../settings/inference-providers';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';
    import { usesSavedFeederLocation } from '../../pages/models/model_location_input';
    import { feederCoordinates, validationRecommendation } from './model-choices';

    let status = $state<ClassifierStatus | null>(null);
    let loadState = $state<WizardLoadStatus>('loading');
    let saving = $state(false);
    let downloading = $state(false);
    let downloadPct = $state(0);
    let validating = $state(false);
    let progress = $state<{ done: number; total: number; label: string; phase: string } | null>(null);
    let results = $state<ModelEvalModelSummary[] | null>(null);
    let matrix = $state<DeviceMatrix | null>(null);
    let validationFailed = $state(false);
    let availableModels = $state<ModelMetadata[]>([]);
    let installedModels = $state<InstalledModel[]>([]);
    let selectedModelId = $state('');
    let selectedProvider = $state<InferenceProvider>('auto');
    let providerTouched = $state(false);
    let errorMsg = $state('');
    let validationMsg = $state('');
    let providerMessage = $state('');
    let latitudeText = $state('');
    let longitudeText = $state('');
    let savedLatitude: number | null = null;
    let savedLongitude: number | null = null;
    let runId = '';
    let runModelId = '';
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
    let progressPct = $derived(progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0);
    let installedIds = $derived(new Set(installedModels.map((model) => model.id)));
    let selectedInstalledModel = $derived(installedModels.find((model) => model.id === selectedModelId) ?? null);
    let selectedModel = $derived(availableModels.find((model) => model.id === selectedModelId) ?? installedModels.find((model) => model.id === selectedModelId)?.metadata ?? null);
    let selectedModelSummary = $derived(summarizeModelMetadata(selectedModel));
    let selectedValidation = $derived(results?.find((result) => result.model_id === selectedModelId) ?? null);
    let recommendation = $derived(validationRecommendation(selectedModelId, selectedValidation ?? undefined, matrix));
    let usesLocation = $derived(selectedModel !== null && usesSavedFeederLocation(selectedModel));
    let coordinates = $derived(feederCoordinates(latitudeText, longitudeText));
    let locationValid = $derived(!usesLocation || coordinates.error === null);
    let selectedValidatedProviders = $derived(
        selectedValidation
            ? recommendation.providers
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
    let needsDownload = $derived(!!selectedModelId && (!installedIds.has(selectedModelId) || selectedInstalledModel?.ready === false));
    let selectedModelReady = $derived(
        !!selectedModelId
        && !needsDownload
        && !validationFailed
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
    let canSave = $derived(loadState === 'ready' && selectedModelReady && locationValid && !configuredProviderUnavailable && !validating && !downloading);

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
            if (destroyed) return;
            status = classifierStatus;
            availableModels = getVisibleTieredModelLineup(
                available,
                true,
                classifierStatus.effective_model_id ?? classifierStatus.active_model_id
            );
            installedModels = classifierModels(installed);
            selectedModelId = selectSetupModelId(classifierStatus, availableModels, installedModels);
            selectedProvider = parseInferenceProvider(settings.inference_provider) ?? 'auto';
            savedLatitude = settings.location_latitude ?? null;
            savedLongitude = settings.location_longitude ?? null;
            latitudeText = savedLatitude === null ? '' : String(savedLatitude);
            longitudeText = savedLongitude === null ? '' : String(savedLongitude);
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
        validationFailed = true;
        validating = false;
        progress = null;
        errorMsg = $_('setup.model.validation_timeout', {
            default: 'Hardware validation exceeded 30 minutes. It may still be finishing in Diagnostics; check its status before starting another run.'
        });
    }

    async function poll() {
        if (destroyed) return;
        if (validationDeadline > 0 && Date.now() >= validationDeadline) {
            failValidationTimeout();
            return;
        }
        if (pollInFlight || document.hidden) return;
        pollInFlight = true;
        let finished = false;
        try {
            const list = await listModelEvalRuns();
            if (destroyed) return;
            if (list.active && list.active.run_id === runId) {
                progress = { ...list.active.progress, phase: list.active.phase };
                return;
            }
            const summary = await getModelEvalRun(runId);
            if (destroyed || selectedModelId !== runModelId) return;
            if (!summary.finished_at && !summary.error) return;
            if (summary.error) {
                stopPolling();
                errorMsg = summary.error;
                validationFailed = true;
                validating = false;
                progress = null;
                return;
            }
            finished = true;
            const [installed, classifierStatus, deviceMatrix] = await Promise.all([
                fetchInstalledModels(), fetchClassifierStatus(), getModelEvalDeviceMatrix(runId)
            ]);
            if (destroyed || selectedModelId !== runModelId) return;
            stopPolling();
            installedModels = classifierModels(installed);
            status = classifierStatus;
            matrix = deviceMatrix;
            results = summary.models ?? [];
            const selectedResult = results.find((result) => result.model_id === selectedModelId);
            const checked = validationRecommendation(selectedModelId, selectedResult, matrix);
            validationFailed = !selectedResult || !rowOk(selectedResult) || checked.providers.length === 0;
            if (!validationFailed && checked.provider) {
                const explicitPassed = selectedProvider === 'auto' || checked.providers.includes(selectedProvider);
                if (providerTouched && !explicitPassed) {
                    providerMessage = $_('setup.model.provider_replaced', {
                        values: { previous: providerLabel(selectedProvider), provider: providerLabel(checked.provider) },
                        default: `${providerLabel(selectedProvider)} did not pass the check for this model, so ${providerLabel(checked.provider)} is selected instead.`
                    });
                }
                if (!providerTouched || !explicitPassed) selectedProvider = checked.provider;
                providerTouched = true;
            }
            errorMsg = validationFailed ? $_('setup.model.no_passing_provider', { default: 'This model did not pass hardware validation. Review the results and try again before continuing.' }) : '';
            validating = false;
            progress = null;
            validationMsg = validationSummary(results);
            await setupWizardStore.refresh();
        } catch {
            if (validationDeadline > 0 && Date.now() >= validationDeadline) {
                failValidationTimeout();
            } else if (!destroyed && finished) {
                errorMsg = $_('setup.model.readiness_retry', { default: 'The check finished, but model readiness could not be refreshed. Retrying; you can leave this step and return later.' });
            }
            // Otherwise transient; keep polling until it resolves or the deadline.
        } finally {
            pollInFlight = false;
        }
    }

    async function runValidation() {
        if (destroyed || validating || downloading || saving || needsDownload || !selectedModelId || !locationValid) return;
        errorMsg = '';
        results = null;
        matrix = null;
        validationFailed = false;
        validationMsg = '';
        providerMessage = '';
        validating = true;
        progress = { done: 0, total: 0, label: $_('setup.model.starting', { default: 'Starting…' }), phase: 'starting' };
        try {
            await saveLocation();
            if (destroyed) return;
            runModelId = selectedModelId;
            const { run_id } = await startModelEvalRun({
                sweep_devices: true,
                compat_only: true,
                model_ids: [runModelId],
            });
            if (destroyed) return;
            runId = run_id;
            validationDeadline = Date.now() + VALIDATION_TIMEOUT_MS;
            poller = setInterval(poll, 2000);
            void poll();
        } catch (err) {
            if (destroyed) return;
            validationFailed = true;
            validating = false;
            progress = null;
            errorMsg = err instanceof Error ? err.message : $_('setup.model.sweep_error', { default: 'Could not start validation.' });
        }
    }

    async function downloadSelectedModel(): Promise<void> {
        if (!selectedModelId || downloading || validating || saving) return;
        errorMsg = '';
        validationMsg = '';
        downloadPct = 0;
        downloading = true;

        try {
            const result = await downloadModel(selectedModelId);
            if (destroyed) return;
            if (result.status !== 'pending') {
                throw new Error(result.message || $_('settings.detection.model_manager_start_failed', { default: 'Failed to start download' }));
            }

            const deadline = Date.now() + (15 * 60 * 1000);
            let consecutiveStatusFailures = 0;
            while (!destroyed && Date.now() < deadline) {
                await new Promise((resolve) => setTimeout(resolve, 1500));
                if (destroyed) return;
                let downloadStatus: DownloadProgress | null;
                try {
                    downloadStatus = await fetchDownloadStatus(selectedModelId);
                    consecutiveStatusFailures = 0;
                } catch (err) {
                    consecutiveStatusFailures += 1;
                    if (consecutiveStatusFailures >= 3) throw err;
                    continue;
                }
                if (destroyed) return;
                if (!downloadStatus) continue;
                downloadPct = Math.round(downloadStatus.progress ?? 0);
                if (downloadStatus.status === 'error') {
                    throw new Error(downloadStatus.error || $_('settings.detection.model_manager_start_failed', { default: 'Download failed' }));
                }
                if (downloadStatus.status === 'completed') {
                    const [installed, classifierStatus] = await Promise.all([fetchInstalledModels(), fetchClassifierStatus()]);
                    if (destroyed) return;
                    installedModels = classifierModels(installed);
                    status = classifierStatus;
                    validationMsg = $_('settings.detection.model_manager_install_downloaded', { default: 'Downloaded and verified.' });
                    return;
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
        return validationRecommendation(m.model_id, m, matrix).providers.length > 0;
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

    function resetValidationResult(modelId: string): void {
        selectedModelId = modelId;
        results = null;
        matrix = null;
        validationFailed = false;
        validationMsg = '';
        providerMessage = '';
        errorMsg = '';
        const installed = installedModels.find((model) => model.id === modelId);
        const preferred = parseInferenceProvider(installed?.preferred_inference_provider);
        selectedProvider = preferred ?? 'auto';
        providerTouched = false;
    }

    async function saveLocation(): Promise<void> {
        if (!usesLocation) return;
        const location = feederCoordinates(latitudeText, longitudeText);
        if (location.error !== null) throw new Error($_('setup.model.location_incomplete', { default: 'Enter both latitude and longitude, or leave both empty.' }));
        if (location.latitude === savedLatitude && location.longitude === savedLongitude) return;
        await updateSettings({ location_latitude: location.latitude, location_longitude: location.longitude });
        savedLatitude = location.latitude;
        savedLongitude = location.longitude;
    }

    // Continue commits the choices and advances, matching the other wizard steps.
    async function save() {
        if (!canSave || saving || destroyed) return;
        errorMsg = '';
        saving = true;
        try {
            await saveLocation();
            if (destroyed) return;
            const changingModel = selectedModelId !== status?.active_model_id;
            if (changingModel) {
                await activateModel(selectedModelId);
            }
            if (destroyed) return;
            if (providerTouched || changingModel) {
                await updateSettings({ inference_provider: selectedProvider });
            }
            if (destroyed) return;
            await setupWizardStore.refresh();
            if (destroyed) return;
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
    canContinue={canSave}
    busy={saving}
    onContinue={save}
>
    <WizardLoadState state={loadState} onRetry={load}>
        <div>
            <label for="setup-model-id" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.model.choose_model', { default: 'Model' })}</label>
            <select id="setup-model-id" bind:value={selectedModelId} onchange={(event) => resetValidationResult(event.currentTarget.value)} disabled={validating || downloading || saving} class="select-base mt-1">
                {#each availableModels as model (model.id)}
                    <option value={model.id}>{model.name}{installedIds.has(model.id) ? '' : ` · ${$_('common.download_required', { default: 'Download required' })}`}</option>
                {/each}
            </select>
            {#if selectedModel}
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{modelHardwareNote(selectedModel)}</p>
                {#if selectedModelSummary}
                    <p class="mt-1 text-2xs font-semibold text-slate-500 dark:text-slate-400">{selectedModelSummary.labels.join(' · ')}</p>
                {/if}
                {#if selectedInstalledModel?.ready === false}
                    <p role="status" class="mt-1 text-xs font-semibold text-amber-700 dark:text-amber-300">{$_('setup.model.incomplete_install', { default: 'This model install is incomplete. Download and verify it again before continuing.' })}</p>
                {:else if needsDownload}
                    <p class="mt-1 text-xs font-semibold text-amber-700 dark:text-amber-300">{$_('setup.model.download_required', { default: 'Download and verify this model here before validating it on this hardware.' })}</p>
                {:else if !selectedModelReady}
                    <p class="mt-1 text-xs font-semibold text-amber-700 dark:text-amber-300">{$_('setup.model.validation_required', { default: 'Validate this model on the current image and hardware before continuing.' })}</p>
                {/if}
            {/if}
        </div>

        <div>
            <label for="setup-provider" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('settings.detection.inference_provider', { default: 'Inference Provider' })}</label>
            <select id="setup-provider" bind:value={selectedProvider} onchange={() => { providerTouched = true; providerMessage = ''; }} disabled={validating || downloading || saving} class="select-base mt-1">
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

        {#if usesLocation}
            <fieldset disabled={validating || downloading || saving} class="space-y-2 border-l-2 border-brand-100 pl-4 dark:border-brand-900/60">
                <legend class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.model.location_title', { default: 'Feeder location' })}</legend>
                <p class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">{$_('setup.model.location_hint', { default: 'Validating or continuing saves these coordinates first, using the same feeder location as Settings → Integrations → Location. This model does not use the date or a location accuracy radius.' })}</p>
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <label for="setup-model-latitude" class="text-sm text-slate-700 dark:text-slate-300">
                        {$_('manual_observation.location.latitude', { default: 'Latitude' })}
                        <input id="setup-model-latitude" type="number" min="-90" max="90" step="any" value={latitudeText} oninput={(event) => (latitudeText = event.currentTarget.value)} class="input-base mt-1" aria-invalid={coordinates.error !== null} aria-describedby="setup-model-location-status" />
                    </label>
                    <label for="setup-model-longitude" class="text-sm text-slate-700 dark:text-slate-300">
                        {$_('manual_observation.location.longitude', { default: 'Longitude' })}
                        <input id="setup-model-longitude" type="number" min="-180" max="180" step="any" value={longitudeText} oninput={(event) => (longitudeText = event.currentTarget.value)} class="input-base mt-1" aria-invalid={coordinates.error !== null} aria-describedby="setup-model-location-status" />
                    </label>
                </div>
                <p id="setup-model-location-status" role={coordinates.error ? 'alert' : 'status'} class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    {#if coordinates.error === 'incomplete'}
                        {$_('setup.model.location_incomplete', { default: 'Enter both latitude and longitude, or leave both empty.' })}
                    {:else if coordinates.error === 'range'}
                        {$_('manual_observation.location.invalid', { default: 'Latitude must be −90 to 90 and longitude −180 to 180.' })}
                    {:else if coordinates.latitude === null}
                        {$_('setup.model.location_empty', { default: 'No location will be used: this model identifies birds without it.' })}
                    {:else}
                        {$_('settings.detection.model_manager_location_title', { default: 'Uses your feeder location' })}
                    {/if}
                </p>
            </fieldset>
        {/if}

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
            <button type="button" class="btn btn-secondary px-5 py-2.5" onclick={downloadSelectedModel} disabled={!selectedModelId || saving}>
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
            <button type="button" class="btn btn-secondary px-5 py-2.5" onclick={runValidation} disabled={!selectedModelId || !locationValid || saving}>
                {results ? $_('setup.model.revalidate', { default: 'Re-run validation' }) : $_('setup.model.validate', { default: 'Validate on my hardware' })}
            </button>
        {/if}

        {#if validating}
            <p role="status" class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">{$_('setup.model.check_running', { default: 'Continue is available when the check finishes. Leaving this step does not stop the check. Return later to read the saved results.' })}</p>
        {/if}
        {#if providerMessage}
            <p role="status" class="text-xs font-semibold text-amber-700 dark:text-amber-300">{providerMessage}</p>
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
                        {@const outcome = validationRecommendation(m.model_id, m, matrix)}
                        <li class="flex items-center justify-between gap-3 p-2.5">
                            <div class="min-w-0">
                                <p class="truncate text-sm font-medium text-slate-800 dark:text-slate-100">{m.model_id}</p>
                                <p class="text-xs text-slate-500 dark:text-slate-400">
                                    {#if outcome.provider && outcome.medianMs !== null}
                                        {$_('setup.model.best_provider', { values: { provider: providerLabel(outcome.provider), ms: outcome.medianMs.toFixed(0) }, default: `Best validated provider: ${providerLabel(outcome.provider)}, ${outcome.medianMs.toFixed(0)} ms per image` })}
                                    {:else if outcome.provider}
                                        {$_('setup.model.best_provider_without_timing', { values: { provider: providerLabel(outcome.provider) }, default: `Best validated provider: ${providerLabel(outcome.provider)}` })}
                                    {/if}
                                </p>
                                {#if m.failed_providers?.length}
                                    <p class="text-xs text-amber-700 dark:text-amber-300">{$_('setup.model.failed_providers', { values: { providers: m.failed_providers.map((value) => providerLabel(parseInferenceProvider(value) ?? 'auto')).join(', ') }, default: `Failed: ${m.failed_providers.join(', ')}` })}</p>
                                {/if}
                            </div>
                            <span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold {rowOk(m) ? 'bg-success-100 text-success-800 dark:bg-success-900/30 dark:text-success-200' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200'}">
                                {rowOk(m) ? $_('setup.model.row_ok', { default: 'Runs' }) : $_('setup.model.row_warn', { default: 'Check' })}
                            </span>
                        </li>
                    {/each}
                </ul>
                <p class="text-xs text-slate-500 dark:text-slate-400">{$_('model_eval.compat_only_body', { default: 'This run checked that each provider loads, gives finite output and agrees with the CPU baseline. It did not measure accuracy, so no accuracy figures are shown. Run Evaluation to measure accuracy.' })}</p>
            {/if}
        {/if}
    </WizardLoadState>
</WizardStepLayout>

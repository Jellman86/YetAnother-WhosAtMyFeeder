<script lang="ts">
    import { onDestroy, tick } from 'svelte';
    import { useDisclosure } from '../../settings/disclosures.svelte';
    import { RUNTIME_DISCLOSURES } from '../../settings/runtime-problem';
    import { _ } from 'svelte-i18n';
    import { formatDateTime } from '../../utils/datetime';
    import ModelManager from '../../pages/models/ModelManager.svelte';
    import type { ClassifierStatus } from '../../api';
    import { startModelEvalRun, listModelEvalRuns, getModelEvalRun, getModelEvalDeviceMatrix, type DeviceMatrix } from '../../api/model_eval';
    import { stopCause } from '../../utils/model-eval-view';
    import { BIRD_MODEL_REGION_OVERRIDE_VALUES, type BirdModelRegionOverride } from '../../settings/bird-model-region-override';
    import type { BirdFinder, BirdFinderProvider } from '../../settings/bird-finder';
    import {
        buildInferenceProviderChoices,
        getProviderPreferenceOrder,
        type InferenceProvider,
    } from '../../settings/inference-providers';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import DetectionStatusBand from './DetectionStatusBand.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import NativeProfileRevalidation from './NativeProfileRevalidation.svelte';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import type { DiagnosticStage, DiagnosticStageState, DiagnosticResult } from '../../utils/diagnostic-runner';

    const GPU_DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/docs/setup/hardware-acceleration.md';

    let {
        liveWorkerCount = $bindable<number | null>(null),
        backgroundWorkerCount = $bindable<number | null>(null),
        autoVideoClassification = false,
        birdModelRegionOverride = $bindable<BirdModelRegionOverride>('auto'),
        birdFinder = $bindable<BirdFinder>('yolox_tiny'),
        birdFinderProvider = $bindable<BirdFinderProvider>('auto'),
        imageExecutionMode = $bindable<'in_process' | 'subprocess' | string>('subprocess'),
        inferenceProvider = $bindable<'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu' | 'intel_npu'>('auto'),
        strictNonFiniteOutput = $bindable(true),
        debugUiEnabled = false,
        classifierStatus = null,
        onrefreshclassifierstatus,
        onopenlocationsettings,
        onopenmodelevaluation
    }: {
        liveWorkerCount: number | null;
        backgroundWorkerCount: number | null;
        /** Shown in the status line; switched in Detection, with the other video checks. */
        autoVideoClassification?: boolean;
        birdModelRegionOverride: BirdModelRegionOverride;
        birdFinder: BirdFinder;
        birdFinderProvider?: BirdFinderProvider;
        imageExecutionMode: 'in_process' | 'subprocess' | string;
        inferenceProvider: 'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu' | 'intel_npu';
        strictNonFiniteOutput?: boolean;
        /** The troubleshooting switch is offered only in a build with the debug interface on. */
        debugUiEnabled?: boolean;
        classifierStatus: ClassifierStatus | null;
        /** Re-reads the live runtime only; resolves false when it could not be read. */
        onrefreshclassifierstatus?: () => Promise<boolean>;
        onopenlocationsettings?: () => void;
        onopenmodelevaluation?: () => void;
    } = $props();

    // Memory and isolation stay folded away until the owner has changed them,
    // so a customised value is never hidden behind a closed disclosure.
    const memoryCustomised = $derived(
        imageExecutionMode !== 'subprocess' || liveWorkerCount !== null || backgroundWorkerCount !== null
    );

    // The status band's anchors: the model cell jumps to the Models card, the
    // health cell to the runtime report.
    const MODELS_CARD_ID = 'detection-models-card';
    const RUNTIME_REPORT_ID = 'detection-runtime-report';
    const HARDWARE_CARD_ID = RUNTIME_DISCLOSURES[0];
    const RUNTIME_REPORT_SECTION_ID = RUNTIME_DISCLOSURES[1];


    const healthIssueCount = $derived(
        (classifierStatus?.fallback_reason ? 1 : 0) +
            (classifierStatus?.model_config_warnings?.length ?? 0) +
            (classifierStatus?.openvino_model_compile_ok === false ? 1 : 0) +
            (classifierStatus?.image_flavor_warning ? 1 : 0) +
            (classifierStatus?.cuda_probe_error ? 1 : 0) +
            (classifierStatus?.active_model_installed === false ? 1 : 0)
    );

    // Hardware is advanced and starts closed, unless the runtime has something to report; the
    // status line's health link opens it before scrolling to the report inside it.
    // Both open themselves for a runtime problem (the Settings page reports it on every status
    // read); the status line's health link opens both too, whatever was remembered.
    const hardwareCard = useDisclosure(() => ({ id: HARDWARE_CARD_ID }));
    const runtimeReport = useDisclosure(() => ({ id: RUNTIME_REPORT_SECTION_ID }));
    async function revealAnchor(anchorId: string): Promise<void> {
        if (anchorId === RUNTIME_REPORT_ID) {
            hardwareCard.open = true;
            runtimeReport.open = true;
        }
        await tick();
    }

    const bandProviderLabel = $derived(
        classifierStatus?.active_provider ? compatProviderLabel(classifierStatus.active_provider) : '—'
    );
    const openvinoUnsupportedOps = $derived(classifierStatus?.openvino_model_compile_unsupported_ops || []);
    const hasOpenvinoOpIncompatibility = $derived(
        (classifierStatus?.openvino_model_compile_ok === false) && openvinoUnsupportedOps.length > 0
    );
    const recommendedFallbackProvider = $derived(
        (classifierStatus?.cuda_available ?? false) ? 'NVIDIA CUDA' : 'CPU'
    );
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
    const inferenceProviderChoices = $derived(buildInferenceProviderChoices(classifierStatus, inferenceProvider));
    const inferenceProviderOptions = $derived(inferenceProviderChoices.map((choice) => ({
        value: choice.value,
        label: choice.unavailable
            ? `${providerLabel(choice.value)} · ${$_('common.unavailable', { default: 'Unavailable' })}`
            : providerLabel(choice.value),
        disabled: choice.unavailable,
    })));
    const providerPreferenceOrder = $derived(getProviderPreferenceOrder(classifierStatus));
    const providerPreferenceLabel = $derived(providerPreferenceOrder.map(providerLabel).join(' → '));
    const configuredProviderUnavailable = $derived(
        inferenceProvider !== 'auto'
        && inferenceProviderChoices.some((choice) => choice.value === inferenceProvider && choice.unavailable)
    );
    const packagedProviders = $derived(classifierStatus?.packaged_inference_providers ?? []);
    const showCudaDiagnostics = $derived(packagedProviders.length === 0 || packagedProviders.includes('cuda'));
    const showIntelDiagnostics = $derived(
        packagedProviders.length === 0 || packagedProviders.some((provider) => provider.startsWith('intel_'))
    );

    // --- Per-host device compatibility check ---
    const verifiedProviders = $derived(classifierStatus?.host_device_eligibility?.verified_providers ?? []);
    function providerVerified(p: string): boolean {
        return verifiedProviders.includes(p);
    }
    let compatRunning = $state(false);
    let compatAllModels = $state(false);
    let compatPhase = $state<string | null>(null);
    let compatProgress = $state<{ done: number; total: number; label: string } | null>(null);
    let compatMatrix = $state<DeviceMatrix | null>(null);
    let compatError = $state<string | null>(null);
    let compatPoll: ReturnType<typeof setInterval> | null = null;
    let compatPollInFlight = false;
    // Identifies the newest check so a superseded poll's late reply is ignored.
    let compatCheck = 0;
    // Models the latest check covered, so Retry repeats the same scope. Empty means every installed model.
    let compatModelIds: string[] = [];
    let settleCompat: () => void = () => {};
    let runtimeRefreshFailed = $state(false);

    // A check can move classification onto a newly validated provider, so the
    // runtime shown afterwards must be read back from the workers rather than
    // assumed from the matrix's recommendation.
    async function refreshRuntimeAfterCheck(): Promise<void> {
        if (!onrefreshclassifierstatus) return;
        runtimeRefreshFailed = !(await onrefreshclassifierstatus());
    }

    /** Starts a device check and resolves once it has finished, failed or been superseded. */
    async function runCompatCheck(modelIds: string[] = []): Promise<void> {
        if (compatPoll) clearInterval(compatPoll);
        compatPoll = null;
        settleCompat();
        const settled = new Promise<void>((resolve) => (settleCompat = resolve));
        compatModelIds = modelIds;
        cdOpen = true;
        cdRunId += 1;
        runtimeRefreshFailed = false;
        compatError = null;
        compatMatrix = null;
        compatRunning = true;
        compatPhase = 'starting';
        compatProgress = null;
        const check = ++compatCheck;
        let seenActive = false;
        try {
            const { run_id } = await startModelEvalRun({
                sweep_devices: true,
                compat_only: true,
                sweep_all_models: modelIds.length === 0 && compatAllModels,
                model_ids: modelIds,
            });
            if (check !== compatCheck) return;
            compatPoll = window.setInterval(async () => {
                if (compatPollInFlight || document.hidden) return;
                compatPollInFlight = true;
                try {
                    const list = await listModelEvalRuns();
                    if (check !== compatCheck) return;
                    if (list.active && list.active.run_id === run_id) {
                        seenActive = true;
                        compatPhase = list.active.phase ?? null;
                        compatProgress = list.active.progress ?? null;
                    } else {
                        if (!seenActive) {
                            const summary = await getModelEvalRun(run_id).catch(() => null);
                            if (check !== compatCheck) return;
                            const stopped = stopCause(summary?.error_code);
                            if (!summary?.finished_at && !stopped) return;
                            if (stopped) {
                                clearInterval(compatPoll ?? undefined);
                                compatPoll = null;
                                compatRunning = false;
                                compatPhase = 'error';
                                compatError = $_(`model_eval.stopped.${stopped}`);
                                cdRunId += 1;
                                await refreshRuntimeAfterCheck();
                                settleCompat();
                                return;
                            }
                        }
                        clearInterval(compatPoll ?? undefined);
                        compatPoll = null;
                        compatRunning = false;
                        compatPhase = 'complete';
                        try {
                            const matrix = await getModelEvalDeviceMatrix(run_id);
                            if (check !== compatCheck) return;
                            if (!matrix) {
                                throw new Error(
                                    $_('settings.detection.compat_results_unavailable', {
                                        default: 'Compatibility results could not be loaded. Please retry.'
                                    })
                                );
                            }
                            compatMatrix = matrix;
                            cdRunId += 1;
                        } catch (error) {
                            if (check !== compatCheck) return;
                            compatMatrix = null;
                            compatError = error instanceof Error && error.message.trim()
                                ? error.message
                                : $_('settings.detection.compat_results_unavailable', {
                                    default: 'Compatibility results could not be loaded. Please retry.'
                                });
                            cdRunId += 1;
                        }
                        if (check === compatCheck) await refreshRuntimeAfterCheck();
                        settleCompat();
                    }
                } catch {
                    /* transient — keep polling */
                } finally {
                    compatPollInFlight = false;
                }
            }, 2000);
        } catch (e) {
            if (check !== compatCheck) return;
            compatRunning = false;
            compatError = (e as Error).message;
            settleCompat();
        }
        return settled;
    }

    // Scoped to one finder, so the run never swaps the active identification model.
    function checkFinderDevices(modelId: string): Promise<void> {
        return runCompatCheck([modelId]);
    }

    function compatProviders(matrix: DeviceMatrix): string[] {
        return matrix.providers?.length ? matrix.providers : matrix.devices;
    }

    function compatProviderLabel(provider: string): string {
        return ['auto', 'cpu', 'cuda', 'intel_cpu', 'intel_gpu', 'intel_npu'].includes(provider)
            ? providerLabel(provider as InferenceProvider)
            : provider;
    }

    type CompatRow = DeviceMatrix['models'][string] | NonNullable<DeviceMatrix['crop_detectors']>[string];

    function compatRows(matrix: DeviceMatrix): Array<[string, CompatRow]> {
        return [
            ...Object.entries(matrix.models),
            ...Object.entries(matrix.crop_detectors ?? {}),
        ];
    }

    function compatEntry(row: CompatRow | undefined, provider: string) {
        return row?.providers?.[provider] ?? row?.devices?.[provider];
    }

    function compatDeviceCell(row: CompatRow | undefined, dev: string): { label: string; cls: string } {
        if (!row || row.error) return { label: '—', cls: 'text-slate-600 dark:text-slate-400' };
        const e = compatEntry(row, dev);
        if (!e) return { label: '—', cls: 'text-slate-600 dark:text-slate-400' };
        if (!e.compiles) return { label: '✗ fails', cls: 'text-red-700 dark:text-red-400' };
        if (e.finite === false) return { label: '⚠ NaN', cls: 'text-red-700 dark:text-red-400' };
        if (e.baseline || dev === row.baseline_provider || dev === 'CPU') return { label: '✓ baseline', cls: 'text-slate-600 dark:text-slate-400' };
        const n = e.images_compared;
        if (e.matches_cpu && n) return { label: `✓ ${n}/${n}`, cls: 'text-success-700 dark:text-success-300' };
        if (typeof e.detection_match_rate === 'number' && n) {
            return { label: `⚠ ${Math.round(e.detection_match_rate * n)}/${n}`, cls: 'text-attention-600 dark:text-attention-400' };
        }
        if (typeof e.top1_match_rate === 'number' && n) {
            return { label: `⚠ ${Math.round(e.top1_match_rate * n)}/${n}`, cls: 'text-attention-600 dark:text-attention-400' };
        }
        return { label: '✓ runs', cls: 'text-success-700 dark:text-success-300' };
    }

    // Present the compatibility run through the shared DiagnosticDialog: one stage
    // per device, aggregated from the matrix. `warning` is honest for a device that
    // runs but whose results differ from the CPU baseline.
    let cdOpen = $state(false);
    let cdRunId = $state(0);

    function compatCellOutcome(row: CompatRow | undefined, dev: string): { state: DiagnosticStageState; note: string } {
        if (!row || row.error) return { state: 'skipped', note: '—' };
        const e = compatEntry(row, dev);
        if (!e) return { state: 'skipped', note: '—' };
        if (!e.compiles) return { state: 'failed', note: $_('settings.detection.compat_note_fails', { default: 'fails to compile' }) };
        if (e.finite === false) return { state: 'failed', note: $_('settings.detection.compat_note_nan', { default: 'non-finite output' }) };
        if (e.baseline || dev === row.baseline_provider || dev === 'CPU') return { state: 'passed', note: $_('settings.detection.compat_note_baseline', { default: 'CPU baseline' }) };
        const n = e.images_compared;
        if (e.matches_cpu && n) return { state: 'passed', note: $_('settings.detection.compat_note_match', { default: '{n}/{n} match CPU', values: { n } }) };
        if (typeof e.detection_match_rate === 'number' && n) {
            return { state: 'warning', note: `${Math.round(e.detection_match_rate * n)}/${n} boxes match CPU` };
        }
        if (typeof e.top1_match_rate === 'number' && n) {
            return { state: 'warning', note: $_('settings.detection.compat_note_partial', { default: '{m}/{n} match CPU', values: { m: Math.round(e.top1_match_rate * n), n } }) };
        }
        return { state: 'passed', note: $_('settings.detection.compat_note_runs', { default: 'runs' }) };
    }

    const compatStateRank: Record<DiagnosticStageState, number> = { pending: 0, running: 0, skipped: 1, passed: 2, warning: 3, failed: 4 };

    function compatDeviceStage(matrix: DeviceMatrix, dev: string): DiagnosticStage {
        let state: DiagnosticStageState = 'skipped';
        const parts: string[] = [];
        for (const [mid, row] of compatRows(matrix)) {
            const outcome = compatCellOutcome(row, dev);
            if (compatStateRank[outcome.state] > compatStateRank[state]) state = outcome.state;
            parts.push(`${mid}: ${outcome.note}`);
        }
        return { id: dev, label: compatProviderLabel(dev), state, message: parts.join(' · ') };
    }

    const compatDialogStages = $derived.by((): DiagnosticStage[] => {
        const matrix = compatMatrix;
        if (!matrix) {
            return [{
                id: 'run',
                label: $_('settings.detection.compat_stage_run', { default: "Validating this host's devices" }),
                state: compatRunning ? 'running' : 'pending',
                message: compatProgress
                    ? `${compatProgress.done}/${compatProgress.total} · ${compatProgress.label}`
                    : $_('settings.detection.compat_stage_run_hint', { default: 'Compiling and comparing each device against the CPU baseline…' })
            }];
        }
        return compatProviders(matrix).map((dev) => compatDeviceStage(matrix, dev));
    });

    const compatDialogResult = $derived.by((): DiagnosticResult | null => {
        if (compatError) return { ok: false, message: compatError };
        if (!compatMatrix) return null;
        const failed = compatDialogStages.some((s) => s.state === 'failed');
        const warned = compatDialogStages.some((s) => s.state === 'warning');
        const skipped = compatDialogStages.some((s) => s.state === 'skipped');
        return {
            ok: !failed && !warned && !skipped,
            message: failed
                ? $_('settings.detection.compat_result_failed', { default: 'Some devices failed validation. See the breakdown below.' })
                : skipped
                    ? $_('settings.detection.compat_result_skipped', { default: 'Some devices could not be validated. See the breakdown below.' })
                    : warned
                        ? $_('settings.detection.compat_result_warn', { default: 'All devices run, but some differ from the CPU baseline.' })
                        : $_('settings.detection.compat_result_ok', { default: 'All devices match the CPU baseline.' })
        };
    });

    onDestroy(() => {
        compatCheck += 1;
        if (compatPoll) clearInterval(compatPoll);
        settleCompat();
    });
</script>

<!-- At the narrowest widths with enlarged text a long word may break, rather than push the page sideways. -->
<div class="space-y-6 wrap-anywhere">

    <NativeProfileRevalidation />

    <div class="space-y-3">
        <DetectionStatusBand
            {classifierStatus}
            {imageExecutionMode}
            autoVideoEnabled={autoVideoClassification}
            activeProviderLabel={bandProviderLabel}
            issueCount={healthIssueCount}
            modelsAnchorId={MODELS_CARD_ID}
            reportAnchorId={RUNTIME_REPORT_ID}
            onreveal={revealAnchor}
        />


        {#if classifierStatus?.fallback_reason || classifierStatus?.model_config_warnings?.length || classifierStatus?.openvino_model_compile_ok === false}
            <div role="alert" class="text-sm text-attention-800 dark:text-attention-200">
                {#if classifierStatus.fallback_reason}
                    {$_('settings.detection.provider_fallback_reason', { default: 'Fallback:' })} {classifierStatus.fallback_reason}
                {:else if classifierStatus.model_config_warnings?.length}
                    {$_('settings.detection.model_config_warning', { default: 'Model config warning:' })} {classifierStatus.model_config_warnings[0]}
                {:else}
                    {$_('settings.detection.openvino_compile_failure', { default: 'OpenVINO model incompatibility on this host' })}
                {/if}
            </div>
        {/if}
    </div>

    <SettingsCard
        title={$_('settings.detection.models_card_title', { default: 'Models' })}
        description={$_('settings.detection.models_card_desc', { default: 'Two models work in turn. The bird finder locates each bird in the camera frame; the identification model names its species.' })}
    >
        <div class="space-y-4">
                <SettingsRow
                    labelId="setting-region-override"
                    label={$_('settings.detection.region_override_title', { default: 'Bird model region' })}
                    description={$_('settings.detection.region_override_desc', { default: 'Auto uses your configured country. Manual override always wins.' })}
                    layout="stacked"
                >
                    <SettingsSelect
                        id="bird-model-region-override"
                        value={birdModelRegionOverride}
                        ariaLabel={$_('settings.detection.region_override_title', { default: 'Bird model region' })}
                        options={BIRD_MODEL_REGION_OVERRIDE_VALUES.map((option) => ({
                            value: option,
                            label: option === 'auto'
                                ? $_('settings.detection.region_override_auto', { default: 'Auto' })
                                : option === 'eu'
                                    ? $_('settings.detection.region_override_eu', { default: 'Europe' })
                                    : $_('settings.detection.region_override_na', { default: 'North America' })
                        }))}
                        onchange={(v) => (birdModelRegionOverride = v as BirdModelRegionOverride)}
                    />
                </SettingsRow>

        </div>
        <div id={MODELS_CARD_ID} class="scroll-mt-24">
            <ModelManager
                executionMode={imageExecutionMode}
                autoVideoEnabled={autoVideoClassification}
                bind:birdFinder
                bind:birdFinderProvider
                {classifierStatus}
                deviceCheckRunning={compatRunning}
                onruntimechange={onrefreshclassifierstatus}
                oncheckfinderdevices={checkFinderDevices}
                {onopenlocationsettings}
            />
        </div>
    </SettingsCard>

    <SettingsCard
        collapsible
        id={HARDWARE_CARD_ID}

        title={$_('settings.detection.hardware_title', { default: 'Hardware' })}
        description={$_('settings.detection.hardware_desc', { default: 'Which device runs the models, and how much memory they may use. Auto picks the fastest device that passed the check on this host.' })}
    >
        <div class="space-y-4">
            <SettingsRow
                labelId="setting-inference-provider"
                label={$_('settings.detection.inference_provider', { default: 'Inference Provider' })}
                description={$_('settings.detection.inference_provider_desc', { default: 'Only providers included in this image, detected on this host, and supported by the active model are shown.' })}
                layout="stacked"
            >
                <div class="space-y-2">
                    <SettingsSelect
                        id="inference-provider"
                        value={inferenceProvider}
                        ariaLabel={$_('settings.detection.inference_provider', { default: 'Inference Provider' })}
                        options={inferenceProviderOptions}
                        onchange={(v) => (inferenceProvider = v as InferenceProvider)}
                    />
                    {#if providerPreferenceLabel}
                        <p aria-live="polite" class="text-xs font-semibold text-slate-600 dark:text-slate-400">
                            {$_('settings.detection.provider_runtime_order', {
                                values: { order: providerPreferenceLabel },
                                default: `Current runtime order: ${providerPreferenceLabel}`
                            })}
                        </p>
                    {/if}
                    {#if configuredProviderUnavailable}
                        <p role="status" class="text-sm leading-snug text-slate-600 dark:text-slate-400">
                            {$_('settings.detection.provider_saved_unavailable', {
                                values: { provider: providerLabel(inferenceProvider as InferenceProvider) },
                                default: `Saved: ${providerLabel(inferenceProvider as InferenceProvider)}. It is not among the devices this model can use here now, so another device is used. Check devices on this host, or choose Auto.`
                            })}
                        </p>
                    {/if}
                </div>
            </SettingsRow>

            {#if classifierStatus && ((classifierStatus.host_available_providers?.length ?? classifierStatus.available_providers?.length ?? 0) > 0)}
                <div class="space-y-3">
                    <p class="text-sm font-bold text-slate-900 dark:text-white">{$_('settings.detection.compat_panel_title', { default: 'Check devices on this host' })}</p>
                    <p class="text-xs leading-relaxed text-slate-600 dark:text-slate-400">{$_('settings.detection.compat_panel_desc', { default: 'Runs the installed models on each device this image can use and compares the results with the CPU. Graphics and NPU devices are used only after they pass here.' })}</p>
                    <p class="text-xs text-slate-600 dark:text-slate-400 leading-snug">
                        {#if verifiedProviders.length}
                            {$_('settings.detection.compat_verified', { default: 'Verified on this host:' })} <span class="font-bold">{verifiedProviders.join(', ')}</span>{#if classifierStatus.host_device_eligibility?.generated_at} · {formatDateTime(classifierStatus.host_device_eligibility.generated_at)}{/if}
                        {:else}
                            {$_('settings.detection.compat_unverified', { default: 'Not yet run on this host. Run the check to verify the providers available in this image.' })}
                        {/if}
                    </p>
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="inline-flex min-h-11 max-w-full flex-wrap items-center gap-3">
                            <SettingsToggle
                                checked={compatAllModels}
                                disabled={compatRunning}
                                labelledBy="compat-all-models-label"
                                srLabel={$_('settings.detection.compat_all_models', { default: 'Also test models that are not installed' })}
                                onchange={(value) => (compatAllModels = value)}
                            />
                            <span class="min-w-0">
                                <span id="compat-all-models-label" class="block text-sm font-semibold text-slate-800 dark:text-slate-100">{$_('settings.detection.compat_all_models', { default: 'Also test models that are not installed' })}</span>
                                <span class="block text-xs text-slate-600 dark:text-slate-400">{$_('settings.detection.compat_all_hint', { default: 'Downloads each one first, so the check takes much longer.' })}</span>
                            </span>
                        </span>
                        <button type="button" onclick={() => runCompatCheck()} disabled={compatRunning} class="btn btn-primary min-h-11 max-w-full px-4 py-2 whitespace-normal">
                            {compatRunning ? $_('settings.detection.compat_running', { default: 'Running…' }) : $_('settings.detection.compat_run', { default: 'Run compatibility check' })}
                        </button>
                    </div>
                    {#if compatError}<p role="alert" class="text-xs font-bold text-red-700 dark:text-red-400">{compatError}</p>{/if}
                    {#if runtimeRefreshFailed}
                        <p role="alert" class="text-xs font-bold text-attention-700 dark:text-attention-300">
                            {$_('settings.detection.runtime_refresh_failed', { default: 'The check finished, but YA-WAMF could not read the runtime it is now using. Reload the page to see the current provider.' })}
                        </p>
                    {/if}
                    {#if compatRunning && compatProgress}
                        <p role="status" class="text-xs text-slate-600 dark:text-slate-400">{compatPhase}: {compatProgress.done}/{compatProgress.total} {compatProgress.label}</p>
                    {/if}
                </div>
            {/if}
        </div>
        <a
            href={GPU_DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex min-h-11 items-center gap-1.5 text-xs font-bold text-brand-700 hover:underline dark:text-brand-300"
        >
            {$_('settings.detection.gpu_setup_docs', { default: 'GPU setup & diagnostics guide' })}
            <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h4m0 0v4m0-4L10 14" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 9v10h10" />
            </svg>
        </a>

        <AdvancedSection
            id="detection-memory-advanced"
            title={$_('settings.detection.memory_title', { default: 'Memory and isolation' })}
            openByDefault={memoryCustomised}
        >
            <div class="space-y-4">
                <SettingsRow
                    labelId="setting-execution-mode"
                    label={$_('settings.detection.execution_mode', { default: 'Execution Mode' })}
                    description={$_('settings.detection.execution_mode_desc', { default: 'Subprocess, the default, identifies birds in worker processes the app can restart, so a stalled or crashed identification never takes the interface down. One worker runs by default; each additional worker you configure holds its own copy of the model in memory. In-Process keeps a single copy inside the app itself: less memory, but heavy identification competes with the pages you are looking at.' })}
                    layout="stacked"
                >
                    <SettingsSelect
                        id="image-execution-mode"
                        value={imageExecutionMode}
                        ariaLabel={$_('settings.detection.execution_mode', { default: 'Execution Mode' })}
                        options={[
                            { value: 'subprocess', label: $_('settings.detection.mode_subprocess', { default: 'Subprocess (Isolated)' }) },
                            { value: 'in_process', label: $_('settings.detection.mode_in_process', { default: 'In-Process (Shared RAM)' }) }
                        ]}
                        onchange={(v) => (imageExecutionMode = v)}
                    />
                    {#if imageExecutionMode === 'subprocess' && classifierStatus?.resolved_live_workers}
                        <p class="text-xs text-slate-600 dark:text-slate-400">
                            {$_('settings.detection.execution_mode_worker_plan', {
                                default:
                                    'Resolved for this install: {live} live and {background} background worker processes, each with its own copy of the model.',
                                values: {
                                    live: classifierStatus.resolved_live_workers,
                                    background: classifierStatus.resolved_background_workers ?? 1
                                }
                            })}
                            {#if classifierStatus.active_model_estimated_ram_mb}
                                {$_('settings.detection.execution_mode_worker_ram', {
                                    default: 'The active model is estimated at {each} MB per copy, about {total} MB across the workers.',
                                    values: {
                                        each: classifierStatus.active_model_estimated_ram_mb,
                                        total:
                                            classifierStatus.active_model_estimated_ram_mb *
                                            ((classifierStatus.resolved_live_workers ?? 1) +
                                                (classifierStatus.resolved_background_workers ?? 1))
                                    }
                                })}
                            {/if}
                        </p>
                    {/if}
                </SettingsRow>

                {#if imageExecutionMode === 'subprocess'}
                    <SettingsRow
                        labelId="setting-worker-counts"
                        label={$_('settings.detection.worker_counts', { default: 'Worker processes' })}
                        description={$_('settings.detection.worker_counts_desc', { default: 'Each worker holds its own copy of the model. Leave empty for the default of one. Applied the next time the classifier workers restart.' })}
                        layout="stacked"
                    >
                        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <label class="flex flex-col gap-1.5">
                                <span class="text-xs font-bold text-slate-600 dark:text-slate-400">{$_('settings.detection.worker_counts_live', { default: 'Live' })}</span>
                                <input
                                    id="live-worker-count"
                                    type="number"
                                    min="1"
                                    max="8"
                                    step="1"
                                    value={liveWorkerCount ?? ''}
                                    placeholder={$_('settings.detection.worker_counts_auto', { default: '1 (default)' })}
                                    aria-label={$_('settings.detection.worker_counts_live', { default: 'Live' })}
                                    oninput={(event) => {
                                        const raw = event.currentTarget.value.trim();
                                        liveWorkerCount = raw === '' ? null : Math.max(1, Math.min(8, Number(raw) || 1));
                                    }}
                                    class="input-base w-full"
                                />
                            </label>
                            <label class="flex flex-col gap-1.5">
                                <span class="text-xs font-bold text-slate-600 dark:text-slate-400">{$_('settings.detection.worker_counts_background', { default: 'Background' })}</span>
                                <input
                                    id="background-worker-count"
                                    type="number"
                                    min="1"
                                    max="4"
                                    step="1"
                                    value={backgroundWorkerCount ?? ''}
                                    placeholder={$_('settings.detection.worker_counts_auto', { default: '1 (default)' })}
                                    aria-label={$_('settings.detection.worker_counts_background', { default: 'Background' })}
                                    oninput={(event) => {
                                        const raw = event.currentTarget.value.trim();
                                        backgroundWorkerCount = raw === '' ? null : Math.max(1, Math.min(4, Number(raw) || 1));
                                    }}
                                    class="input-base w-full"
                                />
                            </label>
                        </div>
                    </SettingsRow>
                {/if}
            </div>
        </AdvancedSection>

        <div id={RUNTIME_REPORT_ID} class="scroll-mt-24">
            <AdvancedSection
                id={RUNTIME_REPORT_SECTION_ID}
                title={$_('settings.detection.runtime_report_title', { default: 'Runtime report' })}
            >
            {#if classifierStatus}
                <div class="space-y-3">
                    <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">
                        {$_('settings.detection.inference_diagnostics_title', { default: 'Runtime diagnostics' })}
                    </p>
                    <div class="flex flex-wrap items-center gap-2">
                        {#if showCudaDiagnostics}
                            <span class="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-bold {(classifierStatus.cuda_available ?? false) ? 'bg-success-500/10 text-success-700 dark:text-success-300' : ((classifierStatus.cuda_provider_installed ?? false) ? 'bg-attention-500/10 text-attention-700 dark:text-attention-300' : 'bg-slate-500/10 text-slate-600 dark:text-slate-400')}">
                                {#if classifierStatus.cuda_available}
                                    {$_('settings.detection.cuda_available')}
                                {:else if (classifierStatus.cuda_provider_installed ?? false) && !(classifierStatus.cuda_hardware_available ?? false)}
                                    {$_('settings.detection.cuda_runtime_only', { default: 'CUDA runtime installed (no NVIDIA GPU detected)' })}
                                {:else}
                                    {$_('settings.detection.cuda_unavailable')}
                                {/if}
                            </span>
                        {/if}
                        {#if showIntelDiagnostics}
                            <span class="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-bold {(classifierStatus.openvino_available ?? false) ? 'bg-success-500/10 text-success-700 dark:text-success-300' : 'bg-slate-500/10 text-slate-600 dark:text-slate-400'}">
                                {$_('settings.detection.openvino_status', { default: 'OpenVINO' })}: {(classifierStatus.openvino_available ?? false) ? $_('common.available', { default: 'Available' }) : $_('common.unavailable', { default: 'Unavailable' })}
                            </span>
                            <span class="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-bold {(classifierStatus.intel_gpu_available ?? false) ? 'bg-success-500/10 text-success-700 dark:text-success-300' : 'bg-slate-500/10 text-slate-600 dark:text-slate-400'}">
                                {$_('settings.detection.intel_gpu_status', { default: 'Intel GPU' })}: {(classifierStatus.intel_gpu_available ?? false) ? ($_('settings.detection.auto_detected', { default: 'Auto-detected' }) + (providerVerified('intel_gpu') ? '· verified ✓' : '· unverified')) : $_('common.not_available', { default: 'Not detected' })}
                            </span>
                            <span class="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-bold {(classifierStatus.intel_npu_available ?? false) ? 'bg-success-500/10 text-success-700 dark:text-success-300' : 'bg-slate-500/10 text-slate-600 dark:text-slate-400'}">
                                {$_('settings.detection.intel_npu_status', { default: 'Intel NPU' })}: {(classifierStatus.intel_npu_available ?? false) ? ($_('settings.detection.auto_detected', { default: 'Auto-detected' }) + (providerVerified('intel_npu') ? '· verified ✓' : '· unverified')) : $_('common.not_available', { default: 'Not detected' })}
                            </span>
                        {/if}
                    </div>

                    <div class="flex flex-wrap items-center gap-2 text-xs font-bold text-slate-600 dark:text-slate-400">
                        {#if classifierStatus.image_flavor}
                            <span>{$_('settings.detection.image_flavor_label', { default: 'Image' })}: {classifierStatus.image_flavor}</span>
                        {/if}
                        {#if classifierStatus.packaged_inference_providers?.length}
                            <span>{$_('settings.detection.packaged_providers_label', { default: 'Packaged' })}: {classifierStatus.packaged_inference_providers.join(', ')}</span>
                        {/if}
                        <span>{$_('settings.detection.selected_provider_label', { default: 'Selected' })}: {classifierStatus.selected_provider ?? inferenceProvider}</span>
                        {#if classifierStatus.runtime_source === 'planned'}
                            <span>{$_('settings.detection.planned_provider_label', { default: 'Planned' })}: {classifierStatus.active_provider ?? 'unknown'}</span>
                        {:else}
                            <span>{$_('settings.detection.active_provider_label', { default: 'Active' })}: {classifierStatus.active_provider ?? 'unknown'}</span>
                        {/if}
                        {#if classifierStatus.inference_backend}
                            <span>{$_('settings.detection.inference_backend_label', { default: 'Backend' })}: {classifierStatus.inference_backend}</span>
                        {/if}
                    </div>
                    {#if classifierStatus.image_flavor_warning === 'selected_provider_not_packaged'}
                        <div role="alert" class="flex items-start gap-2 text-xs font-medium leading-relaxed text-attention-800 dark:text-attention-200">
                            <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                <path d="M10.3 2.9 1.8 17a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 2.9a2 2 0 0 0-3.4 0Z" />
                                <path d="M12 9v4M12 17h.01" />
                            </svg>
                            <p>{$_('settings.detection.image_flavor_mismatch', {
                                default: 'The {provider} runtime is not included in the {flavor} image. Use the full image or a matching provider image, then recreate the container. CPU fallback remains available.',
                                values: {
                                    provider: classifierStatus.selected_provider ?? inferenceProvider,
                                    flavor: classifierStatus.image_flavor ?? 'unknown'
                                }
                            })}</p>
                        </div>
                    {/if}
                    <p class="text-xs font-bold text-slate-600 dark:text-slate-400">
                        {$_('settings.detection.personalization_status_label', { default: 'Personalization' })}:
                        {(classifierStatus.personalized_rerank_enabled ?? false) ? $_('common.enabled', { default: 'Enabled' }) : $_('common.disabled', { default: 'Disabled' })}
                        · {$_('settings.detection.personalization_active_pairs', { default: 'Active camera/model pairs' })}: {classifierStatus.personalization_active_camera_models ?? 0}
                        · {$_('settings.detection.personalization_feedback_rows', { default: 'Feedback tags' })}: {classifierStatus.personalization_feedback_rows ?? 0}
                        ({$_('settings.detection.personalization_min_tags', { default: 'min' })} {classifierStatus.personalization_min_feedback_tags ?? 20})
                    </p>
                    {#if classifierStatus.fallback_reason}
                        <p class="text-xs font-bold text-attention-700 dark:text-attention-300">{$_('settings.detection.provider_fallback_reason', { default: 'Fallback:' })} {classifierStatus.fallback_reason}</p>
                    {/if}
                    {#if classifierStatus.model_config_warnings?.length}
                        {#each classifierStatus.model_config_warnings as modelConfigWarning}
                            <p class="text-xs font-bold text-attention-700 dark:text-attention-300">{$_('settings.detection.model_config_warning', { default: 'Model config warning:' })} {modelConfigWarning}</p>
                        {/each}
                    {/if}
                    {#if classifierStatus.cuda_probe_error}
                        <div class="text-attention-800 dark:text-attention-200">
                            <div class="text-sm font-semibold text-attention-700 dark:text-attention-300">CUDA diagnostics</div>
                            <div class="mt-2 space-y-1 break-all text-xs font-medium text-attention-900 dark:text-attention-100">
                                <p><span class="font-bold">NVIDIA GPU:</span> {(classifierStatus.cuda_hardware_available ?? false) ? 'detected' : 'not detected'}</p>
                                <p><span class="font-bold">{$_('settings.detection.probe_error', { default: 'Probe error:' })}</span> {classifierStatus.cuda_probe_error}</p>
                            </div>
                        </div>
                    {/if}
                    {#if classifierStatus.openvino_model_compile_ok === false}
                        <div class="space-y-2 text-attention-800 dark:text-attention-200">
                            <p class="text-sm font-semibold text-attention-700 dark:text-attention-300">{$_('settings.detection.openvino_compile_failure', { default: 'OpenVINO model incompatibility on this host' })}</p>
                            <p class="break-all text-xs font-medium text-attention-900 dark:text-attention-100">
                                {$_('settings.detection.openvino_compile_failure_detail', { default: 'Active model' })}: <code>{classifierStatus.active_model_id || 'unknown'}</code>
                                {#if classifierStatus.openvino_model_compile_device}({classifierStatus.openvino_model_compile_device}){/if}
                            </p>
                            <p class="text-xs font-medium text-attention-900 dark:text-attention-100">
                                Automatic fallback is active: <code>{classifierStatus.inference_backend || 'unknown'}</code> / <code>{classifierStatus.active_provider || 'unknown'}</code>
                            </p>
                            {#if hasOpenvinoOpIncompatibility}
                                <p class="text-xs font-medium text-attention-900 dark:text-attention-100">OpenVINO reported unsupported ONNX operators for this model/runtime:</p>
                                <div class="flex flex-wrap gap-1">
                                    {#each openvinoUnsupportedOps as op}
                                        <span class="inline-flex items-center text-xs text-attention-800 dark:text-attention-200">{op}</span>
                                    {/each}
                                </div>
                            {/if}
                            <p class="text-xs font-medium text-attention-900 dark:text-attention-100">
                                Next steps: switch to <code>eva02_large_inat21</code> for OpenVINO, or keep this model and set provider to <code>{recommendedFallbackProvider}</code>.
                            </p>
                            {#if classifierStatus.openvino_model_compile_error}
                                <details class="group pt-1">
                                    <summary class="flex min-h-11 cursor-pointer items-center gap-2 py-3 text-sm font-semibold text-attention-700 focus-ring dark:text-attention-300">
                                        <svg class="h-4 w-4 shrink-0 transition-transform duration-200 group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                                        {$_('settings.detection.model_manager_technical_details', { default: 'Technical details' })}
                                    </summary>
                                    <p class="mt-1 break-all text-xs font-medium text-attention-900 dark:text-attention-100">{classifierStatus.openvino_model_compile_error}</p>
                                </details>
                            {/if}
                        </div>
                    {/if}
                    {#if ((classifierStatus.openvino_available === false) || classifierStatus.openvino_gpu_probe_error) && (classifierStatus.openvino_import_error || classifierStatus.openvino_probe_error || classifierStatus.openvino_gpu_probe_error || classifierStatus.dev_dri_present !== undefined)}
                        <div class="text-attention-800 dark:text-attention-200">
                            <div class="text-sm font-semibold text-attention-700 dark:text-attention-300">{$_('settings.detection.openvino_diagnostics', { default: 'OpenVINO diagnostics' })}</div>
                            <div class="mt-2 space-y-1 break-all text-xs font-medium text-attention-900 dark:text-attention-100">
                                {#if classifierStatus.openvino_version}<p><span class="font-bold">Version:</span> {classifierStatus.openvino_version}</p>{/if}
                                {#if classifierStatus.openvino_import_path}<p><span class="font-bold">Import:</span> <code>{classifierStatus.openvino_import_path}</code></p>{/if}
                                <p><span class="font-bold">/dev/dri:</span> {classifierStatus.dev_dri_present ? 'present' : 'missing'}{#if classifierStatus.dev_dri_entries?.length} (<code>{classifierStatus.dev_dri_entries.join(', ')}</code>){/if}</p>
                                {#if classifierStatus.process_uid != null}
                                    <p><span class="font-bold">UID/GID:</span> {classifierStatus.process_uid}:{classifierStatus.process_gid}{#if classifierStatus.process_groups?.length} groups <code>{classifierStatus.process_groups.join(', ')}</code>{/if}</p>
                                {/if}
                                {#if classifierStatus.openvino_import_error}<p><span class="font-bold">{$_('settings.detection.import_error', { default: 'Import error:' })}</span> {classifierStatus.openvino_import_error}</p>{/if}
                                {#if classifierStatus.openvino_probe_error}<p><span class="font-bold">{$_('settings.detection.probe_error', { default: 'Probe error:' })}</span> {classifierStatus.openvino_probe_error}</p>{/if}
                                {#if classifierStatus.openvino_gpu_probe_error}<p><span class="font-bold">{$_('settings.detection.gpu_plugin_error', { default: 'GPU plugin error:' })}</span> {classifierStatus.openvino_gpu_probe_error}</p>{/if}
                            </div>
                        </div>
                    {/if}
                </div>
            {/if}
            {#if compatMatrix}
                <div class="border-t border-slate-200 pt-4 dark:border-slate-700">
                    <h3 class="text-sm font-bold text-slate-900 dark:text-white">
                        {$_('settings.detection.compat_card_title', { default: 'Device compatibility' })}
                    </h3>
                    <div class="mt-2 overflow-x-auto">
                        <table class="w-full text-xs">
                            <thead class="border-b border-slate-200 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-400">
                                <tr><th class="text-left py-1 pr-3">{$_('settings.detection.compat_model', { default: 'Model' })}</th>{#each (compatMatrix.providers?.length ? compatMatrix.providers : compatMatrix.devices) as dev}<th class="text-left px-2">{compatProviderLabel(dev)}</th>{/each}</tr>
                            </thead>
                            <tbody>
                                {#each compatRows(compatMatrix) as [mid, row]}
                                    <tr class="border-b border-slate-100 dark:border-slate-800">
                                        <td class="py-1 pr-3 font-medium text-slate-700 dark:text-slate-300">
                                            {mid}{#if row.comparison_kind === 'crop_box'} <span class="text-slate-600 dark:text-slate-400">· crop</span>{/if}
                                        </td>
                                        {#each (compatMatrix.providers?.length ? compatMatrix.providers : compatMatrix.devices) as dev}
                                            {@const c = compatDeviceCell(row, dev)}
                                            <td class="px-2 {c.cls}">{c.label}</td>
                                        {/each}
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
                </div>
            {/if}
            </AdvancedSection>
        </div>
    </SettingsCard>

    <SettingsCard
        collapsible
        id="models-testing"
        title={$_('settings.models.testing_title', { default: 'Testing the models' })}
        description={$_('settings.models.testing_desc', { default: 'Compare the installed models on reference photos of known species from iNaturalist and Wikimedia Commons.' })}
    >
        <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="min-w-0 flex-1 basis-56 text-sm text-slate-600 dark:text-slate-300">
                {$_('settings.models.testing_action', { default: 'Model evaluation runs every installed model on those photos and shows how often each is right and how long it takes.' })}
            </p>
            {#if onopenmodelevaluation}
                <a
                    href="/diagnostics/model-eval"
                    class="btn btn-secondary min-h-11 max-w-full px-4 whitespace-normal"
                    onclick={(event) => { event.preventDefault(); onopenmodelevaluation?.(); }}
                >
                    {$_('settings.models.testing_open', { default: 'Open model evaluation' })}
                </a>
            {/if}
        </div>
        {#if debugUiEnabled}
            <SettingsRow
                labelId="setting-strict-non-finite-output"
                label={$_('settings.debug.strict_non_finite_output', { default: 'Discard results the model could not compute' })}
                description={$_('settings.debug.strict_non_finite_output_desc', { default: 'On, a result that is not a number is thrown away and the model is restarted. Turn it off only while you look into a model fault.' })}
            >
                <SettingsToggle
                    checked={strictNonFiniteOutput}
                    labelledBy="setting-strict-non-finite-output"
                    srLabel={$_('settings.debug.strict_non_finite_output', { default: 'Discard results the model could not compute' })}
                    onchange={(value) => (strictNonFiniteOutput = value)}
                />
            </SettingsRow>
        {/if}
    </SettingsCard>
</div>

{#if cdOpen}
    <DiagnosticDialog
        title={$_('settings.detection.compat_test_title', { default: 'Device compatibility check' })}
        subtitle={$_('settings.detection.compat_test_subtitle', { default: 'Validates every provider available to this image and model against the CPU baseline.' })}
        stages={compatDialogStages}
        busy={compatRunning}
        result={compatDialogResult}
        runId={cdRunId}
        retryLabel={$_('settings.detection.compat_run', { default: 'Run compatibility check' })}
        onClose={() => (cdOpen = false)}
        onRetry={() => runCompatCheck(compatModelIds)}
    />
{/if}

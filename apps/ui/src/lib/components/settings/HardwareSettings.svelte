<script lang="ts">
    import SettingsSubheading from './_primitives/SettingsSubheading.svelte';
    import { _ } from 'svelte-i18n';
    import { RUNTIME_DISCLOSURES } from '../../settings/runtime-problem';
    import { formatDateTime } from '../../utils/datetime';
    import type { ClassifierStatus } from '../../api';
    import { buildInferenceProviderChoices, getProviderPreferenceOrder, type InferenceProvider } from '../../settings/inference-providers';
    import { compatEntry, compatRows, INFERENCE_PROVIDER_LABELS, isInferenceProvider, type CompatRow } from '../../settings/device-matrix';
    import { deviceCheckProblemText, type DeviceCheck } from '../../settings/device-check.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';

    const GPU_DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/docs/setup/hardware-acceleration.md';

    // Hardware: which device runs the models, how much memory they may use, and the runtime report.
    // Under Identifying birds' More options; the device check it starts is shared with the model list.
    let {
        liveWorkerCount = $bindable<number | null>(null),
        backgroundWorkerCount = $bindable<number | null>(null),
        imageExecutionMode = $bindable<'in_process' | 'subprocess' | string>('subprocess'),
        inferenceProvider = $bindable<InferenceProvider>('auto'),
        strictNonFiniteOutput = $bindable(true),
        debugUiEnabled = false,
        classifierStatus = null,
        deviceCheck
    }: {
        liveWorkerCount: number | null;
        backgroundWorkerCount: number | null;
        imageExecutionMode: 'in_process' | 'subprocess' | string;
        inferenceProvider: InferenceProvider;
        strictNonFiniteOutput?: boolean;
        /** The troubleshooting switch is offered only in a build with the debug interface on. */
        debugUiEnabled?: boolean;
        classifierStatus: ClassifierStatus | null;
        deviceCheck: DeviceCheck;
    } = $props();

    // Memory and isolation stay folded away until the owner has changed them,
    // so a customised value is never hidden behind a closed disclosure.
    const memoryCustomised = $derived(
        imageExecutionMode !== 'subprocess' || liveWorkerCount !== null || backgroundWorkerCount !== null
    );

    // The model list's report link opens the runtime report and scrolls to it.
    const RUNTIME_REPORT_ID = 'detection-runtime-report';
    const RUNTIME_REPORT_SECTION_ID = RUNTIME_DISCLOSURES[0];

    const openvinoUnsupportedOps = $derived(classifierStatus?.openvino_model_compile_unsupported_ops || []);
    const hasOpenvinoOpIncompatibility = $derived(
        (classifierStatus?.openvino_model_compile_ok === false) && openvinoUnsupportedOps.length > 0
    );
    const recommendedFallbackProvider = $derived(
        (classifierStatus?.cuda_available ?? false) ? 'NVIDIA CUDA' : 'CPU'
    );
    function providerLabel(provider: InferenceProvider): string {
        const label = INFERENCE_PROVIDER_LABELS[provider];
        return $_(label.key, { default: label.fallback });
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

    const verifiedProviders = $derived(classifierStatus?.host_device_eligibility?.verified_providers ?? []);
    function providerVerified(p: string): boolean {
        return verifiedProviders.includes(p);
    }

    function compatProviderLabel(provider: string): string {
        return isInferenceProvider(provider) ? providerLabel(provider) : provider;
    }

    function compatDeviceCell(row: CompatRow | undefined, dev: string): { label: string; cls: string } {
        if (!row || row.error) return { label: '—', cls: 'text-muted' };
        const e = compatEntry(row, dev);
        if (!e) return { label: '—', cls: 'text-muted' };
        if (!e.compiles) return { label: '✗ fails', cls: 'text-status-fail' };
        if (e.finite === false) return { label: '⚠ NaN', cls: 'text-status-fail' };
        if (e.baseline || dev === row.baseline_provider || dev === 'CPU') return { label: '✓ baseline', cls: 'text-muted' };
        const n = e.images_compared;
        if (e.matches_cpu && n) return { label: `✓ ${n}/${n}`, cls: 'text-status-ok' };
        if (typeof e.detection_match_rate === 'number' && n) {
            return { label: `⚠ ${Math.round(e.detection_match_rate * n)}/${n}`, cls: 'text-status-attention' };
        }
        if (typeof e.top1_match_rate === 'number' && n) {
            return { label: `⚠ ${Math.round(e.top1_match_rate * n)}/${n}`, cls: 'text-status-attention' };
        }
        return { label: '✓ runs', cls: 'text-status-ok' };
    }

</script>

<SettingsCard
    nested
    id="models-hardware"
    title={$_('settings.detection.hardware_title', { default: 'Hardware' })}
    description={$_('settings.detection.hardware_desc', { default: 'Which device runs the models, and how much memory they may use. Auto picks the fastest device that passed the check on this host.' })}
>
    <div class="space-y-4">
        <SettingsRow
            labelId="setting-inference-provider"
            label={$_('settings.detection.inference_provider', { default: 'Identification model runs on' })}
            description={$_('settings.detection.inference_provider_desc', { default: 'Only providers included in this image, detected on this host, and supported by the active model are shown.' })}
            layout="stacked"
        >
            <div class="space-y-2">
                <SettingsSelect
                    id="inference-provider"
                    value={inferenceProvider}
                    ariaLabel={$_('settings.detection.inference_provider', { default: 'Identification model runs on' })}
                    options={inferenceProviderOptions}
                    onchange={(v) => (inferenceProvider = v as InferenceProvider)}
                />
                {#if providerPreferenceLabel}
                    <p aria-live="polite" class="text-xs font-semibold text-muted">
                        {$_('settings.detection.provider_runtime_order', {
                            values: { order: providerPreferenceLabel },
                            default: `Current runtime order: ${providerPreferenceLabel}`
                        })}
                    </p>
                {/if}
                {#if configuredProviderUnavailable}
                    <p role="status" class="text-sm leading-snug text-muted">
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
                <p class="text-sm font-semibold text-strong">{$_('settings.detection.compat_panel_title', { default: 'Check devices on this host' })}</p>
                <p class="text-xs leading-relaxed text-muted">{$_('settings.detection.compat_panel_desc', { default: 'Runs the installed models on each device this image can use and compares the results with the CPU. Graphics and NPU devices are used only after they pass here.' })}</p>
                <p class="text-xs text-muted leading-snug">
                    {#if verifiedProviders.length}
                        {$_('settings.detection.compat_verified', { default: 'Verified on this host:' })} <span class="font-semibold">{verifiedProviders.join(', ')}</span>{#if classifierStatus.host_device_eligibility?.generated_at} · {formatDateTime(classifierStatus.host_device_eligibility.generated_at)}{/if}
                    {:else}
                        {$_('settings.detection.compat_unverified', { default: 'Not yet run on this host. Run the check to verify the providers available in this image.' })}
                    {/if}
                </p>
                <div class="flex flex-wrap items-center gap-2">
                    <span class="inline-flex min-h-11 max-w-full flex-wrap items-center gap-3">
                        <SettingsToggle
                            checked={deviceCheck.allModels}
                            disabled={deviceCheck.running}
                            labelledBy="compat-all-models-label"
                            srLabel={$_('settings.detection.compat_all_models', { default: 'Also test models that are not installed' })}
                            onchange={(value) => (deviceCheck.allModels = value)}
                        />
                        <span class="min-w-0">
                            <span id="compat-all-models-label" class="block text-sm font-semibold text-ink">{$_('settings.detection.compat_all_models', { default: 'Also test models that are not installed' })}</span>
                            <span class="block text-xs text-muted">{$_('settings.detection.compat_all_hint', { default: 'Downloads each one first, so the check takes much longer.' })}</span>
                        </span>
                    </span>
                    <button type="button" onclick={() => deviceCheck.run()} disabled={deviceCheck.running} class="btn btn-primary min-h-11 max-w-full px-4 py-2 whitespace-normal">
                        {deviceCheck.running ? $_('settings.detection.compat_running', { default: 'Running…' }) : $_('settings.detection.compat_run', { default: 'Check devices for every installed model' })}
                    </button>
                </div>
                {#if deviceCheck.problem}<p role="alert" class="text-xs text-status-fail">{deviceCheckProblemText(deviceCheck.problem, $_)}</p>{/if}
                {#if deviceCheck.runtimeRefreshFailed}
                    <p role="alert" class="text-xs text-status-attention">
                        {$_('settings.detection.runtime_refresh_failed', { default: 'The check finished, but YA-WAMF could not read the runtime it is now using. Reload the page to see the current provider.' })}
                    </p>
                {/if}
                {#if deviceCheck.running && deviceCheck.progress}
                    <p role="status" class="text-xs text-muted">{deviceCheck.phase}: {deviceCheck.progress.done}/{deviceCheck.progress.total} {deviceCheck.progress.label}</p>
                {/if}
            </div>
        {/if}
    </div>
    <a
        href={GPU_DOCS_URL}
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex min-h-11 items-center gap-1.5 text-xs text-accent-ink hover:underline"
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
                    <p class="text-xs text-muted">
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
                                default: 'The active model is estimated at {each} MB per copy, about {total} MB across the workers.',
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
                    description={$_('settings.detection.worker_counts_desc', { default: 'Each worker holds its own copy of the model. Leave empty for the default of one. Applied the next time the workers restart.' })}
                    layout="stacked"
                >
                    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <label class="flex flex-col gap-1.5">
                            <span class="text-xs text-muted">{$_('settings.detection.worker_counts_live', { default: 'Live' })}</span>
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
                            <span class="text-xs text-muted">{$_('settings.detection.worker_counts_background', { default: 'Background' })}</span>
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
        </div>
    </AdvancedSection>

    <div id={RUNTIME_REPORT_ID} class="scroll-mt-24">
        <AdvancedSection
            id={RUNTIME_REPORT_SECTION_ID}
            title={$_('settings.detection.runtime_report_title', { default: 'Runtime report' })}
        >
        {#if classifierStatus}
            <div class="space-y-3">
                <p class="text-sm font-semibold text-ink">
                    {$_('settings.detection.inference_diagnostics_title', { default: 'Runtime diagnostics' })}
                </p>
                <div class="flex flex-wrap items-center gap-2">
                    {#if showCudaDiagnostics}
                        <span class="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold {(classifierStatus.cuda_available ?? false) ? 'bg-status-ok-soft text-status-ok' : ((classifierStatus.cuda_provider_installed ?? false) ? 'bg-status-attention-soft text-status-attention' : 'bg-surface-sunken text-muted')}">
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
                        <span class="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold {(classifierStatus.openvino_available ?? false) ? 'bg-status-ok-soft text-status-ok' : 'bg-surface-sunken text-muted'}">
                            {$_('settings.detection.openvino_status', { default: 'OpenVINO' })}: {(classifierStatus.openvino_available ?? false) ? $_('common.available', { default: 'Available' }) : $_('common.unavailable', { default: 'Unavailable' })}
                        </span>
                        <span class="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold {(classifierStatus.intel_gpu_available ?? false) ? 'bg-status-ok-soft text-status-ok' : 'bg-surface-sunken text-muted'}">
                            {$_('settings.detection.intel_gpu_status', { default: 'Intel GPU' })}: {(classifierStatus.intel_gpu_available ?? false) ? (providerVerified('intel_gpu') ? $_('settings.detection.auto_detected_verified', { default: 'Auto-detected · verified ✓' }) : $_('settings.detection.auto_detected_unverified', { default: 'Auto-detected · unverified' })) : $_('common.not_available', { default: 'Not available' })}
                        </span>
                        <span class="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold {(classifierStatus.intel_npu_available ?? false) ? 'bg-status-ok-soft text-status-ok' : 'bg-surface-sunken text-muted'}">
                            {$_('settings.detection.intel_npu_status', { default: 'Intel NPU' })}: {(classifierStatus.intel_npu_available ?? false) ? (providerVerified('intel_npu') ? $_('settings.detection.auto_detected_verified', { default: 'Auto-detected · verified ✓' }) : $_('settings.detection.auto_detected_unverified', { default: 'Auto-detected · unverified' })) : $_('common.not_available', { default: 'Not available' })}
                        </span>
                    {/if}
                </div>

                <div class="flex flex-wrap items-center gap-2 text-xs text-muted">
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
                    <div role="alert" class="flex items-start gap-2 text-xs font-medium leading-relaxed text-status-attention">
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
                <p class="text-xs text-muted">
                    {$_('settings.detection.personalization_status_label', { default: 'Personalization' })}:
                    {(classifierStatus.personalized_rerank_enabled ?? false) ? $_('common.enabled', { default: 'Enabled' }) : $_('common.disabled', { default: 'Disabled' })}
                    · {$_('settings.detection.personalization_active_pairs', { default: 'Active camera/model pairs' })}: {classifierStatus.personalization_active_camera_models ?? 0}
                    · {$_('settings.detection.personalization_feedback_rows', { default: 'Feedback tags' })}: {classifierStatus.personalization_feedback_rows ?? 0}
                    ({$_('settings.detection.personalization_min_tags', { default: 'min' })} {classifierStatus.personalization_min_feedback_tags ?? 20})
                </p>
                {#if classifierStatus.fallback_reason}
                    <p class="text-xs text-status-attention">{$_('settings.detection.provider_fallback_reason', { default: 'Fallback:' })} {classifierStatus.fallback_reason}</p>
                {/if}
                {#if classifierStatus.model_config_warnings?.length}
                    {#each classifierStatus.model_config_warnings as modelConfigWarning}
                        <p class="text-xs text-status-attention">{$_('settings.detection.model_config_warning', { default: 'Model config warning:' })} {modelConfigWarning}</p>
                    {/each}
                {/if}
                {#if classifierStatus.cuda_probe_error}
                    <div class="text-status-attention">
                        <div class="text-sm font-semibold text-status-attention">CUDA diagnostics</div>
                        <div class="mt-2 space-y-1 break-all text-xs font-medium text-status-attention">
                            <p><span class="font-semibold">NVIDIA GPU:</span> {(classifierStatus.cuda_hardware_available ?? false) ? 'detected' : 'not detected'}</p>
                            <p><span class="font-semibold">{$_('settings.detection.probe_error', { default: 'Probe error:' })}</span> {classifierStatus.cuda_probe_error}</p>
                        </div>
                    </div>
                {/if}
                {#if classifierStatus.openvino_model_compile_ok === false}
                    <div class="space-y-2 text-status-attention">
                        <p class="text-sm font-semibold text-status-attention">{$_('settings.detection.openvino_compile_failure', { default: 'OpenVINO model incompatibility on this host' })}</p>
                        <p class="text-xs font-medium text-status-attention">
                            {$_('settings.detection.openvino_compile_failure_detail', {
                                values: { fallback: classifierStatus.active_provider || classifierStatus.inference_backend || 'CPU' },
                                default: 'This model cannot compile on the currently selected OpenVINO device. YA-WAMF will keep the model installed but run inference on {fallback}.'
                            })}
                        </p>
                        <p class="break-all text-xs font-medium text-status-attention">
                            {$_('settings.detection.active_model_label', { default: 'Active model' })}: <code>{classifierStatus.active_model_id || 'unknown'}</code>
                            {#if classifierStatus.openvino_model_compile_device}({classifierStatus.openvino_model_compile_device}){/if}
                        </p>
                        <p class="text-xs font-medium text-status-attention">
                            Automatic fallback is active: <code>{classifierStatus.inference_backend || 'unknown'}</code> / <code>{classifierStatus.active_provider || 'unknown'}</code>
                        </p>
                        {#if hasOpenvinoOpIncompatibility}
                            <p class="text-xs font-medium text-status-attention">OpenVINO reported unsupported ONNX operators for this model/runtime:</p>
                            <div class="flex flex-wrap gap-1">
                                {#each openvinoUnsupportedOps as op}
                                    <span class="inline-flex items-center text-xs text-status-attention">{op}</span>
                                {/each}
                            </div>
                        {/if}
                        <p class="text-xs font-medium text-status-attention">
                            Next steps: switch to <code>eva02_large_inat21</code> for OpenVINO, or keep this model and set provider to <code>{recommendedFallbackProvider}</code>.
                        </p>
                        {#if classifierStatus.openvino_model_compile_error}
                            <details class="group pt-1">
                                <summary class="flex min-h-11 cursor-pointer items-center gap-2 py-3 text-sm font-semibold text-status-attention focus-ring">
                                    <svg class="h-4 w-4 shrink-0 transition-transform duration-200 group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                                    {$_('settings.detection.model_manager_technical_details', { default: 'Technical details' })}
                                </summary>
                                <p class="mt-1 break-all text-xs font-medium text-status-attention">{classifierStatus.openvino_model_compile_error}</p>
                            </details>
                        {/if}
                    </div>
                {/if}
                {#if ((classifierStatus.openvino_available === false) || classifierStatus.openvino_gpu_probe_error) && (classifierStatus.openvino_import_error || classifierStatus.openvino_probe_error || classifierStatus.openvino_gpu_probe_error || classifierStatus.dev_dri_present !== undefined)}
                    <div class="text-status-attention">
                        <div class="text-sm font-semibold text-status-attention">{$_('settings.detection.openvino_diagnostics', { default: 'OpenVINO diagnostics' })}</div>
                        <div class="mt-2 space-y-1 break-all text-xs font-medium text-status-attention">
                            {#if classifierStatus.openvino_version}<p><span class="font-semibold">Version:</span> {classifierStatus.openvino_version}</p>{/if}
                            {#if classifierStatus.openvino_import_path}<p><span class="font-semibold">Import:</span> <code>{classifierStatus.openvino_import_path}</code></p>{/if}
                            <p><span class="font-semibold">/dev/dri:</span> {classifierStatus.dev_dri_present ? 'present' : 'missing'}{#if classifierStatus.dev_dri_entries?.length} (<code>{classifierStatus.dev_dri_entries.join(', ')}</code>){/if}</p>
                            {#if classifierStatus.process_uid != null}
                                <p><span class="font-semibold">UID/GID:</span> {classifierStatus.process_uid}:{classifierStatus.process_gid}{#if classifierStatus.process_groups?.length} groups <code>{classifierStatus.process_groups.join(', ')}</code>{/if}</p>
                            {/if}
                            {#if classifierStatus.openvino_import_error}<p><span class="font-semibold">{$_('settings.detection.import_error', { default: 'Import error:' })}</span> {classifierStatus.openvino_import_error}</p>{/if}
                            {#if classifierStatus.openvino_probe_error}<p><span class="font-semibold">{$_('settings.detection.probe_error', { default: 'Probe error:' })}</span> {classifierStatus.openvino_probe_error}</p>{/if}
                            {#if classifierStatus.openvino_gpu_probe_error}<p><span class="font-semibold">{$_('settings.detection.gpu_plugin_error', { default: 'GPU plugin error:' })}</span> {classifierStatus.openvino_gpu_probe_error}</p>{/if}
                        </div>
                    </div>
                {/if}
            </div>
        {/if}
        {#if deviceCheck.matrix}
            <div class="border-t border-line-soft pt-4">
                <SettingsSubheading>{$_('settings.detection.compat_card_title', { default: 'Device compatibility' })}</SettingsSubheading>
                <div class="mt-2 overflow-x-auto">
                    <table class="w-full text-xs">
                        <thead class="border-b border-line-soft text-xs text-muted">
                            <tr><th class="text-left py-1 pr-3">{$_('settings.detection.compat_model', { default: 'Model' })}</th>{#each (deviceCheck.matrix.providers?.length ? deviceCheck.matrix.providers : deviceCheck.matrix.devices) as dev}<th class="text-left px-2">{compatProviderLabel(dev)}</th>{/each}</tr>
                        </thead>
                        <tbody>
                            {#each compatRows(deviceCheck.matrix) as [mid, row]}
                                <tr class="border-b border-line-soft">
                                    <td class="py-1 pr-3 font-medium text-ink">
                                        {mid}{#if row.comparison_kind === 'crop_box'} <span class="text-muted">· crop</span>{/if}
                                    </td>
                                    {#each (deviceCheck.matrix.providers?.length ? deviceCheck.matrix.providers : deviceCheck.matrix.devices) as dev}
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

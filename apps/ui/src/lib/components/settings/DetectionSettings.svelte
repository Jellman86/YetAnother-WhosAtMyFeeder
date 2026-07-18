<script lang="ts">
    import { onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { formatDateTime } from '../../utils/datetime';
    import ModelManager from '../../pages/models/ModelManager.svelte';
    import { searchSpecies, type ClassifierStatus, type SearchResult } from '../../api';
    import { startModelEvalRun, listModelEvalRuns, getModelEvalDeviceMatrix, type DeviceMatrix } from '../../api/model_eval';
    import type { BlockedSpeciesEntry } from '../../api/settings';
    import { getManualTagSearchOptions } from '../../search/manual-tag-search';
    import { BIRD_MODEL_REGION_OVERRIDE_VALUES, type BirdModelRegionOverride } from '../../settings/bird-model-region-override';
    import {
        buildBlockedSpeciesEntry,
        formatBlockedSpeciesLabel,
        mergeBlockedSpeciesEntries
    } from '../../settings/blocked-species';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import type { DiagnosticStage, DiagnosticStageState, DiagnosticResult } from '../../utils/diagnostic-runner';

    const GPU_DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/docs/troubleshooting/diagnostics.md#-gpu-acceleration-diagnostics-cuda--openvino';

    let {
        threshold = $bindable(0.7),
        minConfidence = $bindable(0.4),
        trustFrigateSublabel = $bindable(true),
        writeFrigateSublabel = $bindable(true),
        personalizedRerankEnabled = $bindable(false),
        autoVideoClassification = $bindable(false),
        videoClassificationDelay = $bindable(30),
        videoClassificationMaxRetries = $bindable(3),
        videoClassificationMaxConcurrent = $bindable(1),
        videoClassificationFrames = $bindable(15),
        birdModelRegionOverride = $bindable<BirdModelRegionOverride>('auto'),
        imageExecutionMode = $bindable<'in_process' | 'subprocess' | string>('in_process'),
        inferenceProvider = $bindable<'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu' | 'intel_npu'>('auto'),
        classifierStatus = null,
        videoCircuitOpen = false,
        videoCircuitUntil = null,
        videoCircuitFailures = 0,
        blockedLabels = $bindable<string[]>([]),
        blockedSpecies = $bindable<BlockedSpeciesEntry[]>([])
    }: {
        threshold: number;
        minConfidence: number;
        trustFrigateSublabel: boolean;
        writeFrigateSublabel: boolean;
        personalizedRerankEnabled: boolean;
        autoVideoClassification: boolean;
        videoClassificationDelay: number;
        videoClassificationMaxRetries: number;
        videoClassificationMaxConcurrent: number;
        videoClassificationFrames: number;
        birdModelRegionOverride: BirdModelRegionOverride;
        imageExecutionMode: 'in_process' | 'subprocess' | string;
        inferenceProvider: 'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu' | 'intel_npu';
        classifierStatus: ClassifierStatus | null;
        videoCircuitOpen: boolean;
        videoCircuitUntil: string | null;
        videoCircuitFailures: number;
        blockedLabels: string[];
        blockedSpecies: BlockedSpeciesEntry[];
    } = $props();

    const circuitUntil = $derived(videoCircuitUntil ? formatDateTime(videoCircuitUntil) : null);
    const openvinoUnsupportedOps = $derived(classifierStatus?.openvino_model_compile_unsupported_ops || []);
    const hasOpenvinoOpIncompatibility = $derived(
        (classifierStatus?.openvino_model_compile_ok === false) && openvinoUnsupportedOps.length > 0
    );
    const recommendedFallbackProvider = $derived(
        (classifierStatus?.cuda_available ?? false) ? 'NVIDIA CUDA' : 'CPU'
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

    async function runCompatCheck() {
        cdOpen = true;
        cdRunId += 1;
        compatError = null;
        compatMatrix = null;
        compatRunning = true;
        compatPhase = 'starting';
        compatProgress = null;
        let seenActive = false;
        try {
            const { run_id } = await startModelEvalRun({
                sweep_devices: true,
                compat_only: true,
                sweep_all_models: compatAllModels,
            });
            compatPoll = window.setInterval(async () => {
                if (compatPollInFlight || document.hidden) return;
                compatPollInFlight = true;
                try {
                    const list = await listModelEvalRuns();
                    if (list.active && list.active.run_id === run_id) {
                        seenActive = true;
                        compatPhase = list.active.phase ?? null;
                        compatProgress = list.active.progress ?? null;
                    } else if (seenActive) {
                        clearInterval(compatPoll ?? undefined);
                        compatPoll = null;
                        compatRunning = false;
                        compatPhase = 'complete';
                        try {
                            const matrix = await getModelEvalDeviceMatrix(run_id);
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
                            compatMatrix = null;
                            compatError = error instanceof Error && error.message.trim()
                                ? error.message
                                : $_('settings.detection.compat_results_unavailable', {
                                    default: 'Compatibility results could not be loaded. Please retry.'
                                });
                            cdRunId += 1;
                        }
                    }
                } catch {
                    /* transient — keep polling */
                } finally {
                    compatPollInFlight = false;
                }
            }, 2000);
        } catch (e) {
            compatRunning = false;
            compatError = (e as Error).message;
        }
    }

    function compatDeviceCell(row: DeviceMatrix['models'][string] | undefined, dev: string): { label: string; cls: string } {
        if (!row || row.error) return { label: '—', cls: 'text-slate-400' };
        const e = row.devices?.[dev];
        if (!e) return { label: '—', cls: 'text-slate-400' };
        if (!e.compiles) return { label: '✗ fails', cls: 'text-red-600 dark:text-red-400' };
        if (e.finite === false) return { label: '⚠ NaN', cls: 'text-red-600 dark:text-red-400' };
        if (dev === 'CPU') return { label: '✓ baseline', cls: 'text-slate-500' };
        const n = e.images_compared;
        if (e.matches_cpu && n) return { label: `✓ ${n}/${n}`, cls: 'text-accent-600 dark:text-accent-400' };
        if (typeof e.top1_match_rate === 'number' && n) {
            return { label: `⚠ ${Math.round(e.top1_match_rate * n)}/${n}`, cls: 'text-amber-600 dark:text-amber-400' };
        }
        return { label: '✓ runs', cls: 'text-accent-600 dark:text-accent-400' };
    }

    // Present the compatibility run through the shared DiagnosticDialog: one stage
    // per device, aggregated from the matrix. `warning` is honest for a device that
    // runs but whose results differ from the CPU baseline.
    let cdOpen = $state(false);
    let cdRunId = $state(0);

    type CompatRow = DeviceMatrix['models'][string];

    function compatCellOutcome(row: CompatRow | undefined, dev: string): { state: DiagnosticStageState; note: string } {
        if (!row || row.error) return { state: 'skipped', note: '—' };
        const e = row.devices?.[dev];
        if (!e) return { state: 'skipped', note: '—' };
        if (!e.compiles) return { state: 'failed', note: $_('settings.detection.compat_note_fails', { default: 'fails to compile' }) };
        if (e.finite === false) return { state: 'failed', note: $_('settings.detection.compat_note_nan', { default: 'non-finite output' }) };
        if (dev === 'CPU') return { state: 'passed', note: $_('settings.detection.compat_note_baseline', { default: 'CPU baseline' }) };
        const n = e.images_compared;
        if (e.matches_cpu && n) return { state: 'passed', note: $_('settings.detection.compat_note_match', { default: '{n}/{n} match CPU', values: { n } }) };
        if (typeof e.top1_match_rate === 'number' && n) {
            return { state: 'warning', note: $_('settings.detection.compat_note_partial', { default: '{m}/{n} match CPU', values: { m: Math.round(e.top1_match_rate * n), n } }) };
        }
        return { state: 'passed', note: $_('settings.detection.compat_note_runs', { default: 'runs' }) };
    }

    const compatStateRank: Record<DiagnosticStageState, number> = { pending: 0, running: 0, skipped: 1, passed: 2, warning: 3, failed: 4 };

    function compatDeviceStage(matrix: DeviceMatrix, dev: string): DiagnosticStage {
        let state: DiagnosticStageState = 'skipped';
        const parts: string[] = [];
        for (const [mid, row] of Object.entries(matrix.models)) {
            const outcome = compatCellOutcome(row, dev);
            if (compatStateRank[outcome.state] > compatStateRank[state]) state = outcome.state;
            parts.push(`${mid}: ${outcome.note}`);
        }
        return { id: dev, label: dev, state, message: parts.join(' · ') };
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
        return matrix.devices.map((dev) => compatDeviceStage(matrix, dev));
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
                ? $_('settings.detection.compat_result_failed', { default: 'Some devices failed validation — see the breakdown below.' })
                : skipped
                    ? $_('settings.detection.compat_result_skipped', { default: 'Some devices could not be validated — see the breakdown below.' })
                    : warned
                        ? $_('settings.detection.compat_result_warn', { default: 'All devices run, but some differ from the CPU baseline.' })
                        : $_('settings.detection.compat_result_ok', { default: 'All devices match the CPU baseline.' })
        };
    });

    onDestroy(() => {
        if (compatPoll) clearInterval(compatPoll);
    });

    let blockedSpeciesSearchQuery = $state('');
    let blockedSpeciesSearchResults = $state<SearchResult[]>([]);
    let blockedSpeciesSearching = $state(false);
    let blockedSpeciesSearchError = $state<string | null>(null);
    let blockedSpeciesSearchTimeout: ReturnType<typeof setTimeout> | undefined;

    $effect(() => {
        const query = blockedSpeciesSearchQuery.trim();
        clearTimeout(blockedSpeciesSearchTimeout);

        if (!query) {
            blockedSpeciesSearchResults = [];
            blockedSpeciesSearchError = null;
            blockedSpeciesSearching = false;
            return;
        }

        blockedSpeciesSearchTimeout = setTimeout(async () => {
            blockedSpeciesSearching = true;
            blockedSpeciesSearchError = null;
            try {
                const searchOptions = getManualTagSearchOptions(query);
                blockedSpeciesSearchResults = await searchSpecies(
                    query,
                    searchOptions.limit,
                    searchOptions.hydrateMissing
                );
            } catch (error) {
                console.error('Blocked species search failed', error);
                blockedSpeciesSearchResults = [];
                blockedSpeciesSearchError = $_('common.error');
            } finally {
                blockedSpeciesSearching = false;
            }
        }, 300);
    });

    onDestroy(() => {
        if (blockedSpeciesSearchTimeout) {
            clearTimeout(blockedSpeciesSearchTimeout);
            blockedSpeciesSearchTimeout = undefined;
        }
    });

    function normalizeEntryText(value: string | null | undefined): string | null {
        const text = String(value || '').trim();
        return text || null;
    }

    function blockedSpeciesKey(entry: BlockedSpeciesEntry): string | null {
        if (entry.taxa_id != null) return `taxa:${entry.taxa_id}`;
        const scientific = normalizeEntryText(entry.scientific_name);
        if (scientific) return `scientific:${scientific.toLocaleLowerCase()}`;
        const common = normalizeEntryText(entry.common_name);
        if (common) return `common:${common.toLocaleLowerCase()}`;
        return null;
    }

    function sameBlockedSpeciesEntry(a: BlockedSpeciesEntry, b: BlockedSpeciesEntry): boolean {
        const keyA = blockedSpeciesKey(a);
        const keyB = blockedSpeciesKey(b);
        return Boolean(keyA && keyB && keyA === keyB);
    }

    function getResultNames(result: SearchResult) {
        const common = result.common_name?.trim() || null;
        const scientific = result.scientific_name?.trim() || null;
        const fallback = result.display_name || result.id;
        if (common && scientific && common !== scientific) {
            return { primary: common, secondary: scientific };
        }
        return { primary: common || scientific || fallback, secondary: null };
    }

    function isSearchResultAlreadyBlocked(result: SearchResult): boolean {
        const entry = buildBlockedSpeciesEntry(result);
        if (!entry) return false;
        return blockedSpecies.some((existingEntry) => sameBlockedSpeciesEntry(existingEntry, entry));
    }

    function addBlockedSpecies(result: SearchResult) {
        const entry = buildBlockedSpeciesEntry(result);
        if (!entry) return;
        blockedSpecies = mergeBlockedSpeciesEntries([...blockedSpecies, entry]);
        blockedSpeciesSearchQuery = '';
        blockedSpeciesSearchResults = [];
        blockedSpeciesSearchError = null;
    }

    function removeBlockedSpecies(entryToRemove: BlockedSpeciesEntry) {
        blockedSpecies = blockedSpecies.filter((entry) => !sameBlockedSpeciesEntry(entry, entryToRemove));
    }

    function removeLegacyBlockedLabel(labelToRemove: string) {
        blockedLabels = blockedLabels.filter((label) => label !== labelToRemove);
    }
</script>

<div class="space-y-6">
    {#snippet engineIcon()}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v3m0 12v3M3 12h3m12 0h3M7.05 7.05l2.12 2.12m5.66 5.66 2.12 2.12m0-9.9-2.12 2.12m-5.66 5.66-2.12 2.12M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" /></svg>
    {/snippet}
    {#snippet blockedIcon()}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="m5.6 5.6 12.8 12.8" /></svg>
    {/snippet}

    <SettingsCard
        accent
        iconSnippet={engineIcon}
        title={$_('settings.detection.classification_engine')}
        description={$_('settings.detection.classification_engine_desc', { default: 'How feeder snapshots are classified — confidence, model, and hardware acceleration.' })}
    >
        {#if classifierStatus?.active_model_id}
            <div class="flex flex-col gap-1 border-b border-slate-200 pb-4 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between sm:gap-4" role="status">
                <span class="text-xs font-bold text-slate-500 dark:text-slate-400">
                    {$_('settings.detection.model_manager_active', { default: 'Active model' })}
                </span>
                <code class="break-all text-sm font-bold text-slate-800 dark:text-slate-100">{classifierStatus.active_model_id}</code>
            </div>
        {/if}

        <SettingsRow
            labelId="setting-confidence-threshold"
            label={$_('settings.detection.confidence_threshold')}
            layout="stacked"
        >
            <div class="space-y-2">
                <div class="flex justify-end">
                    <output for="confidence-threshold-slider" class="rounded-lg bg-brand-500 px-2 py-1 text-xs font-black text-white">{(threshold * 100).toFixed(0)}%</output>
                </div>
                <input
                    id="confidence-threshold-slider"
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    bind:value={threshold}
                    aria-valuemin="0"
                    aria-valuemax="100"
                    aria-valuenow={Math.round(threshold * 100)}
                    aria-valuetext="{(threshold * 100).toFixed(0)} percent"
                    aria-label="{$_('settings.detection.confidence_threshold')}: {(threshold * 100).toFixed(0)}%"
                    class="h-11 w-full cursor-pointer accent-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
                />
                <div class="flex justify-between gap-4">
                    <span class="text-xs font-bold text-slate-500 dark:text-slate-400">{$_('settings.detection.threshold_loose')}</span>
                    <span class="text-right text-xs font-bold text-slate-500 dark:text-slate-400">{$_('settings.detection.threshold_strict')}</span>
                </div>
            </div>
        </SettingsRow>

        {#if autoVideoClassification && videoCircuitOpen}
            <div role="alert" class="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-slate-700 dark:text-slate-200">
                <p class="mb-2 text-xs font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                    {$_('settings.video_circuit.title')}
                </p>
                <p class="text-sm font-bold leading-relaxed">{$_('settings.video_circuit.message', { values: { failures: videoCircuitFailures } })}</p>
                {#if circuitUntil}
                    <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('settings.video_circuit.until', { values: { time: circuitUntil } })}</p>
                {/if}
            </div>
        {/if}

        {#if classifierStatus?.fallback_reason || classifierStatus?.model_config_warnings?.length || classifierStatus?.openvino_model_compile_ok === false}
            <div role="alert" class="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm font-bold text-amber-800 dark:text-amber-200">
                {#if classifierStatus.fallback_reason}
                    {$_('settings.detection.provider_fallback_reason', { default: 'Fallback:' })} {classifierStatus.fallback_reason}
                {:else if classifierStatus.model_config_warnings?.length}
                    {$_('settings.detection.model_config_warning', { default: 'Model config warning:' })} {classifierStatus.model_config_warnings[0]}
                {:else}
                    {$_('settings.detection.openvino_compile_failure', { default: 'OpenVINO model incompatibility on this host' })}
                {/if}
            </div>
        {/if}

        <AdvancedSection
            id="detection-classification-advanced"
            title={$_('settings.detection.model_manager_title', { default: 'Model Manager' })}
        >
            <ModelManager />

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
        </AdvancedSection>

        <AdvancedSection
            id="detection-fine-tuning-advanced"
            title={$_('settings.detection.fine_tuning_advanced_title', { default: 'Advanced fine tuning' })}
        >
            <SettingsRow
                labelId="setting-min-confidence"
                label={$_('settings.detection.min_confidence_floor')}
                description={$_('settings.detection.floor_help')}
                layout="stacked"
            >
                <div class="space-y-2">
                    <div class="flex justify-end">
                        <output for="min-confidence-slider" class="rounded-lg bg-amber-500 px-2 py-1 text-xs font-black text-white">{(minConfidence * 100).toFixed(0)}%</output>
                    </div>
                    <input
                        id="min-confidence-slider"
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        bind:value={minConfidence}
                        aria-valuemin="0"
                        aria-valuemax="100"
                        aria-valuenow={Math.round(minConfidence * 100)}
                        aria-valuetext="{(minConfidence * 100).toFixed(0)} percent"
                        aria-label="{$_('settings.detection.min_confidence_floor')}: {(minConfidence * 100).toFixed(0)}%"
                        class="h-11 w-full cursor-pointer accent-amber-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
                    />
                    <div class="flex justify-between gap-4">
                        <span class="text-xs font-bold text-slate-500 dark:text-slate-400">{$_('settings.detection.floor_capture_all')}</span>
                        <span class="text-right text-xs font-bold text-slate-500 dark:text-slate-400">{$_('settings.detection.floor_reject_unsure')}</span>
                    </div>
                </div>
            </SettingsRow>

            <SettingsRow
                labelId="setting-personalized-rerank"
                label={$_('settings.detection.personalized_rerank', { default: 'Personalized re-ranking' })}
                description={$_('settings.detection.personalized_rerank_desc', { default: 'Use manual tags to adapt ranking per camera and model. Disable to use base model scores only.' })}
            >
                <SettingsToggle
                    checked={personalizedRerankEnabled}
                    labelledBy="setting-personalized-rerank"
                    srLabel={$_('settings.detection.personalized_rerank', { default: 'Personalized re-ranking' })}
                    onchange={(v) => (personalizedRerankEnabled = v)}
                />
            </SettingsRow>

            <SettingsRow
                labelId="setting-auto-video"
                label={$_('settings.detection.auto_video')}
                description={$_('settings.detection.auto_video_desc')}
            >
                <SettingsToggle
                    checked={autoVideoClassification}
                    labelledBy="setting-auto-video"
                    srLabel={$_('settings.detection.auto_video')}
                    onchange={(v) => (autoVideoClassification = v)}
                />
            </SettingsRow>

                <SettingsRow
                    labelId="setting-trust-frigate"
                    label={$_('settings.detection.trust_frigate')}
                    description={$_('settings.detection.trust_frigate_desc')}
                >
                    <SettingsToggle
                        checked={trustFrigateSublabel}
                        labelledBy="setting-trust-frigate"
                        srLabel={$_('settings.detection.trust_frigate')}
                        onchange={(v) => (trustFrigateSublabel = v)}
                    />
                </SettingsRow>

                <SettingsRow
                    labelId="setting-write-frigate"
                    label={$_('settings.detection.write_frigate_sublabel')}
                    description={$_('settings.detection.write_frigate_sublabel_desc')}
                >
                    <SettingsToggle
                        checked={writeFrigateSublabel}
                        labelledBy="setting-write-frigate"
                        srLabel={$_('settings.detection.write_frigate_sublabel')}
                        onchange={(v) => (writeFrigateSublabel = v)}
                    />
                </SettingsRow>

                {#if autoVideoClassification}
                    <div class="pt-2 border-t border-dashed border-slate-200/70 dark:border-slate-700/60">
                        <p class="mb-3 text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-400">
                            {$_('settings.detection.auto_video_advanced_title', { default: 'Auto-video tuning' })}
                        </p>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <SettingsRow
                                labelId="setting-video-delay"
                                label={$_('settings.detection.video_delay')}
                                layout="stacked"
                            >
                                <SettingsInput
                                    id="video-delay"
                                    type="number"
                                    min={0}
                                    value={videoClassificationDelay}
                                    ariaLabel={$_('settings.detection.video_delay')}
                                    oninput={(v) => (videoClassificationDelay = Number(v) || 0)}
                                />
                            </SettingsRow>
                            <SettingsRow
                                labelId="setting-video-retries"
                                label={$_('settings.detection.video_retries')}
                                layout="stacked"
                            >
                                <SettingsInput
                                    id="video-retries"
                                    type="number"
                                    min={0}
                                    value={videoClassificationMaxRetries}
                                    ariaLabel={$_('settings.detection.video_retries')}
                                    oninput={(v) => (videoClassificationMaxRetries = Number(v) || 0)}
                                />
                            </SettingsRow>
                            <SettingsRow
                                labelId="setting-video-max-concurrent"
                                label={$_('settings.detection.video_max_concurrent', { default: 'Video Concurrency' })}
                                layout="stacked"
                            >
                                <SettingsInput
                                    id="video-max-concurrent"
                                    type="number"
                                    min={1}
                                    max={20}
                                    value={videoClassificationMaxConcurrent}
                                    ariaLabel={$_('settings.detection.video_max_concurrent_label', { default: 'Max Concurrent Video Jobs' })}
                                    oninput={(v) => (videoClassificationMaxConcurrent = Number(v) || 1)}
                                />
                            </SettingsRow>
                            <SettingsRow
                                labelId="setting-video-frames"
                                label={$_('settings.detection.video_frames', { default: 'Frames' })}
                                layout="stacked"
                            >
                                <SettingsInput
                                    id="video-frames"
                                    type="number"
                                    min={5}
                                    max={100}
                                    value={videoClassificationFrames}
                                    ariaLabel={$_('settings.detection.video_frames', { default: 'Video Frames' })}
                                    oninput={(v) => (videoClassificationFrames = Number(v) || 5)}
                                />
                            </SettingsRow>
                        </div>
                        <p class="mt-2 text-xs italic text-slate-500 dark:text-slate-400">{$_('settings.detection.video_retry_note')}</p>
                        <p class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                            {#if imageExecutionMode === 'in_process'}
                                {$_('settings.detection.video_concurrency_best_practice_in_process', { default: 'In-Process mode shares one backend runtime. Best practice is to keep video concurrency at 1 unless you have verified your model runtime stays stable under overlap.' })}
                            {:else}
                                {$_('settings.detection.video_concurrency_best_practice_subprocess', { default: 'Subprocess mode isolates classifier workers more strongly, but raising video concurrency still increases CPU, RAM, and GPU pressure.' })}
                            {/if}
                        </p>
                    </div>
                {/if}
        </AdvancedSection>

        <AdvancedSection
            id="detection-inference-advanced"
            title={$_('settings.detection.inference_advanced_title', { default: 'Execution mode & runtime diagnostics' })}
        >
            <SettingsRow
                labelId="setting-inference-provider"
                label={$_('settings.detection.inference_provider', { default: 'Inference Provider' })}
                description={$_('settings.detection.inference_provider_desc', { default: 'Select CPU, NVIDIA CUDA, or Intel OpenVINO acceleration for ONNX models. Auto prefers Intel GPU, then CUDA, then CPU.' })}
                layout="stacked"
            >
                <SettingsSelect
                    id="inference-provider"
                    value={inferenceProvider}
                    ariaLabel={$_('settings.detection.inference_provider', { default: 'Inference Provider' })}
                    options={[
                        { value: 'auto', label: $_('settings.detection.provider_auto', { default: 'Auto' }) },
                        { value: 'cpu', label: $_('settings.detection.provider_cpu', { default: 'CPU (ONNX Runtime)' }) },
                        { value: 'cuda', label: $_('settings.detection.provider_cuda', { default: 'NVIDIA CUDA' }) },
                        { value: 'intel_gpu', label: $_('settings.detection.provider_intel_gpu', { default: 'Intel GPU (OpenVINO)' }) },
                        { value: 'intel_cpu', label: $_('settings.detection.provider_intel_cpu', { default: 'Intel CPU (OpenVINO)' }) },
                        { value: 'intel_npu', label: $_('settings.detection.provider_intel_npu', { default: 'Intel NPU (OpenVINO)' }) }
                    ]}
                    onchange={(v) => (inferenceProvider = v as 'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu' | 'intel_npu')}
                />
            </SettingsRow>

            <a
                href={GPU_DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                class="group flex items-center justify-between gap-3 rounded-2xl border border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-900/50 px-4 py-3 hover:border-brand-500/40 transition-colors"
            >
                <div class="min-w-0">
                    <p class="text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-400">{$_('common.github', { default: 'GitHub' })}</p>
                    <p class="text-xs font-bold text-slate-700 dark:text-slate-200 leading-tight">{$_('settings.detection.gpu_setup_docs', { default: 'GPU setup & diagnostics guide' })}</p>
                </div>
                <span class="inline-flex shrink-0 items-center gap-1 text-xs font-black uppercase tracking-wide text-brand-700 dark:text-brand-300">
                    <span>{$_('common.show', { default: 'Show' })}</span>
                    <svg class="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h4m0 0v4m0-4L10 14" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 9v10h10" />
                    </svg>
                </span>
            </a>

                <SettingsRow
                    labelId="setting-execution-mode"
                    label={$_('settings.detection.execution_mode', { default: 'Execution Mode' })}
                    description={$_('settings.detection.execution_mode_desc', { default: 'In-Process uses much less RAM by sharing model weights, especially with larger models. Subprocess provides stronger isolation and stability, but uses significantly more memory.' })}
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
                </SettingsRow>

            {#if classifierStatus}
                <div class="pt-2 border-t border-dashed border-slate-200/70 dark:border-slate-700/60 space-y-3">
                    <p class="text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        {$_('settings.detection.inference_diagnostics_title', { default: 'Runtime diagnostics' })}
                    </p>
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-black {(classifierStatus.cuda_available ?? false) ? 'bg-accent-500/10 text-accent-700 dark:text-accent-300' : ((classifierStatus.cuda_provider_installed ?? false) ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300' : 'bg-slate-500/10 text-slate-600 dark:text-slate-400')}">
                            {#if classifierStatus.cuda_available}
                                {$_('settings.detection.cuda_available')}
                            {:else if (classifierStatus.cuda_provider_installed ?? false) && !(classifierStatus.cuda_hardware_available ?? false)}
                                {$_('settings.detection.cuda_runtime_only', { default: 'CUDA runtime installed (no NVIDIA GPU detected)' })}
                            {:else}
                                {$_('settings.detection.cuda_unavailable')}
                            {/if}
                        </span>
                        <span class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-black {(classifierStatus.openvino_available ?? false) ? 'bg-accent-500/10 text-accent-700 dark:text-accent-300' : 'bg-slate-500/10 text-slate-600 dark:text-slate-400'}">
                            {$_('settings.detection.openvino_status', { default: 'OpenVINO' })}: {(classifierStatus.openvino_available ?? false) ? $_('common.available', { default: 'Available' }) : $_('common.unavailable', { default: 'Unavailable' })}
                        </span>
                        <span class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-black {(classifierStatus.intel_gpu_available ?? false) ? 'bg-accent-500/10 text-accent-700 dark:text-accent-300' : 'bg-slate-500/10 text-slate-600 dark:text-slate-400'}">
                            {$_('settings.detection.intel_gpu_status', { default: 'Intel GPU' })}: {(classifierStatus.intel_gpu_available ?? false) ? ($_('settings.detection.auto_detected', { default: 'Auto-detected' }) + (providerVerified('intel_gpu') ? ' · verified ✓' : ' · unverified')) : $_('common.not_available', { default: 'Not detected' })}
                        </span>
                        <span class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-black {(classifierStatus.intel_npu_available ?? false) ? 'bg-accent-500/10 text-accent-700 dark:text-accent-300' : 'bg-slate-500/10 text-slate-600 dark:text-slate-400'}">
                            {$_('settings.detection.intel_npu_status', { default: 'Intel NPU' })}: {(classifierStatus.intel_npu_available ?? false) ? ($_('settings.detection.auto_detected', { default: 'Auto-detected' }) + (providerVerified('intel_npu') ? ' · verified ✓' : ' · unverified')) : $_('common.not_available', { default: 'Not detected' })}
                        </span>
                    </div>

                    <div class="flex flex-wrap items-center gap-2 text-xs font-bold text-slate-600 dark:text-slate-400">
                        <span>{$_('settings.detection.selected_provider_label', { default: 'Selected' })}: {classifierStatus.selected_provider ?? inferenceProvider}</span>
                        <span>{$_('settings.detection.active_provider_label', { default: 'Active' })}: {classifierStatus.active_provider ?? 'unknown'}</span>
                        {#if classifierStatus.inference_backend}
                            <span>{$_('settings.detection.inference_backend_label', { default: 'Backend' })}: {classifierStatus.inference_backend}</span>
                        {/if}
                    </div>
                    <p class="text-xs font-bold text-slate-600 dark:text-slate-400">
                        {$_('settings.detection.personalization_status_label', { default: 'Personalization' })}:
                        {(classifierStatus.personalized_rerank_enabled ?? false) ? $_('common.enabled', { default: 'Enabled' }) : $_('common.disabled', { default: 'Disabled' })}
                        · {$_('settings.detection.personalization_active_pairs', { default: 'Active camera/model pairs' })}: {classifierStatus.personalization_active_camera_models ?? 0}
                        · {$_('settings.detection.personalization_feedback_rows', { default: 'Feedback tags' })}: {classifierStatus.personalization_feedback_rows ?? 0}
                        ({$_('settings.detection.personalization_min_tags', { default: 'min' })} {classifierStatus.personalization_min_feedback_tags ?? 20})
                    </p>
                    {#if classifierStatus.fallback_reason}
                        <p class="text-xs font-bold text-amber-700 dark:text-amber-300">{$_('settings.detection.provider_fallback_reason', { default: 'Fallback:' })} {classifierStatus.fallback_reason}</p>
                    {/if}
                    {#if classifierStatus.model_config_warnings?.length}
                        {#each classifierStatus.model_config_warnings as modelConfigWarning}
                            <p class="text-xs font-bold text-amber-700 dark:text-amber-300">{$_('settings.detection.model_config_warning', { default: 'Model config warning:' })} {modelConfigWarning}</p>
                        {/each}
                    {/if}
                    {#if classifierStatus.cuda_probe_error}
                        <div class="rounded-2xl border border-amber-200/80 dark:border-amber-700/40 bg-amber-50/80 dark:bg-amber-950/20 p-3">
                            <div class="text-xs font-black uppercase tracking-wide text-amber-700 dark:text-amber-300">CUDA diagnostics</div>
                            <div class="mt-2 space-y-1 break-all text-xs font-medium text-amber-900 dark:text-amber-100">
                                <p><span class="font-black">NVIDIA GPU:</span> {(classifierStatus.cuda_hardware_available ?? false) ? 'detected' : 'not detected'}</p>
                                <p><span class="font-black">{$_('settings.detection.probe_error', { default: 'Probe error:' })}</span> {classifierStatus.cuda_probe_error}</p>
                            </div>
                        </div>
                    {/if}
                    {#if classifierStatus.openvino_model_compile_ok === false}
                        <div class="rounded-2xl border border-amber-200/80 dark:border-amber-700/40 bg-amber-50/80 dark:bg-amber-950/20 p-3 space-y-2">
                            <p class="text-xs font-black uppercase tracking-wide text-amber-700 dark:text-amber-300">{$_('settings.detection.openvino_compile_failure', { default: 'OpenVINO model incompatibility on this host' })}</p>
                            <p class="break-all text-xs font-medium text-amber-900 dark:text-amber-100">
                                {$_('settings.detection.openvino_compile_failure_detail', { default: 'Active model' })}: <code>{classifierStatus.active_model_id || 'unknown'}</code>
                                {#if classifierStatus.openvino_model_compile_device}({classifierStatus.openvino_model_compile_device}){/if}
                            </p>
                            <p class="text-xs font-medium text-amber-900 dark:text-amber-100">
                                Automatic fallback is active: <code>{classifierStatus.inference_backend || 'unknown'}</code> / <code>{classifierStatus.active_provider || 'unknown'}</code>
                            </p>
                            {#if hasOpenvinoOpIncompatibility}
                                <p class="text-xs font-medium text-amber-900 dark:text-amber-100">OpenVINO reported unsupported ONNX operators for this model/runtime:</p>
                                <div class="flex flex-wrap gap-1">
                                    {#each openvinoUnsupportedOps as op}
                                        <span class="inline-flex items-center rounded-md border border-amber-300/70 bg-amber-100 px-2 py-0.5 text-xs font-black text-amber-800 dark:border-amber-700/60 dark:bg-amber-900/40 dark:text-amber-200">{op}</span>
                                    {/each}
                                </div>
                            {/if}
                            <p class="text-xs font-medium text-amber-900 dark:text-amber-100">
                                Next steps: switch to <code>eva02_large_inat21</code> for OpenVINO, or keep this model and set provider to <code>{recommendedFallbackProvider}</code>.
                            </p>
                            {#if classifierStatus.openvino_model_compile_error}
                                <details class="pt-1">
                                    <summary class="min-h-11 cursor-pointer py-3 text-xs font-black uppercase tracking-wide text-amber-700 dark:text-amber-300">Technical details</summary>
                                    <p class="mt-1 break-all text-xs font-medium text-amber-900 dark:text-amber-100">{classifierStatus.openvino_model_compile_error}</p>
                                </details>
                            {/if}
                        </div>
                    {/if}
                    {#if ((classifierStatus.openvino_available === false) || classifierStatus.openvino_gpu_probe_error) && (classifierStatus.openvino_import_error || classifierStatus.openvino_probe_error || classifierStatus.openvino_gpu_probe_error || classifierStatus.dev_dri_present !== undefined)}
                        <div class="rounded-2xl border border-amber-200/80 dark:border-amber-700/40 bg-amber-50/80 dark:bg-amber-950/20 p-3">
                            <div class="text-xs font-black uppercase tracking-wide text-amber-700 dark:text-amber-300">{$_('settings.detection.openvino_diagnostics', { default: 'OpenVINO diagnostics' })}</div>
                            <div class="mt-2 space-y-1 break-all text-xs font-medium text-amber-900 dark:text-amber-100">
                                {#if classifierStatus.openvino_version}<p><span class="font-black">Version:</span> {classifierStatus.openvino_version}</p>{/if}
                                {#if classifierStatus.openvino_import_path}<p><span class="font-black">Import:</span> <code>{classifierStatus.openvino_import_path}</code></p>{/if}
                                <p><span class="font-black">/dev/dri:</span> {classifierStatus.dev_dri_present ? 'present' : 'missing'}{#if classifierStatus.dev_dri_entries?.length} (<code>{classifierStatus.dev_dri_entries.join(', ')}</code>){/if}</p>
                                {#if classifierStatus.process_uid != null}
                                    <p><span class="font-black">UID/GID:</span> {classifierStatus.process_uid}:{classifierStatus.process_gid}{#if classifierStatus.process_groups?.length} groups <code>{classifierStatus.process_groups.join(', ')}</code>{/if}</p>
                                {/if}
                                {#if classifierStatus.openvino_import_error}<p><span class="font-black">{$_('settings.detection.import_error', { default: 'Import error:' })}</span> {classifierStatus.openvino_import_error}</p>{/if}
                                {#if classifierStatus.openvino_probe_error}<p><span class="font-black">{$_('settings.detection.probe_error', { default: 'Probe error:' })}</span> {classifierStatus.openvino_probe_error}</p>{/if}
                                {#if classifierStatus.openvino_gpu_probe_error}<p><span class="font-black">{$_('settings.detection.gpu_plugin_error', { default: 'GPU plugin error:' })}</span> {classifierStatus.openvino_gpu_probe_error}</p>{/if}
                            </div>
                        </div>
                    {/if}
                </div>
            {/if}
            {#if classifierStatus && ((classifierStatus.intel_gpu_available ?? false) || (classifierStatus.intel_npu_available ?? false))}
                <div class="border-t border-slate-200 pt-4 dark:border-slate-700">
                    <h4 class="text-sm font-black text-slate-900 dark:text-white">
                        {$_('settings.detection.compat_card_title', { default: 'Device compatibility' })}
                    </h4>
            <div class="space-y-3">
                <div class="flex items-start justify-between gap-3 flex-wrap">
                    <p class="text-xs text-slate-600 dark:text-slate-400 leading-snug max-w-md">
                        {#if verifiedProviders.length}
                            {$_('settings.detection.compat_verified', { default: 'Verified on this host:' })} <span class="font-bold">{verifiedProviders.join(', ')}</span>{#if classifierStatus.host_device_eligibility?.generated_at} · {formatDateTime(classifierStatus.host_device_eligibility.generated_at)}{/if}
                        {:else}
                            {$_('settings.detection.compat_unverified', { default: 'Not yet run on this host — iGPU/NPU are only used for models verified here. Run the check to enable them.' })}
                        {/if}
                    </p>
                    <div class="flex items-center gap-2 shrink-0">
                        <label class="inline-flex min-h-11 cursor-pointer items-center gap-2 text-xs font-bold text-slate-600 dark:text-slate-400" title={$_('settings.detection.compat_all_hint', { default: 'Download and test every registry model, not just installed ones (slower).' })}>
                            <input type="checkbox" bind:checked={compatAllModels} disabled={compatRunning} class="rounded" />
                            {$_('settings.detection.compat_all_models', { default: 'test all models' })}
                        </label>
                        <button type="button" onclick={runCompatCheck} disabled={compatRunning}
                            class="min-h-11 cursor-pointer rounded-xl bg-brand-600 px-4 py-2 text-xs font-bold text-white hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-400 dark:focus-visible:ring-offset-slate-950 dark:disabled:bg-slate-700">
                            {compatRunning ? $_('settings.detection.compat_running', { default: 'Running…' }) : $_('settings.detection.compat_run', { default: 'Run compatibility check' })}
                        </button>
                    </div>
                </div>
                {#if compatError}<p role="alert" class="text-xs font-bold text-red-600 dark:text-red-400">{compatError}</p>{/if}
                {#if compatRunning && compatProgress}
                    <p role="status" class="text-xs text-slate-600 dark:text-slate-400">{compatPhase}: {compatProgress.done}/{compatProgress.total} {compatProgress.label}</p>
                {/if}
                {#if compatMatrix}
                    <div class="overflow-x-auto">
                        <table class="w-full text-xs">
                            <thead class="border-b border-slate-200 text-xs uppercase text-slate-600 dark:border-slate-700 dark:text-slate-400">
                                <tr><th class="text-left py-1 pr-3">{$_('settings.detection.compat_model', { default: 'Model' })}</th>{#each compatMatrix.devices as dev}<th class="text-left px-2">{dev}</th>{/each}</tr>
                            </thead>
                            <tbody>
                                {#each Object.entries(compatMatrix.models) as [mid, row]}
                                    <tr class="border-b border-slate-100 dark:border-slate-800">
                                        <td class="py-1 pr-3 font-medium text-slate-700 dark:text-slate-300">{mid}</td>
                                        {#each compatMatrix.devices as dev}
                                            {@const c = compatDeviceCell(row, dev)}
                                            <td class="px-2 {c.cls}">{c.label}</td>
                                        {/each}
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
                {/if}
            </div>
                </div>
            {/if}
        </AdvancedSection>
    </SettingsCard>

    <SettingsCard accent iconSnippet={blockedIcon} title={$_('settings.detection.blocked_labels')}>
        <p class="text-xs font-medium leading-relaxed text-slate-500 dark:text-slate-400">
            {$_('settings.detection.blocked_species_picker_desc', { default: 'Search for a species to block it reliably across common-name, scientific-name, and taxonomy-aware matches. Legacy raw labels still apply until you remove them.' })}
        </p>

        <SettingsInput
            id="blocked-species-search"
            type="text"
            value={blockedSpeciesSearchQuery}
            placeholder={$_('settings.detection.blocked_species_placeholder', { default: 'Search species to block' })}
            ariaLabel={$_('settings.detection.blocked_labels')}
            oninput={(v) => (blockedSpeciesSearchQuery = v)}
        />

        {#if blockedSpeciesSearchQuery.trim()}
            <div class="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700/50 bg-white/60 dark:bg-slate-900/40 shadow-sm">
                <div class="max-h-64 overflow-y-auto p-1">
                    {#each blockedSpeciesSearchResults as result}
                        {@const names = getResultNames(result)}
                        {@const alreadyBlocked = isSearchResultAlreadyBlocked(result)}
                        <button
                            type="button"
                            onclick={() => addBlockedSpecies(result)}
                            disabled={alreadyBlocked}
                            class="min-h-11 w-full cursor-pointer rounded-xl px-4 py-2.5 text-left text-sm font-medium transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-default disabled:opacity-60 dark:hover:bg-red-950/20 dark:hover:text-red-300 {alreadyBlocked ? 'bg-red-500/10 text-red-600 dark:text-red-300' : 'text-slate-700 dark:text-slate-200'}"
                        >
                            <span class="block">
                                {names.primary}
                                {#if alreadyBlocked}
                                    <span class="ml-2 inline-flex items-center rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-black uppercase tracking-wide text-red-600 dark:text-red-300">
                                        {$_('common.added', { default: 'Added' })}
                                    </span>
                                {/if}
                            </span>
                            {#if names.secondary}
                                <span class="block text-xs italic text-slate-500 dark:text-slate-400">{names.secondary}</span>
                            {/if}
                        </button>
                    {/each}
                    {#if blockedSpeciesSearchError}
                        <p role="alert" class="px-4 py-4 text-sm font-medium text-red-600 dark:text-red-400">{blockedSpeciesSearchError}</p>
                    {:else if blockedSpeciesSearchResults.length === 0}
                        <p role="status" class="px-4 py-4 text-sm italic text-slate-500 dark:text-slate-400">
                            {blockedSpeciesSearching ? $_('common.loading') : $_('settings.detection.no_blocked_species_results', { default: 'No matching species found.' })}
                        </p>
                    {/if}
                </div>
            </div>
        {/if}

        {#if blockedSpecies.length > 0}
            <div>
                <p class="mb-3 text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-400">{$_('settings.detection.blocked_species_structured', { default: 'Blocked species' })}</p>
                <div class="flex flex-wrap gap-2">
                    {#each blockedSpecies as entry}
                        <span class="group flex min-h-11 items-center gap-2 rounded-xl border border-red-200 bg-red-50 pl-3 text-xs font-bold text-red-700 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-200">
                            {formatBlockedSpeciesLabel(entry)}
                            <button
                                type="button"
                                onclick={() => removeBlockedSpecies(entry)}
                                aria-label={$_('settings.detection.blocked_label_remove', { values: { label: formatBlockedSpeciesLabel(entry) } })}
                                class="inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl text-red-500 transition-colors hover:bg-red-100 hover:text-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 dark:hover:bg-red-900/40 dark:hover:text-red-100"
                            >
                                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                                    <path d="M6 6l12 12M18 6 6 18" />
                                </svg>
                            </button>
                        </span>
                    {/each}
                </div>
            </div>
        {/if}

        {#if blockedLabels.length > 0}
            <div>
                <p class="mb-3 text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-400">{$_('settings.detection.blocked_species_legacy', { default: 'Legacy raw labels' })}</p>
                <div class="flex flex-wrap gap-2">
                    {#each blockedLabels as label}
                        <span class="group flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white pl-3 text-xs font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            {label}
                            <span class="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-black uppercase tracking-wide text-amber-700 dark:text-amber-300">{$_('common.legacy', { default: 'Legacy' })}</span>
                            <button
                                type="button"
                                onclick={() => removeLegacyBlockedLabel(label)}
                                aria-label={$_('settings.detection.blocked_label_remove', { values: { label } })}
                                class="inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 dark:hover:bg-red-950/30 dark:hover:text-red-300"
                            >
                                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                                    <path d="M6 6l12 12M18 6 6 18" />
                                </svg>
                            </button>
                        </span>
                    {/each}
                </div>
            </div>
        {/if}

        {#if blockedSpecies.length === 0 && blockedLabels.length === 0}
            <p class="text-xs font-bold italic text-slate-400">{$_('settings.detection.no_blocked_labels')}</p>
        {/if}
    </SettingsCard>
</div>

{#if cdOpen}
    <DiagnosticDialog
        title={$_('settings.detection.compat_test_title', { default: 'Device compatibility check' })}
        subtitle={$_('settings.detection.compat_test_subtitle', { default: 'Validates each detected device (Intel GPU/NPU, CUDA) against the CPU baseline for the installed model(s).' })}
        stages={compatDialogStages}
        busy={compatRunning}
        result={compatDialogResult}
        runId={cdRunId}
        retryLabel={$_('settings.detection.compat_run', { default: 'Run compatibility check' })}
        onClose={() => (cdOpen = false)}
        onRetry={runCompatCheck}
    />
{/if}

<script lang="ts">
    import { onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { formatDateTime } from '../../utils/datetime';
    import ModelManager from '../../pages/models/ModelManager.svelte';
    import { searchSpecies, type ClassifierStatus, type SearchResult } from '../../api';
    import type { BlockedSpeciesEntry } from '../../api/settings';
    import { getManualTagSearchOptions } from '../../search/manual-tag-search';
    import { BIRD_MODEL_REGION_OVERRIDE_VALUES, type BirdModelRegionOverride } from '../../settings/bird-model-region-override';
    import type { CropModelOverride, CropSourceOverride } from '../../settings/crop-overrides';
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
        birdCropDetectorTier = $bindable<'fast' | 'accurate' | string>('fast'),
        birdCropSourcePriority = $bindable<'frigate_hints_first' | 'crop_model_first' | 'crop_model_only' | 'frigate_hints_only' | string>('frigate_hints_first'),
        birdModelRegionOverride = $bindable<BirdModelRegionOverride>('auto'),
        cropModelOverrides = $bindable<Record<string, CropModelOverride>>({}),
        cropSourceOverrides = $bindable<Record<string, CropSourceOverride>>({}),
        imageExecutionMode = $bindable<'in_process' | 'subprocess' | string>('in_process'),
        inferenceProvider = $bindable<'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu'>('auto'),
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
        birdCropDetectorTier: 'fast' | 'accurate' | string;
        birdCropSourcePriority: 'frigate_hints_first' | 'crop_model_first' | 'crop_model_only' | 'frigate_hints_only' | string;
        birdModelRegionOverride: BirdModelRegionOverride;
        cropModelOverrides: Record<string, CropModelOverride>;
        cropSourceOverrides: Record<string, CropSourceOverride>;
        imageExecutionMode: 'in_process' | 'subprocess' | string;
        inferenceProvider: 'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu';
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

    let blockedSpeciesSearchQuery = $state('');
    let blockedSpeciesSearchResults = $state<SearchResult[]>([]);
    let blockedSpeciesSearching = $state(false);
    let blockedSpeciesSearchError = $state<string | null>(null);
    let blockedSpeciesSearchTimeout: any;

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
            blockedSpeciesSearchTimeout = null;
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
    <SettingsCard icon="🎯" title={$_('settings.detection.classification_engine')}>
        <ModelManager bind:cropModelOverrides bind:cropSourceOverrides />

        <AdvancedSection
            id="detection-classification-advanced"
            title={$_('settings.detection.classification_advanced_title', { default: 'Crop detector & region overrides' })}
        >
            <SettingsRow
                labelId="setting-crop-tier"
                label={$_('settings.detection.crop_tier_title', { default: 'Bird crop detector tier' })}
                description={$_('settings.detection.crop_tier_desc', { default: 'Fast keeps the current SSD detector as the default. Accurate uses the experimental YOLOX-Tiny tier and falls back to fast automatically when it is unavailable.' })}
                layout="stacked"
            >
                <SettingsSelect
                    id="bird-crop-detector-tier"
                    value={birdCropDetectorTier}
                    ariaLabel={$_('settings.detection.crop_tier_title', { default: 'Bird crop detector tier' })}
                    options={[
                        { value: 'fast', label: 'Fast (SSD-MobileNet)' },
                        { value: 'accurate', label: 'Accurate (YOLOX-Tiny, experimental)' }
                    ]}
                    onchange={(v) => (birdCropDetectorTier = v)}
                />
            </SettingsRow>

            <SettingsRow
                labelId="setting-crop-priority"
                label={$_('settings.detection.crop_priority_title', { default: 'Crop source priority' })}
                description={$_('settings.detection.crop_priority_desc', { default: 'Choose whether Frigate hints or the configured crop model are tried first. The selected crop detector tier is always respected whenever the model path is used.' })}
                layout="stacked"
            >
                <SettingsSelect
                    id="bird-crop-source-priority"
                    value={birdCropSourcePriority}
                    ariaLabel={$_('settings.detection.crop_priority_title', { default: 'Crop source priority' })}
                    options={[
                        { value: 'frigate_hints_first', label: $_('settings.detection.crop_priority_frigate_first', { default: 'Frigate hints first' }) },
                        { value: 'crop_model_first', label: $_('settings.detection.crop_priority_crop_first', { default: 'Crop model first' }) },
                        { value: 'crop_model_only', label: $_('settings.detection.crop_priority_crop_only', { default: 'Crop model only' }) },
                        { value: 'frigate_hints_only', label: $_('settings.detection.crop_priority_frigate_only', { default: 'Frigate hints only' }) }
                    ]}
                    onchange={(v) => (birdCropSourcePriority = v)}
                />
            </SettingsRow>

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
    </SettingsCard>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        <SettingsCard icon="🎚️" title={$_('settings.detection.fine_tuning')}>
            <SettingsRow
                labelId="setting-confidence-threshold"
                label={$_('settings.detection.confidence_threshold')}
                layout="stacked"
            >
                <div class="space-y-2">
                    <div class="flex justify-end">
                        <output for="confidence-threshold-slider" class="px-2 py-1 bg-teal-500 text-white text-[10px] font-black rounded-lg">{(threshold * 100).toFixed(0)}%</output>
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
                        class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-teal-500"
                    />
                    <div class="flex justify-between">
                        <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.threshold_loose')}</span>
                        <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.threshold_strict')}</span>
                    </div>
                </div>
            </SettingsRow>

            <SettingsRow
                labelId="setting-min-confidence"
                label={$_('settings.detection.min_confidence_floor')}
                description={$_('settings.detection.floor_help')}
                layout="stacked"
            >
                <div class="space-y-2">
                    <div class="flex justify-end">
                        <output for="min-confidence-slider" class="px-2 py-1 bg-amber-500 text-white text-[10px] font-black rounded-lg">{(minConfidence * 100).toFixed(0)}%</output>
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
                        class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-amber-500"
                    />
                    <div class="flex justify-between">
                        <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.floor_capture_all')}</span>
                        <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.floor_reject_unsure')}</span>
                    </div>
                </div>
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

            {#if autoVideoClassification && videoCircuitOpen}
                <div role="alert" class="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-slate-700 dark:text-slate-200">
                    <p class="text-[10px] font-black uppercase tracking-[0.2em] text-amber-600 dark:text-amber-400 mb-2">
                        {$_('settings.video_circuit.title')}
                    </p>
                    <p class="text-xs font-bold leading-relaxed">{$_('settings.video_circuit.message', { values: { failures: videoCircuitFailures } })}</p>
                    {#if circuitUntil}
                        <p class="text-[10px] text-slate-500 mt-2">{$_('settings.video_circuit.until', { values: { time: circuitUntil } })}</p>
                    {/if}
                </div>
            {/if}

            {#if autoVideoClassification}
                <AdvancedSection
                    id="detection-auto-video-advanced"
                    title={$_('settings.detection.auto_video_advanced_title', { default: 'Auto-video tuning' })}
                >
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
                    <p class="text-[10px] text-slate-500 dark:text-slate-400 italic">{$_('settings.detection.video_retry_note')}</p>
                    <p class="text-[10px] text-slate-500 dark:text-slate-400">
                        {#if imageExecutionMode === 'in_process'}
                            {$_('settings.detection.video_concurrency_best_practice_in_process', { default: 'In-Process mode shares one backend runtime. Best practice is to keep video concurrency at 1 unless you have verified your model runtime stays stable under overlap.' })}
                        {:else}
                            {$_('settings.detection.video_concurrency_best_practice_subprocess', { default: 'Subprocess mode isolates classifier workers more strongly, but raising video concurrency still increases CPU, RAM, and GPU pressure.' })}
                        {/if}
                    </p>
                </AdvancedSection>
            {/if}
        </SettingsCard>

        <SettingsCard icon="⚡" title={$_('settings.detection.inference_provider', { default: 'Inference Provider' })}>
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
                        { value: 'intel_cpu', label: $_('settings.detection.provider_intel_cpu', { default: 'Intel CPU (OpenVINO)' }) }
                    ]}
                    onchange={(v) => (inferenceProvider = v as 'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu')}
                />
            </SettingsRow>

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

            <a
                href={GPU_DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                class="group flex items-center justify-between gap-3 rounded-2xl border border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-900/50 px-4 py-3 hover:border-teal-500/40 transition-colors"
            >
                <div class="min-w-0">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('common.github', { default: 'GitHub' })}</p>
                    <p class="text-xs font-bold text-slate-700 dark:text-slate-200 leading-tight">{$_('settings.detection.gpu_setup_docs', { default: 'GPU setup & diagnostics guide' })}</p>
                </div>
                <span class="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-teal-600 dark:text-teal-400 shrink-0">
                    <span>{$_('common.show', { default: 'Show' })}</span>
                    <svg class="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h4m0 0v4m0-4L10 14" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 9v10h10" />
                    </svg>
                </span>
            </a>

            {#if classifierStatus}
                <AdvancedSection
                    id="detection-inference-diagnostics"
                    title={$_('settings.detection.inference_diagnostics_title', { default: 'Runtime diagnostics' })}
                >
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black {(classifierStatus.cuda_available ?? false) ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : ((classifierStatus.cuda_provider_installed ?? false) ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400' : 'bg-slate-500/10 text-slate-500')}">
                            {#if classifierStatus.cuda_available}
                                {$_('settings.detection.cuda_available')}
                            {:else if (classifierStatus.cuda_provider_installed ?? false) && !(classifierStatus.cuda_hardware_available ?? false)}
                                {$_('settings.detection.cuda_runtime_only', { default: 'CUDA runtime installed (no NVIDIA GPU detected)' })}
                            {:else}
                                {$_('settings.detection.cuda_unavailable')}
                            {/if}
                        </span>
                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black {(classifierStatus.openvino_available ?? false) ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-slate-500/10 text-slate-500'}">
                            {$_('settings.detection.openvino_status', { default: 'OpenVINO' })}: {(classifierStatus.openvino_available ?? false) ? $_('common.available', { default: 'Available' }) : $_('common.unavailable', { default: 'Unavailable' })}
                        </span>
                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black {(classifierStatus.intel_gpu_available ?? false) ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-slate-500/10 text-slate-500'}">
                            {$_('settings.detection.intel_gpu_status', { default: 'Intel GPU' })}: {(classifierStatus.intel_gpu_available ?? false) ? $_('settings.detection.auto_detected', { default: 'Auto-detected' }) : $_('common.not_available', { default: 'Not detected' })}
                        </span>
                    </div>
                    <div class="flex flex-wrap items-center gap-2 text-[10px] font-bold text-slate-500">
                        <span>{$_('settings.detection.selected_provider_label', { default: 'Selected' })}: {classifierStatus.selected_provider ?? inferenceProvider}</span>
                        <span>{$_('settings.detection.active_provider_label', { default: 'Active' })}: {classifierStatus.active_provider ?? 'unknown'}</span>
                        {#if classifierStatus.inference_backend}
                            <span>{$_('settings.detection.inference_backend_label', { default: 'Backend' })}: {classifierStatus.inference_backend}</span>
                        {/if}
                    </div>
                    <p class="text-[10px] font-bold text-slate-500">
                        {$_('settings.detection.personalization_status_label', { default: 'Personalization' })}:
                        {(classifierStatus.personalized_rerank_enabled ?? false) ? $_('common.enabled', { default: 'Enabled' }) : $_('common.disabled', { default: 'Disabled' })}
                        · {$_('settings.detection.personalization_active_pairs', { default: 'Active camera/model pairs' })}: {classifierStatus.personalization_active_camera_models ?? 0}
                        · {$_('settings.detection.personalization_feedback_rows', { default: 'Feedback tags' })}: {classifierStatus.personalization_feedback_rows ?? 0}
                        ({$_('settings.detection.personalization_min_tags', { default: 'min' })} {classifierStatus.personalization_min_feedback_tags ?? 20})
                    </p>
                    {#if classifierStatus.fallback_reason}
                        <p class="text-[10px] font-bold text-amber-600 dark:text-amber-400">{$_('settings.detection.provider_fallback_reason', { default: 'Fallback:' })} {classifierStatus.fallback_reason}</p>
                    {/if}
                    {#if classifierStatus.model_config_warnings?.length}
                        {#each classifierStatus.model_config_warnings as modelConfigWarning}
                            <p class="text-[10px] font-bold text-amber-600 dark:text-amber-400">{$_('settings.detection.model_config_warning', { default: 'Model config warning:' })} {modelConfigWarning}</p>
                        {/each}
                    {/if}
                    {#if classifierStatus.cuda_probe_error}
                        <div class="rounded-2xl border border-amber-200/80 dark:border-amber-700/40 bg-amber-50/80 dark:bg-amber-950/20 p-3">
                            <div class="text-[10px] font-black uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">CUDA diagnostics</div>
                            <div class="mt-2 space-y-1 text-[10px] font-medium text-amber-900 dark:text-amber-100 break-all">
                                <p><span class="font-black">NVIDIA GPU:</span> {(classifierStatus.cuda_hardware_available ?? false) ? 'detected' : 'not detected'}</p>
                                <p><span class="font-black">{$_('settings.detection.probe_error', { default: 'Probe error:' })}</span> {classifierStatus.cuda_probe_error}</p>
                            </div>
                        </div>
                    {/if}
                    {#if classifierStatus.openvino_model_compile_ok === false}
                        <div class="rounded-2xl border border-amber-200/80 dark:border-amber-700/40 bg-amber-50/80 dark:bg-amber-950/20 p-3 space-y-2">
                            <p class="text-[10px] font-black uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">{$_('settings.detection.openvino_compile_failure', { default: 'OpenVINO model incompatibility on this host' })}</p>
                            <p class="text-[10px] font-medium text-amber-900 dark:text-amber-100 break-all">
                                {$_('settings.detection.openvino_compile_failure_detail', { default: 'Active model' })}: <code>{classifierStatus.active_model_id || 'unknown'}</code>
                                {#if classifierStatus.openvino_model_compile_device}({classifierStatus.openvino_model_compile_device}){/if}
                            </p>
                            <p class="text-[10px] font-medium text-amber-900 dark:text-amber-100">
                                Automatic fallback is active: <code>{classifierStatus.inference_backend || 'unknown'}</code> / <code>{classifierStatus.active_provider || 'unknown'}</code>
                            </p>
                            {#if hasOpenvinoOpIncompatibility}
                                <p class="text-[10px] font-medium text-amber-900 dark:text-amber-100">OpenVINO reported unsupported ONNX operators for this model/runtime:</p>
                                <div class="flex flex-wrap gap-1">
                                    {#each openvinoUnsupportedOps as op}
                                        <span class="inline-flex items-center px-2 py-0.5 rounded-md bg-amber-100 dark:bg-amber-900/40 border border-amber-300/70 dark:border-amber-700/60 text-[10px] font-black text-amber-800 dark:text-amber-200">{op}</span>
                                    {/each}
                                </div>
                            {/if}
                            <p class="text-[10px] font-medium text-amber-900 dark:text-amber-100">
                                Next steps: switch to <code>eva02_large_inat21</code> for OpenVINO, or keep this model and set provider to <code>{recommendedFallbackProvider}</code>.
                            </p>
                            {#if classifierStatus.openvino_model_compile_error}
                                <details class="pt-1">
                                    <summary class="cursor-pointer text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">Technical details</summary>
                                    <p class="mt-1 text-[10px] font-medium text-amber-900 dark:text-amber-100 break-all">{classifierStatus.openvino_model_compile_error}</p>
                                </details>
                            {/if}
                        </div>
                    {/if}
                    {#if ((classifierStatus.openvino_available === false) || classifierStatus.openvino_gpu_probe_error) && (classifierStatus.openvino_import_error || classifierStatus.openvino_probe_error || classifierStatus.openvino_gpu_probe_error || classifierStatus.dev_dri_present !== undefined)}
                        <div class="rounded-2xl border border-amber-200/80 dark:border-amber-700/40 bg-amber-50/80 dark:bg-amber-950/20 p-3">
                            <div class="text-[10px] font-black uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">{$_('settings.detection.openvino_diagnostics', { default: 'OpenVINO diagnostics' })}</div>
                            <div class="mt-2 space-y-1 text-[10px] font-medium text-amber-900 dark:text-amber-100 break-all">
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
                </AdvancedSection>
            {/if}
        </SettingsCard>
    </div>

    <SettingsCard icon="🚫" title={$_('settings.detection.blocked_labels')}>
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
                            class="w-full rounded-xl px-4 py-2.5 text-left text-sm font-medium transition-all hover:bg-red-50 hover:text-red-600 disabled:cursor-default disabled:opacity-60 dark:hover:bg-red-950/20 dark:hover:text-red-300 {alreadyBlocked ? 'bg-red-500/10 text-red-600 dark:text-red-300' : 'text-slate-700 dark:text-slate-200'}"
                        >
                            <span class="block">
                                {names.primary}
                                {#if alreadyBlocked}
                                    <span class="ml-2 inline-flex items-center rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.18em] text-red-500">
                                        {$_('common.added', { default: 'Added' })}
                                    </span>
                                {/if}
                            </span>
                            {#if names.secondary}
                                <span class="block text-[11px] italic text-slate-400 dark:text-slate-500">{names.secondary}</span>
                            {/if}
                        </button>
                    {/each}
                    {#if blockedSpeciesSearchError}
                        <p class="px-4 py-4 text-sm font-medium text-red-500">{blockedSpeciesSearchError}</p>
                    {:else if blockedSpeciesSearchResults.length === 0}
                        <p class="px-4 py-4 text-sm italic text-slate-400">
                            {blockedSpeciesSearching ? $_('common.loading') : $_('settings.detection.no_blocked_species_results', { default: 'No matching species found.' })}
                        </p>
                    {/if}
                </div>
            </div>
        {/if}

        {#if blockedSpecies.length > 0}
            <div>
                <p class="mb-3 text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">{$_('settings.detection.blocked_species_structured', { default: 'Blocked species' })}</p>
                <div class="flex flex-wrap gap-2">
                    {#each blockedSpecies as entry}
                        <span class="group flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-bold text-red-700 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-200">
                            {formatBlockedSpeciesLabel(entry)}
                            <button
                                type="button"
                                onclick={() => removeBlockedSpecies(entry)}
                                aria-label={$_('settings.detection.blocked_label_remove', { values: { label: formatBlockedSpeciesLabel(entry) } })}
                                class="text-red-400 transition-colors hover:text-red-600 dark:hover:text-red-100"
                            >
                                ✕
                            </button>
                        </span>
                    {/each}
                </div>
            </div>
        {/if}

        {#if blockedLabels.length > 0}
            <div>
                <p class="mb-3 text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">{$_('settings.detection.blocked_species_legacy', { default: 'Legacy raw labels' })}</p>
                <div class="flex flex-wrap gap-2">
                    {#each blockedLabels as label}
                        <span class="group flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            {label}
                            <span class="rounded-full bg-amber-500/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.18em] text-amber-600 dark:text-amber-300">{$_('common.legacy', { default: 'Legacy' })}</span>
                            <button
                                type="button"
                                onclick={() => removeLegacyBlockedLabel(label)}
                                aria-label={$_('settings.detection.blocked_label_remove', { values: { label } })}
                                class="text-slate-400 transition-colors hover:text-red-500"
                            >
                                ✕
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

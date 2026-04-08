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
    const GPU_DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/docs/troubleshooting/diagnostics.md#-gpu-acceleration-diagnostics-cuda--openvino';

    // Props
    let {
        threshold = $bindable(0.7),
        minConfidence = $bindable(0.4),
        trustFrigateSublabel = $bindable(true),
        writeFrigateSublabel = $bindable(true),
        personalizedRerankEnabled = $bindable(false),
        autoVideoClassification = $bindable(false),
        videoClassificationDelay = $bindable(30),
        videoClassificationMaxRetries = $bindable(3),
        videoClassificationMaxConcurrent = $bindable(5),
        videoClassificationFrames = $bindable(15),
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
        if (entry.taxa_id != null) {
            return `taxa:${entry.taxa_id}`;
        }

        const scientific = normalizeEntryText(entry.scientific_name);
        if (scientific) {
            return `scientific:${scientific.toLocaleLowerCase()}`;
        }

        const common = normalizeEntryText(entry.common_name);
        if (common) {
            return `common:${common.toLocaleLowerCase()}`;
        }

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
        if (!entry) {
            return false;
        }
        return blockedSpecies.some((existingEntry) => sameBlockedSpeciesEntry(existingEntry, entry));
    }

    function addBlockedSpecies(result: SearchResult) {
        const entry = buildBlockedSpeciesEntry(result);
        if (!entry) {
            return;
        }
        blockedSpecies = mergeBlockedSpeciesEntries([...blockedSpecies, entry]);
        blockedSpeciesSearchQuery = '';
        blockedSpeciesSearchResults = [];
        blockedSpeciesSearchError = null;
    }

    function removeBlockedSpecies(entryToRemove: BlockedSpeciesEntry) {
        blockedSpecies = blockedSpecies.filter(
            (entry) => !sameBlockedSpeciesEntry(entry, entryToRemove)
        );
    }

    function removeLegacyBlockedLabel(labelToRemove: string) {
        blockedLabels = blockedLabels.filter((label) => label !== labelToRemove);
    }
</script>

<div class="space-y-6">
    <!-- Classification Model -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center gap-3 mb-8">
            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.detection.classification_engine')}</h3>
        </div>
        <div class="mb-6 rounded-2xl border border-slate-200/70 bg-slate-50/80 p-5 text-slate-700 shadow-sm dark:border-slate-700/70 dark:bg-slate-900/30 dark:text-slate-200">
            <label for="bird-model-region-override" class="block text-xs font-black uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                {$_('settings.detection.region_override_title', { default: 'Bird model region' })}
            </label>
            <p class="mt-2 text-xs font-medium leading-relaxed text-slate-600 dark:text-slate-300">
                {$_('settings.detection.region_override_desc', { default: 'Auto uses your configured country. Manual override always wins.' })}
            </p>
            <select
                id="bird-model-region-override"
                bind:value={birdModelRegionOverride}
                class="mt-4 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-900 shadow-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-950/60 dark:text-white"
            >
                {#each BIRD_MODEL_REGION_OVERRIDE_VALUES as option}
                    <option value={option}>
                        {option === 'auto'
                            ? $_('settings.detection.region_override_auto', { default: 'Auto' })
                            : option === 'eu'
                                ? $_('settings.detection.region_override_eu', { default: 'Europe' })
                                : $_('settings.detection.region_override_na', { default: 'North America' })}
                    </option>
                {/each}
            </select>
        </div>
        <ModelManager bind:cropModelOverrides bind:cropSourceOverrides />
    </section>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Tuning -->
        <section class="card-base rounded-3xl p-8">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400 mb-6">{$_('settings.detection.fine_tuning')}</h4>

            <div class="space-y-8">
                <div>
                    <div class="flex justify-between mb-4">
                        <label for="confidence-threshold-slider" class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.confidence_threshold')}</label>
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
                                        <div class="flex justify-between mt-2"><span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.threshold_loose')}</span><span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.threshold_strict')}</span></div>
                                    </div>
                        
                                        <div>
                                            <div class="flex justify-between mb-4">
                                                <label for="min-confidence-slider" class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.min_confidence_floor')}</label>
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
                                                aria-describedby="min-confidence-help"
                                                class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-amber-500"
                                            />
                                            <div class="flex justify-between mt-2">
                                                <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.floor_capture_all')}</span>
                                                <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.floor_reject_unsure')}</span>
                                            </div>
                                            <p id="min-confidence-help" class="mt-3 text-[10px] text-slate-500 font-bold leading-tight">{$_('settings.detection.floor_help')}</p>
                                        </div>
                <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 flex items-center justify-between gap-4">
                    <div id="trust-frigate-label" class="flex-1">
                        <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.trust_frigate')}</span>
                        <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.detection.trust_frigate_desc')}</span>
                    </div>
                    <button
                        role="switch"
                        aria-checked={trustFrigateSublabel}
                        aria-labelledby="trust-frigate-label"
                        onclick={() => trustFrigateSublabel = !trustFrigateSublabel}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                trustFrigateSublabel = !trustFrigateSublabel;
                            }
                        }}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {trustFrigateSublabel ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                    >
                        <span class="sr-only">{$_('settings.detection.trust_frigate')}</span>
                        <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {trustFrigateSublabel ? 'translate-x-5' : 'translate-x-0'}"></span>
                    </button>
                </div>

                <div class="p-4 rounded-2xl bg-cyan-500/5 border border-cyan-500/10 flex items-center justify-between gap-4">
                    <div id="write-frigate-label" class="flex-1">
                        <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.write_frigate_sublabel')}</span>
                        <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.detection.write_frigate_sublabel_desc')}</span>
                    </div>
                    <button
                        role="switch"
                        aria-checked={writeFrigateSublabel}
                        aria-labelledby="write-frigate-label"
                        onclick={() => writeFrigateSublabel = !writeFrigateSublabel}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                writeFrigateSublabel = !writeFrigateSublabel;
                            }
                        }}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {writeFrigateSublabel ? 'bg-cyan-500' : 'bg-slate-300 dark:bg-slate-600'}"
                    >
                        <span class="sr-only">{$_('settings.detection.write_frigate_sublabel')}</span>
                        <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {writeFrigateSublabel ? 'translate-x-5' : 'translate-x-0'}"></span>
                    </button>
                </div>

                <div class="p-4 rounded-2xl bg-indigo-500/5 border border-indigo-500/10 flex items-center justify-between gap-4">
                    <div id="personalized-rerank-label" class="flex-1">
                        <span class="block text-sm font-black text-slate-900 dark:text-white">
                            {$_('settings.detection.personalized_rerank', { default: 'Personalized re-ranking' })}
                        </span>
                        <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">
                            {$_('settings.detection.personalized_rerank_desc', { default: 'Use manual tags to adapt ranking per camera and model. Disable to use base model scores only.' })}
                        </span>
                    </div>
                    <button
                        role="switch"
                        aria-checked={personalizedRerankEnabled}
                        aria-labelledby="personalized-rerank-label"
                        onclick={() => personalizedRerankEnabled = !personalizedRerankEnabled}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                personalizedRerankEnabled = !personalizedRerankEnabled;
                            }
                        }}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {personalizedRerankEnabled ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
                    >
                        <span class="sr-only">
                            {$_('settings.detection.personalized_rerank', { default: 'Personalized re-ranking' })}
                        </span>
                        <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {personalizedRerankEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                    </button>
                </div>

                <div class="space-y-4 pt-4 border-t border-slate-100 dark:border-slate-700/50">
                    <div class="flex items-center justify-between">
                        <div id="auto-video-label">
                            <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.auto_video')}</span>
                            <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.detection.auto_video_desc')}</span>
                        </div>
                        <button
                            role="switch"
                            aria-checked={autoVideoClassification}
                            aria-labelledby="auto-video-label"
                            onclick={() => autoVideoClassification = !autoVideoClassification}
                            onkeydown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    autoVideoClassification = !autoVideoClassification;
                                }
                            }}
                            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {autoVideoClassification ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
                        >
                            <span class="sr-only">{$_('settings.detection.auto_video')}</span>
                            <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {autoVideoClassification ? 'translate-x-5' : 'translate-x-0'}"></span>
                        </button>
                    </div>

                    {#if autoVideoClassification}
                        {#if videoCircuitOpen}
                            <div role="alert" class="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-slate-700 dark:text-slate-200">
                                <p class="text-[10px] font-black uppercase tracking-[0.2em] text-amber-600 dark:text-amber-400 mb-2">
                                    {$_('settings.video_circuit.title')}
                                </p>
                                <p class="text-xs font-bold leading-relaxed">
                                    {$_('settings.video_circuit.message', { values: { failures: videoCircuitFailures } })}
                                </p>
                                {#if circuitUntil}
                                    <p class="text-[10px] text-slate-500 mt-2">
                                        {$_('settings.video_circuit.until', { values: { time: circuitUntil } })}
                                    </p>
                                {/if}
                            </div>
                        {/if}
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 animate-in fade-in slide-in-from-top-2">
                            <div>
                                <label for="video-delay" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.detection.video_delay')}</label>
                                <input
                                    id="video-delay"
                                    type="number"
                                    bind:value={videoClassificationDelay}
                                    min="0"
                                    aria-label={$_('settings.detection.video_delay')}
                                    class="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                            </div>
                            <div>
                                <label for="video-retries" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.detection.video_retries')}</label>
                                <input
                                    id="video-retries"
                                    type="number"
                                    bind:value={videoClassificationMaxRetries}
                                    min="0"
                                    aria-label={$_('settings.detection.video_retries')}
                                    class="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                            </div>
                            <div>
                                <label for="video-max-concurrent" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.detection.video_max_concurrent', { default: 'Max Concurrent' })}</label>
                                <input
                                    id="video-max-concurrent"
                                    type="number"
                                    bind:value={videoClassificationMaxConcurrent}
                                    min="1"
                                    max="20"
                                    aria-label={$_('settings.detection.video_max_concurrent', { default: 'Max Concurrent Video Jobs' })}
                                    class="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                            </div>
                            <div>
                                <label for="video-frames" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.detection.video_frames', { default: 'Frames' })}</label>
                                <input
                                    id="video-frames"
                                    type="number"
                                    bind:value={videoClassificationFrames}
                                    min="5"
                                    max="100"
                                    aria-label={$_('settings.detection.video_frames', { default: 'Video Frames' })}
                                    class="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                            </div>
                        </div>
                        <p class="text-[9px] text-slate-400 italic">{$_('settings.detection.video_retry_note')}</p>
                    {/if}
                </div>
            </div>
        </section>

        <!-- Inference / Acceleration -->
        <section class="card-base rounded-3xl p-8">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400 mb-6">{$_('settings.detection.inference_provider', { default: 'Inference Provider' })}</h4>

            <div class="space-y-4">
                <div class="flex items-start justify-between gap-4">
                    <div id="inference-provider-label" class="flex-1">
                        <span class="block text-sm font-black text-slate-900 dark:text-white">
                            {$_('settings.detection.inference_provider', { default: 'Inference Provider' })}
                        </span>
                        <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">
                            {$_('settings.detection.inference_provider_desc', { default: 'Select CPU, NVIDIA CUDA, or Intel OpenVINO acceleration for ONNX models. Auto prefers Intel GPU, then CUDA, then CPU.' })}
                        </span>
                    </div>
                    <select
                        bind:value={inferenceProvider}
                        aria-labelledby="inference-provider-label"
                        class="min-w-[10rem] px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                    >
                        <option value="auto">{$_('settings.detection.provider_auto', { default: 'Auto' })}</option>
                        <option value="cpu">{$_('settings.detection.provider_cpu', { default: 'CPU (ONNX Runtime)' })}</option>
                        <option value="cuda">{$_('settings.detection.provider_cuda', { default: 'NVIDIA CUDA' })}</option>
                        <option value="intel_gpu">{$_('settings.detection.provider_intel_gpu', { default: 'Intel GPU (OpenVINO)' })}</option>
                        <option value="intel_cpu">{$_('settings.detection.provider_intel_cpu', { default: 'Intel CPU (OpenVINO)' })}</option>
                    </select>
                </div>

                <div class="flex items-start justify-between gap-4 pt-2">
                    <div id="execution-mode-label" class="flex-1">
                        <span class="block text-sm font-black text-slate-900 dark:text-white">
                            {$_('settings.detection.execution_mode', { default: 'Execution Mode' })}
                        </span>
                        <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">
                            {$_('settings.detection.execution_mode_desc', { default: 'In-Process uses much less RAM by sharing model weights, especially with larger models. Subprocess provides stronger isolation and stability, but uses significantly more memory.' })}
                        </span>
                    </div>
                    <select
                        bind:value={imageExecutionMode}
                        aria-labelledby="execution-mode-label"
                        class="min-w-[10rem] px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                    >
                        <option value="subprocess">{$_('settings.detection.mode_subprocess', { default: 'Subprocess (Isolated)' })}</option>
                        <option value="in_process">{$_('settings.detection.mode_in_process', { default: 'In-Process (Shared RAM)' })}</option>
                    </select>
                </div>

                <a
                    href={GPU_DOCS_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="group flex items-center justify-between gap-3 rounded-2xl border border-indigo-200/70 dark:border-indigo-700/40 bg-indigo-50/70 dark:bg-indigo-950/20 px-4 py-3 hover:bg-indigo-100/70 dark:hover:bg-indigo-950/30 transition-colors"
                >
                    <div class="min-w-0">
                        <p class="text-[10px] font-black uppercase tracking-[0.16em] text-indigo-600 dark:text-indigo-300">
                            {$_('common.github', { default: 'GitHub' })}
                        </p>
                        <p class="text-xs font-bold text-slate-700 dark:text-slate-200 leading-tight">
                            {$_('settings.detection.gpu_setup_docs', { default: 'GPU setup & diagnostics guide' })}
                        </p>
                    </div>
                    <span class="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-300 shrink-0">
                        <span>{$_('common.show', { default: 'Show' })}</span>
                        <svg class="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h4m0 0v4m0-4L10 14" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 9v10h10" />
                        </svg>
                    </span>
                </a>

                {#if classifierStatus}
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black {(classifierStatus.cuda_available ?? false) ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : ((classifierStatus.cuda_provider_installed ?? false) ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400' : 'bg-slate-500/10 text-slate-500')}">
                            {#if classifierStatus.cuda_available}
                                {$_('settings.detection.cuda_available')}
                            {:else if classifierStatus.cuda_provider_installed}
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
                        <span>
                            {$_('settings.detection.selected_provider_label', { default: 'Selected' })}: {classifierStatus.selected_provider ?? inferenceProvider}
                        </span>
                        <span>
                            {$_('settings.detection.active_provider_label', { default: 'Active' })}: {classifierStatus.active_provider ?? 'unknown'}
                        </span>
                        {#if classifierStatus.inference_backend}
                            <span>
                                {$_('settings.detection.inference_backend_label', { default: 'Backend' })}: {classifierStatus.inference_backend}
                            </span>
                        {/if}
                    </div>
                    <p class="text-[10px] font-bold text-slate-500">
                        {$_('settings.detection.personalization_status_label', { default: 'Personalization' })}:
                        {(classifierStatus.personalized_rerank_enabled ?? false)
                            ? $_('common.enabled', { default: 'Enabled' })
                            : $_('common.disabled', { default: 'Disabled' })}
                        · {$_('settings.detection.personalization_active_pairs', { default: 'Active camera/model pairs' })}:
                        {classifierStatus.personalization_active_camera_models ?? 0}
                        · {$_('settings.detection.personalization_feedback_rows', { default: 'Feedback tags' })}:
                        {classifierStatus.personalization_feedback_rows ?? 0}
                        ({$_('settings.detection.personalization_min_tags', { default: 'min' })} {classifierStatus.personalization_min_feedback_tags ?? 20})
                    </p>
                    {#if classifierStatus.fallback_reason}
                        <p class="text-[10px] font-bold text-amber-600 dark:text-amber-400">
                            {$_('settings.detection.provider_fallback_reason', { default: 'Fallback:' })} {classifierStatus.fallback_reason}
                        </p>
                    {/if}
                    {#if classifierStatus.model_config_warnings?.length}
                        {#each classifierStatus.model_config_warnings as modelConfigWarning}
                            <p class="text-[10px] font-bold text-amber-600 dark:text-amber-400">
                                {$_('settings.detection.model_config_warning', { default: 'Model config warning:' })} {modelConfigWarning}
                            </p>
                        {/each}
                    {/if}
                    {#if classifierStatus.openvino_model_compile_ok === false}
                        <div class="rounded-2xl border border-amber-200/80 dark:border-amber-700/40 bg-amber-50/80 dark:bg-amber-950/20 p-3 space-y-2">
                            <p class="text-[10px] font-black uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">
                                {$_('settings.detection.openvino_compile_failure', { default: 'OpenVINO model incompatibility on this host' })}
                            </p>
                            <p class="text-[10px] font-medium text-amber-900 dark:text-amber-100 break-all">
                                {$_('settings.detection.openvino_compile_failure_detail', {
                                    default: 'Active model'
                                })}: <code>{classifierStatus.active_model_id || 'unknown'}</code>
                                {#if classifierStatus.openvino_model_compile_device}
                                    ({classifierStatus.openvino_model_compile_device})
                                {/if}
                            </p>
                            <p class="text-[10px] font-medium text-amber-900 dark:text-amber-100">
                                Automatic fallback is active: <code>{classifierStatus.inference_backend || 'unknown'}</code> / <code>{classifierStatus.active_provider || 'unknown'}</code>
                            </p>
                            {#if hasOpenvinoOpIncompatibility}
                                <p class="text-[10px] font-medium text-amber-900 dark:text-amber-100">
                                    OpenVINO reported unsupported ONNX operators for this model/runtime:
                                </p>
                                <div class="flex flex-wrap gap-1">
                                    {#each openvinoUnsupportedOps as op}
                                        <span class="inline-flex items-center px-2 py-0.5 rounded-md bg-amber-100 dark:bg-amber-900/40 border border-amber-300/70 dark:border-amber-700/60 text-[10px] font-black text-amber-800 dark:text-amber-200">
                                            {op}
                                        </span>
                                    {/each}
                                </div>
                            {/if}
                            <p class="text-[10px] font-medium text-amber-900 dark:text-amber-100">
                                Next steps: switch to <code>eva02_large_inat21</code> for OpenVINO, or keep this model and set provider to <code>{recommendedFallbackProvider}</code>.
                            </p>
                            {#if classifierStatus.openvino_model_compile_error}
                                <details class="pt-1">
                                    <summary class="cursor-pointer text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                                        Technical details
                                    </summary>
                                    <p class="mt-1 text-[10px] font-medium text-amber-900 dark:text-amber-100 break-all">
                                        {classifierStatus.openvino_model_compile_error}
                                    </p>
                                </details>
                            {/if}
                        </div>
                    {/if}
                    {#if ((classifierStatus.openvino_available === false) || classifierStatus.openvino_gpu_probe_error) && (classifierStatus.openvino_import_error || classifierStatus.openvino_probe_error || classifierStatus.openvino_gpu_probe_error || classifierStatus.dev_dri_present !== undefined)}
                        <div class="rounded-2xl border border-amber-200/80 dark:border-amber-700/40 bg-amber-50/80 dark:bg-amber-950/20 p-3">
                            <div class="text-[10px] font-black uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">
                                {$_('settings.detection.openvino_diagnostics', { default: 'OpenVINO diagnostics' })}
                            </div>
                            <div class="mt-2 space-y-1 text-[10px] font-medium text-amber-900 dark:text-amber-100 break-all">
                                {#if classifierStatus.openvino_version}
                                    <p><span class="font-black">Version:</span> {classifierStatus.openvino_version}</p>
                                {/if}
                                {#if classifierStatus.openvino_import_path}
                                    <p><span class="font-black">Import:</span> <code>{classifierStatus.openvino_import_path}</code></p>
                                {/if}
                                <p><span class="font-black">/dev/dri:</span> {classifierStatus.dev_dri_present ? 'present' : 'missing'}{#if classifierStatus.dev_dri_entries?.length} (<code>{classifierStatus.dev_dri_entries.join(', ')}</code>){/if}</p>
                                {#if classifierStatus.process_uid != null}
                                    <p><span class="font-black">UID/GID:</span> {classifierStatus.process_uid}:{classifierStatus.process_gid}{#if classifierStatus.process_groups?.length} groups <code>{classifierStatus.process_groups.join(', ')}</code>{/if}</p>
                                {/if}
                                {#if classifierStatus.openvino_import_error}
                                    <p><span class="font-black">Import error:</span> {classifierStatus.openvino_import_error}</p>
                                {/if}
                                {#if classifierStatus.openvino_probe_error}
                                    <p><span class="font-black">Probe error:</span> {classifierStatus.openvino_probe_error}</p>
                                {/if}
                                {#if classifierStatus.openvino_gpu_probe_error}
                                    <p><span class="font-black">GPU plugin error:</span> {classifierStatus.openvino_gpu_probe_error}</p>
                                {/if}
                            </div>
                        </div>
                    {/if}
                {/if}
            </div>
        </section>
    </div>

    <!-- Blocked Species -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-6">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400">{$_('settings.detection.blocked_labels')}</h4>
            <span class="px-2 py-0.5 bg-red-500/10 text-red-500 text-[9px] font-black rounded uppercase">{$_('settings.detection.ignored_by_discovery')}</span>
        </div>

        <p class="mb-4 text-xs font-medium leading-relaxed text-slate-500 dark:text-slate-400">
            {$_('settings.detection.blocked_species_picker_desc', { default: 'Search for a species to block it reliably across common-name, scientific-name, and taxonomy-aware matches. Legacy raw labels still apply until you remove them.' })}
        </p>

        <div class="mb-4">
            <input
                bind:value={blockedSpeciesSearchQuery}
                placeholder={$_('settings.detection.blocked_species_placeholder', { default: 'Search species to block' })}
                aria-label={$_('settings.detection.blocked_labels')}
                class="flex-1 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
            />
        </div>

        {#if blockedSpeciesSearchQuery.trim()}
            <div class="mb-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900/50">
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
                            {blockedSpeciesSearching
                                ? $_('common.loading')
                                : $_('settings.detection.no_blocked_species_results', { default: 'No matching species found.' })}
                        </p>
                    {/if}
                </div>
            </div>
        {/if}

        {#if blockedSpecies.length > 0}
            <div class="mb-5">
                <p class="mb-3 text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">
                    {$_('settings.detection.blocked_species_structured', { default: 'Blocked species' })}
                </p>
                <div class="flex flex-wrap gap-2">
                    {#each blockedSpecies as entry}
                        <span class="group flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-bold text-red-700 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-200">
                            {formatBlockedSpeciesLabel(entry)}
                            <button
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
                <p class="mb-3 text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">
                    {$_('settings.detection.blocked_species_legacy', { default: 'Legacy raw labels' })}
                </p>
                <div class="flex flex-wrap gap-2">
                    {#each blockedLabels as label}
                        <span class="group flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            {label}
                            <span class="rounded-full bg-amber-500/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.18em] text-amber-600 dark:text-amber-300">
                                {$_('common.legacy', { default: 'Legacy' })}
                            </span>
                            <button
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
            <p class="text-xs font-bold italic text-slate-400">
                {$_('settings.detection.no_blocked_labels')}
            </p>
        {/if}
    </section>
</div>

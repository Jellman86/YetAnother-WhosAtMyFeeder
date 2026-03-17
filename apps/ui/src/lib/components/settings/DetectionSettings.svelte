<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { formatDateTime } from '../../utils/datetime';
    import ModelManager from '../../pages/models/ModelManager.svelte';
    import type { ClassifierStatus } from '../../api';
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
        imageExecutionMode = $bindable<'in_process' | 'subprocess' | string>('subprocess'),
        inferenceProvider = $bindable<'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu'>('auto'),
        classifierStatus = null,
        videoCircuitOpen = false,
        videoCircuitUntil = null,
        videoCircuitFailures = 0,
        blockedLabels = $bindable<string[]>([]),
        newBlockedLabel = $bindable(''),
        addBlockedLabel,
        removeBlockedLabel
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
        inferenceProvider: 'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu';
        classifierStatus: ClassifierStatus | null;
        videoCircuitOpen: boolean;
        videoCircuitUntil: string | null;
        videoCircuitFailures: number;
        blockedLabels: string[];
        newBlockedLabel: string;
        addBlockedLabel: () => void;
        removeBlockedLabel: (label: string) => void;
    } = $props();

    const circuitUntil = $derived(videoCircuitUntil ? formatDateTime(videoCircuitUntil) : null);
    const openvinoUnsupportedOps = $derived(classifierStatus?.openvino_model_compile_unsupported_ops || []);
    const hasOpenvinoOpIncompatibility = $derived(
        (classifierStatus?.openvino_model_compile_ok === false) && openvinoUnsupportedOps.length > 0
    );
    const recommendedFallbackProvider = $derived(
        (classifierStatus?.cuda_available ?? false) ? 'NVIDIA CUDA' : 'CPU'
    );
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
        <ModelManager />
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
                            {$_('settings.detection.execution_mode_desc', { default: 'Subprocess provides isolation and stability (recommended). In-Process saves significant RAM by sharing model weights, but a crash will take down the entire backend.' })}
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

    <!-- Blocked Labels -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-6">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400">{$_('settings.detection.blocked_labels')}</h4>
            <span class="px-2 py-0.5 bg-red-500/10 text-red-500 text-[9px] font-black rounded uppercase">{$_('settings.detection.ignored_by_discovery')}</span>
        </div>

        <div class="flex gap-2 mb-6">
            <input
                bind:value={newBlockedLabel}
                onkeydown={(e) => e.key === 'Enter' && addBlockedLabel()}
                placeholder={$_('settings.detection.blocked_labels_placeholder')}
                aria-label={$_('settings.detection.blocked_labels')}
                class="flex-1 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
            />
            <button
                onclick={addBlockedLabel}
                disabled={!newBlockedLabel.trim()}
                aria-label="{$_('common.add')} {$_('settings.detection.blocked_labels')}"
                class="px-6 py-3 bg-slate-900 dark:bg-slate-700 text-white text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-slate-800 transition-all disabled:opacity-50"
            >
                {$_('common.add')}
            </button>
        </div>

        <div class="flex flex-wrap gap-2">
            {#each blockedLabels as label}
                <span class="group flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300">
                    {label}
                    <button
                        onclick={() => removeBlockedLabel(label)}
                        aria-label={$_('settings.detection.blocked_label_remove', { values: { label } })}
                        class="text-slate-400 hover:text-red-500 transition-colors"
                    >
                        ✕
                    </button>
                </span>
            {/each}
            {#if blockedLabels.length === 0}<p class="text-xs font-bold text-slate-400 italic">{$_('settings.detection.no_blocked_labels')}</p>{/if}
        </div>
    </section>
</div>

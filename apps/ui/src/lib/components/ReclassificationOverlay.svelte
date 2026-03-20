<script lang="ts">
    import { fade, scale } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
    import { getThumbnailUrl, fetchClassifierStatus } from '../api';
    import type { ReclassificationProgress } from '../stores/detections.svelte';
    import VideoAnalysisFilmReel from './VideoAnalysisFilmReel.svelte';

    import { detectionsStore } from '../stores/detections.svelte';

    let { progress, small = false } = $props<{
        progress: ReclassificationProgress;
        small?: boolean;
    }>();

    let latestFrame = $derived(progress.frameResults[progress.frameResults.length - 1]);
    let finalTopResult = $derived(
        Array.isArray(progress.results) && progress.results.length > 0 ? progress.results[0] : null
    );
    let currentFrameThumb = $derived(latestFrame?.thumb || null);
    let backdropImageUrl = $derived.by(() => {
        if (currentFrameThumb) return `data:image/jpeg;base64,${currentFrameThumb}`;
        if (!small && progress.eventId) return getThumbnailUrl(progress.eventId);
        return null;
    });
    let safeCurrentFrame = $derived(Number.isFinite(progress.currentFrame) ? Math.max(0, Math.floor(progress.currentFrame)) : 0);
    let safeTotalFrames = $derived(
        Number.isFinite(progress.totalFrames)
            ? Math.max(1, Math.floor(progress.totalFrames))
            : 1
    );
    let isComplete = $derived(progress.status === 'completed' || safeCurrentFrame >= safeTotalFrames);
    let progressPercent = $derived(Math.round((safeCurrentFrame / safeTotalFrames) * 100));
    let displayFrameIndex = $derived(progress.frameIndex || safeCurrentFrame);
    let displayClipTotal = $derived(progress.clipTotal || safeTotalFrames);
    let modelLabel = $derived(progress.modelName || null);
    let displayLabel = $derived(
        isComplete && finalTopResult?.label ? finalTopResult.label : latestFrame?.label
    );
    let displayScorePercent = $derived(
        isComplete && typeof finalTopResult?.score === 'number'
            ? Math.round(finalTopResult.score * 100)
            : (typeof latestFrame?.score === 'number' ? Math.round(latestFrame.score * 100) : null)
    );
    let progressStrategy = $derived((progress.strategy || '').toLowerCase());
    let isAutoVideoReclassification = $derived(progressStrategy === 'auto_video');
    let autoDismissSecondsRemaining = $state<number | null>(null);
    const AUTO_DISMISS_MS = 30_000;

    let videoInferenceProvider = $state<string | null>(null);
    let videoInferenceBackend = $state<string | null>(null);

    $effect(() => {
        let mounted = true;
        async function fetchProvider() {
            try {
                const status = await fetchClassifierStatus();
                if (mounted) {
                    videoInferenceProvider = status.active_provider ?? null;
                    videoInferenceBackend = status.inference_backend ?? null;
                }
            } catch (e) {
                // ignore
            }
        }
        void fetchProvider();
        return () => { mounted = false; };
    });

    function handleDismiss() {
        detectionsStore.dismissReclassification(progress.eventId);
    }

    $effect(() => {
        if (small || !isComplete || typeof window === 'undefined') return;
        autoDismissSecondsRemaining = Math.ceil(AUTO_DISMISS_MS / 1000);
        const deadline = Date.now() + AUTO_DISMISS_MS;
        const timer = window.setTimeout(() => {
            autoDismissSecondsRemaining = 0;
            handleDismiss();
        }, AUTO_DISMISS_MS);
        const interval = window.setInterval(() => {
            autoDismissSecondsRemaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
        }, 1000);
        return () => {
            window.clearTimeout(timer);
            window.clearInterval(interval);
        };
    });

    $effect(() => {
        if (!isComplete) {
            autoDismissSecondsRemaining = null;
        }
    });

</script>

<div 
    class="absolute inset-0 z-20 flex flex-col items-center {small ? 'justify-center overflow-hidden p-3' : 'justify-start overflow-y-auto overflow-x-hidden p-4 sm:p-6'} bg-white/35 dark:bg-slate-900/45 border border-slate-200/60 dark:border-slate-700/50 backdrop-blur-xl rounded-xl"
    transition:fade={{ duration: 200 }}
>
    <!-- Current frame backdrop -->
    {#if backdropImageUrl}
        <div
            class="absolute inset-0 bg-center bg-cover opacity-60 blur-2xl scale-110"
            style="background-image: url({backdropImageUrl})"
        ></div>
    {/if}
    <div class="absolute inset-0 bg-gradient-to-br from-white/55 via-white/35 to-slate-100/50 dark:from-slate-950/70 dark:via-slate-950/55 dark:to-slate-900/70"></div>
    <div class="absolute inset-0 bg-gradient-to-t from-slate-950/45 via-transparent to-transparent dark:from-black/60"></div>

    <div class="relative w-full {small ? '' : 'max-w-4xl h-full'} flex flex-col items-center {small ? 'gap-2' : 'gap-5'}">
        
        {#if !small}
            <div class="flex-1 w-full flex items-center justify-center">
                <div class="w-full max-w-xl flex flex-col items-center gap-4">
                    <!-- Circular Progress (Large mode) -->
                    <div class="relative flex items-center justify-center" in:scale>
                        <svg class="w-24 h-24 transform -rotate-90">
                            <circle
                                cx="48"
                                cy="48"
                                r="40"
                                stroke="currentColor"
                                stroke-width="6"
                                fill="transparent"
                                class="text-slate-900/10 dark:text-slate-200/10"
                            />
                            <circle
                                cx="48"
                                cy="48"
                                r="40"
                                stroke="currentColor"
                                stroke-width="6"
                                fill="transparent"
                                stroke-dasharray={251.2}
                                stroke-dashoffset={251.2 - (251.2 * progressPercent) / 100}
                                stroke-linecap="round"
                                class="text-teal-400 transition-all duration-500 ease-out"
                            />
                        </svg>
                        <div class="absolute inset-0 flex flex-col items-center justify-center">
                            <span class="text-2xl font-black text-slate-900 dark:text-white">{progressPercent}%</span>
                            <span class="text-[10px] font-bold text-teal-600 dark:text-teal-300 uppercase tracking-widest leading-none">{$_('detection.reclassification.analysis')}</span>
                        </div>
                    </div>

                    <!-- Live Label Feedback -->
                    <div class="flex flex-col items-center gap-1 min-h-[64px] px-4">
                        {#if !isComplete}
                            <div class="flex items-center gap-2 mb-1.5">
                                <span class="px-2 py-0.5 rounded-md bg-teal-500/15 border border-teal-500/30 text-[9px] font-black text-teal-700 dark:text-teal-300 uppercase tracking-widest flex items-center gap-1.5">
                                    {#if videoInferenceProvider}
                                        <svg class="w-3 h-3 text-teal-600 dark:text-teal-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                            <title>{videoInferenceProvider}</title>
                                            <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
                                            <rect x="9" y="9" width="6" height="6"></rect>
                                            <line x1="9" y1="1" x2="9" y2="4"></line>
                                            <line x1="15" y1="1" x2="15" y2="4"></line>
                                            <line x1="9" y1="20" x2="9" y2="23"></line>
                                            <line x1="15" y1="20" x2="15" y2="23"></line>
                                            <line x1="20" y1="9" x2="23" y2="9"></line>
                                            <line x1="20" y1="14" x2="23" y2="14"></line>
                                            <line x1="1" y1="9" x2="4" y2="9"></line>
                                            <line x1="1" y1="14" x2="4" y2="14"></line>
                                        </svg>
                                    {/if}
                                    <span>{$_('detection.reclassification.frame_progress', { values: { current: displayFrameIndex, total: displayClipTotal } })}</span>
                                </span>
                                {#if progress.ramUsage}
                                    <span class="px-2 py-0.5 rounded-md bg-indigo-500/15 border border-indigo-500/30 text-[9px] font-black text-indigo-700 dark:text-indigo-300 uppercase tracking-widest flex items-center gap-1.5" title="System RAM Usage">
                                        <svg class="w-3 h-3 text-indigo-600 dark:text-indigo-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                            <path d="M4 6h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"/>
                                            <path d="M6 22v-4"/>
                                            <path d="M10 22v-4"/>
                                            <path d="M14 22v-4"/>
                                            <path d="M18 22v-4"/>
                                            <path d="M6 6V2"/>
                                            <path d="M10 6V2"/>
                                            <path d="M14 6V2"/>
                                            <path d="M18 6V2"/>
                                        </svg>
                                        <span>{progress.ramUsage}</span>
                                    </span>
                                {/if}
                            </div>
                        {/if}
                        {#if isAutoVideoReclassification}
                            <span
                                class="px-2 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/25 text-[9px] font-black text-cyan-700 dark:text-cyan-300 uppercase tracking-widest mb-1.5"
                                title={$_('detection.reclassification.auto_video_source_hint', { default: 'Automatic video reclassification queue (including Analyze Unknowns).' })}
                            >
                                {$_('detection.reclassification.auto_video_source', { default: 'Auto Video' })}
                            </span>
                        {/if}
                        {#if displayLabel}
                            <div class="flex flex-col items-center" transition:fade>
                                {#if isComplete}
                                    <span class="px-2 py-0.5 rounded-md bg-emerald-500/15 border border-emerald-500/30 text-[9px] font-black text-emerald-700 dark:text-emerald-300 uppercase tracking-widest mb-1.5">
                                        {$_('detection.reclassification.final_result', { default: 'Final Result' })}
                                    </span>
                                {/if}
                                <span class="text-base font-black text-slate-900 dark:text-white truncate max-w-[260px] drop-shadow-md text-center">
                                    {displayLabel}
                                </span>
                                {#if displayScorePercent !== null}
                                    <span class="text-[10px] font-black text-slate-500 dark:text-slate-300 uppercase tracking-widest mt-1">
                                        {displayScorePercent}%
                                    </span>
                                {/if}
                            </div>
                        {/if}
                        {#if modelLabel}
                            <span class="text-[9px] font-black text-slate-600 dark:text-slate-300 uppercase tracking-widest mt-1">
                                {$_('detection.reclassification.model', { values: { name: modelLabel } })}
                            </span>
                        {/if}
                        {#if isComplete}
                            <div in:scale={{ delay: 300 }} class="mt-4 w-full max-w-sm space-y-2">
                                <button 
                                    onclick={handleDismiss}
                                    class="w-full py-2.5 bg-teal-500 hover:bg-teal-600 text-white font-black uppercase tracking-widest text-xs rounded-xl transition-all shadow-lg shadow-teal-500/40 border border-slate-200/70 dark:border-white/10"
                                >
                                    {$_('detection.reclassification.done')}
                                </button>
                                {#if autoDismissSecondsRemaining !== null}
                                    <div class="rounded-xl border border-white/15 bg-black/20 dark:bg-black/25 px-3 py-2">
                                        <div class="flex items-center justify-between gap-3 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300">
                                            <span>{$_('common.close', { default: 'Close' })}</span>
                                            <span>{$_('detection.reclassification.auto_close_in', { default: 'Auto closes in {seconds}s', values: { seconds: autoDismissSecondsRemaining } })}</span>
                                        </div>
                                        <div class="mt-2 h-1.5 rounded-full bg-white/10 overflow-hidden">
                                            <div
                                                class="h-full rounded-full bg-gradient-to-r from-emerald-300 via-teal-300 to-cyan-300 transition-all duration-500 ease-linear motion-reduce:transition-none"
                                                style={`width: ${Math.max(0, Math.min(100, ((autoDismissSecondsRemaining ?? 0) / 30) * 100))}%`}
                                            ></div>
                                        </div>
                                    </div>
                                {/if}
                            </div>
                        {/if}
                    </div>
                </div>
            </div>
        {:else}
            <!-- Compact Progress (Small mode) -->
            <div class="flex items-center justify-between w-full mb-1">
                <div class="flex items-center gap-1.5 min-w-0">
                    <div class="w-1.5 h-1.5 rounded-full bg-teal-400 {isComplete ? '' : 'animate-ping'}"></div>
                    <span class="text-[10px] font-black text-slate-700 dark:text-white uppercase tracking-wider">{$_('detection.reclassification.ai_analysis')}</span>
                    {#if isAutoVideoReclassification}
                        <span
                            class="px-1.5 py-0.5 rounded-md border border-cyan-400/30 bg-cyan-400/10 text-[8px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300"
                            title={$_('detection.reclassification.auto_video_source_hint', { default: 'Automatic video reclassification queue (including Analyze Unknowns).' })}
                        >
                            {$_('detection.reclassification.auto_video_source', { default: 'Auto Video' })}
                        </span>
                    {/if}
                </div>
                <span class="text-xs font-black text-teal-600 dark:text-teal-300">{progressPercent}%</span>
            </div>
        {/if}

        <!-- Live Label Feedback -->
        <div class="flex flex-col items-center gap-1 {small ? 'min-h-0' : 'min-h-[64px]'} {small ? '' : 'px-4'} {small ? '' : 'hidden'}">
            {#if displayLabel}
                <div class="flex flex-col items-center" transition:fade>
                    {#if !small && !isComplete}
                        <div class="flex items-center gap-2 mb-1.5">
                            <span class="px-2 py-0.5 rounded-md bg-teal-500/15 border border-teal-500/30 text-[9px] font-black text-teal-700 dark:text-teal-300 uppercase tracking-widest flex items-center gap-1.5">
                                {#if videoInferenceProvider}
                                    <svg class="w-3 h-3 text-teal-600 dark:text-teal-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <title>{videoInferenceProvider}</title>
                                        <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
                                        <rect x="9" y="9" width="6" height="6"></rect>
                                        <line x1="9" y1="1" x2="9" y2="4"></line>
                                        <line x1="15" y1="1" x2="15" y2="4"></line>
                                        <line x1="9" y1="20" x2="9" y2="23"></line>
                                        <line x1="15" y1="20" x2="15" y2="23"></line>
                                        <line x1="20" y1="9" x2="23" y2="9"></line>
                                        <line x1="20" y1="14" x2="23" y2="14"></line>
                                        <line x1="1" y1="9" x2="4" y2="9"></line>
                                        <line x1="1" y1="14" x2="4" y2="14"></line>
                                    </svg>
                                {/if}
                                <span>{$_('detection.reclassification.frame_progress', { values: { current: displayFrameIndex, total: displayClipTotal } })}</span>
                            </span>
                            {#if progress.ramUsage}
                                <span class="px-2 py-0.5 rounded-md bg-indigo-500/15 border border-indigo-500/30 text-[9px] font-black text-indigo-700 dark:text-indigo-300 uppercase tracking-widest flex items-center gap-1.5" title="System RAM Usage">
                                    <svg class="w-3 h-3 text-indigo-600 dark:text-indigo-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M4 6h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"/>
                                        <path d="M6 22v-4"/>
                                        <path d="M10 22v-4"/>
                                        <path d="M14 22v-4"/>
                                        <path d="M18 22v-4"/>
                                        <path d="M6 6V2"/>
                                        <path d="M10 6V2"/>
                                        <path d="M14 6V2"/>
                                        <path d="M18 6V2"/>
                                    </svg>
                                    <span>{progress.ramUsage}</span>
                                </span>
                            {/if}
                        </div>
                    {/if}
                    {#if !small && isComplete}
                        <span class="px-2 py-0.5 rounded-md bg-emerald-500/15 border border-emerald-500/30 text-[9px] font-black text-emerald-700 dark:text-emerald-300 uppercase tracking-widest mb-1.5">
                            {$_('detection.reclassification.final_result', { default: 'Final Result' })}
                        </span>
                    {/if}
                    <span class="{small ? 'text-[10px]' : 'text-base'} font-black text-slate-900 dark:text-white truncate max-w-[200px] drop-shadow-md">
                        {displayLabel}
                    </span>
                    {#if !small && displayScorePercent !== null}
                        <span class="text-[10px] font-black text-slate-500 dark:text-slate-300 uppercase tracking-widest mt-1">
                            {displayScorePercent}%
                        </span>
                    {/if}
                </div>
            {/if}
            {#if modelLabel && !small}
                <span class="text-[9px] font-black text-slate-600 dark:text-slate-300 uppercase tracking-widest mt-1">
                    {$_('detection.reclassification.model', { values: { name: modelLabel } })}
                </span>
            {/if}
            {#if isComplete && !small}
                <div in:scale={{ delay: 300 }} class="mt-4 w-full">
                    <button 
                        onclick={handleDismiss}
                        class="w-full py-2.5 bg-teal-500 hover:bg-teal-600 text-white font-black uppercase tracking-widest text-xs rounded-xl transition-all shadow-lg shadow-teal-500/40 border border-slate-200/70 dark:border-white/10"
                    >
                        {$_('detection.reclassification.done')}
                    </button>
                </div>
            {/if}
        </div>

        {#if !small}
            <div class="mt-auto w-full pt-3">
                <VideoAnalysisFilmReel
                    {progress}
                    variant="overlay"
                    showFooter={false}
                />
            </div>
        {:else}
            <VideoAnalysisFilmReel
                {progress}
                variant="compact"
                showFooter={false}
            />
        {/if}
    </div>
</div>

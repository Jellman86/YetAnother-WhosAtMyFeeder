<script lang="ts">
    import { fade, scale } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
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

    function handleDismiss() {
        detectionsStore.dismissReclassification(progress.eventId);
    }

    $effect(() => {
        if (small || !isComplete || typeof window === 'undefined') return;
        const timer = window.setTimeout(() => {
            handleDismiss();
        }, 15000);
        return () => window.clearTimeout(timer);
    });

</script>

<div 
    class="absolute inset-0 z-20 flex flex-col items-center {small ? 'justify-center overflow-hidden p-3' : 'justify-start overflow-y-auto overflow-x-hidden p-6'} bg-white/50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-700/50 backdrop-blur-xl rounded-xl"
    transition:fade={{ duration: 200 }}
>
    {#if !small}
        <button
            type="button"
            onclick={handleDismiss}
            class="absolute top-3 right-3 z-30 w-8 h-8 rounded-full bg-white/80 dark:bg-slate-800/80 text-slate-700 dark:text-slate-200 border border-slate-200/80 dark:border-slate-600/70 hover:bg-white dark:hover:bg-slate-800 transition-colors"
            aria-label={$_('common.close', { default: 'Close' })}
            title={$_('common.close', { default: 'Close' })}
        >
            <span aria-hidden="true">&times;</span>
        </button>
    {/if}

    <!-- Current frame backdrop -->
    {#if currentFrameThumb}
        <div
            class="absolute inset-0 bg-center bg-cover opacity-30 blur-sm scale-105"
            style="background-image: url(data:image/jpeg;base64,{currentFrameThumb})"
        ></div>
    {/if}
    <div class="absolute inset-0 bg-gradient-to-br from-white/50 via-slate-50/70 to-slate-100/70 dark:from-slate-900/60 dark:via-slate-900/70 dark:to-slate-900/80"></div>

    <div class="relative w-full {small ? '' : 'max-w-3xl'} flex flex-col items-center {small ? 'gap-2' : 'gap-6'}">
        
        {#if !small}
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
        {:else}
            <!-- Compact Progress (Small mode) -->
            <div class="flex items-center justify-between w-full mb-1">
                <div class="flex items-center gap-1.5">
                    <div class="w-1.5 h-1.5 rounded-full bg-teal-400 {isComplete ? '' : 'animate-ping'}"></div>
                    <span class="text-[10px] font-black text-slate-700 dark:text-white uppercase tracking-wider">{$_('detection.reclassification.ai_analysis')}</span>
                </div>
                <span class="text-xs font-black text-teal-600 dark:text-teal-300">{progressPercent}%</span>
            </div>
        {/if}

        <VideoAnalysisFilmReel
            {progress}
            variant={small ? 'compact' : 'overlay'}
            showFooter={!small}
        />

        <!-- Live Label Feedback -->
        <div class="flex flex-col items-center gap-1 {small ? 'min-h-0' : 'min-h-[64px]'}">
            {#if displayLabel}
                <div class="flex flex-col items-center" transition:fade>
                    {#if !small && !isComplete}
                        <span class="px-2 py-0.5 rounded-md bg-teal-500/15 border border-teal-500/30 text-[9px] font-black text-teal-700 dark:text-teal-300 uppercase tracking-widest mb-1.5">
                            {$_('detection.reclassification.frame_progress', { values: { current: displayFrameIndex, total: displayClipTotal } })}
                        </span>
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
    </div>
</div>

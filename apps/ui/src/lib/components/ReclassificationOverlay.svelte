<script lang="ts">
    import { fade, scale } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
    import type { ReclassificationProgress } from '../stores/detections.svelte';

    import { detectionsStore } from '../stores/detections.svelte';

    let { progress, small = false } = $props<{
        progress: ReclassificationProgress;
        small?: boolean;
    }>();

    let latestFrame = $derived(progress.frameResults[progress.frameResults.length - 1]);
    let currentFrameThumb = $derived(latestFrame?.thumb || null);
    let isComplete = $derived(progress.status === 'completed' || progress.currentFrame >= progress.totalFrames);
    let progressPercent = $derived(Math.round((progress.currentFrame / progress.totalFrames) * 100));
    let displayFrameIndex = $derived(progress.frameIndex || progress.currentFrame);
    let displayClipTotal = $derived(progress.clipTotal || progress.totalFrames);
    let modelLabel = $derived(progress.modelName || null);

    function handleDismiss() {
        detectionsStore.dismissReclassification(progress.eventId);
    }

</script>

<div 
    class="absolute inset-0 z-20 flex flex-col items-center justify-center {small ? 'p-3' : 'p-6'} bg-white/80 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-700/50 backdrop-blur-xl rounded-xl overflow-hidden"
    transition:fade={{ duration: 200 }}
>
    <!-- Current frame backdrop -->
    {#if currentFrameThumb}
        <div
            class="absolute inset-0 bg-center bg-cover opacity-30 blur-sm scale-105"
            style="background-image: url(data:image/jpeg;base64,{currentFrameThumb})"
        ></div>
    {/if}
    <div class="absolute inset-0 bg-gradient-to-br from-white/70 via-slate-50/80 to-slate-100/80 dark:from-slate-900/60 dark:via-slate-900/70 dark:to-slate-900/80"></div>

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

        <!-- Frame Grid -->
        <div class="w-full bg-white/70 dark:bg-black/40 rounded-2xl {small ? 'p-1.5' : 'p-4'} border border-slate-200/70 dark:border-white/10 backdrop-blur-md shadow-2xl">
            <div class="{small ? 'grid grid-cols-5 gap-1' : 'grid grid-cols-5 gap-2'}">
                {#each Array(progress.totalFrames) as _, i}
                    {@const frame = progress.frameResults[i]}
                    {@const isCurrent = i + 1 === progress.currentFrame && !isComplete}
                    <div class="flex flex-col gap-1">
                        <div
                            class="aspect-[4/3] rounded-lg border border-slate-200/70 dark:border-white/10 transition-all duration-300 overflow-hidden
                                   {frame ? (frame.score > 0.8 ? 'bg-emerald-400/80' : frame.score > 0.5 ? 'bg-teal-400/70' : 'bg-amber-400/70') : 'bg-slate-200/60 dark:bg-white/10'}
                                   {isCurrent ? 'ring-2 ring-teal-500/70 dark:ring-teal-300/80 animate-pulse' : ''}"
                            title={frame ? `${frame.label} • ${(frame.score * 100).toFixed(0)}%` : 'Pending'}
                            style={frame?.thumb ? `background-image: url(data:image/jpeg;base64,${frame.thumb}); background-size: cover; background-position: center;` : ''}
                        ></div>
                        {#if !small}
                            <span
                                class="text-[10px] font-black uppercase tracking-widest text-center
                                       {frame
                                           ? frame.score > 0.8
                                               ? 'text-emerald-600 dark:text-emerald-300'
                                               : frame.score > 0.5
                                                   ? 'text-amber-600 dark:text-amber-300'
                                                   : 'text-rose-600 dark:text-rose-300'
                                           : 'text-slate-500 dark:text-slate-400'}"
                            >
                                {frame ? `${(frame.score * 100).toFixed(0)}%` : '--'}
                            </span>
                        {/if}
                    </div>
                {/each}
            </div>
            {#if !small}
                <div class="mt-3 flex justify-between items-center px-1">
                    <span class="text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest">{$_('detection.reclassification.frame_grid')}</span>
                    <span class="text-[10px] font-black text-teal-600 dark:text-teal-300 uppercase tracking-widest">
                        {$_('detection.reclassification.frame_progress', { values: { current: displayFrameIndex, total: displayClipTotal } })}
                    </span>
                </div>
            {/if}
        </div>

        <!-- Live Label Feedback -->
        <div class="flex flex-col items-center gap-1 {small ? 'min-h-0' : 'min-h-[64px]'}">
            {#if latestFrame}
                <div class="flex flex-col items-center" transition:fade>
                    {#if !small}
                        <span class="px-2 py-0.5 rounded-md bg-teal-500/15 border border-teal-500/30 text-[9px] font-black text-teal-700 dark:text-teal-300 uppercase tracking-widest mb-1.5">
                            {$_('detection.reclassification.frame_progress', { values: { current: displayFrameIndex, total: displayClipTotal } })}
                        </span>
                    {/if}
                    <span class="{small ? 'text-[10px]' : 'text-base'} font-black text-slate-900 dark:text-white truncate max-w-[200px] drop-shadow-md">
                        {latestFrame.label}
                    </span>
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

<style>
    .shadow-glow {
        box-shadow: 0 0 15px rgba(20, 184, 166, 0.3);
    }
</style>

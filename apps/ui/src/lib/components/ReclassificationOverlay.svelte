<script lang="ts">
    import type { ReclassificationProgress } from '../stores/detections.svelte';

    let { progress } = $props<{ progress: ReclassificationProgress }>();

    // Calculate progress percentage
    const progressPercent = $derived((progress.currentFrame / progress.totalFrames) * 100);
</script>

<div class="absolute inset-0 z-10 bg-slate-900/95 dark:bg-slate-950/95 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center p-6 animate-in fade-in duration-300">
    <!-- Header -->
    <div class="text-center mb-6">
        <div class="flex items-center justify-center gap-2 mb-2">
            <svg class="w-6 h-6 text-teal-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <h3 class="text-xl font-bold text-white">Analyzing Video</h3>
        </div>
        <p class="text-sm text-slate-300">Processing frames to improve classification accuracy</p>
    </div>

    <!-- Progress Stats -->
    <div class="w-full max-w-md mb-6 grid grid-cols-2 gap-4">
        <div class="bg-slate-800/50 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-teal-400">{progress.currentFrame}</div>
            <div class="text-xs text-slate-400 uppercase tracking-wider">Frames Analyzed</div>
        </div>
        <div class="bg-slate-800/50 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-emerald-400">{Math.round(progressPercent)}%</div>
            <div class="text-xs text-slate-400 uppercase tracking-wider">Complete</div>
        </div>
    </div>

    <!-- Progress Bar -->
    <div class="w-full max-w-md mb-6">
        <div class="flex justify-between text-xs text-slate-400 mb-2">
            <span>Frame {progress.currentFrame} of {progress.totalFrames}</span>
            <span>{Math.round(progressPercent)}%</span>
        </div>
        <div class="w-full bg-slate-700 rounded-full h-3 overflow-hidden border border-slate-600 shadow-inner">
            <div
                class="bg-gradient-to-r from-teal-500 via-emerald-400 to-teal-500 h-full transition-all duration-500 ease-out bg-[length:200%_100%] animate-shimmer"
                style="width: {progressPercent}%"
            ></div>
        </div>
    </div>

    <!-- Current Detection Info -->
    {#if progress.topLabel}
        <div class="w-full max-w-md bg-slate-800/50 rounded-lg p-4 border border-slate-700">
            <div class="flex items-center justify-between">
                <div>
                    <div class="text-xs text-slate-400 uppercase tracking-wider mb-1">Current Frame Prediction</div>
                    <div class="text-lg font-bold text-white">{progress.topLabel}</div>
                </div>
                <div class="text-right">
                    <div class="text-xs text-slate-400 uppercase tracking-wider mb-1">Confidence</div>
                    <div class="text-lg font-bold {progress.frameScore > 0.7 ? 'text-emerald-400' : progress.frameScore > 0.5 ? 'text-yellow-400' : 'text-orange-400'}">
                        {Math.round(progress.frameScore * 100)}%
                    </div>
                </div>
            </div>
        </div>
    {/if}

    <!-- Timeline Visualization (Level 2) -->
    <div class="w-full max-w-md mt-6">
        <div class="text-xs text-slate-400 uppercase tracking-wider mb-2 text-center">Processing Timeline</div>
        <div class="flex gap-1 justify-center">
            {#each Array(progress.totalFrames) as _, i}
                <div
                    class="w-3 h-3 rounded-full transition-all duration-300"
                    class:bg-emerald-500={i < progress.currentFrame}
                    class:bg-teal-500={i === progress.currentFrame - 1}
                    class:bg-slate-600={i >= progress.currentFrame}
                    class:animate-pulse={i === progress.currentFrame - 1}
                ></div>
            {/each}
        </div>
    </div>
</div>

<style>
    @keyframes shimmer {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
    }
    .animate-shimmer {
        animation: shimmer 2s linear infinite;
    }
</style>

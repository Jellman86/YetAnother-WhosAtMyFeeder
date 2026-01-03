<script lang="ts">
    import type { ReclassificationProgress } from '../stores/detections.svelte';
    import { detectionsStore } from '../stores/detections.svelte';

    let { progress } = $props<{ progress: ReclassificationProgress }>();

    // Calculate progress percentage
    let progressPercent = $derived((progress.currentFrame / progress.totalFrames) * 100);

    // Calculate final results
    let finalLabel = $derived(
        (progress.results && progress.results.length > 0) ? progress.results[0].label : progress.topLabel
    );
    let finalScore = $derived(
        (progress.results && progress.results.length > 0) ? progress.results[0].score : progress.frameScore
    );
</script>

<div class="absolute inset-0 z-50 bg-slate-900/95 dark:bg-slate-950/95 backdrop-blur-md flex flex-col items-center justify-center p-6 animate-in fade-in duration-300">
    
    {#if progress.status === 'completed'}
        <!-- Completion UI -->
        <div class="text-center animate-in zoom-in duration-300">
            <div class="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4 animate-bounce-short">
                <svg class="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                </svg>
            </div>
            
            <h3 class="text-2xl font-black text-white mb-2">Reclassification Complete</h3>
            
            <div class="bg-slate-800/80 rounded-xl p-4 border border-slate-700/50 mb-6 min-w-[200px]">
                <p class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">New Identification</p>
                
                <p class="text-xl font-black text-white">{finalLabel}</p>
                <p class="text-emerald-400 font-bold">{(finalScore * 100).toFixed(1)}% Confidence</p>
            </div>

            <button
                onclick={() => detectionsStore.dismissReclassification(progress.eventId)}
                class="px-6 py-2.5 bg-emerald-500 hover:bg-emerald-600 text-white font-bold rounded-lg transition-colors shadow-lg shadow-emerald-500/30"
            >
                Done
            </button>
        </div>

    {:else}
        <!-- Progress UI -->
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
    {/if}
</div>

<style>
    @keyframes shimmer {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
    }
    .animate-shimmer {
        animation: shimmer 2s linear infinite;
    }
    .animate-bounce-short {
        animation: bounce-short 0.5s ease-in-out 1;
    }
    @keyframes bounce-short {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
    }
</style>
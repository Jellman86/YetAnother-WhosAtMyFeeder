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

<div class="absolute inset-0 z-[100] bg-slate-900/90 dark:bg-slate-950/90 backdrop-blur-xl flex flex-col items-center justify-center p-6 animate-in fade-in duration-300 rounded-2xl">
    
    {#if progress.status === 'completed'}
        <!-- Completion UI -->
        <div class="text-center animate-in zoom-in duration-300 max-w-sm">
            <div class="w-20 h-20 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-6 animate-bounce-short">
                <svg class="w-10 h-10 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                </svg>
            </div>
            
            <h3 class="text-2xl font-black text-white mb-2">Reclassification Complete</h3>
            <p class="text-slate-400 text-sm mb-6">The detection metadata has been updated in the database.</p>
            
            <div class="bg-white/5 rounded-2xl p-6 border border-white/10 mb-8 backdrop-blur-md">
                <p class="text-[10px] font-black text-teal-400 uppercase tracking-[0.2em] mb-2">New Identification</p>
                <p class="text-3xl font-black text-white mb-1 tracking-tight">{finalLabel}</p>
                <p class="text-emerald-400 font-bold">{(finalScore * 100).toFixed(1)}% Confidence</p>
            </div>

            <button
                onclick={() => detectionsStore.dismissReclassification(progress.eventId)}
                class="w-full py-4 bg-emerald-500 hover:bg-emerald-600 text-white font-black uppercase tracking-widest rounded-xl transition-all shadow-lg shadow-emerald-500/20 active:scale-95"
            >
                Done
            </button>
        </div>

    {:else}
        <!-- Progress UI -->
        <div class="text-center mb-8">
            <div class="flex items-center justify-center gap-3 mb-3">
                <div class="w-8 h-8 border-4 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
                <h3 class="text-2xl font-black text-white tracking-tight">Analyzing Video</h3>
            </div>
            <p class="text-slate-400 font-medium">Scanning frames for temporal verification...</p>
        </div>

        <!-- Progress Stats -->
        <div class="w-full max-w-sm mb-8 grid grid-cols-2 gap-4">
            <div class="bg-white/5 rounded-2xl p-4 border border-white/10 text-center">
                <div class="text-3xl font-black text-teal-400">{progress.currentFrame}</div>
                <div class="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Frames</div>
            </div>
            <div class="bg-white/5 rounded-2xl p-4 border border-white/10 text-center">
                <div class="text-3xl font-black text-emerald-400">{Math.round(progressPercent)}%</div>
                <div class="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Progress</div>
            </div>
        </div>

        <!-- Progress Bar -->
        <div class="w-full max-w-sm mb-8">
            <div class="w-full bg-white/10 rounded-full h-4 overflow-hidden p-1 border border-white/5">
                <div
                    class="bg-gradient-to-r from-teal-500 to-emerald-400 h-full rounded-full transition-all duration-500 ease-out shadow-[0_0_15px_rgba(20,184,166,0.5)]"
                    style="width: {progressPercent}%"
                ></div>
            </div>
        </div>

        <!-- Current Prediction -->
        {#if progress.topLabel}
            <div class="w-full max-w-sm bg-black/40 rounded-2xl p-5 border border-white/10 backdrop-blur-sm">
                <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0">
                        <div class="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Current Frame</div>
                        <div class="text-lg font-bold text-white truncate leading-tight">{progress.topLabel}</div>
                    </div>
                    <div class="text-right shrink-0">
                        <div class="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Conf</div>
                        <div class="text-lg font-black {(progress.frameScore > 0.7) ? 'text-emerald-400' : 'text-yellow-400'}">
                            {Math.round(progress.frameScore * 100)}%
                        </div>
                    </div>
                </div>
            </div>
        {/if}

        <!-- Timeline -->
        <div class="w-full max-w-sm mt-8">
            <div class="flex gap-1.5 justify-center">
                {#each Array(progress.totalFrames) as _, i}
                    <div
                        class="w-2.5 h-2.5 rounded-full transition-all duration-300 
                               {(i < progress.currentFrame) ? 'bg-emerald-500' : ''} 
                               {(i === progress.currentFrame - 1) ? 'bg-teal-500 animate-pulse scale-125' : ''} 
                               {(i >= progress.currentFrame) ? 'bg-white/10' : ''}"
                    ></div>
                {/each}
            </div>
        </div>
    {/if}
</div>

<style>
    .animate-bounce-short {
        animation: bounce-short 0.6s ease-in-out infinite;
    }
    @keyframes bounce-short {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-8px); }
    }
</style>
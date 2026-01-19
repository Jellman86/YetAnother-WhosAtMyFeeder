<script lang="ts">
    import { fade, scale } from 'svelte/transition';
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

    function handleDismiss() {
        detectionsStore.dismissReclassification(progress.eventId);
    }

</script>

<div 
    class="absolute inset-0 z-20 flex flex-col items-center justify-center {small ? 'p-3' : 'p-6'} bg-slate-900/60 backdrop-blur-xl rounded-xl overflow-hidden"
    transition:fade={{ duration: 200 }}
>
    <!-- Current frame backdrop -->
    {#if currentFrameThumb}
        <div
            class="absolute inset-0 bg-center bg-cover opacity-30 blur-sm scale-105"
            style="background-image: url(data:image/jpeg;base64,{currentFrameThumb})"
        ></div>
    {/if}
    <div class="absolute inset-0 bg-gradient-to-br from-slate-900/60 to-slate-900/80"></div>

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
                        class="text-slate-200/10"
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
                    <span class="text-2xl font-black text-white">{progressPercent}%</span>
                    <span class="text-[10px] font-bold text-teal-300 uppercase tracking-widest leading-none">Analysis</span>
                </div>
            </div>
        {:else}
            <!-- Compact Progress (Small mode) -->
            <div class="flex items-center justify-between w-full mb-1">
                <div class="flex items-center gap-1.5">
                    <div class="w-1.5 h-1.5 rounded-full bg-teal-400 {isComplete ? '' : 'animate-ping'}"></div>
                    <span class="text-[10px] font-black text-white uppercase tracking-wider">AI Analysis</span>
                </div>
                <span class="text-xs font-black text-teal-300">{progressPercent}%</span>
            </div>
        {/if}

        <!-- Frame Grid -->
        <div class="w-full bg-black/40 rounded-2xl {small ? 'p-1.5' : 'p-4'} border border-white/10 backdrop-blur-md shadow-2xl">
            <div class="{small ? 'grid grid-cols-5 gap-1' : 'grid grid-cols-5 gap-2'}">
                {#each Array(progress.totalFrames) as _, i}
                    {@const frame = progress.frameResults[i]}
                    {@const isCurrent = i + 1 === progress.currentFrame && !isComplete}
                    <div
                        class="aspect-[4/3] rounded-lg border border-white/10 transition-all duration-300 overflow-hidden
                               {frame ? (frame.score > 0.8 ? 'bg-emerald-400/80' : frame.score > 0.5 ? 'bg-teal-400/70' : 'bg-amber-400/70') : 'bg-white/10'}
                               {isCurrent ? 'ring-2 ring-teal-300/80 animate-pulse' : ''}"
                        title={frame ? `${frame.label} • ${(frame.score * 100).toFixed(0)}%` : 'Pending'}
                        style={frame?.thumb ? `background-image: url(data:image/jpeg;base64,${frame.thumb}); background-size: cover; background-position: center;` : ''}
                    ></div>
                {/each}
            </div>
            {#if !small}
                <div class="mt-3 flex justify-between items-center px-1">
                    <span class="text-[10px] font-black text-slate-400 uppercase tracking-widest">Frame Grid</span>
                    <span class="text-[10px] font-black text-teal-300 uppercase tracking-widest">
                        Frame {progress.currentFrame}/{progress.totalFrames}
                    </span>
                </div>
            {/if}
        </div>

        <!-- Live Label Feedback -->
        <div class="flex flex-col items-center gap-1 {small ? 'min-h-0' : 'min-h-[64px]'}">
            {#if latestFrame}
                <div class="flex flex-col items-center" transition:fade>
                    {#if !small}
                        <span class="px-2 py-0.5 rounded-md bg-teal-500/20 border border-teal-500/30 text-[9px] font-black text-teal-300 uppercase tracking-widest mb-1.5">
                            Frame {progress.currentFrame} Results
                        </span>
                    {/if}
                    <span class="{small ? 'text-[10px]' : 'text-base'} font-black text-white truncate max-w-[200px] drop-shadow-md">
                        {latestFrame.label}
                    </span>
                </div>
            {/if}
            {#if isComplete && !small}
                <div in:scale={{ delay: 300 }} class="mt-4 w-full">
                    <button 
                        onclick={handleDismiss}
                        class="w-full py-2.5 bg-teal-500 hover:bg-teal-600 text-white font-black uppercase tracking-widest text-xs rounded-xl transition-all shadow-lg shadow-teal-500/40 border border-white/10"
                    >
                        Done
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

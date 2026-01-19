<script lang="ts">
    import { fade, slide, scale } from 'svelte/transition';
    import type { ReclassificationProgress } from '../stores/detections.svelte';

    import { detectionsStore } from '../stores/detections.svelte';

    let { progress, small = false } = $props<{
        progress: ReclassificationProgress;
        small?: boolean;
    }>();

    let latestFrame = $derived(progress.frameResults[progress.frameResults.length - 1]);
    let isComplete = $derived(progress.status === 'completed' || progress.currentFrame >= progress.totalFrames);
    let progressPercent = $derived(Math.round((progress.currentFrame / progress.totalFrames) * 100));

    const statusMessages = [
        "Analyzing temporal features...",
        "Evaluating plumage patterns...",
        "Comparing silhouettes...",
        "Averaging frame ensemble...",
        "Detecting motion vectors...",
        "Normalizing color space..."
    ];

    let statusIndex = $state(0);
    
    $effect(() => {
        const interval = setInterval(() => {
            statusIndex = (statusIndex + 1) % statusMessages.length;
        }, 2000);
        return () => clearInterval(interval);
    });

    function handleDismiss() {
        detectionsStore.dismissReclassification(progress.eventId);
    }

</script>

<div 
    class="absolute inset-0 z-20 flex flex-col items-center justify-center {small ? 'p-3' : 'p-6'} bg-slate-900/60 backdrop-blur-xl rounded-xl overflow-hidden"
    transition:fade={{ duration: 200 }}
>
    <!-- Background pulsing effect -->
    <div class="absolute inset-0 bg-gradient-to-br from-brand-500/10 to-teal-500/10 {isComplete ? '' : 'animate-pulse'}"></div>

    <div class="relative w-full {small ? '' : 'max-w-xs'} flex flex-col items-center {small ? 'gap-2' : 'gap-6'}">
        
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

        <!-- Frame Strip -->
        <div class="w-full bg-black/40 rounded-xl {small ? 'p-1.5' : 'p-3'} border border-white/10 backdrop-blur-md shadow-2xl">
            <div class="flex items-center gap-1 {small ? 'h-8' : 'h-12'} w-full">
                {#each Array(progress.totalFrames) as _, i}
                    {@const frame = progress.frameResults[i]}
                    {@const isCurrent = i + 1 === progress.currentFrame && !isComplete}
                    <div
                        class="flex-1 h-full rounded-md border border-white/10 transition-all duration-300 overflow-hidden
                               {frame ? (frame.score > 0.8 ? 'bg-emerald-400/80' : frame.score > 0.5 ? 'bg-teal-400/70' : 'bg-amber-400/70') : 'bg-white/10'}
                               {isCurrent ? 'ring-2 ring-teal-300/80 animate-pulse' : ''}"
                        title={frame ? `${frame.label} • ${(frame.score * 100).toFixed(0)}%` : 'Pending'}
                        style={frame?.thumb ? `background-image: url(data:image/jpeg;base64,${frame.thumb}); background-size: cover; background-position: center;` : ''}
                    ></div>
                {/each}
            </div>
            {#if !small}
                <div class="mt-2.5 flex justify-between items-center px-1">
                    <span class="text-[10px] font-black text-slate-400 uppercase tracking-widest">Frame Scan</span>
                    <div class="flex gap-1">
                        {#if isComplete}
                            <div class="w-1.5 h-1.5 rounded-full bg-emerald-400"></div>
                        {:else}
                            {#each Array(3) as _, i}
                                <div class="w-1 h-1 rounded-full bg-teal-400 animate-bounce" style="animation-delay: {i * 150}ms"></div>
                            {/each}
                        {/if}
                    </div>
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
            {#if !small && !isComplete}
                <p class="text-[11px] text-slate-400 font-bold italic animate-pulse mt-1">
                    {statusMessages[statusIndex]}
                </p>
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

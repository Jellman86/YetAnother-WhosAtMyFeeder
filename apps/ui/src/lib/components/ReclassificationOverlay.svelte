<script lang="ts">
    import { fade, slide, scale } from 'svelte/transition';
    import type { ReclassificationProgress } from '../stores/detections.svelte';

    let { progress, small = false } = $props<{
        progress: ReclassificationProgress;
        small?: boolean;
    }>();

    // Calculate histogram data
    let histogramBars = $derived(progress.frameResults.map((res, i) => ({
        height: Math.max(res.score * 100, 4), // Min height of 4% for visibility
        score: res.score,
        label: res.label
    })));

    let latestFrame = $derived(progress.frameResults[progress.frameResults.length - 1]);
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

</script>

<div 
    class="absolute inset-0 z-20 flex flex-col items-center justify-center {small ? 'p-3' : 'p-6'} bg-slate-900/40 backdrop-blur-md rounded-xl overflow-hidden"
    transition:fade={{ duration: 200 }}
>
    <!-- Background pulsing effect -->
    <div class="absolute inset-0 bg-gradient-to-br from-brand-500/10 to-teal-500/10 animate-pulse"></div>

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
                        class="text-slate-200/20"
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
                    <span class="text-[10px] font-bold text-teal-300 uppercase tracking-widest leading-none">AI Link</span>
                </div>
            </div>
        {:else}
            <!-- Compact Progress (Small mode) -->
            <div class="flex items-center justify-between w-full mb-1">
                <div class="flex items-center gap-1.5">
                    <div class="w-1.5 h-1.5 rounded-full bg-teal-400 animate-ping"></div>
                    <span class="text-[10px] font-black text-white uppercase tracking-wider">AI Analysis</span>
                </div>
                <span class="text-xs font-black text-teal-300">{progressPercent}%</span>
            </div>
        {/if}

        <!-- Confidence Histogram -->
        <div class="w-full bg-slate-950/40 rounded-xl {small ? 'p-1.5' : 'p-3'} border border-white/5 backdrop-blur-sm shadow-2xl">
            <div class="flex items-end justify-between gap-0.5 {small ? 'h-8' : 'h-16'} w-full px-0.5">
                {#each Array(progress.totalFrames) as _, i}
                    {@const bar = histogramBars[i]}
                    <div class="flex-1 group relative">
                        {#if bar}
                            <div 
                                class="w-full rounded-t-sm transition-all duration-300 ease-out
                                       {bar.score > 0.8 ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' : 
                                        bar.score > 0.5 ? 'bg-teal-400' : 'bg-amber-400'}"
                                style="height: {bar.height}%"
                            ></div>
                        {:else}
                            <div class="w-full h-0.5 bg-white/5 rounded-t-sm"></div>
                        {/if}
                    </div>
                {/each}
            </div>
            {#if !small}
                <div class="mt-2 flex justify-between items-center px-1">
                    <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Confidence Scan</span>
                    <div class="flex gap-0.5">
                        {#each Array(3) as _, i}
                            <div class="w-1 h-1 rounded-full bg-teal-400 animate-bounce" style="animation-delay: {i * 150}ms"></div>
                        {/each}
                    </div>
                </div>
            {/if}
        </div>

        <!-- Live Label Feedback -->
        <div class="flex flex-col items-center gap-0.5 {small ? 'min-h-0' : 'min-h-[48px]'}">
            {#if latestFrame}
                <div class="flex items-center gap-2" transition:fade>
                    {#if !small}
                        <span class="px-2 py-0.5 rounded-md bg-white/10 border border-white/10 text-[10px] font-medium text-teal-300 uppercase tracking-wider">
                            Frame {progress.currentFrame}
                        </span>
                    {/if}
                    <span class="{small ? 'text-[10px]' : 'text-sm'} font-bold text-white truncate max-w-[150px]">
                        {latestFrame.label}
                    </span>
                </div>
            {/if}
            {#if !small}
                <p class="text-[11px] text-slate-300 font-medium italic animate-pulse">
                    {statusMessages[statusIndex]}
                </p>
            {/if}
        </div>
    </div>
</div>

<style>
    .shadow-glow {
        box-shadow: 0 0 15px rgba(20, 184, 166, 0.3);
    }
</style>

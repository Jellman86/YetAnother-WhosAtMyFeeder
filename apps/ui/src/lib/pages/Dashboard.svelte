<script lang="ts">
    import DetectionCard from '../components/DetectionCard.svelte';
    import type { Detection } from '../api';

    let { detections } = $props<{ detections: Detection[] }>();
</script>

<div class="mb-8">
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Live Detections</h2>
</div>

<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
    {#each detections as detection (detection.frigate_event || detection.id)}
        <DetectionCard {detection} />
    {/each}
    
    {#if detections.length === 0}
        <div class="col-span-full text-center py-16 text-slate-500 dark:text-slate-400 bg-white/80 dark:bg-slate-800/50 rounded-2xl shadow-card dark:shadow-card-dark border border-slate-200/80 dark:border-slate-700/50 backdrop-blur-sm">
            <div class="flex flex-col items-center justify-center">
                <div class="w-16 h-16 mb-4 rounded-full bg-slate-100 dark:bg-slate-700/50 flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-slate-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                </div>
                <p class="text-lg font-semibold text-slate-700 dark:text-slate-300">No detections yet</p>
                <p class="text-sm mt-1">Waiting for birds to visit...</p>
            </div>
        </div>
    {/if}
</div>

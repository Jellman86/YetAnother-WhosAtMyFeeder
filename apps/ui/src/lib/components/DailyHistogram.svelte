<script lang="ts">
    interface Props {
        data: number[];
        title?: string;
    }

    let { data, title = "Activity Pulse" }: Props = $props();

    let maxVal = $derived(Math.max(...data, 1));
    
    // Labels for the X axis (0, 6, 12, 18, 23)
    const labels = [0, 6, 12, 18, 23].map(h => `${h}:00`);
</script>

<div class="bg-white dark:bg-slate-800/50 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-700/50 shadow-sm backdrop-blur-sm">
    <div class="flex items-center justify-between mb-6">
        <h3 class="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-teal-500 animate-pulse"></span>
            {title}
        </h3>
        <span class="text-[10px] text-slate-400">Last 24 Hours</span>
    </div>

    <div class="relative h-32 flex items-end gap-1 px-1">
        {#each data as val, i}
            <div 
                class="flex-1 bg-teal-500/20 dark:bg-teal-400/10 rounded-t-sm relative group"
                style="height: {(val / maxVal) * 100}%"
            >
                <!-- Bar Fill -->
                <div class="absolute inset-0 bg-teal-500 dark:bg-teal-400 rounded-t-sm opacity-60 group-hover:opacity-100 transition-opacity"></div>
                
                <!-- Tooltip -->
                <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-slate-900 text-white text-[10px] rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
                    {val} birds at {i}:00
                </div>
            </div>
        {/each}
    </div>

    <!-- X-Axis Labels -->
    <div class="flex justify-between mt-2 px-1">
        {#each [0, 6, 12, 18, 23] as hour}
            <span class="text-[9px] text-slate-400 font-medium">{hour}:00</span>
        {/each}
    </div>
</div>

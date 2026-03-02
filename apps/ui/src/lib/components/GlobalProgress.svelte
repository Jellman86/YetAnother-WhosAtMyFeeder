<script lang="ts">
    import { slide } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
    import { notificationCenter, type NotificationItem } from '../stores/notification_center.svelte';

    let items = $derived(notificationCenter.items);
    let ongoingItems = $derived(items.filter((item) => item.type === 'process' && !item.read));

    function getProgress(item: NotificationItem) {
        const meta = item.meta ?? {};
        const total = Number(meta.total ?? 0);
        const current = Number(meta.current ?? meta.processed ?? 0);
        if (!Number.isFinite(total) || total <= 0) return 0;
        return Math.min(100, Math.max(0, Math.round((current / total) * 100)));
    }

    let aggregateProgress = $derived.by(() => {
        if (ongoingItems.length === 0) return 0;
        const total = ongoingItems.reduce((acc, item) => acc + getProgress(item), 0);
        return Math.round(total / ongoingItems.length);
    });

    let currentMessage = $derived.by(() => {
        if (ongoingItems.length === 0) return "";
        const active = ongoingItems[0];
        return active.title;
    });

    let summaryLabel = $derived.by(() => {
        if (ongoingItems.length === 0) return "";
        if (ongoingItems.length === 1) {
            return ongoingItems[0].title;
        }
        return `${ongoingItems.length} background tasks in progress`;
    });

    let showDetails = $state(false);
</script>

{#if ongoingItems.length > 0}
    <div 
        class="w-full bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 overflow-hidden relative group shrink-0"
        transition:slide={{ duration: 300 }}
        role="status"
        aria-live="polite"
    >
        <!-- Subtle pulse background -->
        <div class="absolute inset-0 bg-emerald-500/5 animate-pulse pointer-events-none"></div>

        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 relative z-10">
            <div class="flex flex-col gap-2">
                <div class="flex items-center justify-between gap-4">
                    <div 
                        class="flex items-center gap-3 min-w-0 flex-1 cursor-help focus:outline-none focus:ring-2 focus:ring-emerald-500 rounded-lg" 
                        onmouseenter={() => showDetails = true} 
                        onmouseleave={() => showDetails = false}
                        onclick={() => showDetails = !showDetails}
                        role="button"
                        tabindex="0"
                        onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') showDetails = !showDetails }}
                    >
                        <div class="w-6 h-6 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center text-emerald-600 dark:text-emerald-400 flex-shrink-0">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                        </div>
                        <div class="min-w-0 flex flex-col md:flex-row md:items-baseline md:gap-3 cursor-help">
                            <p class="text-[10px] font-black text-slate-900 dark:text-white uppercase tracking-tight truncate">
                                {summaryLabel}
                            </p>
                            {#if ongoingItems.length > 1 && currentMessage}
                                <p class="text-[9px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-widest truncate max-w-[200px] md:max-w-md">
                                    {currentMessage}
                                </p>
                            {/if}
                        </div>
                    </div>
                    
                    <div class="flex items-center gap-4">
                        <div class="flex items-center gap-2">
                            <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest whitespace-nowrap">
                                {aggregateProgress}% Total
                            </p>
                        </div>
                    </div>
                </div>

                <!-- Aggregated Progress Bar -->
                <div class="h-2 w-full bg-emerald-100 dark:bg-emerald-950/60 rounded-full overflow-hidden relative">
                    <div 
                        class="h-full bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-500 transition-all duration-500"
                        style="width: {aggregateProgress}%"
                    ></div>
                </div>

                <!-- Detailed View -->
                {#if showDetails && ongoingItems.length > 1}
                    <div class="pt-2 border-t border-slate-100 dark:border-slate-800/50 mt-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2" in:slide>
                        {#each ongoingItems as job (job.id)}
                            <div class="flex items-center justify-between gap-3 text-[9px] min-w-0">
                                <div class="flex items-center gap-2 min-w-0 flex-1">
                                    <span class="px-1.5 py-0.5 rounded-md font-black uppercase tracking-wide whitespace-nowrap bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 truncate max-w-[150px]">
                                        {job.title}
                                    </span>
                                </div>
                                <span class="text-slate-400 truncate flex-1 text-right">
                                    {job.message || ''}
                                </span>
                                <span class="font-black text-emerald-600 dark:text-emerald-400 w-8 text-right">
                                    {getProgress(job)}%
                                </span>
                            </div>
                        {/each}
                    </div>
                {/if}
            </div>
        </div>
    </div>
{/if}

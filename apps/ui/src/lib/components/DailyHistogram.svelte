<script lang="ts">
    import { _ } from 'svelte-i18n';

    interface Props {
        data: number[];
        title?: string;
    }

    let { data, title }: Props = $props();
    let maxVal = $derived(Math.max(...data, 1));
    let total = $derived(data.reduce((sum, value) => sum + value, 0));
</script>

<section data-dashboard-activity class="border-y border-slate-200 py-5 dark:border-slate-700">
    <header class="mb-5 flex items-start justify-between gap-3">
        <div class="flex items-center gap-3">
            <span class="flex h-9 w-9 items-center justify-center rounded-xl border border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-800 dark:bg-teal-950/40 dark:text-teal-300" aria-hidden="true">
                <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M4 18V9m4 9V5m4 13v-7m4 7V7m4 11V3" /></svg>
            </span>
            <div>
                <h3 class="font-display text-lg font-bold text-slate-950 dark:text-white">{title ?? $_('dashboard.histogram.title')}</h3>
                <p class="text-sm text-slate-500 dark:text-slate-400">{$_('dashboard.histogram.last_24h')}</p>
            </div>
        </div>
        <span class="font-display text-2xl font-bold tabular-nums text-teal-700 dark:text-teal-300">{total.toLocaleString()}</span>
    </header>

    {#if total > 0}
        <div
            class="relative flex h-28 items-end gap-1 px-1"
            role="img"
            aria-label={`${title ?? $_('dashboard.histogram.title')}: ${total.toLocaleString()} ${$_('common.detections')}, ${$_('dashboard.histogram.last_24h')}`}
        >
            {#each data as val, i}
                <div
                    class="group relative min-h-px flex-1 rounded-t-sm bg-teal-500/25 dark:bg-teal-400/15"
                    style="height: {Math.max((val / maxVal) * 100, val > 0 ? 4 : 1)}%"
                    aria-hidden="true"
                    title={$_('dashboard.histogram.tooltip', { values: { count: val, time: `${i}:00` } })}
                >
                    <div class="absolute inset-0 rounded-t-sm bg-teal-500 opacity-65 transition-opacity group-hover:opacity-100 dark:bg-teal-400"></div>
                </div>
            {/each}
        </div>
        <div class="mt-2 flex justify-between px-1" aria-hidden="true">
            {#each [0, 6, 12, 18, 23] as hour}
                <span class="text-xs font-medium text-slate-500 dark:text-slate-400">{hour}:00</span>
            {/each}
        </div>
    {:else}
        <div class="flex min-h-28 items-center justify-center border-y border-dashed border-slate-200 text-center dark:border-slate-700" role="status">
            <p class="text-sm text-slate-500 dark:text-slate-400">{$_('dashboard.no_detections')}</p>
        </div>
    {/if}
</section>

<script lang="ts">
    import { _ } from 'svelte-i18n';

    /**
     * Visits per hour over the desk's rolling 24 hours. `data` is indexed by local clock hour, so
     * the bars are turned to run oldest to newest and end at the current hour: drawn midnight to
     * 23:00, yesterday evening would sit to the right of this morning.
     */
    interface Props {
        data: number[];
        title?: string;
        /** The clock hour the window ends in; the page passes it so the axis and the count agree. */
        currentHour?: number;
    }

    let { data, title, currentHour = new Date().getHours() }: Props = $props();

    const bars = $derived(
        Array.from({ length: 24 }, (_, offset) => {
            const hour = (currentHour + 1 + offset) % 24;
            return { hour, value: data[hour] ?? 0, isNow: offset === 23 };
        })
    );
    const maxVal = $derived(Math.max(...bars.map((bar) => bar.value), 1));
    const total = $derived(bars.reduce((sum, bar) => sum + bar.value, 0));
    const peak = $derived(bars.reduce((best, bar) => (bar.value > best.value ? bar : best), bars[0]));

    function hourLabel(hour: number): string {
        return `${String(hour).padStart(2, '0')}:00`;
    }
</script>

<section data-dashboard-activity class="space-y-3" aria-labelledby="dashboard-activity-title">
    <div>
        <h3 id="dashboard-activity-title" class="flex items-center gap-2 font-display text-sm font-bold text-slate-950 dark:text-white">
            <svg class="h-4 w-4 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 18V9m4 9V5m4 13v-7m4 7V7m4 11V3" /></svg>
            {title ?? $_('dashboard.histogram.title')}
        </h3>
        <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.histogram.visits_per_hour', { default: 'Visits per hour, last 24 hours' })}</p>
    </div>

    {#if total > 0}
        <p class="text-sm text-slate-700 dark:text-slate-200" data-dashboard-activity-peak>
            {$_('dashboard.histogram.peak', {
                values: { time: hourLabel(peak.hour), count: peak.value },
                default: 'Busiest at {time}, {count} visits'
            })}
        </p>
        <div
            class="relative flex h-24 items-end gap-0.5"
            role="img"
            aria-label={$_('dashboard.histogram.aria', {
                values: { count: total, time: hourLabel(peak.hour) },
                default: 'Visits per hour over the last 24 hours: {count} in all, busiest at {time}'
            })}
        >
            {#each bars as bar (bar.hour)}
                <div
                    class="min-h-px flex-1 rounded-t-sm {bar.isNow
                        ? 'bg-brand-600 dark:bg-brand-400'
                        : bar.value > 0
                          ? 'bg-brand-500/60 dark:bg-brand-400/50'
                          : 'bg-slate-200 dark:bg-slate-800'}"
                    style:height="{Math.max((bar.value / maxVal) * 100, bar.value > 0 ? 6 : 2)}%"
                    title={$_('dashboard.histogram.tooltip_visits', {
                        values: { count: bar.value, time: hourLabel(bar.hour) },
                        default: '{count} visits at {time}'
                    })}
                    aria-hidden="true"
                ></div>
            {/each}
        </div>
        <div class="flex justify-between text-xs text-slate-500 dark:text-slate-400" aria-hidden="true">
            <span>{hourLabel(bars[0].hour)}</span>
            <span>{hourLabel(bars[12].hour)}</span>
            <span class="font-semibold text-slate-700 dark:text-slate-200">{$_('dashboard.histogram.now', { default: 'now' })}</span>
        </div>
    {:else}
        <p class="text-xs text-slate-500 dark:text-slate-400" role="status">{$_('dashboard.no_detections')}</p>
    {/if}
</section>

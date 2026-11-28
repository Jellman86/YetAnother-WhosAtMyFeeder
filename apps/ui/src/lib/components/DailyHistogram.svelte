<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { formatHour } from '../utils/datetime';
    import type { DeskWindowKind } from '../utils/desk-window';

    /**
     * Visits per hour over the desk's window. `data` is indexed by local clock hour. Over the last
     * 24 hours the bars are turned to run oldest to newest and end at the current hour: drawn
     * midnight to 23:00, yesterday evening would sit to the right of this morning. Today runs from
     * midnight to the current hour, with no hour still to come drawn as an empty one.
     */
    interface Props {
        data: number[];
        title?: string;
        /** The clock hour the window ends in; the page passes it so the axis and the count agree. */
        currentHour?: number;
        windowKind?: DeskWindowKind;
    }

    let { data, title, currentHour = new Date().getHours(), windowKind = 'rolling' }: Props = $props();

    const bars = $derived(
        windowKind === 'today'
            ? Array.from({ length: currentHour + 1 }, (_, hour) => ({ hour, value: data[hour] ?? 0, isNow: hour === currentHour }))
            : Array.from({ length: 24 }, (_, offset) => {
                const hour = (currentHour + 1 + offset) % 24;
                return { hour, value: data[hour] ?? 0, isNow: offset === 23 };
            })
    );
    const middle = $derived(bars[Math.floor((bars.length - 1) / 2)]);
    const maxVal = $derived(Math.max(...bars.map((bar) => bar.value), 1));
    const total = $derived(bars.reduce((sum, bar) => sum + bar.value, 0));
    const peak = $derived(bars.reduce((best, bar) => (bar.value > best.value ? bar : best), bars[0]));

</script>

<section data-dashboard-activity class="panel space-y-4" aria-labelledby="dashboard-activity-title">
    <div>
        <h2 id="dashboard-activity-title" class="flex items-center gap-2 font-display text-xl font-bold text-strong">
            <svg class="h-5 w-5 text-accent-ink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 18V9m4 9V5m4 13v-7m4 7V7m4 11V3" /></svg>
            {title ?? $_('dashboard.histogram.title')}
        </h2>
        <p class="mt-0.5 text-sm text-muted">
            {windowKind === 'today'
                ? $_('dashboard.histogram.visits_per_hour_today', { default: 'Visits per hour, today' })
                : $_('dashboard.histogram.visits_per_hour', { default: 'Visits per hour, last 24 hours' })}
        </p>
    </div>

    {#if total > 0}
        <p class="text-sm text-ink" data-dashboard-activity-peak>
            {$_('dashboard.histogram.peak', {
                values: { time: formatHour(peak.hour), count: peak.value },
                default: 'Busiest at {time}, {count, plural, one {# visit} other {# visits}}'
            })}
        </p>
        <div
            class="relative flex h-24 items-end gap-0.5"
            role="img"
            aria-label={windowKind === 'today'
                ? $_('dashboard.histogram.aria_today', {
                    values: { count: total, time: formatHour(peak.hour) },
                    default: 'Visits per hour today: {count, plural, one {# visit} other {# visits}} in all, busiest at {time}'
                })
                : $_('dashboard.histogram.aria', {
                    values: { count: total, time: formatHour(peak.hour) },
                    default: 'Visits per hour over the last 24 hours: {count, plural, one {# visit} other {# visits}} in all, busiest at {time}'
                })}
        >
            {#each bars as bar (bar.hour)}
                <div
                    data-chart-bar
                    class="min-h-px flex-1 rounded-t-xs {bar.isNow
                        ? 'bg-accent-ink'
                        : bar.value > 0
                          ? 'bg-accent-line'
                          : 'bg-line-strong'}"
                    style:height="{Math.max((bar.value / maxVal) * 100, bar.value > 0 ? 6 : 2)}%"
                    title={$_('dashboard.histogram.tooltip_visits', {
                        values: { count: bar.value, time: formatHour(bar.hour) },
                        default: '{count, plural, one {# visit} other {# visits}} at {time}'
                    })}
                    aria-hidden="true"
                ></div>
            {/each}
        </div>
        <div class="flex justify-between text-xs text-muted" aria-hidden="true">
            <span>{formatHour(bars[0].hour)}</span>
            {#if middle !== bars[0] && !middle.isNow}<span>{formatHour(middle.hour)}</span>{/if}
            <span class="font-semibold text-ink">{$_('dashboard.histogram.now', { default: 'now' })}</span>
        </div>
    {:else}
        <p class="text-xs text-muted" role="status">
            {windowKind === 'today'
                ? $_('dashboard.no_detections_today', { default: 'No visits yet today.' })
                : $_('dashboard.no_detections')}
        </p>
    {/if}
</section>

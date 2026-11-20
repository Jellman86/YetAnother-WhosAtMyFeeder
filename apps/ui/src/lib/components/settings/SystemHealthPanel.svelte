<script lang="ts">
    import { onMount, type Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import ChartFigure from '../ui/ChartFigure.svelte';
    import Stat from '../ui/Stat.svelte';
    import { fetchSystemTelemetryHistory, type SystemTelemetryHistory } from '../../api';
    import { REFRESH_CADENCE_MS } from '../../app/refresh-cadence';
    import { startVisiblePoll } from '../../app/visible-poll';
    import { formatTime } from '../../utils/datetime';
    import {
        CHART_HEIGHT,
        CHART_WIDTH,
        chartSeries,
        cpuLoad,
        formatBytes,
        formatPercent,
        markerFor,
        pointAt,
        seriesSegments,
        sampleTable,
        shareRows,
        timeTicks,
        undrawnAccelerators,
        unreadableAccelerators,
        windowSummary,
        type Accelerator,
        type ChartSeries,
        type SeriesScope,
        type ShareRole,
        type ShareRow
    } from '../../utils/system-history';
    import { logger } from '../../utils/logger';

    /**
     * The owner's view of what this host is doing: the last half hour of CPU and every
     * accelerator counter that can be read, the live figures, and which processes are
     * using CPU, memory, and an accelerator runtime,
     * with this app's own processes named and everything else on the host as one honest
     * remainder.
     *
     * The history is kept by the server, so the chart is full the moment it opens.
     */
    const POLL_MS = REFRESH_CADENCE_MS.systemLoadHistory;

    interface Props {
        /** Header controls; without them the header names the chart's window. */
        headerActions?: Snippet;
        /** The overall verdict, shown first so the card opens with whether things are working. */
        status?: Snippet;
        /** Supporting detail closed beneath the figures. */
        details?: Snippet;
        /**
         * False until the status has its first reading. How long the verdict is depends on what it
         * finds, so nothing is shown beneath it before then: it can grow without moving the page.
         */
        statusRead?: boolean;
    }

    let { headerActions, status, details, statusRead = true }: Props = $props();

    let history = $state.raw<SystemTelemetryHistory | null>(null);
    let loading = $state(true);
    let failed = $state(false);
    let inspectedIndex = $state<number | null>(null);

    async function refresh(signal: AbortSignal): Promise<void> {
        try {
            const next = await fetchSystemTelemetryHistory(signal);
            if (signal.aborted) return;
            history = next;
            failed = false;
        } catch (error) {
            if (signal.aborted) return;
            failed = true;
            logger.warn('System load history unavailable', { message: String(error) });
        } finally {
            if (!signal.aborted) loading = false;
        }
    }

    onMount(() => {
        const controller = new AbortController();
        const stop = startVisiblePoll({ read: () => refresh(controller.signal), delayMs: () => POLL_MS });
        return () => {
            controller.abort();
            stop();
        };
    });

    const points = $derived(history?.points ?? []);
    const windowSeconds = $derived(history?.window_seconds ?? 1800);
    const latest = $derived(points.length > 0 ? points[points.length - 1] : null);
    const cpuLabel = $derived($_('settings.system_health.legend_cpu', { default: 'CPU' }));
    const series = $derived(history ? chartSeries(history, cpuLabel) : []);
    const unreadable = $derived(history ? unreadableAccelerators(history) : []);
    const undrawn = $derived(history ? undrawnAccelerators(history) : []);
    const cpuSegments = $derived(seriesSegments(points, cpuLoad, windowSeconds));
    const ticks = $derived(timeTicks(points, windowSeconds));

    /** The chart in words: every sample at the time it was taken (utils/system-history.ts). */
    const chartTable = $derived({
        columns: [$_('settings.system_health.col_time', { default: 'Time' }), ...series.map((line) => line.label)],
        swatches: [null, ...series.map((line) => line.fill)],
        rows: sampleTable(points, series, timeOf, $_('settings.system_health.not_measured', { default: 'Not measured' }))
    });
    const cpuSummary = $derived(windowSummary(points, cpuLoad));
    const rows = $derived(history ? shareRows(history) : []);
    const inspected = $derived(
        inspectedIndex !== null && points[inspectedIndex] ? points[inspectedIndex] : null
    );
    const inspectedX = $derived.by(() => {
        if (inspectedIndex === null || points.length === 0) return null;
        const at = points[inspectedIndex]?.at;
        if (at === undefined) return null;
        const latestAt = points[points.length - 1].at;
        return ((at - (latestAt - windowSeconds)) / windowSeconds) * CHART_WIDTH;
    });

    function timeOf(epochSeconds: number): string {
        return formatTime(new Date(epochSeconds * 1000).toISOString());
    }

    function onPointerMove(event: PointerEvent): void {
        const target = event.currentTarget as SVGSVGElement;
        const box = target.getBoundingClientRect();
        const x = ((event.clientX - box.left) / box.width) * CHART_WIDTH;
        inspectedIndex = pointAt(points, x, windowSeconds)?.index ?? null;
    }

    /** What a line's number covers. A GPU inside a container can only be this app's own work. */
    function scopeNote(scope: SeriesScope): string {
        if (scope === 'host') return $_('settings.system_health.scope_host', { default: 'whole host' });
        if (scope === 'device') return $_('settings.system_health.scope_device', { default: 'whole device' });
        return $_('settings.system_health.scope_app', { default: 'this app only' });
    }

    function unreadableNote(accelerator: Accelerator): string {
        if (accelerator.unreadable === 'nvidia_no_counter') {
            return $_('settings.system_health.unreadable_nvidia', {
                values: { label: accelerator.label },
                default:
                    '{label} is present, but its driver publishes no utilisation counter a container can read.'
            });
        }
        return $_('settings.system_health.unreadable_accelerator', {
            values: { label: accelerator.label },
            default: '{label} is present, but its counter cannot be read from inside the container.'
        });
    }

    /** The inspected sample said out loud, so the keyboard scrubber reads as values, not an index. */
    const inspectedSpoken = $derived.by(() => {
        if (!inspected) return undefined;
        const parts = series.map(
            (line) => `${line.label} ${formatPercent(line.load(inspected)) ?? $_('settings.system_health.unmeasured', { default: 'not measured' })}`
        );
        return `${timeOf(inspected.at)}, ${parts.join(', ')}`;
    });

    function roleLabel(row: ShareRow): string {
        const keys: Record<ShareRole, [string, string]> = {
            main: ['settings.system_health.role_main', 'YA-WAMF'],
            live_worker: ['settings.system_health.role_live_worker', 'Live worker'],
            background_worker: ['settings.system_health.role_background_worker', 'Background worker'],
            video_worker: ['settings.system_health.role_video_worker', 'Video worker'],
            ffmpeg: ['settings.system_health.role_ffmpeg', 'ffmpeg'],
            other_child: ['settings.system_health.role_other_child', 'Other process of this app'],
            other_host: ['settings.system_health.role_other_host', 'Other on this host'],
            idle: ['settings.system_health.role_idle', 'Idle']
        };
        const [key, fallback] = keys[row.role];
        return $_(key, { default: fallback });
    }

    // Validated on both surfaces for colour-vision separation; identity is never colour alone,
    // every row is named and the remainder is hatched.
    const swatch: Record<ShareRole, string> = {
        main: 'bg-blue-600 dark:bg-blue-500',
        live_worker: 'bg-teal-600',
        background_worker: 'bg-rose-600 dark:bg-rose-500',
        video_worker: 'bg-violet-600 dark:bg-violet-500',
        ffmpeg: 'bg-amber-700 dark:bg-amber-600',
        other_child: 'bg-subtle',
        other_host: 'system-health-hatched',
        idle: 'bg-subtle/40'
    };

    const appShare = $derived(latest?.app_cpu_percent ?? null);
    const cpuUnmeasured = $derived(points.length > 0 && cpuSegments.length === 0);
    const shareMeasured = $derived(rows.some((row) => row.cpuPercent !== null && row.cpuPercent > 0));
    const acceleratorSeries = $derived(series.filter((line) => line.id !== 'cpu'));
    const memberNote = (row: ShareRow): string | null =>
        row.members.length > 1 || (row.members.length === 1 && row.role !== 'main' && row.role !== 'ffmpeg')
            ? row.members.join(', ')
            : null;
</script>

<!-- A series' sample, the same line and dash as on the chart, wherever the series is named. -->
{#snippet seriesKey(line: ChartSeries)}
    <svg viewBox="0 0 24 2" class="h-0.5 w-6 shrink-0 self-center overflow-visible" aria-hidden="true" data-system-health-key={line.colour}>
        <line x1="0" y1="1" x2="24" y2="1" class={line.stroke} stroke-width="2.5" stroke-dasharray={line.dash} />
    </svg>
{/snippet}

<div data-system-health>
    <SettingsCard
        underPageTitle
        title={$_('settings.system_health.title', { default: 'System' })}
        description={$_('settings.system_health.description', {
            default: 'What this host is doing, and how much of it is this app.'
        })}
    >
        {#snippet actions()}
            {#if headerActions}
                {@render headerActions()}
            {:else}
                <p class="text-xs text-muted">
                    {$_('settings.system_health.window', { default: 'Last 30 minutes, sampled every 5 s' })}
                </p>
            {/if}
        {/snippet}

        {#if status}
            {@render status()}
        {/if}

        {#if !statusRead}
            <!-- The history is still read from the start; it is shown once the verdict above it is. -->
        {:else if loading && !history}
            <!-- Holds roughly the chart's height, so what follows the card does not jump when the history lands. -->
            <p class="min-h-96 text-sm text-muted md:min-h-80" data-system-health-loading>
                {$_('settings.system_health.loading', { default: 'Reading the last half hour…' })}
            </p>
        {:else if failed && !history}
            <p class="text-sm text-muted" data-system-health-unavailable>
                {$_('settings.system_health.unavailable', { default: 'Load history is not available right now.' })}
            </p>
        {:else if history}
            <div class="grid gap-6 md:grid-cols-[minmax(0,1fr)_12rem]">
                <div class="min-w-0">
                    {#if headerActions}
                        <p class="mb-2 text-xs text-muted">
                            {$_('settings.system_health.window', { default: 'Last 30 minutes, sampled every 5 s' })}
                        </p>
                    {/if}

                    {#if points.length === 0}
                        <p class="text-sm text-muted" data-system-health-empty>
                            {$_('settings.system_health.empty', { default: 'The first samples arrive a few seconds after start.' })}
                        </p>
                    {:else if cpuUnmeasured}
                        <p class="text-sm text-muted" data-system-health-cpu-unmeasured>
                            {$_('settings.system_health.cpu_unmeasured', { default: 'CPU load cannot be measured on this host; the counters it needs are not readable from inside the container.' })}
                        </p>
                    {:else}
                        {#snippet seriesLegend()}
                        <ul
                            class="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted"
                            aria-label={$_('settings.system_health.legend', { default: 'Series' })}
                            data-system-health-legend
                        >
                            {#each series as line (line.id)}
                                <li class="inline-flex items-baseline gap-2">
                                    {@render seriesKey(line)}
                                    <span>{line.label}</span>
                                    <span class="text-3xs text-muted">{scopeNote(line.scope)}</span>
                                </li>
                            {/each}
                        </ul>
                        {/snippet}
                        <ChartFigure
                            title={$_('settings.system_health.chart_title', { default: 'Load over the last 30 minutes' })}
                            hideTitle
                            legend={seriesLegend}
                            table={chartTable}
                        >
                        <!-- A right gutter inside the column holds the scale, clear of the newest samples. -->
                        <div class="relative mr-9">
                            <svg
                                viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}"
                                preserveAspectRatio="none"
                                class="block chart-h w-full overflow-visible"
                                role="img"
                                aria-label={cpuSummary
                                    ? $_('settings.system_health.summary', {
                                          values: { average: formatPercent(cpuSummary.average), peak: formatPercent(cpuSummary.peak), time: timeOf(cpuSummary.peakAt) },
                                          default: 'CPU average {average}, peak {peak} at {time}'
                                      })
                                    : cpuLabel}
                                onpointermove={onPointerMove}
                                onpointerleave={() => (inspectedIndex = null)}
                                data-system-health-chart
                            >
                                <line x1="0" y1="0.5" x2={CHART_WIDTH} y2="0.5" class="stroke-line" stroke-dasharray="3 5" vector-effect="non-scaling-stroke" />
                                <line x1="0" y1={CHART_HEIGHT / 2} x2={CHART_WIDTH} y2={CHART_HEIGHT / 2} class="stroke-line" stroke-dasharray="3 5" vector-effect="non-scaling-stroke" />
                                <line x1="0" y1={CHART_HEIGHT} x2={CHART_WIDTH} y2={CHART_HEIGHT} class="stroke-line-strong" vector-effect="non-scaling-stroke" />
                                {#each series as line (line.id)}
                                    {#each seriesSegments(points, line.load, windowSeconds) as segment (segment)}
                                        <polyline
                                            points={segment}
                                            fill="none"
                                            class={line.stroke}
                                            stroke-width="2"
                                            stroke-dasharray={line.dash}
                                            vector-effect="non-scaling-stroke"
                                            stroke-linejoin="round"
                                        />
                                    {/each}
                                {/each}
                                {#if inspectedX !== null && inspectedIndex !== null}
                                    <line x1={inspectedX} y1="0" x2={inspectedX} y2={CHART_HEIGHT} class="stroke-subtle" vector-effect="non-scaling-stroke" />
                                {/if}
                            </svg>
                            {#if inspectedX !== null && inspectedIndex !== null}
                                <!-- A dot on each line says which sample the crosshair and the figures belong to.
                                     Drawn outside the stretched chart so it stays round. -->
                                {#each series as line (line.id)}
                                    {@const marker = markerFor(points, inspectedIndex, line.load, windowSeconds)}
                                    {#if marker}
                                        <span
                                            class="pointer-events-none absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-current bg-surface {line.marker}"
                                            style="left: {(marker.x / CHART_WIDTH) * 100}%; top: {(marker.y / CHART_HEIGHT) * 100}%"
                                            data-system-health-marker
                                        ></span>
                                    {/if}
                                {/each}
                            {/if}
                            <span class="pointer-events-none absolute left-full top-0 ml-1.5 -translate-y-1/2 text-3xs tabular-nums text-muted">100%</span>
                            <span class="pointer-events-none absolute left-full top-1/2 ml-1.5 -translate-y-1/2 text-3xs tabular-nums text-muted">50%</span>
                            {#if inspected}
                                <div
                                    class="pointer-events-none absolute top-2 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-md"
                                    style="left: {Math.min(80, Math.max(0, ((inspectedX ?? 0) / CHART_WIDTH) * 100))}%"
                                    data-system-health-tooltip
                                >
                                    <p class="font-semibold tabular-nums text-ink">{timeOf(inspected.at)}</p>
                                    <dl class="mt-0.5 space-y-0.5 tabular-nums text-muted">
                                        {#each series as line (line.id)}
                                            <div class="flex justify-between gap-4"><dt class="flex items-center gap-1.5 whitespace-nowrap">{@render seriesKey(line)}{line.label}</dt><dd class="font-semibold">{formatPercent(line.load(inspected)) ?? '—'}</dd></div>
                                        {/each}
                                        <div class="flex justify-between gap-4"><dt class="whitespace-nowrap">{$_('settings.system_health.app_share', { default: 'This app' })}</dt><dd class="font-semibold">{formatPercent(inspected.app_cpu_percent) ?? '—'}</dd></div>
                                        <div class="flex justify-between gap-4"><dt class="whitespace-nowrap">{$_('settings.system_health.role_other_host', { default: 'Other on this host' })}</dt><dd class="font-semibold">{formatPercent(inspected.other_cpu_percent) ?? '—'}</dd></div>
                                    </dl>
                                </div>
                            {/if}
                        </div>
                        <!--
                            The keyboard's crosshair. A pointer already has the chart itself, so the
                            control stays out of sight until it is focused rather than sitting under
                            the graph as a handle with nothing visibly attached to it.
                        -->
                        <input
                            type="range"
                            min="0"
                            max={Math.max(0, points.length - 1)}
                            value={inspectedIndex ?? points.length - 1}
                            oninput={(event) => (inspectedIndex = Number(event.currentTarget.value))}
                            onblur={() => (inspectedIndex = null)}
                            class="focus-ring system-health-scrub mt-1 block h-3 w-full cursor-crosshair appearance-none rounded-full bg-transparent"
                            aria-label={$_('settings.system_health.inspect', { default: 'Inspect a sample' })}
                            aria-valuetext={inspectedSpoken}
                            data-system-health-scrub
                        />
                        <div class="flex justify-between text-3xs tabular-nums text-muted">
                            {#each ticks as tick (tick.at)}
                                <span>{timeOf(tick.at)}</span>
                            {/each}
                        </div>
                        </ChartFigure>
                        {#if acceleratorSeries.some((line) => line.scope === 'app')}
                            <p class="mt-2 text-xs text-muted" data-system-health-app-scope>
                                {$_('settings.system_health.app_scope_note', {
                                    default: 'GPU time is published per process, so that line is the work YA-WAMF sent to the GPU. Another container sharing the same GPU is not visible here.'
                                })}
                            </p>
                        {/if}
                        {#each unreadable as accelerator (accelerator.id)}
                            <p class="mt-2 text-xs text-muted" data-system-health-unreadable={accelerator.id}>
                                {unreadableNote(accelerator)}
                            </p>
                        {/each}
                        {#each undrawn as accelerator (accelerator.id)}
                            <p class="mt-2 text-xs text-muted" data-system-health-undrawn={accelerator.id}>
                                {$_('settings.system_health.undrawn_accelerator', {
                                    values: { label: accelerator.label },
                                    default: '{label} is measured, but the chart draws three accelerators at most, so its line is left out.'
                                })}
                            </p>
                        {/each}
                        {#if acceleratorSeries.length === 0 && unreadable.length === 0}
                            <p class="mt-2 text-xs text-muted" data-system-health-no-accelerator>
                                {$_('settings.system_health.no_accelerator', { default: 'No accelerator counter is readable on this host, so only the CPU is drawn.' })}
                            </p>
                        {/if}
                        {#if cpuSummary}
                            <p class="mt-2 text-xs text-muted" data-system-health-summary>
                                {$_('settings.system_health.summary', {
                                    values: { average: formatPercent(cpuSummary.average), peak: formatPercent(cpuSummary.peak), time: timeOf(cpuSummary.peakAt) },
                                    default: 'CPU average {average}, peak {peak} at {time}'
                                })}
                            </p>
                        {/if}
                    {/if}
                </div>

                <div>
                    <!-- As many readings to a row as fit at 6rem each: three on a phone, one beside the chart, and
                     one at a time when the text is enlarged. -->
                <dl class="grid grid-cols-[repeat(auto-fit,minmax(6rem,1fr))] gap-4 md:gap-5" data-system-health-now>
                        {#each series as line (line.id)}
                            <div class="min-w-0" data-system-health-reading={line.id}>
                                <dt class="flex items-center gap-2 text-sm font-semibold text-ink">
                                    {@render seriesKey(line)}
                                    {line.id === 'cpu'
                                        ? $_('settings.system_health.cpu_now', { default: 'CPU now' })
                                        : $_('settings.system_health.accelerator_now', { values: { label: line.label }, default: '{label} now' })}
                                </dt>
                                <!-- The notes belong to the value, so they sit inside its <dd>: a list item holds
                                     only its term and description. -->
                                <dd class="mt-1">
                                    {#if line.latest === null}
                                        <span class="block text-sm font-medium text-muted">{$_('settings.system_health.not_measured', { default: 'Not measured' })}</span>
                                        {#if line.id !== 'cpu'}
                                            <p class="mt-1 text-xs text-muted" data-system-health-measurement-gap>
                                                {$_('settings.system_health.measurement_gap', { default: 'No utilisation reading for this sample. The worker rows below show their loaded accelerator; this gap does not establish a CPU fallback.' })}
                                            </p>
                                        {/if}
                                    {:else}
                                        <span class="figure block text-3xl text-strong">{formatPercent(line.latest)}</span>
                                    {/if}
                                    {#if line.id !== 'cpu'}
                                        <p class="text-3xs text-muted">{scopeNote(line.scope)}</p>
                                    {/if}
                                </dd>
                            </div>
                        {/each}
                        <Stat
                            label={$_('settings.system_health.memory_now', { default: 'This app in memory' })}
                            value={formatBytes(history.app_rss_bytes)}
                            unit={history.host.memory_total_bytes
                                ? $_('settings.system_health.memory_of', { values: { total: formatBytes(history.host.memory_total_bytes) }, default: 'of {total}' })
                                : undefined}
                        />
                    </dl>
                    <!-- About the host, not one of the readings, so it follows the list rather than sitting in it. -->
                    <p class="mt-4 text-xs text-muted md:mt-5" data-system-health-host>
                        {#if history.host.cpu_count}
                            {history.host.cpu_quota
                                ? $_('settings.system_health.cores_limited', { values: { count: history.host.cpu_count, quota: history.host.cpu_quota }, default: '{count, plural, one {# core} other {# cores}}, limited to {quota}' })
                                : $_('settings.system_health.cores', { values: { count: history.host.cpu_count }, default: '{count, plural, one {# core} other {# cores}}, no CPU limit on the container' })}
                        {/if}
                    </p>
                </div>
            </div>

            {#if rows.length > 0}
                <div class="border-t border-line pt-5" data-system-health-share>
                    <div class="flex flex-wrap items-baseline justify-between gap-2">
                        <h3 id="system-health-share-heading" class="font-display text-base font-bold text-strong">
                            {$_('settings.system_health.share_title', { default: 'Resource use right now' })}
                        </h3>
                        {#if latest?.cpu_percent !== null && latest?.cpu_percent !== undefined}
                            <p class="text-xs tabular-nums text-muted">
                                {$_('settings.system_health.share_summary', {
                                    values: {
                                        app: formatPercent(appShare) ?? '—',
                                        other: formatPercent(latest.other_cpu_percent) ?? '—',
                                        idle: formatPercent(rows.find((row) => row.role === 'idle')?.cpuPercent) ?? '—'
                                    },
                                    default: 'This app {app} · rest of the host {other} · idle {idle}'
                                })}
                            </p>
                        {/if}
                    </div>
                    {#if shareMeasured}
                        <div class="mt-3 flex h-3 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
                            {#each rows as row (row.role)}
                                {#if row.cpuPercent !== null && row.cpuPercent > 0}
                                    <span class="{swatch[row.role]} block h-full" style="flex: {row.cpuPercent} 0 0"></span>
                                {/if}
                            {/each}
                        </div>
                    {/if}
                    <!-- On a phone each process is a short list of its own, so no column is ever cut off. -->
                    <ul class="mt-3 divide-y divide-line sm:hidden" data-system-health-stacked>
                        {#each rows as row (row.role)}
                            {#if row.role !== 'idle'}
                                <li class="py-2" data-system-health-row={row.role}>
                                    <p class="flex flex-wrap items-center gap-x-2 text-sm">
                                        <span class="{swatch[row.role]} inline-block h-2.5 w-2.5 rounded-xs" aria-hidden="true"></span>
                                        <span class="font-semibold text-strong" class:italic={row.role === 'other_host'}>{roleLabel(row)}</span>
                                        {#if memberNote(row)}
                                            <span class="text-xs text-muted">{memberNote(row)}</span>
                                        {/if}
                                    </p>
                                    {#if row.role === 'other_host'}
                                        <p class="mt-0.5 text-xs text-muted">
                                            {$_('settings.system_health.role_other_host_note', { default: 'Not this app. Cannot be named without the Docker socket.' })}
                                        </p>
                                    {/if}
                                    <dl class="mt-1 grid grid-cols-3 gap-x-3 text-xs">
                                        <div class="min-w-0">
                                            <dt class="text-muted">{$_('settings.system_health.col_cpu', { default: 'CPU' })}</dt>
                                            <dd class="font-semibold tabular-nums text-strong">{formatPercent(row.cpuPercent) ?? '—'}</dd>
                                        </div>
                                        <div class="min-w-0">
                                            <dt class="text-muted">{$_('settings.system_health.col_accelerator', { default: 'Accelerator' })}</dt>
                                            <dd class="wrap-break-word font-semibold text-strong">{row.acceleratorLabels.length > 0 ? row.acceleratorLabels.join(', ') : '—'}</dd>
                                        </div>
                                        <div class="min-w-0">
                                            <dt class="text-muted">{$_('settings.system_health.col_memory', { default: 'Memory' })}</dt>
                                            <dd class="font-semibold tabular-nums text-strong">{formatBytes(row.rssBytes) ?? '—'}</dd>
                                        </div>
                                    </dl>
                                </li>
                            {/if}
                        {/each}
                    </ul>
                    <!-- A table keeps its columns: when they cannot fit, as with enlarged text, it
                         scrolls sideways within its own box instead of widening the page. -->
                    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
                    <!-- When the columns cannot fit it scrolls on its own, so a keyboard must be able to reach it. -->
                    <div class="mt-3 hidden overflow-x-auto rounded-lg focus-ring sm:block" tabindex="0" role="region" aria-label={$_('settings.system_health.table_region', { default: 'Work by process' })} data-system-health-table-region>
                    <table class="w-full text-xs sm:text-sm" data-system-health-table>
                        <thead class="text-xs font-semibold text-ink">
                            <tr>
                                <th scope="col" class="pb-2 text-left font-bold">{$_('settings.system_health.col_process', { default: 'Process' })}</th>
                                <th scope="col" class="pb-2 pl-2 text-right font-bold">{$_('settings.system_health.col_cpu', { default: 'CPU' })}</th>
                                <th scope="col" class="pb-2 pl-2 text-right font-bold">{$_('settings.system_health.col_accelerator', { default: 'Accelerator' })}</th>
                                <th scope="col" class="pb-2 pl-2 text-right font-bold">{$_('settings.system_health.col_memory', { default: 'Memory' })}</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-line">
                            {#each rows as row (row.role)}
                                {#if row.role !== 'idle'}
                                    <tr data-system-health-row={row.role}>
                                        <td class="py-2 pr-3">
                                            <span class="inline-flex items-center gap-2">
                                                <span class="{swatch[row.role]} inline-block h-2.5 w-2.5 rounded-xs" aria-hidden="true"></span>
                                                <span class="font-semibold text-strong" class:italic={row.role === 'other_host'}>{roleLabel(row)}</span>
                                                {#if memberNote(row)}
                                                    <span class="text-xs text-muted">{memberNote(row)}</span>
                                                {/if}
                                            </span>
                                            {#if row.role === 'other_host'}
                                                <span class="mt-0.5 block text-xs text-muted">
                                                    {$_('settings.system_health.role_other_host_note', { default: 'Not this app. Cannot be named without the Docker socket.' })}
                                                </span>
                                            {/if}
                                        </td>
                                        <td class="py-2 pl-2 text-right font-semibold tabular-nums text-strong">{formatPercent(row.cpuPercent) ?? '—'}</td>
                                        <td class="py-2 pl-2 text-right text-muted">
                                            {#if row.acceleratorLabels.length > 0}
                                                <span class="block font-semibold text-strong">{row.acceleratorLabels.join(', ')}</span>
                                                <span class="block text-sm">{$_('settings.system_health.accelerator_loaded', { default: 'loaded' })}</span>
                                            {:else}
                                                —
                                            {/if}
                                        </td>
                                        <td class="py-2 pl-2 text-right tabular-nums text-muted">{formatBytes(row.rssBytes) ?? '—'}</td>
                                    </tr>
                                {/if}
                            {/each}
                        </tbody>
                    </table>
                    </div>
                    <p class="mt-3 text-xs text-muted">
                        {$_('settings.system_health.note', {
                            default: "CPU and memory are read from this container's own processes. Accelerator cells name the runtime a model worker actually loaded; NPU utilisation is device-wide and cannot be divided honestly between workers. Anything else on the host is measured only as the CPU remainder."
                        })}
                    </p>
                </div>
            {/if}
        {/if}

        {#if details && statusRead}
            {@render details()}
        {/if}
    </SettingsCard>
</div>

<style>
    /*
     * The scrubber is the keyboard's way onto the chart. Left visible it reads as a
     * handle for something, with no track and nothing attached to it, so it is shown
     * only while it is focused; the chart's own crosshair and dots are the feedback.
     */
    .system-health-scrub {
        opacity: 0;
        transition: opacity 120ms ease-out;
    }

    .system-health-scrub:focus-visible {
        opacity: 1;
    }

    @media (prefers-reduced-motion: reduce) {
        .system-health-scrub {
            transition: none;
        }
    }

    .system-health-scrub::-webkit-slider-runnable-track {
        height: 2px;
        border-radius: 9999px;
        background: rgb(148 163 184 / 0.5);
    }

    .system-health-scrub::-moz-range-track {
        height: 2px;
        border-radius: 9999px;
        background: rgb(148 163 184 / 0.5);
    }

    .system-health-scrub::-webkit-slider-thumb {
        appearance: none;
        height: 12px;
        width: 12px;
        margin-top: -5px;
        border-radius: 9999px;
        border: 2px solid rgb(255 255 255);
        background: rgb(71 85 105);
        box-shadow: 0 0 0 1px rgb(71 85 105);
    }

    .system-health-scrub::-moz-range-thumb {
        height: 12px;
        width: 12px;
        border: 2px solid rgb(255 255 255);
        border-radius: 9999px;
        background: rgb(71 85 105);
        box-shadow: 0 0 0 1px rgb(71 85 105);
    }

    /* The remainder is hatched as well as grey, so it reads as "unnamed" without colour. */
    .system-health-hatched {
        background: repeating-linear-gradient(135deg, rgb(100 116 139 / 0.55) 0 3px, rgb(100 116 139 / 0.2) 3px 6px);
    }
</style>

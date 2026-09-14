<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import { fetchSystemTelemetryHistory, type SystemTelemetryHistory } from '../../api';
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
        seriesArea,
        seriesSegments,
        shareRows,
        timeTicks,
        unreadableAccelerators,
        windowSummary,
        type Accelerator,
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
    const POLL_MS = 5_000;

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
        void refresh(controller.signal);
        const tick = () => {
            if (document.visibilityState === 'visible') void refresh(controller.signal);
        };
        const interval = window.setInterval(tick, POLL_MS);
        document.addEventListener('visibilitychange', tick);
        return () => {
            controller.abort();
            window.clearInterval(interval);
            document.removeEventListener('visibilitychange', tick);
        };
    });

    const points = $derived(history?.points ?? []);
    const windowSeconds = $derived(history?.window_seconds ?? 1800);
    const latest = $derived(points.length > 0 ? points[points.length - 1] : null);
    const cpuLabel = $derived($_('settings.system_health.legend_cpu', { default: 'CPU, whole host' }));
    const series = $derived(history ? chartSeries(history, cpuLabel) : []);
    const unreadable = $derived(history ? unreadableAccelerators(history) : []);
    const cpuSegments = $derived(seriesSegments(points, cpuLoad, windowSeconds));
    const cpuArea = $derived(seriesArea(points, cpuLoad, windowSeconds));
    const ticks = $derived(timeTicks(points, windowSeconds));
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
        other_child: 'bg-slate-500',
        other_host: 'system-health-hatched',
        idle: 'bg-slate-200 dark:bg-slate-700/60'
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

<div data-system-health>
    <SettingsCard
        title={$_('settings.system_health.title', { default: 'System' })}
        description={$_('settings.system_health.description', {
            default: 'What this host is doing, and how much of it is this app.'
        })}
    >
        {#snippet actions()}
            <p class="text-xs text-slate-500 dark:text-slate-400">
                {$_('settings.system_health.window', { default: 'Last 30 minutes, sampled every 5 s' })}
            </p>
        {/snippet}

        {#if loading && !history}
            <p class="text-sm text-slate-500 dark:text-slate-400" data-system-health-loading>
                {$_('settings.system_health.loading', { default: 'Reading the last half hour…' })}
            </p>
        {:else if failed && !history}
            <p class="text-sm text-slate-500 dark:text-slate-400" data-system-health-unavailable>
                {$_('settings.system_health.unavailable', { default: 'Load history is not available right now.' })}
            </p>
        {:else if history}
            <div class="grid gap-6 md:grid-cols-[minmax(0,1fr)_12rem]">
                <div class="min-w-0">
                    <ul
                        class="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600 dark:text-slate-300"
                        aria-label={$_('settings.system_health.legend', { default: 'Series' })}
                        data-system-health-legend
                    >
                        {#each series as line (line.id)}
                            <li class="inline-flex items-baseline gap-2">
                                <svg viewBox="0 0 16 2" class="h-[2px] w-4 self-center overflow-visible" aria-hidden="true">
                                    <line
                                        x1="0"
                                        y1="1"
                                        x2="16"
                                        y2="1"
                                        class={line.stroke}
                                        stroke-width="2"
                                        stroke-dasharray={line.dash}
                                    />
                                </svg>
                                <span>{line.label}</span>
                                <span class="text-[10px] text-slate-400 dark:text-slate-500">{scopeNote(line.scope)}</span>
                            </li>
                        {/each}
                    </ul>

                    {#if points.length === 0}
                        <p class="text-sm text-slate-500 dark:text-slate-400" data-system-health-empty>
                            {$_('settings.system_health.empty', { default: 'The first samples arrive a few seconds after start.' })}
                        </p>
                    {:else if cpuUnmeasured}
                        <p class="text-sm text-slate-500 dark:text-slate-400" data-system-health-cpu-unmeasured>
                            {$_('settings.system_health.cpu_unmeasured', { default: 'CPU load cannot be measured on this host; the counters it needs are not readable from inside the container.' })}
                        </p>
                    {:else}
                        <div class="relative">
                            <svg
                                viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}"
                                class="block h-48 w-full overflow-visible"
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
                                <line x1="0" y1="0.5" x2={CHART_WIDTH} y2="0.5" class="stroke-slate-200 dark:stroke-slate-700" stroke-dasharray="3 5" />
                                <line x1="0" y1={CHART_HEIGHT / 2} x2={CHART_WIDTH} y2={CHART_HEIGHT / 2} class="stroke-slate-200 dark:stroke-slate-700" stroke-dasharray="3 5" />
                                <line x1="0" y1={CHART_HEIGHT} x2={CHART_WIDTH} y2={CHART_HEIGHT} class="stroke-slate-300 dark:stroke-slate-600" />
                                {#if cpuArea}
                                    <polygon points={cpuArea} class="fill-blue-600/10 dark:fill-blue-500/15" />
                                {/if}
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
                                    <line x1={inspectedX} y1="0" x2={inspectedX} y2={CHART_HEIGHT} class="stroke-slate-400 dark:stroke-slate-500" vector-effect="non-scaling-stroke" />
                                    <!-- A dot on each line says which sample the crosshair and the figures belong to. -->
                                    {#each series as line (line.id)}
                                        {@const marker = markerFor(points, inspectedIndex, line.load, windowSeconds)}
                                        {#if marker}
                                            <circle
                                                cx={marker.x}
                                                cy={marker.y}
                                                r="3.5"
                                                class="{line.stroke} fill-white dark:fill-slate-900"
                                                stroke-width="2"
                                                vector-effect="non-scaling-stroke"
                                                data-system-health-marker
                                            />
                                        {/if}
                                    {/each}
                                {/if}
                            </svg>
                            <span class="pointer-events-none absolute -top-2 right-0 text-[10px] tabular-nums text-slate-400">100%</span>
                            <span class="pointer-events-none absolute right-0 top-1/2 -translate-y-3 text-[10px] tabular-nums text-slate-400">50%</span>
                            {#if inspected}
                                <div
                                    class="pointer-events-none absolute top-2 rounded-lg border border-slate-200 bg-white/95 px-2.5 py-1.5 text-xs shadow-md dark:border-slate-700 dark:bg-slate-900/95"
                                    style="left: {Math.min(80, Math.max(0, ((inspectedX ?? 0) / CHART_WIDTH) * 100))}%"
                                    data-system-health-tooltip
                                >
                                    <p class="font-semibold tabular-nums text-slate-700 dark:text-slate-200">{timeOf(inspected.at)}</p>
                                    <dl class="mt-0.5 space-y-0.5 tabular-nums text-slate-600 dark:text-slate-300">
                                        {#each series as line (line.id)}
                                            <div class="flex justify-between gap-4"><dt class="whitespace-nowrap">{line.label}</dt><dd class="font-semibold">{formatPercent(line.load(inspected)) ?? '—'}</dd></div>
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
                            class="system-health-scrub mt-1 block h-3 w-full cursor-crosshair appearance-none rounded-full bg-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-950"
                            aria-label={$_('settings.system_health.inspect', { default: 'Inspect a sample' })}
                            aria-valuetext={inspectedSpoken}
                            data-system-health-scrub
                        />
                        <div class="flex justify-between text-[10px] tabular-nums text-slate-400">
                            {#each ticks as tick (tick.at)}
                                <span>{timeOf(tick.at)}</span>
                            {/each}
                        </div>
                        {#if acceleratorSeries.some((line) => line.scope === 'app')}
                            <p class="mt-2 text-xs text-slate-500 dark:text-slate-400" data-system-health-app-scope>
                                {$_('settings.system_health.app_scope_note', {
                                    default: 'GPU time is published per process, so that line is the work YA-WAMF sent to the GPU. Another container sharing the same GPU is not visible here.'
                                })}
                            </p>
                        {/if}
                        {#each unreadable as accelerator (accelerator.id)}
                            <p class="mt-2 text-xs text-slate-500 dark:text-slate-400" data-system-health-unreadable={accelerator.id}>
                                {unreadableNote(accelerator)}
                            </p>
                        {/each}
                        {#if acceleratorSeries.length === 0 && unreadable.length === 0}
                            <p class="mt-2 text-xs text-slate-500 dark:text-slate-400" data-system-health-no-accelerator>
                                {$_('settings.system_health.no_accelerator', { default: 'No accelerator counter is readable on this host, so only the CPU is drawn.' })}
                            </p>
                        {/if}
                        {#if cpuSummary}
                            <p class="mt-2 text-xs text-slate-500 dark:text-slate-400" data-system-health-summary>
                                {$_('settings.system_health.summary', {
                                    values: { average: formatPercent(cpuSummary.average), peak: formatPercent(cpuSummary.peak), time: timeOf(cpuSummary.peakAt) },
                                    default: 'CPU average {average}, peak {peak} at {time}'
                                })}
                            </p>
                        {/if}
                    {/if}
                </div>

                <dl class="grid grid-cols-3 gap-4 md:grid-cols-1 md:gap-5" data-system-health-now>
                    <div>
                        <dt class="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{$_('settings.system_health.cpu_now', { default: 'CPU now' })}</dt>
                        <dd class="font-display text-3xl font-bold tabular-nums text-blue-700 dark:text-blue-300">{formatPercent(latest?.cpu_percent) ?? '—'}</dd>
                    </div>
                    {#each acceleratorSeries as line (line.id)}
                        <div>
                            <dt class="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{$_('settings.system_health.accelerator_now', { values: { label: line.label }, default: '{label} now' })}</dt>
                            <dd class="font-display text-3xl font-bold tabular-nums {line.text}">{formatPercent(line.latest) ?? '—'}</dd>
                            <p class="text-[10px] text-slate-400 dark:text-slate-500">{scopeNote(line.scope)}</p>
                        </div>
                    {/each}
                    <div>
                        <dt class="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{$_('settings.system_health.memory_now', { default: 'This app in memory' })}</dt>
                        <dd class="font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">
                            {formatBytes(history.app_rss_bytes) ?? '—'}
                            {#if history.host.memory_total_bytes}
                                <span class="text-xs font-normal text-slate-500 dark:text-slate-400">{$_('settings.system_health.memory_of', { values: { total: formatBytes(history.host.memory_total_bytes) }, default: 'of {total}' })}</span>
                            {/if}
                        </dd>
                    </div>
                    <div class="col-span-3 text-xs text-slate-500 md:col-span-1 dark:text-slate-400" data-system-health-host>
                        {#if history.host.cpu_count}
                            {history.host.cpu_quota
                                ? $_('settings.system_health.cores_limited', { values: { count: history.host.cpu_count, quota: history.host.cpu_quota }, default: '{count} cores, limited to {quota}' })
                                : $_('settings.system_health.cores', { values: { count: history.host.cpu_count }, default: '{count} cores, no CPU limit on the container' })}
                        {/if}
                    </div>
                </dl>
            </div>

            {#if rows.length > 0}
                <div class="border-t border-slate-200/70 pt-5 dark:border-slate-700/50" data-system-health-share>
                    <div class="flex flex-wrap items-baseline justify-between gap-2">
                        <h4 class="font-display text-base font-bold text-slate-900 dark:text-white">
                            {$_('settings.system_health.share_title', { default: 'Resource use right now' })}
                        </h4>
                        {#if latest?.cpu_percent !== null && latest?.cpu_percent !== undefined}
                            <p class="text-xs tabular-nums text-slate-500 dark:text-slate-400">
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
                    <table class="mt-3 w-full text-xs sm:text-sm" data-system-health-table>
                        <thead class="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                            <tr>
                                <th scope="col" class="pb-2 text-left font-bold">{$_('settings.system_health.col_process', { default: 'Process' })}</th>
                                <th scope="col" class="pb-2 text-right font-bold">{$_('settings.system_health.col_cpu', { default: 'CPU' })}</th>
                                <th scope="col" class="pb-2 text-right font-bold">{$_('settings.system_health.col_accelerator', { default: 'Accelerator' })}</th>
                                <th scope="col" class="pb-2 text-right font-bold">{$_('settings.system_health.col_memory', { default: 'Memory' })}</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-200/70 dark:divide-slate-700/50">
                            {#each rows as row (row.role)}
                                {#if row.role !== 'idle'}
                                    <tr data-system-health-row={row.role}>
                                        <td class="py-2 pr-3">
                                            <span class="inline-flex items-center gap-2">
                                                <span class="{swatch[row.role]} inline-block h-2.5 w-2.5 rounded-sm" aria-hidden="true"></span>
                                                <span class="font-semibold text-slate-800 dark:text-slate-100" class:italic={row.role === 'other_host'}>{roleLabel(row)}</span>
                                                {#if memberNote(row)}
                                                    <span class="text-xs text-slate-500 dark:text-slate-400">{memberNote(row)}</span>
                                                {/if}
                                            </span>
                                            {#if row.role === 'other_host'}
                                                <span class="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
                                                    {$_('settings.system_health.role_other_host_note', { default: 'Not this app. Cannot be named without the Docker socket.' })}
                                                </span>
                                            {/if}
                                        </td>
                                        <td class="py-2 text-right font-semibold tabular-nums text-slate-800 dark:text-slate-100">{formatPercent(row.cpuPercent) ?? '—'}</td>
                                        <td class="py-2 text-right text-slate-500 dark:text-slate-400">
                                            {#if row.acceleratorLabels.length > 0}
                                                <span class="block font-semibold text-slate-800 dark:text-slate-100">{row.acceleratorLabels.join(', ')}</span>
                                                <span class="block text-[10px] uppercase tracking-wide">{$_('settings.system_health.accelerator_loaded', { default: 'loaded' })}</span>
                                            {:else}
                                                —
                                            {/if}
                                        </td>
                                        <td class="py-2 text-right tabular-nums text-slate-500 dark:text-slate-400">{formatBytes(row.rssBytes) ?? '—'}</td>
                                    </tr>
                                {/if}
                            {/each}
                        </tbody>
                    </table>
                    <p class="mt-3 text-xs text-slate-500 dark:text-slate-400">
                        {$_('settings.system_health.note', {
                            default: "CPU and memory are read from this container's own processes. Accelerator cells name the runtime a classifier worker actually loaded; NPU utilisation is device-wide and cannot be divided honestly between workers. Anything else on the host is measured only as the CPU remainder."
                        })}
                    </p>
                </div>
            {/if}
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

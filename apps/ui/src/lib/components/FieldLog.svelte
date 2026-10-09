<script lang="ts">
    import FieldLogVisitRow from './FieldLogVisitRow.svelte';
    import FilteredFramePreview from './FilteredFramePreview.svelte';
    import type { Detection } from '../api';
    import type { DetectionVisit } from '../utils/visit-grouping';
    import type { HealthTimelineRow } from '../utils/health-timeline';
    import { namesCameras } from '../utils/field-log';
    import { formatTime } from '../utils/datetime';
    import { _ } from 'svelte-i18n';

    type FieldLogRow = Exclude<HealthTimelineRow, { kind: 'fault' }>;

    interface Props {
        visits?: DetectionVisit[];
        /**
         * Optional pre-merged visit and expected-filter rows for legacy callers.
         * Operational fault history belongs to HealthActivityTimeline instead.
         */
        rows?: FieldLogRow[];
        /** Off when the surrounding page already titles the list and states its window. */
        showHeader?: boolean;
        /** Empty-state wording, for pages whose window is not "today". */
        emptyMessage?: string | null;
        /** Truncation wording, for the same reason. */
        hiddenLabel?: string | null;
        /** Visits in the window beyond the ones shown, so truncation is stated. */
        hiddenCount?: number;
        /** Identifying requires owner access, so guests get a read-only row. */
        canIdentify?: boolean;
        /** The first read is still running: nothing is known yet, so nothing is claimed. */
        loading?: boolean;
        /** The read failed before any visit arrived; an empty log would claim a quiet day. */
        unavailable?: boolean;
        onselect?: (detection: Detection) => void;
        onidentify?: (detection: Detection) => void;
        onplay?: (detection: Detection) => void;
        onseeall?: () => void;
        onretry?: () => void;
    }

    let {
        visits = [],
        rows,
        showHeader = true,
        emptyMessage = null,
        hiddenLabel = null,
        hiddenCount = 0,
        canIdentify = false,
        loading = false,
        unavailable = false,
        onselect,
        onidentify,
        onplay,
        onseeall,
        onretry
    }: Props = $props();

    const renderRows = $derived<FieldLogRow[]>(
        rows ?? visits.map((visit) => ({ kind: 'visit' as const, key: `visit:${visit.key}`, at: 0, visit }))
    );
    const showCamera = $derived(
        namesCameras(renderRows.flatMap((row) => (row.kind === 'visit' ? [row.visit] : [])))
    );

    /**
     * Every row, every capture inside a row and every loading placeholder shares these columns:
     * time, thread, photo, name, [camera], score, action. One template is what keeps a capture's
     * time, node and score under its visit's.
     */
    const grid = $derived(
        showCamera
            ? 'grid grid-cols-[3.25rem_0.6rem_auto_minmax(0,1fr)_auto] gap-x-2 sm:grid-cols-[5rem_0.75rem_auto_minmax(0,1fr)_auto_auto_8rem] sm:gap-x-3'
            : 'grid grid-cols-[3.25rem_0.6rem_auto_minmax(0,1fr)_auto] gap-x-2 sm:grid-cols-[5rem_0.75rem_auto_minmax(0,1fr)_auto_8rem] sm:gap-x-3'
    );

    function quietScore(score: number | null): string {
        return score === null ? '' : `${Math.round(score * 100)}%`;
    }

    // Placeholders vary their name widths so the block reads as rows, not as one slab.
    const PLACEHOLDER_NAMES = ['w-32', 'w-24', 'w-36', 'w-28'];
</script>

<section class="panel space-y-4" data-dashboard-field-log>
    {#if showHeader}
    <header class="flex items-end justify-between gap-3">
        <div class="min-w-0">
            <h2 class="font-display text-2xl font-bold text-slate-950 dark:text-white">
                {$_('dashboard.field_log.title', { default: 'Field log' })}
            </h2>
            <p class="hidden text-sm text-slate-500 sm:block dark:text-slate-400">
                {$_('dashboard.field_log.subtitle', {
                    default: 'Repeat frames of the same bird are folded into one visit'
                })}
            </p>
        </div>
        <button
            onclick={() => onseeall?.()}
            class="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl px-2 py-2 text-sm font-semibold text-brand-700 transition-colors hover:bg-brand-50 focus-ring sm:px-3 dark:text-brand-300 dark:hover:bg-brand-950/40"
        >
            {$_('dashboard.see_full_history')}
            <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" />
            </svg>
        </button>
    </header>
    {/if}

    {#if loading && renderRows.length === 0}
        <!-- The shape of the rows that are coming, at their height, so nothing moves when they land. -->
        <p role="status" class="sr-only">{$_('dashboard.field_log.loading', { default: 'Loading visits…' })}</p>
        <ol class="space-y-0.5" aria-busy="true" data-field-log-loading>
            {#each PLACEHOLDER_NAMES as nameWidth (nameWidth)}
                <li
                    class="{grid} items-center rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 sm:py-2.5 dark:border-slate-700/40"
                    aria-hidden="true"
                    data-field-log-placeholder
                >
                    <span class="h-3 w-10 rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                    <span class="relative flex h-full justify-center">
                        <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
                        <span class="relative my-auto h-2 w-2 rounded-full bg-slate-300 ring-2 ring-white dark:bg-slate-600 dark:ring-slate-900"></span>
                    </span>
                    <span class="grid min-h-11 min-w-11 place-items-center">
                        <span class="h-9 w-9 rounded-lg bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                    </span>
                    <span class="min-w-0 space-y-1.5">
                        <span class="block h-3.5 max-w-full rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60 {nameWidth}" data-loading-placeholder></span>
                        <span class="block h-2.5 w-20 max-w-full rounded bg-slate-200/60 animate-pulse motion-reduce:animate-none dark:bg-slate-700/40" data-loading-placeholder></span>
                    </span>
                    <span class="hidden flex-col items-end gap-1 sm:flex">
                        <span class="h-3 w-8 rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                        <span class="h-[3px] w-16 rounded-full bg-slate-200 dark:bg-slate-700"></span>
                    </span>
                    <span class="flex justify-end">
                        <span class="h-11 w-11 rounded-xl sm:w-14"></span>
                    </span>
                </li>
            {/each}
        </ol>
    {:else if unavailable && renderRows.length === 0}
        <div class="flex flex-col items-center justify-center gap-3 border-y border-dashed border-slate-200 py-10 text-center dark:border-slate-700/50" data-field-log-unavailable>
            <p class="max-w-sm text-sm font-medium text-slate-600 dark:text-slate-300">
                {$_('dashboard.field_log.unavailable', {
                    default: 'Visits could not be loaded. The dashboard tries again every minute.'
                })}
            </p>
            {#if onretry}
                <button type="button" class="btn btn-secondary min-h-11 px-4 text-xs" onclick={() => onretry?.()}>
                    {$_('dashboard.field_log.retry', { default: 'Try again' })}
                </button>
            {/if}
        </div>
    {:else if renderRows.length === 0}
        <div class="flex flex-col items-center justify-center border-y border-dashed border-slate-200 py-12 text-center dark:border-slate-700/50">
            <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800/50 dark:text-slate-500">
                <svg class="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" />
                </svg>
            </div>
            <p class="font-medium text-slate-500 dark:text-slate-400">
                {emptyMessage ?? $_('dashboard.waiting_first_visitor')}
            </p>
        </div>
    {:else}
        <ol class="space-y-0.5">
            {#each renderRows as row (row.key)}
                {#if row.kind === 'filtered'}
                    {@const drop = row.drop}
                    <li
                        class="{grid} items-center gap-y-1 rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 sm:py-2.5 dark:border-slate-700/40"
                        data-field-log-row
                        data-row-kind="filtered"
                        data-needs-review="false"
                    >
                        <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">
                            {drop.timestamp ? formatTime(drop.timestamp) : ''}
                        </span>

                        <span class="relative flex h-full justify-center" aria-hidden="true">
                            <!-- The spine runs behind the nodes so the day reads as one thread. -->
                            <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
                            <span class="relative my-auto h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400 ring-2 ring-white dark:bg-slate-500 dark:ring-slate-900"></span>
                        </span>

                        <FilteredFramePreview eventId={drop.eventId} label={drop.label} />

                        <div class="min-w-0">
                            <p class="truncate text-sm font-semibold italic text-slate-700 dark:text-slate-200">
                                {drop.label ?? $_('common.unknown_species', { default: 'Unknown species' })}
                            </p>
                            <p class="truncate text-[11px] font-medium text-slate-500 dark:text-slate-400">
                                {$_(`jobs.errors_drop_reason_row.${drop.reason}`, {
                                    default: $_('jobs.errors_drop_reason_row.filter_low_confidence', {
                                        default: 'Not recorded, below your naming threshold'
                                    })
                                })}
                            </p>
                        </div>

                        {#if showCamera}<span class="hidden sm:inline-flex"></span>{/if}

                        <span class="hidden flex-col items-end gap-1 sm:flex">
                            <span class="text-xs font-bold tabular-nums text-slate-500 dark:text-slate-400">
                                {quietScore(drop.score)}
                            </span>
                            <span class="h-[3px] w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                <span
                                    class="block h-full rounded-full bg-slate-400 dark:bg-slate-500"
                                    style="width: {Math.round((drop.score ?? 0) * 100)}%"
                                ></span>
                            </span>
                        </span>

                        <span class="flex justify-end"></span>
                    </li>
                {:else}
                    <FieldLogVisitRow visit={row.visit} {grid} {showCamera} {canIdentify} {onselect} {onidentify} {onplay} />
                {/if}
            {/each}
        </ol>

        {#if hiddenCount > 0}
            <button
                class="flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl text-xs font-semibold text-slate-500 transition-colors hover:bg-slate-100 focus-ring dark:text-slate-400 dark:hover:bg-slate-800/60"
                onclick={() => onseeall?.()}
                data-field-log-more
            >
                {hiddenLabel ??
                    $_('dashboard.field_log.earlier', {
                        values: { count: hiddenCount },
                        default: '{count} earlier visits today'
                    })}
                <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M10 5v10m0 0-4-4m4 4 4-4" />
                </svg>
            </button>
        {/if}
    {/if}
</section>

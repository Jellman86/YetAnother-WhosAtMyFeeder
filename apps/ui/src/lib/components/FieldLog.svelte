<script lang="ts">
    import FieldLogVisitRow from './FieldLogVisitRow.svelte';
    import FieldLogGardenRow from './FieldLogGardenRow.svelte';
    import FilteredFramePreview from './FilteredFramePreview.svelte';
    import type { Detection } from '../api';
    import type { GardenCapture, GardenServerVisit } from '../api/garden';
    import type { GardenCaptureScope } from '../utils/garden-visit-viewer.svelte';
    import type { DetectionVisit } from '../utils/visit-grouping';
    import { FIELD_LOG_CELL as cell, FIELD_LOG_GRID as grid, namesCameras, type FieldLogRow } from '../utils/field-log';
    import { formatTime } from '../utils/datetime';
    import { _ } from 'svelte-i18n';

    interface Props {
        visits?: DetectionVisit[];
        /** Pre-merged rows: bird visits with Garden visits or expected-filter drops between them. */
        rows?: FieldLogRow[];
        /** Off when the surrounding page already titles the list and states its window. */
        showHeader?: boolean;
        /** Empty-state wording, for pages whose window is not the desk's last 24 hours. */
        emptyMessage?: string | null;
        /** Truncation wording, for the same reason. */
        hiddenLabel?: string | null;
        /** Visits in the window beyond the ones shown, so truncation is stated. */
        hiddenCount?: number;
        /** Placeholder rows while loading: as many as the log will show, so nothing moves when they land. */
        placeholderRows?: number;
        /** Identifying requires owner access, so guests get a read-only row. */
        canIdentify?: boolean;
        /** The first read is still running: nothing is known yet, so nothing is claimed. */
        loading?: boolean;
        /** The read failed before any visit arrived; an empty log would claim a quiet day. */
        unavailable?: boolean;
        /** Garden visits were asked for and could not be read, so their absence is not a quiet garden. */
        gardenUnavailable?: boolean;
        onselect?: (detection: Detection) => void;
        onidentify?: (detection: Detection) => void;
        onplay?: (detection: Detection) => void;
        ongardenopen?: (visit: GardenServerVisit) => void;
        gardenScope?: GardenCaptureScope;
        ongardencapture?: (visit: GardenServerVisit, capture: GardenCapture, index: number) => void;
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
        placeholderRows = 4,
        canIdentify = false,
        loading = false,
        unavailable = false,
        gardenUnavailable = false,
        onselect,
        onidentify,
        onplay,
        ongardenopen,
        gardenScope,
        ongardencapture,
        onseeall,
        onretry
    }: Props = $props();

    const renderRows = $derived<FieldLogRow[]>(
        rows ?? visits.map((visit) => ({ kind: 'visit' as const, key: `visit:${visit.key}`, at: 0, visit }))
    );
    const showCamera = $derived(
        namesCameras(renderRows.flatMap((row) =>
            row.kind === 'visit' ? [row.visit] : row.kind === 'garden' ? [{ camera: row.visit.representative.camera }] : []
        ))
    );

    function quietScore(score: number | null): string {
        return score === null ? '' : `${Math.round(score * 100)}%`;
    }

    // Placeholders vary their name widths so the block reads as rows, not as one slab.
    const PLACEHOLDER_NAMES = ['w-32', 'w-24', 'w-36', 'w-28'];
    const placeholders = $derived(
        Array.from({ length: placeholderRows }, (_, index) => ({ index, nameWidth: PLACEHOLDER_NAMES[index % PLACEHOLDER_NAMES.length] }))
    );
</script>

<section class="field-log space-y-4 sm:panel" data-dashboard-field-log>
    {#if showHeader}
    <header class="flex flex-wrap items-end justify-between gap-x-3">
        <div class="min-w-0">
            <h2 class="font-display text-2xl font-bold text-slate-950 dark:text-white">
                {$_('dashboard.field_log.title', { default: 'Field log' })}
            </h2>
            <p class="hidden text-sm text-slate-500 log-wide:block dark:text-slate-400">
                {$_('dashboard.field_log.subtitle', {
                    default: 'Repeat frames of the same bird are folded into one visit'
                })}
            </p>
        </div>
        <button
            onclick={() => onseeall?.()}
            class="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl px-2 py-2 text-sm font-semibold text-brand-700 transition-colors hover:bg-brand-50 focus-ring log-wide:px-3 dark:text-brand-300 dark:hover:bg-brand-950/40"
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
            {#each placeholders as { index, nameWidth } (index)}
                <li
                    class="{grid} items-center gap-y-1 rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 log-wide:py-2.5 dark:border-slate-700/40"
                    aria-hidden="true"
                    data-field-log-placeholder
                >
                    <span class="h-3 w-10 rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60 {cell.time}" data-loading-placeholder></span>
                    <span class="relative flex h-full justify-center {cell.node}">
                        <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
                        <span class="relative my-auto h-2 w-2 rounded-full bg-slate-300 ring-2 ring-white dark:bg-slate-600 dark:ring-slate-900"></span>
                    </span>
                    <span class="grid min-h-11 min-w-11 place-items-center {cell.photo}">
                        <span class="h-9 w-9 rounded-lg bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                    </span>
                    <span class="min-w-0 space-y-1.5 {cell.body}">
                        <span class="block h-3.5 max-w-full rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60 {nameWidth}" data-loading-placeholder></span>
                        <span class="block h-2.5 w-20 max-w-full rounded bg-slate-200/60 animate-pulse motion-reduce:animate-none dark:bg-slate-700/40" data-loading-placeholder></span>
                    </span>
                    <span class="hidden flex-col items-end gap-1 log-wide:flex {cell.score}">
                        <span class="h-3 w-8 rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                        <span class="h-[3px] w-16 rounded-full bg-slate-200 dark:bg-slate-700"></span>
                    </span>
                    <span class="flex justify-end {cell.action}">
                        <span class="h-11 w-11 rounded-xl log-wide:w-14"></span>
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
                {emptyMessage ?? $_('dashboard.waiting_first_visitor', { default: 'No visits in the last 24 hours. New visits appear here as they arrive.' })}
            </p>
        </div>
    {:else}
        <ol class="space-y-0.5">
            {#each renderRows as row (row.key)}
                {#if row.kind === 'filtered'}
                    {@const drop = row.drop}
                    <li
                        class="{grid} items-center gap-y-1 rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 log-wide:py-2.5 dark:border-slate-700/40"
                        data-field-log-row
                        data-row-kind="filtered"
                        data-needs-review="false"
                    >
                        <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400 {cell.time}">
                            {drop.timestamp ? formatTime(drop.timestamp) : ''}
                        </span>

                        <span class="relative flex h-full justify-center {cell.node}" aria-hidden="true">
                            <!-- The spine runs behind the nodes so the day reads as one thread. -->
                            <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
                            <span class="relative my-auto h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400 ring-2 ring-white dark:bg-slate-500 dark:ring-slate-900"></span>
                        </span>

                        <span class="flex {cell.photo}"><FilteredFramePreview eventId={drop.eventId} label={drop.label} /></span>

                        <div class="min-w-0 {cell.body}">
                            <p class="truncate text-sm font-semibold italic text-slate-700 dark:text-slate-200">
                                {drop.label ?? $_('common.unknown_species', { default: 'Unknown species' })}
                            </p>
                            <p class="truncate text-2xs font-medium text-slate-500 dark:text-slate-400">
                                {$_(`jobs.errors_drop_reason_row.${drop.reason}`, {
                                    default: $_('jobs.errors_drop_reason_row.filter_low_confidence', {
                                        default: 'Not recorded, below your naming threshold'
                                    })
                                })}
                            </p>
                        </div>

                        <span class="hidden flex-col items-end gap-1 log-wide:flex">
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

                    </li>
                {:else if row.kind === 'garden'}
                    <FieldLogGardenRow visit={row.visit} {grid} {showCamera} scope={gardenScope}
                        onopen={(visit) => ongardenopen?.(visit)} oncapture={ongardencapture ? (capture, index) => ongardencapture?.(row.visit, capture, index) : undefined} />
                {:else}
                    <FieldLogVisitRow visit={row.visit} {grid} {showCamera} {canIdentify} {onselect} {onidentify} {onplay} />
                {/if}
            {/each}
        </ol>

        {#if hiddenCount > 0}
            <button
                class="flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl px-2 py-2 text-xs font-semibold text-slate-500 transition-colors hover:bg-slate-100 focus-ring dark:text-slate-400 dark:hover:bg-slate-800/60"
                onclick={() => onseeall?.()}
                data-field-log-more
            >
                <!-- It leaves the page for the Explorer, so it says so and points onward, not down. -->
                <span class="min-w-0 text-center">
                    {hiddenLabel ??
                        $_('dashboard.field_log.earlier', {
                            values: { count: hiddenCount },
                            default: '{count} earlier visits in the last 24 hours, open in Explorer'
                        })}
                </span>
                <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" />
                </svg>
            </button>
        {/if}
    {/if}

    {#if gardenUnavailable && !loading}
        <p class="px-2 text-xs text-slate-500 dark:text-slate-400" data-field-log-garden-unavailable>
            {$_('dashboard.field_log.garden_unavailable', {
                default: 'Garden visits could not be loaded, so only birds are shown. The dashboard tries again every minute.'
            })}
        </p>
    {/if}
</section>

<style>
    /* The container the `log-wide` and `log-narrow` variants measure, in rem, so the rows follow
       the reader's text size as well as the column's width. */
    .field-log {
        container: field-log / inline-size;
    }
</style>

<script lang="ts">
    import DetectionPreview from './DetectionPreview.svelte';
    import FilteredFramePreview from './FilteredFramePreview.svelte';
    import type { Detection } from '../api';
    import type { DetectionVisit } from '../utils/visit-grouping';
    import type { HealthTimelineRow } from '../utils/health-timeline';
    import { formatTime } from '../utils/datetime';
    import { getBirdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { _ } from 'svelte-i18n';

    interface Props {
        visits?: DetectionVisit[];
        /**
         * Pre-merged rows, used by the Health page so kept visits and filtered
         * frames share one thread. When absent the visits prop is rendered as
         * before, so the dashboard is unaffected.
         */
        rows?: HealthTimelineRow[];
        /** Filtered frames carry no record to open, so their action is suppressed. */
        onopenfiltered?: (eventId: string) => void;
        /** Visits in the window beyond the ones shown, so truncation is stated. */
        hiddenCount?: number;
        /** Identifying requires owner access, so guests get a read-only row. */
        canIdentify?: boolean;
        loading?: boolean;
        onselect?: (detection: Detection) => void;
        onidentify?: (detection: Detection) => void;
        onseeall?: () => void;
    }

    let {
        visits = [],
        rows,
        onopenfiltered,
        hiddenCount = 0,
        canIdentify = false,
        loading = false,
        onselect,
        onidentify,
        onseeall
    }: Props = $props();

    const renderRows = $derived<HealthTimelineRow[]>(
        rows ?? visits.map((visit) => ({ kind: 'visit' as const, key: `visit:${visit.key}`, at: 0, visit }))
    );

    function names(detection: Detection): { primary: string; secondary: string | null } {
        return getBirdNames(
            detection,
            settingsStore.displayCommonNames,
            settingsStore.scientificNamePrimary
        );
    }

    function span(visit: DetectionVisit): string {
        const start = formatTime(visit.startTime);
        const end = formatTime(visit.endTime);
        return start === end ? end : `${start}–${end}`;
    }

    function scoreTone(score: number): string {
        if (score < 0.6) return 'text-accent-700 dark:text-accent-300';
        if (score < 0.85) return 'text-brand-700 dark:text-brand-300';
        return 'text-emerald-700 dark:text-emerald-300';
    }

    function quietScore(score: number | null): string {
        return score === null ? '' : `${Math.round(score * 100)}%`;
    }

    function barTone(score: number): string {
        if (score < 0.6) return 'bg-accent-500';
        if (score < 0.85) return 'bg-brand-500';
        return 'bg-emerald-500';
    }
</script>

<section class="space-y-4" data-dashboard-field-log>
    <header class="flex items-end justify-between gap-3 border-b border-slate-200/70 pb-3 dark:border-slate-700/50">
        <div class="min-w-0">
            <h2 class="font-display text-xl font-bold text-slate-950 dark:text-white">
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

    {#if loading && visits.length === 0}
        <div class="space-y-2" data-field-log-loading>
            {#each Array(5) as _unused, index (index)}
                <div class="h-16 animate-pulse rounded-xl bg-slate-100/80 dark:bg-slate-800/50"></div>
            {/each}
        </div>
    {:else if renderRows.length === 0}
        <div class="flex flex-col items-center justify-center border-y border-dashed border-slate-200 py-12 text-center dark:border-slate-700/50">
            <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800/50 dark:text-slate-500">
                <svg class="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" />
                </svg>
            </div>
            <p class="font-medium text-slate-500 dark:text-slate-400">
                {$_('dashboard.waiting_first_visitor')}
            </p>
        </div>
    {:else}
        <ol class="space-y-0.5">
            {#each renderRows as row (row.key)}
                {#if row.kind === 'filtered'}
                    {@const drop = row.drop}
                    <li
                        class="grid grid-cols-[3.4rem_0.6rem_auto_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-1 rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 sm:grid-cols-[4.5rem_0.75rem_auto_minmax(0,1fr)_auto_auto_5rem] sm:gap-x-3 sm:py-2.5 dark:border-slate-700/40"
                        data-field-log-row
                        data-row-kind="filtered"
                        data-needs-review="false"
                    >
                        <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">
                            {drop.timestamp ? formatTime(drop.timestamp) : ''}
                        </span>

                        <span class="relative flex h-full justify-center" aria-hidden="true">
                            <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
                            <span class="relative mt-[0.4rem] h-1.5 w-1.5 shrink-0 self-start rounded-full bg-slate-400 ring-2 ring-white dark:bg-slate-500 dark:ring-slate-900"></span>
                        </span>

                        <FilteredFramePreview eventId={drop.eventId} label={drop.label} onopen={() => onopenfiltered?.(drop.eventId)} />

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

                        <span class="hidden sm:inline-flex"></span>

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
                {@const visit = row.visit}
                {@const naming = names(visit.lead)}
                {@const score = visit.best.score ?? 0}
                <li
                    class="grid grid-cols-[3.4rem_0.6rem_auto_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-1 rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 sm:grid-cols-[4.5rem_0.75rem_auto_minmax(0,1fr)_auto_auto_5rem] sm:gap-x-3 sm:py-2.5 dark:border-slate-700/40"
                    class:bg-gradient-to-r={visit.needsReview}
                    class:from-accent-50={visit.needsReview}
                    class:dark:from-accent-950={visit.needsReview}
                    data-field-log-row
                    data-needs-review={visit.needsReview ? 'true' : 'false'}
                >
                    <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">
                        {span(visit)}
                    </span>

                    <span class="relative flex h-full justify-center" aria-hidden="true">
                        <!-- The spine runs behind the nodes so the day reads as one thread. -->
                        <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
                        <span
                            class="relative mt-[0.4rem] h-1.5 w-1.5 shrink-0 self-start rounded-full ring-2 ring-white dark:ring-slate-900 {visit.needsReview
                                ? 'bg-accent-500'
                                : 'bg-brand-500'}"
                        ></span>
                    </span>

                    <DetectionPreview
                        detection={visit.best}
                        frames={visit.frames}
                        frameCount={visit.frames.length}
                        primaryName={naming.primary}
                        secondaryName={naming.secondary}
                        onopen={(frame) => onselect?.(frame)}
                    />

                    <div class="min-w-0">
                        <p class="flex items-baseline gap-1.5">
                            <span class="truncate text-sm font-semibold text-slate-900 dark:text-white">
                                {naming.primary}
                            </span>
                            {#if visit.frames.length > 1}
                                <span class="shrink-0 text-xs font-medium text-slate-500 dark:text-slate-400">
                                    ×{visit.frames.length}
                                </span>
                            {/if}
                        </p>
                        <p class="text-[11px] tabular-nums text-slate-500 sm:hidden dark:text-slate-400">
                            {Math.round(score * 100)}% &middot; {visit.camera}
                        </p>
                        {#if visit.needsReview}
                            <p class="truncate text-[11px] font-medium text-accent-700 dark:text-accent-300">
                                {$_('dashboard.field_log.needs_name', {
                                    default: 'Below the naming threshold'
                                })}
                            </p>
                        {:else if naming.secondary}
                            <p class="truncate text-[11px] italic text-slate-500 dark:text-slate-400">
                                {naming.secondary}
                            </p>
                        {/if}
                    </div>

                    <span class="hidden shrink-0 items-center gap-1.5 rounded-full border border-slate-200 px-2 py-0.5 text-[11px] text-slate-500 sm:inline-flex dark:border-slate-700 dark:text-slate-400">
                        <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M4 8h11v8H4z" />
                            <path stroke-linecap="round" stroke-linejoin="round" d="m15 12 5-3v6l-5-3z" />
                        </svg>
                        {visit.camera}
                    </span>

                    <span class="hidden flex-col items-end gap-1 sm:flex">
                        <span class="text-xs font-bold tabular-nums {scoreTone(score)}">
                            {Math.round(score * 100)}%
                        </span>
                        <span class="h-[3px] w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                            <span
                                class="block h-full rounded-full {barTone(score)}"
                                style="width: {Math.round(score * 100)}%"
                            ></span>
                        </span>
                    </span>

                    <span class="flex justify-end">
                        {#if visit.needsReview && canIdentify}
                            <button
                                class="btn btn-primary min-h-11 px-2.5 py-1.5 text-xs sm:px-3"
                                onclick={() => onidentify?.(visit.best)}
                            >
                                {$_('dashboard.field_log.identify', { default: 'Identify' })}
                            </button>
                        {:else}
                            <button
                                class="btn btn-ghost min-h-11 px-2.5 py-1.5 text-xs sm:px-3"
                                onclick={() => onselect?.(visit.best)}
                            >
                                {$_('dashboard.field_log.open', { default: 'Open' })}
                            </button>
                        {/if}
                    </span>
                </li>
                {/if}
            {/each}
        </ol>

        {#if hiddenCount > 0}
            <button
                class="flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl text-xs font-semibold text-slate-500 transition-colors hover:bg-slate-100 focus-ring dark:text-slate-400 dark:hover:bg-slate-800/60"
                onclick={() => onseeall?.()}
                data-field-log-more
            >
                {$_('dashboard.field_log.earlier', {
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

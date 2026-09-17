<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Detection } from '../api';
    import { getBirdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { formatTime } from '../utils/datetime';
    import type { HealthTimelineRow } from '../utils/health-timeline';
    import DetectionPreview from './DetectionPreview.svelte';
    import FilteredFramePreview from './FilteredFramePreview.svelte';

    interface Props {
        rows: HealthTimelineRow[];
        emptyMessage: string;
        hiddenCount?: number;
        hiddenLabel?: string | null;
        loading?: boolean;
        onselect?: (detection: Detection) => void;
    }

    let {
        rows,
        emptyMessage,
        hiddenCount = 0,
        hiddenLabel = null,
        loading = false,
        onselect
    }: Props = $props();

    function names(detection: Detection): { primary: string; secondary: string | null } {
        return getBirdNames(
            detection,
            settingsStore.displayCommonNames,
            settingsStore.scientificNamePrimary
        );
    }

    function span(row: Extract<HealthTimelineRow, { kind: 'visit' }>): string {
        const start = formatTime(row.visit.startTime);
        const end = formatTime(row.visit.endTime);
        return start === end ? end : `${start}–${end}`;
    }

    function scoreTone(score: number): string {
        if (score < 0.6) return 'text-accent-700 dark:text-accent-300';
        if (score < 0.85) return 'text-brand-700 dark:text-brand-300';
        return 'text-success-700 dark:text-success-300';
    }

    function barTone(score: number): string {
        if (score < 0.6) return 'bg-accent-500';
        if (score < 0.85) return 'bg-brand-500';
        return 'bg-success-500';
    }

    function reasonFallback(reason: string): string {
        const words = reason.replaceAll('_', ' ').trim();
        return words.length > 0 ? words.charAt(0).toUpperCase() + words.slice(1) : reason;
    }

    function dropToneClass(isFault: boolean): string {
        return isFault
            ? 'border-l-rose-400 bg-rose-50/35 dark:border-l-rose-700 dark:bg-rose-950/10'
            : 'border-l-slate-300 bg-slate-50/55 dark:border-l-slate-600 dark:bg-slate-900/35';
    }
</script>

<div
    class="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/50 dark:border-slate-700/60 dark:bg-slate-900/20"
    data-health-activity-timeline
>
    <div
        class="flex flex-wrap gap-x-4 gap-y-2 border-b border-slate-200/70 bg-slate-50/80 px-4 py-3 text-xs font-semibold text-slate-600 dark:border-slate-700/50 dark:bg-slate-900/60 dark:text-slate-300"
        role="group"
        aria-label={$_('jobs.errors_activity_key', { default: 'Activity key' })}
    >
        <span class="inline-flex items-center gap-1.5">
            <span class="h-2 w-2 rounded-full bg-brand-500" aria-hidden="true"></span>
            {$_('jobs.errors_activity_recorded', { default: 'Recorded visit' })}
        </span>
        <span class="inline-flex items-center gap-1.5">
            <span class="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500" aria-hidden="true"></span>
            {$_('jobs.errors_activity_filtered', { default: 'Filtered out' })}
        </span>
        <span class="inline-flex items-center gap-1.5">
            <span class="h-2 w-2 rounded-full bg-rose-500" aria-hidden="true"></span>
            {$_('jobs.errors_activity_fault', { default: 'Pipeline fault' })}
        </span>
    </div>

    {#if loading && rows.length === 0}
        <div class="space-y-px p-2" data-health-activity-loading>
            {#each Array(5) as _unused, index (index)}
                <div class="h-[4.5rem] animate-pulse rounded-xl bg-slate-100/80 dark:bg-slate-800/50"></div>
            {/each}
        </div>
    {:else if rows.length === 0}
        <div class="flex flex-col items-center justify-center px-6 py-12 text-center">
            <div class="mb-4 grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 12h3l2-5 4 10 2-5h5" />
                </svg>
            </div>
            <p class="max-w-lg text-sm font-medium leading-6 text-slate-500 dark:text-slate-400">{emptyMessage}</p>
        </div>
    {:else}
        <ol class="divide-y divide-slate-200/70 dark:divide-slate-700/45">
            {#each rows as row (row.key)}
                {#if row.kind === 'visit'}
                    {@const visit = row.visit}
                    {@const naming = names(visit.lead)}
                    {@const score = visit.best.score ?? 0}
                    <li
                        class="relative grid grid-cols-[3rem_auto_minmax(0,1fr)] items-center gap-x-2.5 gap-y-1 border-l-[3px] border-l-brand-400 bg-brand-50/25 px-2 py-2.5 sm:grid-cols-[4.5rem_0.75rem_auto_minmax(0,1fr)_4.5rem_7.5rem] sm:gap-x-3 sm:px-3 dark:border-l-brand-600 dark:bg-brand-950/10"
                        data-health-activity-row
                        data-row-kind="recorded"
                    >
                        <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">{span(row)}</span>
                        <span class="relative hidden h-full justify-center sm:flex" aria-hidden="true">
                            <span class="absolute inset-y-[-0.8rem] w-px bg-slate-200 dark:bg-slate-700"></span>
                            <span class="relative mt-[0.45rem] h-2 w-2 rounded-full bg-brand-500 ring-2 ring-white dark:ring-slate-900"></span>
                        </span>
                        <DetectionPreview
                            detection={visit.best}
                            frames={visit.frames}
                            frameCount={visit.frames.length}
                            primaryName={naming.primary}
                            secondaryName={naming.secondary}
                            onopen={(frame) => onselect?.(frame)}
                        />
                        <div class="min-w-0 pr-12 sm:pr-0">
                            <p class="flex min-w-0 items-baseline justify-between gap-2">
                                <span class="truncate text-sm font-semibold text-slate-950 dark:text-white">{naming.primary}</span>
                                <span class="shrink-0 text-xs font-bold tabular-nums sm:hidden {scoreTone(score)}">{Math.round(score * 100)}%</span>
                            </p>
                            <p class="flex flex-wrap items-center gap-x-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                                <span class="font-semibold text-brand-700 dark:text-brand-300">
                                    {$_('jobs.errors_activity_recorded', { default: 'Recorded visit' })}
                                </span>
                                <span aria-hidden="true">·</span>
                                <span>{visit.camera}</span>
                                {#if naming.secondary}
                                    <span aria-hidden="true">·</span>
                                    <span class="italic">{naming.secondary}</span>
                                {/if}
                                {#if visit.audioConfirmed}
                                    <span aria-hidden="true">·</span>
                                    <span class="font-medium text-brand-700 dark:text-brand-300">
                                        {$_('detection.fact_heard_yes', { default: 'matching call' })}
                                    </span>
                                {/if}
                            </p>
                        </div>
                        <span class="hidden flex-col items-end gap-1 sm:flex">
                            <span class="text-xs font-bold tabular-nums {scoreTone(score)}">{Math.round(score * 100)}%</span>
                            <span class="h-[3px] w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                <span class="block h-full rounded-full {barTone(score)}" style="width: {Math.round(score * 100)}%"></span>
                            </span>
                        </span>
                        <button
                            type="button"
                            class="btn btn-ghost absolute right-2 top-1/2 h-11 min-h-11 w-11 -translate-y-1/2 justify-self-end px-0 py-1.5 text-xs sm:static sm:h-auto sm:w-auto sm:translate-y-0 sm:px-3"
                            aria-label="{$_('jobs.errors_activity_view_record', { default: 'View record' })}: {naming.primary}"
                            onclick={() => onselect?.(visit.best)}
                        >
                            <span class="hidden sm:inline">{$_('jobs.errors_activity_view_record', { default: 'View record' })}</span>
                            <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" />
                            </svg>
                        </button>
                    </li>
                {:else}
                    {@const drop = row.drop}
                    {@const isFault = row.kind === 'fault'}
                    <li
                        class="grid grid-cols-[3rem_auto_minmax(0,1fr)] items-center gap-x-2.5 gap-y-1 border-l-[3px] px-2 py-2.5 sm:grid-cols-[4.5rem_0.75rem_auto_minmax(0,1fr)_4.5rem] sm:gap-x-3 sm:px-3 {dropToneClass(isFault)}"
                        data-health-activity-row
                        data-row-kind={isFault ? 'fault' : 'filtered'}
                    >
                        <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">
                            {drop.timestamp ? formatTime(drop.timestamp) : ''}
                        </span>
                        <span class="relative hidden h-full justify-center sm:flex" aria-hidden="true">
                            <span class="absolute inset-y-[-0.8rem] w-px bg-slate-200 dark:bg-slate-700"></span>
                            <span class="relative mt-[0.45rem] h-2 w-2 rounded-full ring-2 ring-white dark:ring-slate-900 {isFault ? 'bg-rose-500' : 'bg-slate-400 dark:bg-slate-500'}"></span>
                        </span>
                        <FilteredFramePreview
                            eventId={drop.eventId}
                            label={drop.label}
                            previewLabel={isFault
                                ? $_('jobs.errors_fault_preview', {
                                    values: { species: drop.label ?? $_('jobs.errors_activity_unidentified', { default: 'Unidentified detection' }) },
                                    default: 'Preview the failed detection frame for {species}'
                                })
                                : null}
                        />
                        <div class="min-w-0">
                            <p class="flex min-w-0 items-baseline justify-between gap-2 text-sm font-semibold {isFault ? 'text-rose-900 dark:text-rose-100' : 'italic text-slate-700 dark:text-slate-200'}">
                                <span class="truncate">{drop.label ?? $_('jobs.errors_activity_unidentified', { default: 'Unidentified detection' })}</span>
                                {#if drop.score !== null}
                                    <span class="shrink-0 text-xs font-bold not-italic tabular-nums text-slate-500 sm:hidden dark:text-slate-400">{Math.round(drop.score * 100)}%</span>
                                {/if}
                            </p>
                            <p class="flex flex-wrap items-center gap-x-1.5 text-[11px] font-medium leading-4 {isFault ? 'text-rose-700 dark:text-rose-300' : 'text-slate-500 dark:text-slate-400'}">
                                {#if isFault}
                                    <span class="font-semibold">{$_('jobs.errors_activity_fault', { default: 'Pipeline fault' })}</span>
                                    <span aria-hidden="true">·</span>
                                    <span>{$_(`jobs.errors_drop_reason.${drop.reason}`, { default: reasonFallback(drop.reason) })}</span>
                                {:else}
                                    {$_(`jobs.errors_drop_reason_row.${drop.reason}`, {
                                        default: $_('jobs.errors_drop_reason_row.filter_low_confidence', {
                                            default: 'Not recorded, below your naming threshold'
                                        })
                                    })}
                                {/if}
                            </p>
                        </div>
                        <span class="hidden flex-col items-end gap-1 sm:flex">
                            {#if drop.score !== null}
                                <span class="text-xs font-bold tabular-nums text-slate-500 dark:text-slate-400">{Math.round(drop.score * 100)}%</span>
                                <span class="h-[3px] w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                    <span class="block h-full rounded-full bg-slate-400 dark:bg-slate-500" style="width: {Math.round(drop.score * 100)}%"></span>
                                </span>
                            {/if}
                        </span>
                    </li>
                {/if}
            {/each}
        </ol>

        {#if hiddenCount > 0}
            <p
                class="flex min-h-11 items-center justify-center gap-2 border-t border-slate-200/70 bg-slate-50/70 px-4 py-2 text-center text-xs font-medium text-slate-500 dark:border-slate-700/50 dark:bg-slate-900/50 dark:text-slate-400"
                data-health-activity-remainder
            >
                <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
                {hiddenLabel ?? $_('jobs.errors_activity_earlier', {
                    values: { count: hiddenCount.toLocaleString() },
                    default: '{count} earlier events in this window'
                })}
            </p>
        {/if}
    {/if}
</div>

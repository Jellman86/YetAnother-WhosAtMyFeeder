<script lang="ts">
    import Separator from './Separator.svelte';
    import VisitCaptures from './VisitCaptures.svelte';
    import { _ } from 'svelte-i18n';
    import type { Detection } from '../api';
    import { birdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { formatTime } from '../utils/datetime';
    import { SCORE_FILL, SCORE_TEXT, scoreBand } from '../utils/score-tone';
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
        return $birdNames(
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

    function reasonFallback(reason: string): string {
        const words = reason.replaceAll('_', ' ').trim();
        return words.length > 0 ? words.charAt(0).toUpperCase() + words.slice(1) : reason;
    }

    function dropToneClass(isFault: boolean): string {
        return isFault
            ? 'border-l-status-fail-line bg-status-fail-soft/60'
            : 'border-l-status-neutral-line bg-surface-raised';
    }
</script>

<div
    class="overflow-hidden rounded-2xl border border-line bg-surface"
    data-health-activity-timeline
>
    <div
        class="flex flex-wrap gap-x-4 gap-y-2 border-b border-line bg-surface-raised px-4 py-3 text-xs font-semibold text-muted"
        role="group"
        aria-label={$_('jobs.errors_activity_key', { default: 'Activity key' })}
    >
        <span class="inline-flex items-center gap-1.5">
            <span class="h-2 w-2 rounded-full bg-status-info-line" aria-hidden="true"></span>
            {$_('jobs.errors_activity_recorded', { default: 'Recorded visit' })}
        </span>
        <span class="inline-flex items-center gap-1.5">
            <span class="h-2 w-2 rounded-full bg-status-neutral-line" aria-hidden="true"></span>
            {$_('jobs.errors_activity_filtered', { default: 'Filtered out' })}
        </span>
        <span class="inline-flex items-center gap-1.5">
            <span class="h-2 w-2 rounded-full bg-status-fail-line" aria-hidden="true"></span>
            {$_('jobs.errors_activity_fault', { default: 'Pipeline fault' })}
        </span>
    </div>

    {#if loading && rows.length === 0}
        <div class="space-y-px p-2" data-health-activity-loading>
            {#each Array(5) as _unused, index (index)}
                <div class="h-18 animate-pulse rounded-xl bg-surface-raised"></div>
            {/each}
        </div>
    {:else if rows.length === 0}
        <div class="flex flex-col items-center justify-center px-6 py-12 text-center">
            <div class="mb-4 grid h-12 w-12 place-items-center rounded-full bg-surface-raised text-muted">
                <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 12h3l2-5 4 10 2-5h5" />
                </svg>
            </div>
            <p class="max-w-lg text-sm font-medium leading-6 text-muted">{emptyMessage}</p>
        </div>
    {:else}
        <ol class="divide-y divide-line">
            {#each rows as row (row.key)}
                {#if row.kind === 'visit'}
                    {@const visit = row.visit}
                    {@const naming = names(visit.lead)}
                    {@const score = visit.best.score ?? 0}
                    <li
                        class="relative grid grid-cols-[3rem_auto_minmax(0,1fr)] items-center gap-x-2.5 gap-y-1 border-l-[3px] border-l-status-info-line bg-status-info-soft/40 px-2 py-2.5 sm:grid-cols-[4.5rem_0.75rem_auto_minmax(0,1fr)_4.5rem_7.5rem] sm:gap-x-3 sm:px-3"
                        data-health-activity-row
                        data-row-kind="recorded"
                    >
                        <span class="text-xs tabular-nums text-muted">{span(row)}</span>
                        <span class="relative hidden h-full justify-center sm:flex" class:sm:row-span-2={(visit.server?.capture_count ?? 0) > 1} aria-hidden="true">
                            <span class="absolute inset-y-[-0.8rem] w-px bg-line"></span>
                            <span class="relative mt-[0.45rem] h-2 w-2 rounded-full bg-status-info-line ring-2 ring-surface"></span>
                        </span>
                        <DetectionPreview
                            detection={visit.best}
                            frames={visit.frames}
                            frameCount={(visit.captureCount ?? visit.frames.length)}
                            primaryName={naming.primary}
                            secondaryName={naming.secondary}
                            onopen={(frame) => onselect?.(frame)}
                        />
                        <div class="min-w-0 pr-12 sm:pr-0">
                            <p class="flex min-w-0 items-baseline justify-between gap-2">
                                <span class="truncate text-sm font-semibold text-strong">{naming.primary}</span>
                                <span class="shrink-0 text-xs font-bold tabular-nums sm:hidden {SCORE_TEXT[scoreBand(score)]}">{Math.round(score * 100)}%</span>
                            </p>
                            <p class="flex flex-wrap items-center gap-x-1.5 text-2xs text-muted">
                                <span class="font-semibold text-accent-ink">
                                    {$_('jobs.errors_activity_recorded', { default: 'Recorded visit' })}
                                </span>
                                <Separator />
                                <span>{visit.camera}</span>
                                {#if naming.secondary}
                                    <Separator />
                                    <span class="italic">{naming.secondary}</span>
                                {/if}
                                {#if visit.audioConfirmed}
                                    <Separator />
                                    <span class="font-medium text-accent-ink">
                                        {$_('detection.fact_heard_yes', { default: 'matching call' })}
                                    </span>
                                {/if}
                            </p>
                        </div>
                        <span class="hidden flex-col items-end gap-1 sm:flex">
                            <span class="text-xs font-bold tabular-nums {SCORE_TEXT[scoreBand(score)]}">{Math.round(score * 100)}%</span>
                            <span class="h-[3px] w-16 overflow-hidden rounded-full bg-track">
                                <span class="block h-full rounded-full {SCORE_FILL[scoreBand(score)]}" style="width: {Math.round(score * 100)}%"></span>
                            </span>
                        </span>
                        <button
                            type="button"
                            class="btn btn-ghost absolute right-2 top-2.5 h-11 min-h-11 w-11 justify-self-end px-0 py-1.5 text-xs sm:static sm:h-auto sm:w-auto sm:px-3"
                            aria-label="{$_('jobs.errors_activity_view_record', { default: 'View record' })}: {naming.primary}"
                            onclick={() => onselect?.(visit.best)}
                        >
                            <span class="hidden sm:inline">{$_('jobs.errors_activity_view_record', { default: 'View record' })}</span>
                            <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" />
                            </svg>
                        </button>
                        {#if visit.server && visit.server.capture_count > 1}
                            <div class="col-span-2 col-start-2 -mt-1 min-w-0 sm:col-span-3 sm:col-start-4">
                                <VisitCaptures visit={visit.server} window={visit.window} layout="inline" {onselect} />
                            </div>
                        {/if}
                    </li>
                {:else}
                    {@const drop = row.drop}
                    {@const isFault = row.kind === 'fault'}
                    <li
                        class="grid grid-cols-[3rem_auto_minmax(0,1fr)] items-center gap-x-2.5 gap-y-1 border-l-[3px] px-2 py-2.5 sm:grid-cols-[4.5rem_0.75rem_auto_minmax(0,1fr)_4.5rem] sm:gap-x-3 sm:px-3 {dropToneClass(isFault)}"
                        data-health-activity-row
                        data-row-kind={isFault ? 'fault' : 'filtered'}
                    >
                        <span class="text-xs tabular-nums text-muted">
                            {drop.timestamp ? formatTime(drop.timestamp) : ''}
                        </span>
                        <span class="relative hidden h-full justify-center sm:flex" aria-hidden="true">
                            <span class="absolute inset-y-[-0.8rem] w-px bg-line"></span>
                            <span class="relative mt-[0.45rem] h-2 w-2 rounded-full ring-2 ring-surface {isFault ? 'bg-status-fail-line' : 'bg-status-neutral-line'}"></span>
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
                            <p class="flex min-w-0 items-baseline justify-between gap-2 text-sm font-semibold {isFault ? 'text-strong' : 'italic text-ink'}">
                                <span class="truncate">{drop.label ?? $_('jobs.errors_activity_unidentified', { default: 'Unidentified detection' })}</span>
                                {#if drop.score !== null}
                                    <span class="shrink-0 text-xs font-bold not-italic tabular-nums text-muted sm:hidden">{Math.round(drop.score * 100)}%</span>
                                {/if}
                            </p>
                            <p class="flex flex-wrap items-center gap-x-1.5 text-2xs font-medium leading-4 {isFault ? 'text-status-fail' : 'text-muted'}">
                                {#if isFault}
                                    <span class="font-semibold">{$_('jobs.errors_activity_fault', { default: 'Pipeline fault' })}</span>
                                    <Separator />
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
                                <span class="text-xs font-bold tabular-nums text-muted">{Math.round(drop.score * 100)}%</span>
                                <span class="h-[3px] w-16 overflow-hidden rounded-full bg-track">
                                    <span class="block h-full rounded-full bg-status-neutral-line" style="width: {Math.round(drop.score * 100)}%"></span>
                                </span>
                            {/if}
                        </span>
                    </li>
                {/if}
            {/each}
        </ol>

        {#if hiddenCount > 0}
            <p
                class="flex min-h-11 items-center justify-center gap-2 border-t border-line bg-surface-raised px-4 py-2 text-center text-xs font-medium text-muted"
                data-health-activity-remainder
            >
                <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
                {hiddenLabel ?? $_('jobs.errors_activity_earlier', {
                    values: { count: hiddenCount },
                    default: '{count, plural, one {# earlier event in this window} other {# earlier events in this window}}'
                })}
            </p>
        {/if}
    {/if}
</div>
